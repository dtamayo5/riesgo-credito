"""
Fondeo: lo que mira un fondeador antes de prestarle a la entidad.

Base de préstamo (borrowing base)
  cartera elegible = saldo con mora <= días permitidos por el fondeador
  base de préstamo = cartera elegible x tasa de anticipo
  cobertura de la deuda = base de préstamo / deuda (debe ser >= 1)
  holgura = base de préstamo - deuda (si es negativa, la entidad debe aportar
  cartera o prepagar)

Excedente financiero anual (excess spread), como % de la cartera bruta
  rendimiento de la cartera al día (tasa promedio x proporción que paga)
  + comisiones recurrentes
  - costo del fondeo (costo promedio x cartera no financiada con patrimonio)
  - gastos operativos
  - pérdida esperada a 12 meses (PD12 x LGD x saldo de los créditos no incumplidos)
  = excedente: el colchón que absorbe pérdidas antes de tocar el capital del fondeador.

Punto de equilibrio: múltiplo de la PD que lleva el excedente a cero,
  m* = 1 + excedente / pérdida esperada.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calcular(datos, foto: dict, detalle: pd.DataFrame, ev: pd.DataFrame) -> dict:
    e = datos.entidad
    B = foto["cartera"]
    al_dia = detalle[detalle["dias_mora"] <= 30]
    s_al_dia = al_dia["saldo_capital"].sum()
    rend = foto["tasa_promedio"] * s_al_dia / B
    vivos = detalle[detalle["etapa"] < 3]
    pe = float((vivos["pd12"] * vivos["lgd"] * vivos["saldo_capital"]).sum() / B)
    fondeo = e["costo_fondeo"] * max(B - e["patrimonio"], 0) / B
    excedente = rend + e["comisiones"] - fondeo - e["opex"] - pe
    base = foto["elegible"] * e["anticipo"]
    deuda = e["deuda"]
    hist = ev[["cartera", "elegible"]].copy()
    hist["base_prestamo"] = hist["elegible"] * e["anticipo"]
    hist["pct_elegible"] = hist["elegible"] / hist["cartera"]
    return {
        "cartera": B, "elegible": foto["elegible"], "pct_elegible": foto["elegible"] / B,
        "anticipo": e["anticipo"], "base_prestamo": base, "deuda": deuda,
        "cobertura": base / deuda if deuda else np.nan, "holgura": base - deuda,
        "elegible_requerida": deuda / e["anticipo"] if e["anticipo"] else np.nan,
        "rendimiento": rend, "comisiones": e["comisiones"], "costo_fondeo": fondeo, "opex": e["opex"],
        "perdida_esperada": pe, "excedente": excedente,
        "equilibrio_pd": 1 + excedente / pe if pe > 0 else np.nan,
        "apalancamiento": deuda / e["patrimonio"] if e["patrimonio"] else np.nan,
        "patrimonio": e["patrimonio"], "historia": hist,
    }
