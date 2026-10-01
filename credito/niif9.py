"""
Provisiones por pérdida esperada (NIIF 9) y referencia regulatoria.

  ECL = suma_t  PD marginal_t x LGD x EAD_t x factor de descuento_t

PD (probabilidad de incumplimiento)
  - PD de originación: la del score, calibrada con la tasa de malos histórica
    (promedio del ciclo).
  - PD a 12 meses al corte (punto en el tiempo): el score ordena y la matriz de
    rodamientos de los últimos 12 meses fija el nivel. Para un crédito al día:
        PD12 = PD originación x (PD al día según la cadena / PD promedio del score)
    Para un crédito en mora: la probabilidad de la cadena de llegar a 91+ en
    12 meses desde su tramo (nunca menor que la de un crédito al día).
    La cadena de Markov se eleva a la potencia 12: P^12 da la probabilidad de
    estar absorbido en incumplimiento al cabo de un año.
  - PD de vida: riesgo mensual constante. Año 1 con la PD12 del tramo actual; del
    año 2 en adelante, con la PD de un crédito al día (si sobrevive, se normaliza).

LGD (severidad): curva de recuperaciones observada después del incumplimiento,
  descontada a la tasa del producto:  LGD = 1 - suma_m r_m / (1 + tasa)^(m/12),
  con r_m = recuperaciones del mes m / saldo al incumplir (método de cadena:
  cada mes usa todos los incumplimientos que ya lo alcanzaron).

EAD (exposición): saldo de capital al corte, amortizado con cuota fija hasta el
  vencimiento (el saldo que estaría expuesto en cada mes futuro).

Etapas
  3: más de 90 días de mora (incumplimiento): ECL = saldo x LGD.
  2: más de 30 días, o aumento significativo del riesgo (PD12 >= 2 x PD de
     originación y al menos 3 pp mayor), o curado de 31+ días hace menos de
     6 meses: ECL de toda la vida.
  1: el resto: ECL de 12 meses.

Escenarios: la ECL final es el promedio ponderado de los escenarios NIIF 9 de la
  política (multiplicador de PD y ajuste de LGD). Las etapas se recalculan en cada
  escenario: en un escenario adverso más créditos pasan a etapa 2 (efecto acantilado).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from .utilidades import normalizar

ESTADOS = ["0", "1", "2", "3", "D", "P"]   # al día, 1-30, 31-60, 61-90, incumplido (91+), pagado


def _estado_markov(dias: pd.Series, estado: pd.Series, saldo: pd.Series) -> pd.Series:
    e = pd.Series(np.select([dias <= 0, dias <= 30, dias <= 60, dias <= 90], ["0", "1", "2", "3"], "D"),
                  index=dias.index)
    e[(estado == "Castigado")] = "D"
    e[(estado == "Cancelado") | ((estado == "Vigente") & (saldo <= 0))] = "P"
    return e


def matriz_markov(p: pd.DataFrame, corte, meses: int = 12, productos=None) -> dict:
    """Matriz de transición mensual (por número de créditos) de cada producto y de
    toda la cartera, con estados absorbentes D (incumplido) y P (pagado)."""
    todos = sorted(m for m in p["mes"].unique() if m <= corte)[-(meses + 1):]
    q = p[p["mes"].isin(todos)][["id", "mes", "producto", "dias_mora", "estado", "saldo_capital"]].copy()
    q["e"] = _estado_markov(q["dias_mora"], q["estado"], q["saldo_capital"])
    sig = q[["id", "mes", "e"]].copy()
    sig["mes"] = sig["mes"] - pd.offsets.MonthEnd(1)
    t = q[q["mes"] < todos[-1]].merge(sig.rename(columns={"e": "e1"}), on=["id", "mes"], how="left")
    t["e1"] = t["e1"].fillna("P")            # desaparece del archivo = se canceló
    t = t[t["e"].isin(["0", "1", "2", "3"])]
    salida = {}
    for nombre, g in [("__total__", t)] + list(t.groupby("producto")):
        m = pd.crosstab(g["e"], g["e1"]).reindex(index=ESTADOS, columns=ESTADOS).fillna(0)
        m.loc["D", "D"] = 1
        m.loc["P", "P"] = 1
        salida[nombre] = (m.div(m.sum(axis=1).replace(0, np.nan), axis=0).fillna(0), int(len(g)))
    return salida


def pd_markov(matrices: dict, horizonte: int = 12) -> pd.DataFrame:
    filas = {}
    for prod, (m, n) in matrices.items():
        if prod != "__total__" and n < 2000:
            m = matrices["__total__"][0]
        pot = np.linalg.matrix_power(m.to_numpy(), horizonte)
        filas[prod] = dict(zip(["0", "1", "2", "3"], pot[:4, ESTADOS.index("D")]))
    return pd.DataFrame(filas).T


# --------------------------------------------------------------------- LGD
def curva_lgd(p: pd.DataFrame, corte) -> tuple[pd.DataFrame, pd.DataFrame]:
    """LGD por producto a partir de las recuperaciones observadas."""
    d = p[p["dias_mora"] > C.DIAS_INCUMPLIMIENTO].sort_values("mes").groupby("id").first()
    d = d[["mes", "saldo_capital", "producto", "tasa_ea"]].rename(columns={"mes": "mes_def", "saldo_capital": "ead"})
    d = d[d["ead"] > 0]
    rec = p[p["id"].isin(d.index) & (p["recuperacion_mes"] > 0)][["id", "mes", "recuperacion_mes"]]
    rec = rec.join(d["mes_def"], on="id")
    n = lambda f: f.dt.year * 12 + f.dt.month
    rec["m"] = n(rec["mes"]) - n(rec["mes_def"])
    rec = rec[(rec["m"] >= 1) & (rec["m"] <= C.MESES_RECUPERACION)]
    corte_n = corte.year * 12 + corte.month
    d["meses_obs"] = corte_n - n(d["mes_def"])
    resumen, curvas = [], {}
    grupos = [("Toda la cartera", d.index)] + [(pr, g.index) for pr, g in d.groupby("producto")]
    for nombre, ids in grupos:
        dd = d.loc[ids]
        rr = rec[rec["id"].isin(ids)].groupby("m")["recuperacion_mes"].sum()
        r = np.zeros(C.MESES_RECUPERACION)
        for m in range(1, C.MESES_RECUPERACION + 1):
            expuestos = dd.loc[dd["meses_obs"] >= m, "ead"].sum()
            r[m - 1] = rr.get(m, 0.0) / expuestos if expuestos > 0 else (r[m - 2] if m > 1 else 0.0)
        tasa = np.average(dd["tasa_ea"], weights=dd["ead"]) if len(dd) else 0.2
        desc = (1 + tasa) ** (-np.arange(1, C.MESES_RECUPERACION + 1) / 12)
        rec_total, rec_desc = r.sum(), (r * desc).sum()
        completos = (dd["meses_obs"] >= C.MESES_RECUPERACION).sum()
        resumen.append({"producto": nombre, "incumplimientos": len(dd), "con_24_meses": int(completos),
                        "ead_incumplida": dd["ead"].sum(), "recuperacion": rec_total,
                        "recuperacion_descontada": rec_desc, "lgd": max(1 - rec_desc, C.LGD_PISO),
                        "tasa_descuento": tasa})
        curvas[nombre] = np.cumsum(r)
    res = pd.DataFrame(resumen).set_index("producto")
    total = res.loc["Toda la cartera", "lgd"]
    res["lgd_usada"] = np.where(res["incumplimientos"] >= C.MIN_INCUMPLIMIENTOS_LGD, res["lgd"], total)
    return res, pd.DataFrame(curvas, index=range(1, C.MESES_RECUPERACION + 1))


# ------------------------------------------------------- matriz regulatoria
def referencia_regulatoria(f: pd.DataFrame, matriz: pd.DataFrame) -> pd.DataFrame:
    """Categoría A-E por altura de mora y % de provisión de la matriz de la política."""
    mat = matriz.copy()
    mat["clave"] = mat["producto"].map(normalizar)
    cat = pd.Series("A", index=f.index)
    porc = pd.Series(np.nan, index=f.index)
    for prod in f["producto"].unique():
        k = normalizar(prod)
        sub = mat[mat["clave"] == k]
        if sub.empty:   # mismo tipo de producto (primera palabra)
            sub = mat[mat["clave"].str.split().str[0] == k.split()[0]]
        if sub.empty:
            sub = mat[mat["clave"] == mat["clave"].iloc[0]]
        idx = f.index[f["producto"] == prod]
        dias = f.loc[idx, "dias_mora"]
        for _, r in sub.iterrows():
            sel = idx[(dias >= r["dias_desde"]) & (dias <= r["dias_hasta"])]
            cat[sel] = r["categoria"]
            porc[sel] = r["provision"]
    return pd.DataFrame({"categoria": cat, "porc_ref": porc.fillna(0)})


# --------------------------------------------------------------------- ECL
@dataclass
class ResultadoNIIF9:
    detalle: pd.DataFrame          # un registro por crédito vivo
    escenarios: pd.DataFrame       # ECL por escenario
    pd_cadena: pd.DataFrame
    lgd: pd.DataFrame
    curva_recuperacion: pd.DataFrame
    factor_pit: pd.Series
    matrices: dict
    ecl: float
    ref_especifica: float
    ref_general: float

    @property
    def ref_total(self):
        return self.ref_especifica + self.ref_general


def ecl_creditos(f: pd.DataFrame, mult_pd: float = 1.0, ajuste_lgd: float = 0.0) -> pd.DataFrame:
    """ECL por crédito para un escenario. Devuelve etapa y ECL (recalcula etapas)."""
    pd12 = np.minimum(f["pd12"].to_numpy() * mult_pd, 0.999)
    pdp = np.minimum(f["pd_perf"].to_numpy() * mult_pd, 0.999)
    lgd = np.clip(f["lgd"].to_numpy() + ajuste_lgd, 0, 1)
    dias = f["dias_mora"].to_numpy()
    etapa = np.where(dias > C.DIAS_ETAPA_3, 3,
                     np.where((dias > C.DIAS_ETAPA_2) | f["curado"].to_numpy()
                              | ((pd12 >= C.SICR_MULTIPLO * f["pd_orig"].to_numpy())
                                 & (pd12 - f["pd_orig"].to_numpy() >= C.SICR_ABSOLUTO)), 2, 1))
    pd12 = np.where(dias > C.DIAS_ETAPA_3, 1.0, pd12)
    saldo = f["saldo_capital"].to_numpy()
    n = np.maximum(f["plazo_restante"].to_numpy(), 1).astype(int)
    i = (1 + f["tasa_ea"].to_numpy()) ** (1 / 12) - 1
    T = int(n.max())
    t = np.arange(1, T + 1)[None, :]
    # saldo al inicio del mes t (cuota fija): B_{t-1}
    a = (1 + i)[:, None]
    nn = n[:, None]
    ead = saldo[:, None] * (a ** nn - a ** (t - 1)) / np.where(a ** nn - 1 == 0, 1, a ** nn - 1)
    ead = np.where(t <= nn, np.maximum(ead, 0), 0)
    h1 = 1 - (1 - pd12) ** (1 / 12)
    h2 = 1 - (1 - pdp) ** (1 / 12)
    h = np.where(t <= 12, h1[:, None], h2[:, None])
    sobrevive = np.cumprod(1 - h, axis=1)
    marginal = h * np.concatenate([np.ones((len(f), 1)), sobrevive[:, :-1]], axis=1)
    desc = (1 + f["tasa_ea"].to_numpy())[:, None] ** (-t / 12)
    perdida = marginal * lgd[:, None] * ead * desc
    horizonte = np.where(etapa == 1, np.minimum(12, n), n)[:, None]
    ecl = np.where(t <= horizonte, perdida, 0).sum(axis=1)
    ecl = np.where(etapa == 3, saldo * lgd, ecl)
    pd_vida = 1 - np.where(t <= nn, 1 - h, 1).prod(axis=1)
    return pd.DataFrame({"etapa": etapa, "ecl": ecl, "pd12_esc": pd12, "pd_vida": np.where(etapa == 3, 1, pd_vida)},
                        index=f.index)


def calcular(datos, p: pd.DataFrame, score) -> ResultadoNIIF9:
    corte = datos.corte
    f = p[(p["mes"] == corte) & p["vivo"]].copy()
    f = f.join(datos.org.set_index("id")[[c for c in datos.org.columns
                                         if c not in f.columns and c != "id"]], on="id")
    f = f.join(score.puntuar(f))
    # historia reciente: ¿estuvo en 31+ en los últimos 6 meses?
    desde = corte - pd.offsets.MonthEnd(C.SICR_MESES_CURA)
    max6 = p[(p["mes"] > desde) & (p["mes"] < corte)].groupby("id")["dias_mora"].max()
    f["curado"] = (f["id"].map(max6).fillna(0) > C.DIAS_ETAPA_2) & (f["dias_mora"] <= C.DIAS_ETAPA_2)
    # PD punto en el tiempo
    matrices = matriz_markov(p, corte)
    pdc = pd_markov(matrices)
    f["estado_m"] = _estado_markov(f["dias_mora"], f["estado"], f["saldo_capital"])
    factor = {}
    for prod, g in f[f["estado_m"] == "0"].groupby("producto"):
        fila = pdc.loc[prod] if prod in pdc.index else pdc.loc["__total__"]
        factor[prod] = fila["0"] / g["pd_orig"].mean()
    factor = pd.Series(factor)
    f["factor_pit"] = f["producto"].map(factor).fillna(1.0)
    f["pd_perf"] = np.minimum(f["pd_orig"] * f["factor_pit"], 0.999)
    pd_tramo = [pdc.loc[pr, e] if (pr in pdc.index and e in "123") else np.nan
                for pr, e in zip(f["producto"], f["estado_m"])]
    f["pd12"] = np.where(f["estado_m"].isin(["1", "2", "3"]), np.maximum(pd_tramo, f["pd_perf"]),
                         np.where(f["estado_m"] == "D", 1.0, f["pd_perf"]))
    # LGD
    lgd, curva = curva_lgd(p, corte)
    f["lgd"] = f["producto"].map(lgd["lgd_usada"]).fillna(lgd.loc["Toda la cartera", "lgd"])
    f["plazo_restante"] = np.maximum(f["plazo_meses"] - f["mob"], 1)
    # escenarios
    esc = datos.escenarios.copy()
    filas = []
    ecl_pond = np.zeros(len(f))
    for _, e in esc.iterrows():
        r = ecl_creditos(f, e["mult_pd"], e["ajuste_lgd"])
        fila = {"escenario": e["escenario"], "uso": e["uso"], "peso": e["peso"], "mult_pd": e["mult_pd"],
                "ajuste_lgd": e["ajuste_lgd"], "ecl": r["ecl"].sum()}
        for k in (1, 2, 3):
            fila[f"saldo_e{k}"] = f.loc[r["etapa"] == k, "saldo_capital"].sum()
            fila[f"ecl_e{k}"] = r.loc[r["etapa"] == k, "ecl"].sum()
        filas.append(fila)
        if normalizar(e["uso"]) == "niif 9":
            ecl_pond += e["peso"] * r["ecl"].to_numpy()
    base = ecl_creditos(f)
    f["etapa"] = base["etapa"]
    f["pd_vida"] = base["pd_vida"]
    f["ecl"] = ecl_pond
    ref = referencia_regulatoria(f, datos.matriz)
    f = f.join(ref)
    f["prov_ref"] = f["saldo_capital"] * f["porc_ref"]
    ref_gen = datos.entidad.get("prov_general", 0.0) * f["saldo_capital"].sum()
    return ResultadoNIIF9(f, pd.DataFrame(filas), pdc, lgd, curva, factor, matrices,
                          float(f["ecl"].sum()), float(f["prov_ref"].sum()), float(ref_gen))


# ------------------------------------------------------------ resúmenes
def por_etapa(r: ResultadoNIIF9) -> pd.DataFrame:
    f = r.detalle
    g = f.groupby("etapa").agg(creditos=("id", "size"), saldo=("saldo_capital", "sum"), ecl=("ecl", "sum"),
                               pd12=("pd12", lambda s: np.average(s, weights=f.loc[s.index, "saldo_capital"])),
                               lgd=("lgd", lambda s: np.average(s, weights=f.loc[s.index, "saldo_capital"])))
    g = g.reindex([1, 2, 3]).fillna(0)
    g["participacion"] = g["saldo"] / g["saldo"].sum()
    g["cobertura"] = g["ecl"] / g["saldo"].replace(0, np.nan)
    return g


def por_producto(r: ResultadoNIIF9) -> pd.DataFrame:
    f = r.detalle
    g = f.groupby("producto").agg(saldo=("saldo_capital", "sum"), ecl=("ecl", "sum"), ref=("prov_ref", "sum"))
    for k in (1, 2, 3):
        g[f"ecl_e{k}"] = f[f["etapa"] == k].groupby("producto")["ecl"].sum().reindex(g.index).fillna(0)
    g["cobertura"] = g["ecl"] / g["saldo"]
    g["cobertura_ref"] = g["ref"] / g["saldo"]
    return g.sort_values("saldo", ascending=False)


def por_categoria(r: ResultadoNIIF9) -> pd.DataFrame:
    f = r.detalle
    g = f.groupby("categoria").agg(creditos=("id", "size"), saldo=("saldo_capital", "sum"),
                                   prov_ref=("prov_ref", "sum"), ecl=("ecl", "sum"))
    g["participacion"] = g["saldo"] / g["saldo"].sum()
    return g.reindex([c for c in "ABCDE" if c in g.index])


def por_calificacion(r: ResultadoNIIF9) -> pd.DataFrame:
    f = r.detalle
    letras = [g for g, _ in C.ESCALA_PD]
    g = f.groupby("calificacion").agg(creditos=("id", "size"), saldo=("saldo_capital", "sum"),
                                      pd_orig=("pd_orig", "mean"), pd12=("pd12", "mean"), ecl=("ecl", "sum"))
    g = g.reindex([x for x in letras if x in g.index])
    g["participacion"] = g["saldo"] / g["saldo"].sum()
    g["cobertura"] = g["ecl"] / g["saldo"]
    return g
