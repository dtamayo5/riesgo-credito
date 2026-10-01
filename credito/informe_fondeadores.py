"""
Informe para fondeadores e inversionistas (levantar o renovar deuda).

Mismo motor y mismas cifras que el informe del comité, con el orden de
preguntas de quien presta: ¿qué tan buena es la cartera?, ¿cuánto colchón hay
antes de que mi dinero esté en riesgo?, ¿qué pasa si las cosas empeoran?

  1 Resumen para el fondeador (tesis, fortalezas y riesgos, indicadores)
  2 Originación y crecimiento
  3 Desempeño de la cartera
  4 Base de préstamo y excedente financiero
  5 Estrés y punto de equilibrio
  6 Gestión del riesgo, metodología y advertencias
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from reportlab.lib.units import cm
from reportlab.platypus import PageBreak, Spacer, Table, TableStyle

from .graficas import etiqueta_cosecha
from .informe_comite import metodologia_textos
from .pdf_base import (ANCHO_UTIL, LINEA, Documento, E, P, fila_kpis, imagen, kpi, tabla)
from .utilidades import fecha_larga, millones, num, pct

M = lambda x, d=0: num(x / 1e6, d)  # noqa: E731


def _vinetas(items, simbolo):
    return [P("&bull; " + E(t), "vin") for t in items] if items else [P("-", "vin")]


def _resumen(r) -> list:
    foto, fon, ev, e = r["foto"], r["fondeo"], r["evolucion"], r["entidad"]
    crec = ev["cartera"].iloc[-1] / ev["cartera"].iloc[0] - 1
    F, R = r["fortalezas"], r["riesgos"]
    h = [Spacer(1, 0.2 * cm), P(E(e["nombre"]).upper(), "entidad"),
         P("Informe de cartera para fondeadores", "titulo"),
         P(f"Corte al {fecha_larga(r['corte'])} &nbsp;|&nbsp; {E(e['tipo'])} &nbsp;|&nbsp; Cifras en COP millones", "sub"),
         fila_kpis([
             kpi("Cartera bruta", f"COP {M(foto['cartera'])} M", f"+{num(100 * crec, 0)}% en 12 meses"),
             kpi("Excedente financiero", pct(fon["excedente"]), "anual, después de pérdida esperada"),
             kpi("Cobertura de la deuda", f"{num(fon['cobertura'], 2)} x",
                 f"anticipo {pct(fon['anticipo'], 0)} sobre cartera elegible"),
             kpi("Pérdida neta 12 meses", pct(ev["perdida_neta_12m"].iloc[-1]), "castigos - recuperaciones / cartera"),
         ]), Spacer(1, 0.35 * cm)]
    col = Table([[[P("Fortalezas", "h2")] + _vinetas(F, "+"), [P("Riesgos a monitorear", "h2")] + _vinetas(R, "-")]],
                colWidths=[ANCHO_UTIL / 2] * 2)
    col.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 4),
                             ("LINEAFTER", (0, 0), (0, 0), 0.6, LINEA)]))
    h.append(col)
    d = [["Indicador", "Valor", "Indicador", "Valor"],
         ["Créditos vigentes", num(foto["n_creditos"]), "Patrimonio", f"COP {M(e['patrimonio'])} M"],
         ["Ticket promedio", millones(foto["ticket_promedio"], 1), "Deuda con fondeadores", f"COP {M(fon['deuda'])} M"],
         ["Tasa promedio (cartera al día)", pct(foto["tasa_promedio"]), "Deuda / patrimonio", f"{num(fon['apalancamiento'], 2)} x"],
         ["ICV más de 30 días", pct(foto["icv30"]), "Cartera elegible", pct(fon["pct_elegible"])],
         ["ICV más de 90 días", pct(foto["icv90"]), "Holgura de la base de préstamo", millones(fon["holgura"])],
         ["Provisión NIIF 9 / cartera", pct(r["niif9"].ecl / foto["cartera"]),
          "PD que lleva el excedente a cero", f"{num(fon['equilibrio_pd'], 2)} x la actual"]]
    h += [Spacer(1, 0.3 * cm), P("Indicadores clave", "h2"),
          tabla(d, [4.8 * cm, 3.4 * cm, 5.4 * cm, 3.6 * cm], numericas=(1, 3)), PageBreak()]
    return h


def _originacion(r, g) -> list:
    des, pr = r["desembolsos"], r["productos"]
    u12 = des.tail(12)
    org = r["datos"].org
    rec = org[org["mes_desembolso"] > r["corte"] - pd.offsets.MonthEnd(12)]
    d1 = [["Producto", "Desembolsos 12m (COP M)", "Créditos", "Ticket", "Plazo (meses)", "Tasa EA", "Saldo actual"]]
    for p, gq in rec.groupby("producto"):
        d1.append([E(p), M(gq["monto"].sum()), num(len(gq)), millones(gq["monto"].mean(), 1),
                   num(gq["plazo_meses"].mean(), 1), pct(gq["tasa_ea"].mean()),
                   M(pr.loc[p, "saldo"]) if p in pr.index else "-"])
    d1.append(["Total", M(rec["monto"].sum()), num(len(rec)), millones(rec["monto"].mean(), 1),
               num(rec["plazo_meses"].mean(), 1), pct(rec["tasa_ea"].mean()), M(r["foto"]["cartera"])])
    return [P("2. Originación y crecimiento", "h1"),
            P(f"En los últimos 12 meses la entidad desembolsó {millones(u12['monto'].sum())} en {num(u12['creditos'].sum())} "
              f"créditos. Todos los créditos se evalúan con un score propio (sección 6).", "p"),
            imagen(g["originacion"]), Spacer(1, 0.2 * cm),
            tabla(d1, [3.6 * cm, 3.0 * cm, 1.7 * cm, 2.1 * cm, 2.0 * cm, 1.7 * cm, 2.6 * cm], numericas=range(1, 7),
                  negrita_ultima=True),
            PageBreak()]


def _desempeno(r, g) -> list:
    cos = r["cosechas30"]
    cos90 = r["cosechas90"]
    d = [["Cosecha", "30+ a 6 meses", "30+ a 12 meses", "90+ a 12 meses", "90+ a 18 meses"]]
    for q in cos.index[-8:]:
        val = lambda t, m: "" if (m not in t.columns or pd.isna(t.loc[q, m])) else pct(t.loc[q, m])  # noqa: E731
        d.append([E(etiqueta_cosecha(q)), val(cos, 6), val(cos, 12), val(cos90, 12), val(cos90, 18)])
    ev = r["evolucion"]
    return [P("3. Desempeño de la cartera", "h1"), imagen(g["mora"]), Spacer(1, 0.2 * cm), imagen(g["cosechas"]),
            P("Porcentaje acumulado de créditos de cada cosecha que alguna vez superó el umbral de mora:", "peq"),
            tabla(d, [3.0 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm, 3.2 * cm], numericas=range(1, 5), tam=7.4),
            P(f"Castigos de los últimos 12 meses: {millones(ev['castigos'].sum())}; recuperaciones: "
              f"{millones(ev['recuperaciones'].sum())}.", "p"),
            PageBreak()]


def _fondeo(r, g) -> list:
    fon, e = r["fondeo"], r["entidad"]
    d = [["Base de préstamo", "COP M"],
         ["Cartera bruta", M(fon["cartera"])],
         [f"(-) Cartera con más de {e['dias_elegible']} días de mora", M(fon["cartera"] - fon["elegible"])],
         ["= Cartera elegible", M(fon["elegible"])],
         [f"x Tasa de anticipo ({pct(fon['anticipo'], 0)})", ""],
         ["= Base de préstamo", M(fon["base_prestamo"])],
         ["Deuda con fondeadores", M(fon["deuda"])],
         ["Holgura (base - deuda)", M(fon["holgura"])],
         ["Cobertura de la deuda", f"{num(fon['cobertura'], 2)} x"]]
    d2 = [["Componente", "% anual de la cartera"],
          ["Rendimiento de la cartera al día", pct(fon["rendimiento"])], ["Comisiones recurrentes", pct(fon["comisiones"])],
          ["Costo del fondeo", "-" + pct(fon["costo_fondeo"])], ["Gastos operativos", "-" + pct(fon["opex"])],
          ["Pérdida esperada a 12 meses", "-" + pct(fon["perdida_esperada"])], ["Excedente financiero", pct(fon["excedente"])]]
    tablas = Table([[tabla(d, [5.6 * cm, 2.4 * cm], numericas=(1,), resaltar=(3, 5, 8)),
                     tabla(d2, [5.4 * cm, 2.6 * cm], numericas=(1,), negrita_ultima=True)]],
                   colWidths=[8.6 * cm, ANCHO_UTIL - 8.6 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                                    ("LEFTPADDING", (0, 0), (-1, -1), 0)])
    return [P("4. Base de préstamo y excedente financiero", "h1"),
            P("La base de préstamo es la cartera sana que respalda la deuda; el excedente financiero es el colchón anual "
              "que absorbe pérdidas antes de afectar el capital de la entidad y, después, el del fondeador.", "p"),
            tablas, Spacer(1, 0.3 * cm), imagen(g["cobertura"]), Spacer(1, 0.2 * cm), imagen(g["excedente"]),
            PageBreak()]


def _estres(r, g) -> list:
    es, fon = r["estres"], r["fondeo"]
    d = [["Escenario", "PD x", "ICV 30", "Excedente", "Cobertura deuda", "Provisión adicional / patrimonio"]]
    d.append(["Actual", "1,00", pct(r["foto"]["icv30"]), pct(fon["excedente"]), f"{num(fon['cobertura'], 2)} x", "-"])
    for _, e in es["tabla"].iterrows():
        d.append([E(e["escenario"]), num(e["mult_pd"], 2), pct(e["icv30"]), pct(e["excedente"]),
                  f"{num(e['cobertura_deuda'], 2)} x", pct(e["pct_patrimonio"])])
    inv = es["inverso"]
    f = lambda v: "no se alcanza" if pd.isna(v) else f"{num(v, 2)} veces la PD actual"  # noqa: E731
    d2 = [["¿Cuánto tendría que empeorar la cartera para que...?", "Multiplicador"],
          ["el excedente financiero llegue a cero", f(inv["excedente_cero"])],
          ["la base de préstamo deje de cubrir la deuda", f(inv["cobertura_uno"])],
          ["las provisiones adicionales consuman todo el patrimonio", f(inv["consume_patrimonio"])]]
    lgd = r["niif9"].lgd
    d3 = [["Producto", "Incumplimientos", "Recuperación (24 m)", "LGD descontada"]]
    for p, fl in lgd.iterrows():
        d3.append([E(p), num(fl["incumplimientos"]), pct(fl["recuperacion"]), pct(fl["lgd"])])
    return [P("5. Estrés y punto de equilibrio", "h1"),
            tabla(d, [3.0 * cm, 1.4 * cm, 1.8 * cm, 2.0 * cm, 2.8 * cm, 5.0 * cm], numericas=range(1, 6)),
            Spacer(1, 0.3 * cm), tabla(d2, [10.0 * cm, 5.5 * cm], numericas=(1,)),
            Spacer(1, 0.3 * cm), P("Severidad observada", "h2"), imagen(g["recuperaciones"]),
            tabla(d3, [5.0 * cm, 3.0 * cm, 3.5 * cm, 3.5 * cm], numericas=(1, 2, 3), tam=7.4),
            PageBreak()]


def _gestion(r) -> list:
    sc, h = r["score"], r["hallazgos"]
    m = sc.metricas
    textos = [t for t in metodologia_textos(r) if t[0] in ("Score", "PD", "LGD", "Fondeo")]
    el = [P("6. Gestión del riesgo y metodología", "h1"),
          P(f"<b>Score de originación.</b> Gini de {pct(m['Fuera de tiempo']['gini'])} en validación fuera de tiempo "
            f"({num(m['Fuera de tiempo']['n'])} créditos) y PSI de {num(m['psi'], 3)}.", "p"),
          P(f"<b>Provisiones.</b> Pérdida esperada NIIF 9 de {millones(r['niif9'].ecl)} con etapas, escenarios "
            f"prospectivos y severidad observada; se compara con una referencia regulatoria por altura de mora.", "p"),
          P(f"<b>Calidad de datos.</b> {h.conteo('ERROR')} errores y {h.conteo('ADVERTENCIA')} advertencias en los archivos "
            f"de la entidad, corregidos y documentados con archivo y fila.", "p")]
    for t, x in textos:
        el += [P(t, "h2"), P(E(x), "p")]
    el += [Spacer(1, 0.3 * cm), P("Advertencias", "h2"),
           P("Este informe describe la cartera con la información entregada por la entidad al corte indicado. No es una "
             "calificación de riesgo, ni una oferta o recomendación de inversión, ni sustituye la debida diligencia del "
             "fondeador. Las proyecciones de estrés son ilustrativas y dependen de los supuestos descritos.", "peq")]
    if r["entidad"].get("demo"):
        el.append(P("Demostración: entidad ficticia y datos sintéticos.", "peq"))
    el.append(P("Huellas SHA-256 de los archivos de entrada: " + "; ".join(
        f"{E(n)} {hsh[:16]}..." for n, hsh in r["traza"]["archivos"].items()), "peq"))
    return el


def generar(r: dict, g: dict, ruta: Path) -> Path:
    doc = Documento(ruta, r, "Informe para fondeadores")
    doc.build(_resumen(r) + _originacion(r, g) + _desempeno(r, g) + _fondeo(r, g) + _estres(r, g) + _gestion(r))
    return ruta
