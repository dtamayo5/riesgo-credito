"""
Pruebas de estrés de la cartera.

Cada escenario multiplica la PD y suma puntos a la LGD (hoja Escenarios de la
política). Se mide el impacto sobre tres cosas que le importan a distintos
lectores:
  1. Provisiones: ECL estresada (con etapas recalculadas) menos ECL actual,
     como % del patrimonio (lo que mira el comité y el supervisor).
  2. Excedente financiero: la pérdida esperada crece con el multiplicador (lo
     que mira el fondeador).
  3. Cobertura de la deuda: durante 3 meses entra a mora 30+ un flujo
     (m - 1) veces mayor al promedio reciente, que deja de ser elegible.

Estrés inverso: ¿qué multiplicador de la PD rompe cada umbral? Responde la
pregunta "¿cuánto tendría que empeorar la cartera para que...?".
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C
from .niif9 import ecl_creditos
from .utilidades import normalizar


def calcular(datos, r9, fon: dict, foto: dict, flujo_mora: float) -> dict:
    pat = datos.entidad["patrimonio"]
    f = r9.detalle
    B = foto["cartera"]
    filas = []
    esc = r9.escenarios
    for _, e in esc[esc["uso"].map(normalizar) == "estres"].iterrows():
        m, a = e["mult_pd"], e["ajuste_lgd"]
        delta = e["ecl"] - r9.ecl
        pe = fon["perdida_esperada"] * m * (1 + a / max(f["lgd"].mean(), 1e-9))
        extra = (m - 1) * flujo_mora * C.MESES_DETERIORO_ESTRES
        eleg = max(fon["elegible"] - extra, 0)
        filas.append({
            "escenario": e["escenario"], "mult_pd": m, "ajuste_lgd": a, "ecl": e["ecl"],
            "ecl_adicional": delta, "pct_patrimonio": delta / pat if pat else np.nan,
            "saldo_etapa2": e["saldo_e2"] / B, "icv30": (foto["saldo_30"] + extra) / B,
            "excedente": fon["excedente"] - (pe - fon["perdida_esperada"]),
            "cobertura_deuda": eleg * fon["anticipo"] / fon["deuda"] if fon["deuda"] else np.nan,
        })
    tabla = pd.DataFrame(filas)
    # estrés inverso
    rejilla = np.round(np.arange(1.0, 10.01, 0.25), 2)
    ecl_m = np.array([ecl_creditos(f, m)["ecl"].sum() for m in rejilla])
    delta = ecl_m - ecl_m[0]
    lim = datos.limites.set_index("codigo")
    umbral_pat = float(lim.loc["ESTRES_SEVERO_PAT", "limite"]) if "ESTRES_SEVERO_PAT" in lim.index else 0.25

    def cruce(valores, objetivo):
        idx = np.where(valores >= objetivo)[0]
        if not len(idx):
            return np.nan
        k = idx[0]
        if k == 0:
            return rejilla[0]
        return float(np.interp(objetivo, valores[k - 1:k + 1], rejilla[k - 1:k + 1]))

    inverso = {
        "excedente_cero": fon["equilibrio_pd"],
        "cobertura_uno": (1 + (fon["elegible"] - fon["deuda"] / fon["anticipo"]) /
                          (flujo_mora * C.MESES_DETERIORO_ESTRES)) if flujo_mora > 0 and fon["deuda"] else np.nan,
        "umbral_patrimonio": umbral_pat,
        "consume_umbral": cruce(delta, umbral_pat * pat),
        "consume_patrimonio": cruce(delta, pat),
    }
    curva = pd.DataFrame({"mult_pd": rejilla, "ecl": ecl_m, "ecl_adicional": delta,
                          "pct_patrimonio": delta / pat if pat else np.nan})
    return {"tabla": tabla, "inverso": inverso, "curva": curva, "flujo_mora": flujo_mora}
