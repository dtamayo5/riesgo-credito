"""Indicadores del corte y semáforo de límites.

  Máximo: ROJO si valor > límite; ÁMBAR si valor > alerta; VERDE en otro caso.
  Mínimo: ROJO si valor < límite; ÁMBAR si valor < alerta; VERDE en otro caso.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .utilidades import normalizar, num, pct

ESTADOS = ("ROJO", "ÁMBAR", "VERDE", "SIN DATO")


def calcular_indicadores(r: dict) -> dict:
    foto, r9, sc, fon, es, conc = r["foto"], r["niif9"], r["score"], r["fondeo"], r["estres"], r["concentracion"]
    severo = es["tabla"].sort_values("ecl_adicional").iloc[-1] if len(es["tabla"]) else None
    return {
        "CARTERA": foto["cartera"] / 1e6,
        "ICV_30": foto["icv30"], "ICV_90": foto["icv90"],
        "COBERTURA_30": r9.ecl / foto["saldo_30"] if foto["saldo_30"] else np.nan,
        "COSECHA_MOB6": r["cosecha_mob6"][1], "COSECHA_MOB6_NOMBRE": r["cosecha_mob6"][0],
        "GINI_OOT": sc.metricas["Fuera de tiempo"]["gini"], "PSI": sc.metricas["psi"],
        "CONC_PRODUCTO": conc["producto_max"], "CONC_PRODUCTO_NOMBRE": conc["producto_max_nombre"],
        "CONC_TOP20": conc["top20"],
        "COBERTURA_DEUDA": fon["cobertura"], "EXCEDENTE_FIN": fon["excedente"],
        "ESTRES_SEVERO_PAT": float(severo["pct_patrimonio"]) if severo is not None else np.nan,
        "ESTRES_SEVERO_NOMBRE": severo["escenario"] if severo is not None else "",
        "ECL": r9.ecl / 1e6, "REF_REGULATORIA": r9.ref_total / 1e6,
        "PROV_REGISTRADA": r["entidad"]["prov_registrada"] / 1e6,
        "ERRORES_DATOS": r["hallazgos"].conteo("ERROR"),
        "ADVERTENCIAS_DATOS": r["hallazgos"].conteo("ADVERTENCIA"),
    }


def formatear(valor, unidad: str) -> str:
    if valor is None or (isinstance(valor, float) and np.isnan(valor)):
        return "-"
    u = normalizar(unidad)
    if str(unidad).strip() == "%":
        return pct(valor, 1)
    if u == "veces":
        return num(valor, 2) + " x"
    if u == "numero":
        return num(valor, 2)
    return num(valor, 2)


def evaluar_limites(limites: pd.DataFrame, ind: dict) -> pd.DataFrame:
    detalles = {"CONC_PRODUCTO": "CONC_PRODUCTO_NOMBRE", "COSECHA_MOB6": "COSECHA_MOB6_NOMBRE",
                "ESTRES_SEVERO_PAT": "ESTRES_SEVERO_NOMBRE"}
    filas = []
    for _, l in limites.iterrows():
        v = ind.get(l["codigo"])
        if isinstance(v, (int, float, np.floating)) and not np.isnan(v):
            v = round(float(v), 4)      # se compara la cifra que se muestra, no decimales invisibles
        maximo = normalizar(l["tipo"]).startswith("max")
        if v is None or (isinstance(v, float) and np.isnan(v)):
            estado, uso = "SIN DATO", np.nan
        elif maximo:
            estado = "ROJO" if v > l["limite"] else "ÁMBAR" if v > l["alerta"] else "VERDE"
            uso = v / l["limite"] if l["limite"] else np.nan
        else:
            estado = "ROJO" if v < l["limite"] else "ÁMBAR" if v < l["alerta"] else "VERDE"
            uso = l["limite"] / v if v and v > 0 else np.nan
        filas.append({
            "codigo": l["codigo"], "indicador": l["indicador"], "categoria": l["categoria"],
            "tipo": "Máximo" if maximo else "Mínimo", "unidad": l["unidad"], "valor": v,
            "limite": l["limite"], "alerta": l["alerta"], "uso": uso, "estado": estado,
            "valor_txt": formatear(v, l["unidad"]), "limite_txt": formatear(l["limite"], l["unidad"]),
            "alerta_txt": formatear(l["alerta"], l["unidad"]),
            "detalle": str(ind.get(detalles.get(l["codigo"], ""), "")),
        })
    df = pd.DataFrame(filas)
    df["_o"] = df["estado"].map({e: i for i, e in enumerate(ESTADOS)})
    return df.sort_values(["_o"], kind="stable").drop(columns="_o").reset_index(drop=True)
