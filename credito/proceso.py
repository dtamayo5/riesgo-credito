"""Orquesta el cálculo completo de una entidad y genera sus salidas."""
from __future__ import annotations

import time
from pathlib import Path

from . import cartera, config as C, estres, fondeo, limites, niif9, scoring
from .lectura import leer_entidad


def calcular(carpeta: Path, corte=None) -> dict:
    t0 = time.time()
    datos = leer_entidad(carpeta, corte)
    corte = datos.corte
    p = cartera.panel(datos)
    f = cartera.foto(p, corte)
    foto = cartera.resumen_foto(f, datos.entidad["dias_elegible"])
    ev = cartera.evolucion(p, datos.org, corte, C.MESES_HISTORIA, datos.entidad["dias_elegible"])
    cos30 = cartera.cosechas(p, datos.org, corte, 30)
    cos90 = cartera.cosechas(p, datos.org, corte, 90)
    rod = cartera.rodamientos(p, corte, C.MESES_RODAMIENTO, "saldo")
    rod_n = cartera.rodamientos(p, corte, C.MESES_RODAMIENTO, "creditos")
    flujo = cartera.flujo_a_mora(p, corte, C.MESES_RODAMIENTO)
    conc = cartera.concentracion(f)
    sc = scoring.desarrollar(datos, p)
    r9 = niif9.calcular(datos, p, sc)
    fon = fondeo.calcular(datos, foto, r9.detalle, ev)
    es = estres.calcular(datos, r9, fon, foto, flujo)
    r = {
        "datos": datos, "corte": corte, "entidad": datos.entidad, "hallazgos": datos.hallazgos,
        "foto": foto, "productos": cartera.por_producto(f), "tramos": cartera.por_tramo(f),
        "evolucion": ev, "cosechas30": cos30, "cosechas90": cos90,
        "cosecha_mob6": cartera.indicador_cosecha(cos30, 6), "rodamientos": rod, "rodamientos_n": rod_n,
        "flujo_mora": flujo, "concentracion": conc, "score": sc, "niif9": r9, "fondeo": fon, "estres": es,
        "desembolsos": datos.org.groupby("mes_desembolso").agg(creditos=("id", "size"), monto=("monto", "sum"),
                                                               plazo=("plazo_meses", "mean"), tasa=("tasa_ea", "mean")),
    }
    r["indicadores"] = limites.calcular_indicadores(r)
    r["limites"] = limites.evaluar_limites(datos.limites, r["indicadores"])
    r["segundos_calculo"] = time.time() - t0
    return r


def traza(r: dict, segundos: float) -> dict:
    from datetime import datetime
    sc = r["score"]
    m = sc.muestra
    return {
        "version": C.VERSION, "ejecutado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "segundos": segundos,
        "archivos": r["datos"].huellas,
        "parametros": {
            "Corte": f"{r['corte']:%Y-%m-%d}",
            "Definición de incumplimiento": f"más de {C.DIAS_INCUMPLIMIENTO} días en {C.VENTANA_DESEMPENO} meses",
            "Muestra de desarrollo": f"{m.loc[m['muestra'] == 'Desarrollo', 'mes_desembolso'].min():%Y-%m} a "
                                     f"{m.loc[m['muestra'] == 'Desarrollo', 'mes_desembolso'].max():%Y-%m}",
            "Muestra fuera de tiempo": f"{m.loc[m['muestra'] != 'Desarrollo', 'mes_desembolso'].min():%Y-%m} a "
                                       f"{m.loc[m['muestra'] != 'Desarrollo', 'mes_desembolso'].max():%Y-%m}",
            "Variables del score": ", ".join(C.NOMBRE_VARIABLE.get(v.nombre, v.nombre) for v in sc.variables),
            "Escala del score": f"{C.PUNTOS_BASE} puntos = odds {C.ODDS_BASE}:1; PDO {C.PDO}",
            "Etapa 2": f"> {C.DIAS_ETAPA_2} días, PD >= {C.SICR_MULTIPLO:g}x y +{100 * C.SICR_ABSOLUTO:g} pp, o curado < {C.SICR_MESES_CURA} meses",
            "Etapa 3": f"> {C.DIAS_ETAPA_3} días",
            "Cadena de Markov": "matriz mensual de los últimos 12 meses, por producto",
            "Horizonte de recuperaciones": f"{C.MESES_RECUPERACION} meses",
            "Meses de deterioro en estrés": str(C.MESES_DETERIORO_ESTRES),
        },
    }


def generar(carpeta: Path, corte=None, salida: Path | None = None) -> dict:
    """Calcula y escribe: informe del comité, informe de fondeadores, anexo Excel y gráficas."""
    from . import anexo_excel, graficas, informe_comite, informe_fondeadores, narrativa
    t0 = time.time()
    r = calcular(carpeta, corte)
    r["mensajes"] = narrativa.mensajes_comite(r)
    r["acciones"] = narrativa.acciones(r)
    r["fortalezas"], r["riesgos"] = narrativa.fortalezas_riesgos(r)
    r["traza"] = traza(r, time.time() - t0)
    destino = (salida or C.DIR_SALIDAS) / carpeta.name / f"{r['corte']:%Y-%m-%d}"
    destino.mkdir(parents=True, exist_ok=True)
    g = graficas.generar(r, destino / "graficas")
    f = f"{r['corte']:%Y-%m-%d}"
    r["archivos_salida"] = {
        "comite": informe_comite.generar(r, g, destino / f"informe_comite_{f}.pdf"),
        "fondeadores": informe_fondeadores.generar(r, g, destino / f"informe_fondeadores_{f}.pdf"),
        "anexo": anexo_excel.generar(r, destino / f"anexo_credito_{f}.xlsx"),
    }
    r["traza"]["segundos"] = time.time() - t0
    return r
