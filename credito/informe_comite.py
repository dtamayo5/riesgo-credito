"""
Informe para el Comité de Riesgos / Junta (gestión y referencia regulatoria).

  1 Resumen ejecutivo            7 Referencia regulatoria
  2 Límites y evolución          8 Pruebas de estrés
  3 Cartera                      9 Calidad de datos
  4 Cosechas y rodamientos      10 Metodología y trazabilidad
  5 Score de originación        11 Cómo leer este informe
  6 Provisiones NIIF 9
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from reportlab.lib.units import cm
from reportlab.platypus import CondPageBreak, KeepTogether, PageBreak, Spacer, Table, TableStyle

from . import config as C
from . import niif9
from .graficas import etiqueta_cosecha
from .pdf_base import (ANCHO_UTIL, ESTADO_COLOR, FONDO, LINEA, PRIORIDAD_ESTADO, TONO_ESTADO, Documento, E, P,
                       chip, estilo, fila_kpis, imagen, kpi, lista_tono, num_der, tabla)
from .utilidades import fecha_larga, millones, num, pct

M = lambda x, d=0: num(x / 1e6, d)  # noqa: E731  pesos -> millones con formato


def _resumen(r) -> list:
    ind, foto, r9, lim = r["indicadores"], r["foto"], r["niif9"], r["limites"]
    n = lim["estado"].value_counts()
    ev = r["evolucion"]
    prev = ev.iloc[-2] if len(ev) > 1 else None
    d_icv = f"{'+' if foto['icv30'] >= prev['icv30'] else ''}{num(100 * (foto['icv30'] - prev['icv30']), 1)} pp en el mes" \
        if prev is not None else ""
    crec = foto["cartera"] / prev["cartera"] - 1 if prev is not None else np.nan
    h = [Spacer(1, 0.2 * cm), P(E(r["entidad"]["nombre"]).upper(), "entidad"),
         P("Informe de riesgo de crédito", "titulo"),
         P(f"Corte al {fecha_larga(r['corte'])} &nbsp;|&nbsp; Para el Comité de Riesgos y la Junta Directiva "
           f"&nbsp;|&nbsp; Cifras en millones de pesos (COP M)", "sub"),
         fila_kpis([
             kpi("Cartera bruta", f"COP {M(foto['cartera'])} M",
                 f"{'+' if crec >= 0 else ''}{num(100 * crec, 1)}% en el mes · {num(foto['n_creditos'])} créditos"),
             kpi("Cartera vencida > 30 días", pct(foto["icv30"]), d_icv),
             kpi("Pérdida esperada NIIF 9", f"COP {M(r9.ecl)} M",
                 f"{pct(r9.ecl / foto['cartera'])} de la cartera · {pct(ind['COBERTURA_30'], 0)} de la vencida"),
             kpi("Semáforo de límites", f"{n.get('ROJO', 0)} · {n.get('ÁMBAR', 0)} · {n.get('VERDE', 0)}",
                 "excedidos · en alerta · cumplen"),
         ]),
         Spacer(1, 0.4 * cm), P("1. Mensajes clave del corte", "h1")]
    h.append(lista_tono([(TONO_ESTADO[t], None, E(x)) for t, x in r["mensajes"]]))
    h += [Spacer(1, 0.3 * cm), P("Acciones sugeridas", "h1"),
          P("Generadas por reglas a partir del corte; los montos llevan el indicador al límite o a la zona de alerta. "
            "La decisión es del comité. Guía de lectura y glosario: sección 11.", "peq"), Spacer(1, 0.1 * cm)]
    filas, st = [], [("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3.2),
                     ("BOTTOMPADDING", (0, 0), (-1, -1), 3.2), ("LINEBELOW", (0, 0), (-1, -1), 0.4, LINEA)]
    for i, a in enumerate(r["acciones"]):
        est = PRIORIDAD_ESTADO[a["prioridad"]]
        monto = "-" if pd.isna(a["monto"]) else f"<b>{E(millones(a['monto']))}</b>"
        filas.append([chip(est, a["prioridad"]), P(f"<b>{E(a['accion'])}.</b> {E(a['sustento'])}.", "p1"),
                      P(monto, estilo("mt", fontSize=8.3, leading=10.8, alignment=2))])
        st.append(("BACKGROUND", (0, i), (0, i), ESTADO_COLOR[est] if est else FONDO))
    if filas:
        t = Table(filas, colWidths=[1.7 * cm, ANCHO_UTIL - 4.5 * cm, 2.8 * cm])
        t.setStyle(TableStyle(st))
        h.append(t)
    h.append(PageBreak())
    return h


def _limites(r, g) -> list:
    lim = r["limites"]
    datos = [["Estado", "Indicador", "Categoría", "Valor", "Límite", "Alerta"]]
    for _, l in lim.iterrows():
        txt = E(l["indicador"]) + (f"<br/><font color='#52514e' size='6.8'>{E(etiqueta_cosecha(l['detalle']))}</font>"
                                   if l["detalle"] else "")
        datos.append([chip(l["estado"]), txt, E(l["categoria"]), num_der(E(l["valor_txt"])),
                      num_der(E(l["limite_txt"])), num_der(E(l["alerta_txt"]))])
    return [P("2. Límites y evolución", "h1"),
            P("Límites de la política de crédito de la entidad (hoja Limites). Máximo: rojo si el valor supera el "
              "límite. Mínimo: rojo si el valor es inferior al límite.", "peq"), Spacer(1, 0.15 * cm),
            tabla(datos, [1.7 * cm, 8.0 * cm, 2.6 * cm, 1.9 * cm, 1.6 * cm, 1.6 * cm],
                  estados=list(lim["estado"]), col_estado=0),
            Spacer(1, 0.35 * cm), P("Evolución de la cartera vencida (últimos 12 meses)", "h2"), imagen(g["mora"]),
            PageBreak()]


def _cartera(r) -> list:
    pr, tr, conc, ev, foto = r["productos"], r["tramos"], r["concentracion"], r["evolucion"], r["foto"]
    d1 = [["Producto", "Créditos", "Saldo (COP M)", "Participación", "Tasa EA", "ICV 30", "ICV 90"]]
    for p, f in pr.iterrows():
        d1.append([E(p), num(f["creditos"]), M(f["saldo"]), pct(f["participacion"]), pct(f["tasa"]),
                   pct(f["icv30"]), pct(f["icv90"])])
    d1.append(["Total", num(foto["n_creditos"]), M(foto["cartera"]), "100,0%", pct(foto["tasa_promedio"]),
               pct(foto["icv30"]), pct(foto["icv90"])])
    d2 = [["Altura de mora", "Créditos", "Saldo (COP M)", "Participación"]]
    for t, f in tr.iterrows():
        d2.append([E(t + (" días" if t != "Al día" else "")), num(f["creditos"]), M(f["saldo"]), pct(f["participacion"])])
    d3 = [["Mes", "Cartera", "Desembolsos", "Castigos", "Recuperaciones", "ICV 30", "Pérdida neta 12m"]]
    for m, f in ev.tail(6).iterrows():
        d3.append([E(fecha_larga(m)[3:] if False else m.strftime("%Y-%m")), M(f["cartera"]), M(f["desembolsos"]),
                   M(f["castigos"]), M(f["recuperaciones"]), pct(f["icv30"]), pct(f["perdida_neta_12m"])])
    reg = conc["region"]
    d4 = [["Región", "Participación"]] + [[E(k), pct(v)] for k, v in reg.items()]
    return [P("3. Cartera", "h1"),
            P(f"Cartera bruta de {millones(foto['cartera'])} en {num(foto['n_creditos'])} créditos vigentes, ticket "
              f"promedio {millones(foto['ticket_promedio'], 1)}. ICV = saldo vencido / cartera bruta.", "p"),
            P("Por producto", "h2"),
            tabla(d1, [4.4 * cm, 1.8 * cm, 2.5 * cm, 2.2 * cm, 1.9 * cm, 1.8 * cm, 1.8 * cm],
                  numericas=range(1, 7), negrita_ultima=True),
            Spacer(1, 0.3 * cm),
            Table([[tabla(d2, [3.0 * cm, 1.7 * cm, 2.3 * cm, 2.0 * cm], numericas=(1, 2, 3)),
                    tabla(d4, [3.4 * cm, 2.2 * cm], numericas=(1,))]],
                  colWidths=[9.6 * cm, ANCHO_UTIL - 9.6 * cm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"),
                                                                    ("LEFTPADDING", (0, 0), (-1, -1), 0)]),
            Spacer(1, 0.2 * cm),
            P(f"Concentración: los 20 mayores deudores suman {pct(conc['top20'])} de la cartera y el mayor deudor "
              f"{pct(conc['mayor_deudor'], 2)} (HHI por deudor {num(conc['hhi_deudores'], 1)}).", "p"),
            P("Movimiento de la cartera (COP M)", "h2"),
            tabla(d3, [2.0 * cm, 2.4 * cm, 2.4 * cm, 2.1 * cm, 2.6 * cm, 1.9 * cm, 2.8 * cm], numericas=range(1, 7)),
            P("Castigo = saldo del mes anterior de los créditos que pasan a castigados. Pérdida neta 12m = (castigos - "
              "recuperaciones de 12 meses) / cartera promedio.", "peq"),
            PageBreak()]


def _cosechas(r, g) -> list:
    rod = r["rodamientos"]
    d = [["Desde \\ hacia"] + list(rod.columns)]
    for est, f in rod.iterrows():
        d.append([E(est)] + [pct(v, 1) if v >= 0.0005 else "-" for v in f])
    cos = r["cosechas30"]
    mobs = [3, 6, 9, 12]
    d2 = [["Cosecha", "Créditos"] + [f"MOB {m}" for m in mobs]]
    n_cos = r["datos"].org.assign(q=r["datos"].org["mes_desembolso"].dt.to_period("Q").astype(str)).groupby("q").size()
    for q in cos.index[-8:]:
        d2.append([E(etiqueta_cosecha(q)), num(n_cos.get(q, 0))] +
                  [pct(cos.loc[q, m]) if not pd.isna(cos.loc[q, m]) else "" for m in mobs])
    q, v, ref = r["cosecha_mob6"]
    return [P("4. Cosechas y rodamientos", "h1"),
            P("Una cosecha es el grupo de créditos desembolsados en el mismo trimestre. Comparar cosechas a la misma "
              "edad (MOB, meses desde el desembolso) separa la calidad de la originación del efecto de crecimiento: "
              "una cartera que crece rápido diluye el ICV aunque los créditos nuevos sean peores.", "p"),
            imagen(g["cosechas"]),
            P(f"La cosecha {E(etiqueta_cosecha(q))} tiene {pct(v)} de créditos que alguna vez superaron 30 días a seis "
              f"meses, frente a {pct(ref)} del promedio de las cosechas anteriores.", "p"),
            tabla(d2, [2.4 * cm, 2.0 * cm] + [2.0 * cm] * 4, numericas=range(1, 6), tam=7.4),
            CondPageBreak(7 * cm), P("Matriz de rodamientos (promedio de los últimos 6 meses, ponderada por saldo)", "h2"),
            P("Cada fila suma 100%: de cada peso que estaba en un tramo de mora, qué porcentaje pasó al mes siguiente a "
              "cada destino. La fila 1-30 hacia 31-60 es el rodamiento que más anticipa la mora futura.", "peq"),
            tabla(d, [2.4 * cm] + [2.1 * cm] * 7, numericas=range(1, 8), tam=7.4),
            PageBreak()]


def _score(r, g) -> list:
    sc = r["score"]
    met = sc.metricas
    d1 = [["Muestra", "Créditos", "Malos", "Tasa de malos", "Gini", "KS", "AUC"]]
    for k in ("Desarrollo", "Fuera de tiempo"):
        m = met[k]
        d1.append([k, num(m["n"]), num(m["malos"]), pct(m["tasa_malos"]), pct(m["gini"]), pct(m["ks"]), num(m["auc"], 3)])
    iv = sc.tabla_iv
    d2 = [["Variable", "IV", "Tramos", "Resultado"]]
    for _, f in iv.iterrows():
        d2.append([E(f["nombre"]), num(f["iv"], 3), num(f["tramos"]), E(f["estado"])])
    cal = sc.calificaciones
    d3 = [["Calif.", "PD hasta", "Score", "Créditos", "Part.", "PD modelo", "Malos obs.", "Prueba binomial"]]
    for gr, f in cal.iterrows():
        d3.append([gr, pct(f["pd_hasta"], 0), f"{num(f['score_min'])}-{num(f['score_max'])}", num(f["creditos"]),
                   pct(f["participacion"]), pct(f["pd_modelo"]), pct(f["tasa_observada"]), E(f["prueba_binomial"])])
    d4 = [["Rechazo adicional", "Punto de corte", "Aprobados", "Tasa de malos", "Malos evitados"]]
    for _, f in sc.cortes.iterrows():
        d4.append([pct(f["rechazo"], 0), "-" if pd.isna(f["corte"]) else num(f["corte"]), num(f["aprobados"]),
                   pct(f["tasa_malos"]), pct(f["malos_evitados"], 0)])
    tj = sc.tarjeta
    d5 = [["Variable", "Tramo", "Tasa de malos", "WoE", "Puntos"]]
    for _, f in tj.iterrows():
        d5.append([E(f["nombre"]), E(f["etiqueta"]), pct(f["tasa_malos"]), num(f["woe"], 2), num(f["puntos"])])
    return [P("5. Score de originación", "h1"),
            P(f"Score desarrollado con la historia de la entidad. Malo = más de {C.DIAS_INCUMPLIMIENTO} días de mora en los "
              f"primeros {C.VENTANA_DESEMPENO} meses. Desarrollo: primeras cosechas maduras; fuera de tiempo: las "
              f"siguientes, que el modelo no vio. Escala: {C.PUNTOS_BASE} puntos = {C.ODDS_BASE} buenos por cada malo; "
              f"cada {C.PDO} puntos duplican los odds.", "p"),
            tabla(d1, [3.2 * cm, 2.0 * cm, 1.8 * cm, 2.4 * cm, 1.8 * cm, 1.8 * cm, 1.8 * cm], numericas=range(1, 7)),
            P(f"Estabilidad: PSI de {num(met['psi'], 3)} entre el desarrollo y las originaciones de los últimos "
              f"{C.MESES_PSI} meses ({num(met['n_reciente'])} créditos). Menos de 0,10 = estable; 0,10 a 0,25 = cambio "
              f"moderado; más de 0,25 = cambio significativo.", "p"),
            imagen(g["score"]),
            CondPageBreak(6 * cm), P("Selección de variables (valor de información)", "h2"),
            tabla(d2, [5.5 * cm, 1.8 * cm, 1.6 * cm, 8.0 * cm], numericas=(1, 2), tam=7.4),
            CondPageBreak(6 * cm), P("Calificaciones (muestra madura completa)", "h2"),
            tabla(d3, [1.3 * cm, 1.6 * cm, 2.0 * cm, 1.8 * cm, 1.5 * cm, 2.0 * cm, 2.0 * cm, 3.0 * cm],
                  numericas=range(1, 7), tam=7.4),
            CondPageBreak(5 * cm), P("Puntos de corte (validación fuera de tiempo)", "h2"),
            P("Qué pasaría si se rechazaran además los créditos de menor score: la tasa de malos de los aprobados y la "
              "proporción de malos que se habrían evitado.", "peq"),
            tabla(d4, [3.2 * cm, 2.8 * cm, 2.6 * cm, 2.8 * cm, 2.8 * cm], numericas=range(0, 5), tam=7.4),
            CondPageBreak(8 * cm), P("Tarjeta de puntos", "h2"),
            tabla(d5, [5.0 * cm, 4.6 * cm, 2.4 * cm, 1.8 * cm, 1.8 * cm], numericas=(2, 3, 4), tam=7.2),
            PageBreak()]


def _niif9(r, g) -> list:
    r9 = r["niif9"]
    et = niif9.por_etapa(r9)
    d1 = [["Etapa", "Créditos", "Saldo (COP M)", "Part.", "PD 12m", "LGD", "ECL (COP M)", "Cobertura"]]
    nombres = {1: "1 - 12 meses", 2: "2 - vida (SICR)", 3: "3 - incumplido"}
    for k, f in et.iterrows():
        d1.append([nombres[k], num(f["creditos"]), M(f["saldo"]), pct(f["participacion"]), pct(f["pd12"]),
                   pct(f["lgd"]), M(f["ecl"]), pct(f["cobertura"])])
    d1.append(["Total", num(et["creditos"].sum()), M(et["saldo"].sum()), "100,0%", "", "", M(r9.ecl),
               pct(r9.ecl / et["saldo"].sum())])
    pp = niif9.por_producto(r9)
    d2 = [["Producto", "Saldo", "ECL etapa 1", "ECL etapa 2", "ECL etapa 3", "ECL total", "Cobertura"]]
    for p, f in pp.iterrows():
        d2.append([E(p), M(f["saldo"]), M(f["ecl_e1"]), M(f["ecl_e2"]), M(f["ecl_e3"]), M(f["ecl"]), pct(f["cobertura"])])
    pdc = r9.pd_cadena
    d3 = [["Producto", "Factor PIT", "PD al día", "PD 1-30", "PD 31-60", "PD 61-90", "LGD", "Incumpl."]]
    for p in [x for x in pdc.index if x != "__total__"]:
        lg = r9.lgd.loc[p] if p in r9.lgd.index else r9.lgd.loc["Toda la cartera"]
        d3.append([E(p), num(r9.factor_pit.get(p, np.nan), 2), pct(pdc.loc[p, "0"]), pct(pdc.loc[p, "1"]),
                   pct(pdc.loc[p, "2"]), pct(pdc.loc[p, "3"]), pct(lg["lgd_usada"]), num(lg["incumplimientos"])])
    esc = r9.escenarios
    d4 = [["Escenario", "Uso", "Peso", "PD x", "LGD +", "Saldo en etapa 2", "ECL (COP M)"]]
    for _, e in esc.iterrows():
        d4.append([E(e["escenario"]), E(e["uso"]), "" if pd.isna(e["peso"]) else pct(e["peso"], 0),
                   num(e["mult_pd"], 2), f"{num(100 * e['ajuste_lgd'], 0)} pp", M(e["saldo_e2"]), M(e["ecl"])])
    d4.append(["Ponderado NIIF 9", "", "100%", "", "", "", M(r9.ecl)])
    return [P("6. Provisiones por pérdida esperada (NIIF 9)", "h1"),
            P("ECL = PD x LGD x EAD descontada a la tasa del crédito. Etapa 1: pérdida de 12 meses. Etapa 2 (aumento "
              f"significativo del riesgo: más de {C.DIAS_ETAPA_2} días, PD actual al menos {num(C.SICR_MULTIPLO, 0)} "
              f"veces la de originación y {num(100 * C.SICR_ABSOLUTO, 0)} pp mayor, o curado hace menos de "
              f"{C.SICR_MESES_CURA} meses): pérdida de toda la vida. Etapa 3: más de {C.DIAS_ETAPA_3} días.", "p"),
            tabla(d1, [2.9 * cm, 1.6 * cm, 2.3 * cm, 1.5 * cm, 1.6 * cm, 1.5 * cm, 2.3 * cm, 1.9 * cm],
                  numericas=range(1, 8), negrita_ultima=True),
            Spacer(1, 0.25 * cm), P("Por producto (COP M)", "h2"),
            tabla(d2, [4.0 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.2 * cm, 2.0 * cm], numericas=range(1, 7)),
            Spacer(1, 0.25 * cm), P("Parámetros", "h2"),
            P("PD a 12 meses por tramo de mora: probabilidad de llegar a más de 90 días en un año según la cadena de "
              "rodamientos de los últimos 12 meses (matriz mensual elevada a la 12). Factor PIT: ajuste del score al "
              "nivel de incumplimiento actual de los créditos al día. LGD: 1 - recuperaciones descontadas.", "peq"),
            tabla(d3, [3.6 * cm, 1.8 * cm, 1.8 * cm, 1.7 * cm, 1.8 * cm, 1.8 * cm, 1.6 * cm, 1.7 * cm],
                  numericas=range(1, 8), tam=7.4),
            CondPageBreak(6 * cm), P("Escenarios prospectivos", "h2"),
            tabla(d4, [3.4 * cm, 1.6 * cm, 1.3 * cm, 1.3 * cm, 1.5 * cm, 3.0 * cm, 2.6 * cm], numericas=range(2, 7),
                  negrita_ultima=True, tam=7.4),
            P("Las etapas se recalculan en cada escenario: el aumento del saldo en etapa 2 es el efecto acantilado. "
              "La curva de recuperaciones que sustenta la LGD está en el informe de fondeadores y en la hoja PD_LGD "
              "del anexo.", "peq"),
            PageBreak()]


def _regulatoria(r, g) -> list:
    r9, e = r["niif9"], r["entidad"]
    cat = niif9.por_categoria(r9)
    d1 = [["Categoría", "Créditos", "Saldo (COP M)", "Part.", "Provisión ref.", "ECL NIIF 9"]]
    for c, f in cat.iterrows():
        d1.append([c, num(f["creditos"]), M(f["saldo"]), pct(f["participacion"]), M(f["prov_ref"]), M(f["ecl"])])
    reg = e["prov_registrada"]
    d2 = [["Concepto", "COP M", "% de la cartera"],
          ["Pérdida esperada NIIF 9 (ponderada por escenarios)", M(r9.ecl), pct(r9.ecl / r["foto"]["cartera"])],
          ["Referencia regulatoria: provisión individual por altura de mora", M(r9.ref_especifica),
           pct(r9.ref_especifica / r["foto"]["cartera"])],
          [f"Referencia regulatoria: provisión general ({pct(e['prov_general'], 1)})", M(r9.ref_general),
           pct(r9.ref_general / r["foto"]["cartera"])],
          ["Referencia regulatoria total", M(r9.ref_total), pct(r9.ref_total / r["foto"]["cartera"])]]
    resaltar = ()
    if not np.isnan(reg):
        d2 += [["Provisión registrada en contabilidad", M(reg), pct(reg / r["foto"]["cartera"])],
               ["Diferencia NIIF 9 - registrada", M(r9.ecl - reg), ""],
               ["Diferencia referencia - registrada", M(r9.ref_total - reg), ""]]
        resaltar = (6, 7)
    mat = r["datos"].matriz
    d3 = [["Producto", "Categoría", "Días de mora", "Provisión"]]
    for _, f in mat.iterrows():
        hasta = "o más" if f["dias_hasta"] >= 99999 else f"a {num(f['dias_hasta'])}"
        d3.append([E(f["producto"]), E(f["categoria"]), f"{num(f['dias_desde'])} {hasta}", pct(f["provision"], 1)])
    return [P("7. Referencia regulatoria", "h1"),
            P("Comparación con una provisión estilo regulatorio colombiano: categoría por altura de mora y porcentaje "
              "por categoría (hoja Matriz_provision), más la provisión general cuando aplica. Los porcentajes de la "
              "demostración son ilustrativos: en un cliente se reemplazan por los de la norma aplicable a la entidad "
              "(Superintendencia Financiera o Supersolidaria) y por sus políticas contables.", "p"),
            tabla(d2, [9.2 * cm, 3.0 * cm, 3.0 * cm], numericas=(1, 2), resaltar=resaltar),
            Spacer(1, 0.3 * cm), imagen(g["provisiones"]),
            P("Lectura: la referencia por altura de mora solo reacciona cuando el crédito ya está en mora; la NIIF 9 "
              "anticipa la pérdida con la PD del score, el rodamiento actual y la severidad observada. Una brecha grande "
              "en un producto suele indicar que su recuperación real es menor que la que supone la matriz.", "peq"),
            CondPageBreak(5 * cm), P("Por categoría", "h2"),
            tabla(d1, [2.2 * cm, 2.0 * cm, 2.8 * cm, 1.8 * cm, 2.8 * cm, 2.8 * cm], numericas=range(1, 6)),
            P("La matriz aplicada (categorías, días y porcentajes por producto) está en la hoja Provisiones del anexo.",
              "peq"),
            PageBreak()]


def _estres(r, g) -> list:
    es, pat = r["estres"], r["entidad"]["patrimonio"]
    d1 = [["Escenario", "PD x", "LGD +", "Provisión adicional", "% patrimonio", "Saldo etapa 2", "ICV 30",
           "Excedente", "Cobertura deuda"]]
    for _, e in es["tabla"].iterrows():
        d1.append([E(e["escenario"]), num(e["mult_pd"], 2), f"{num(100 * e['ajuste_lgd'], 0)} pp", M(e["ecl_adicional"]),
                   pct(e["pct_patrimonio"]), pct(e["saldo_etapa2"], 0), pct(e["icv30"]), pct(e["excedente"]),
                   num(e["cobertura_deuda"], 2) + " x"])
    inv = es["inverso"]
    f = lambda v: "no se alcanza (> 10 x)" if pd.isna(v) else f"{num(v, 2)} veces"  # noqa: E731
    d2 = [["Umbral", "Multiplicador de la PD que lo rompe"],
          ["Excedente financiero = 0", f(inv["excedente_cero"])],
          ["Cobertura de la deuda = 1,0 x", f(inv["cobertura_uno"])],
          [f"Provisión adicional = {pct(inv['umbral_patrimonio'], 0)} del patrimonio (límite)", f(inv["consume_umbral"])],
          ["Provisión adicional = 100% del patrimonio", f(inv["consume_patrimonio"])]]
    return [P("8. Pruebas de estrés", "h1"),
            P(f"Patrimonio de referencia: {millones(pat)}. Cada escenario multiplica la PD y suma puntos a la LGD; la "
              f"provisión se recalcula crédito por crédito con etapas nuevas. El ICV y la cobertura suponen que durante "
              f"{C.MESES_DETERIORO_ESTRES} meses entra a mora 30+ un flujo proporcional al multiplicador (promedio "
              f"reciente: {millones(es['flujo_mora'])} por mes).", "p"),
            tabla(d1, [2.6 * cm, 1.1 * cm, 1.2 * cm, 2.2 * cm, 1.8 * cm, 1.8 * cm, 1.5 * cm, 1.7 * cm, 2.0 * cm],
                  numericas=range(1, 9), tam=7.3),
            Spacer(1, 0.3 * cm), imagen(g["estres"]),
            P("Estrés inverso", "h2"),
            P("En lugar de preguntar cuánto se pierde en un escenario, pregunta cuánto tendría que empeorar la cartera "
              "para romper cada umbral. Un multiplicador cercano a 1 indica poco margen.", "peq"),
            tabla(d2, [9.5 * cm, 5.5 * cm], numericas=(1,)),
            PageBreak()]


def _calidad(r) -> list:
    h = r["hallazgos"].tabla()
    conteo = [["Severidad", "Cantidad", "Qué significa"],
              ["ERROR", num((h["severidad"] == "ERROR").sum()), "Registro excluido del cálculo: corregir en el origen"],
              ["ADVERTENCIA", num((h["severidad"] == "ADVERTENCIA").sum()), "Corregido automáticamente: verificar"],
              ["INFO", num((h["severidad"] == "INFO").sum()), "Conversión de formato o dato opcional ausente"]]
    datos = [["Severidad", "Archivo", "Fila", "Campo", "Valor", "Detalle y acción"]]
    for _, f in h.iterrows():
        datos.append([f["severidad"], E(f["hoja"]), "" if pd.isna(f["fila_excel"]) else num(f["fila_excel"]),
                      E(f["campo"]), E(f["valor_original"]),
                      E(f["detalle"]) + (f" <i>{E(f['accion'])}</i>" if f["accion"] else "")])
    return [P("9. Calidad de datos", "h1"),
            P("Cada hallazgo indica el archivo y la fila para corregir el origen. Cuando el mismo problema se repite, se "
              "agrupa en una línea con el número de filas y las primeras afectadas (detalle completo en el anexo).", "p"),
            tabla(conteo, [3.0 * cm, 2.0 * cm, 9.5 * cm], numericas=(1,)), Spacer(1, 0.3 * cm),
            tabla(datos, [2.2 * cm, 2.6 * cm, 1.3 * cm, 2.5 * cm, 2.0 * cm, 6.8 * cm], numericas=(2,), tam=7.0),
            PageBreak()]


def metodologia_textos(r) -> list[tuple[str, str]]:
    return [
        ("Datos", "Originaciones (un registro por crédito con las variables de la solicitud) y desempeño mensual "
         "(saldo de capital, días de mora, estado y recuperaciones). Cartera bruta = saldo de los créditos vigentes."),
        ("Score", "Tramos con peso de evidencia (WoE) monótonos para variables numéricas, selección por valor de "
         "información, correlación, signo y significancia, regresión logística por IRLS y tarjeta de puntos. PD de "
         "originación calibrada a la tasa de malos de todas las cosechas maduras. Validación fuera de tiempo (Gini, KS, "
         "AUC), prueba binomial por calificación y PSI."),
        ("PD", "Punto en el tiempo: cadena de Markov mensual de los últimos 12 meses por producto (estados al día, 1-30, "
         "31-60, 61-90, incumplido y pagado), elevada a la 12. El score reparte el nivel entre los créditos al día. PD "
         "de vida con riesgo mensual constante: año 1 con la PD del tramo actual y después con la de un crédito al día."),
        ("LGD", f"Curva de recuperaciones de {C.MESES_RECUPERACION} meses después del incumplimiento por producto, "
         "método de cadena (cada mes usa todos los incumplimientos que lo alcanzaron), descontada a la tasa promedio "
         f"del producto. Piso de {pct(C.LGD_PISO, 0)}; productos con menos de {C.MIN_INCUMPLIMIENTOS_LGD} "
         "incumplimientos usan la LGD de toda la cartera."),
        ("EAD y descuento", "Saldo de capital con amortización de cuota fija hasta el vencimiento; flujos de pérdida "
         "descontados a la tasa efectiva del crédito. No se modelan prepagos (supuesto conservador) ni intereses "
         "causados."),
        ("Fondeo", "Cartera elegible = saldo con mora menor o igual al máximo del fondeador. Excedente financiero = "
         "rendimiento de la cartera al día + comisiones - costo del fondeo sobre la cartera no financiada con "
         "patrimonio - gastos - pérdida esperada a 12 meses."),
        ("Alcance y limitaciones",
         ("Demostración con entidad ficticia y datos sintéticos. " if r["entidad"].get("demo") else "")
         + "La referencia regulatoria usa la matriz de la política, no un modelo de referencia oficial. El informe "
         "apoya la gestión y no reemplaza los reportes regulatorios ni el criterio del área de riesgos y del revisor fiscal."),
    ]


def _metodologia(r) -> list:
    tr = r["traza"]
    param = [["Parámetro", "Valor"]] + [[E(k), E(v)] for k, v in tr["parametros"].items()]
    archivos = [["Archivo de entrada", "Huella SHA-256"]] + [[E(n), f"<font size='6.5'>{h}</font>"]
                                                              for n, h in tr["archivos"].items()]
    h = [P("10. Metodología y trazabilidad", "h1")]
    for t, x in metodologia_textos(r):
        h += [P(t, "h2"), P(E(x), "p")]
    h += [CondPageBreak(6 * cm), P("Parámetros de la ejecución", "h2"), tabla(param, [7.0 * cm, 7.0 * cm], tam=7.4),
          Spacer(1, 0.3 * cm), P("Trazabilidad de insumos", "h2"),
          P("La huella SHA-256 cambia si alguien modifica el archivo: permite verificar qué datos produjeron el informe.",
            "peq"),
          tabla(archivos, [4.4 * cm, 12.6 * cm]), Spacer(1, 0.2 * cm),
          P(f"Motor v{tr['version']} · ejecutado el {tr['ejecutado']} · tiempo de cálculo {num(tr['segundos'], 1)} "
            f"segundos.", "peq")]
    return h


GUIA = [
    ("1. Resumen", "¿Qué requiere atención?", "Mensajes en rojo y ámbar; montos de las acciones.",
     "Aprobar o ajustar el plan de acción."),
    ("2. Límites", "¿Cumplimos la política?", "Estado de cada límite y tendencia de la mora.",
     "Anticiparse a los indicadores que se acercan a su alerta."),
    ("3. Cartera", "¿Qué tenemos y dónde está la mora?", "ICV por producto y movimiento del mes.",
     "Priorizar cobranza y revisar productos con peor indicador."),
    ("4. Cosechas", "¿Estamos originando peor?", "Cosechas recientes frente a las anteriores a la misma edad.",
     "Ajustar política de originación y punto de corte."),
    ("5. Score", "¿El modelo sirve y está estable?", "Gini fuera de tiempo, PSI, calibración.",
     "Mantener, ajustar el corte o recalibrar."),
    ("6. NIIF 9", "¿Cuánto debemos provisionar?", "ECL por etapa y producto; escenarios.",
     "Aprobar la provisión y los supuestos prospectivos."),
    ("7. Regulatoria", "¿Cumplimos el mínimo de referencia?", "Diferencias NIIF 9, referencia y registrada.",
     "Ajustes contables y explicación al revisor fiscal."),
    ("8. Estrés", "¿Resistimos una crisis?", "Provisión adicional / patrimonio y estrés inverso.",
     "Capital, crecimiento y apetito de riesgo."),
    ("9-10. Datos y método", "¿Las cifras son confiables y trazables?", "Hallazgos y huellas de archivos.",
     "Responsables de corregir datos; soporte ante auditoría."),
]
GLOSARIO = [
    ("ICV", "Índice de cartera vencida: saldo con más de N días de mora / cartera bruta."),
    ("Cosecha / MOB", "Créditos desembolsados en el mismo periodo / meses transcurridos desde el desembolso."),
    ("Rodamiento", "Porcentaje del saldo de un tramo de mora que pasa al siguiente en un mes."),
    ("Score / tarjeta de puntos", "Puntaje que ordena a los solicitantes por riesgo; más puntos = menos riesgo."),
    ("Gini / KS", "Poder para separar buenos de malos (0 = azar, 100% = perfecto). Un Gini de 40% a 60% es habitual."),
    ("PSI", "Cambio en la distribución de los solicitantes frente a la del desarrollo del modelo."),
    ("PD / LGD / EAD", "Probabilidad de incumplir / pérdida si incumple (% del saldo) / saldo expuesto."),
    ("ECL", "Pérdida crediticia esperada (NIIF 9): PD x LGD x EAD descontada."),
    ("Etapas 1-2-3", "Sin deterioro (12 meses) / aumento significativo del riesgo (vida) / incumplido."),
    ("SICR", "Aumento significativo del riesgo de crédito desde la originación."),
    ("Factor PIT", "Ajuste que lleva la PD promedio del ciclo al nivel de incumplimiento actual."),
    ("Estrés inverso", "Cuánto tendría que empeorar la cartera para romper un umbral."),
]


def _guia(r) -> list:
    d = [["Sección", "Pregunta", "Qué mirar primero", "Qué decide el comité"]] + [[E(c) for c in f] for f in GUIA]
    sem = [["Color", "Significado", "Respuesta esperada"],
           [chip("ROJO"), "Límite excedido", "Acción correctiva con plazo y responsable"],
           [chip("ÁMBAR"), "Zona de alerta", "Acción preventiva o seguimiento reforzado"],
           [chip("VERDE"), "Dentro de la política", "Monitoreo normal"]]
    glo = [["Término", "En palabras simples"]] + [[E(a), E(b)] for a, b in GLOSARIO]
    return [CondPageBreak(9 * cm), Spacer(1, 0.4 * cm), P("11. Cómo leer este informe", "h1"),
            P("Lea la página 1 completa y luego solo las secciones con indicadores en rojo o ámbar.", "p"),
            tabla(d, [2.6 * cm, 4.0 * cm, 5.4 * cm, 5.2 * cm], tam=7.4), Spacer(1, 0.3 * cm),
            KeepTogether([P("El semáforo", "h2"),
                          tabla(sem, [1.9 * cm, 5.6 * cm, 9.7 * cm], estados=["ROJO", "ÁMBAR", "VERDE"], col_estado=0)]),
            Spacer(1, 0.3 * cm), KeepTogether([P("Glosario", "h2"), tabla(glo, [4.2 * cm, 13.0 * cm], tam=7.4)])]


def generar(r: dict, g: dict, ruta: Path) -> Path:
    doc = Documento(ruta, r, "Informe de riesgo de crédito")
    doc.build(_resumen(r) + _limites(r, g) + _cartera(r) + _cosechas(r, g) + _score(r, g) + _niif9(r, g)
              + _regulatoria(r, g) + _estres(r, g) + _calidad(r) + _metodologia(r) + _guia(r))
    return ruta
