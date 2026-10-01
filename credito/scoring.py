"""
Score de originación: tramos con WoE, regresión logística y tarjeta de puntos.

Recorrido:
  1. Muestra: créditos con al menos 12 meses de historia. "Malo" = superó 90 días
     de mora en sus primeros 12 meses. Las primeras cosechas son el DESARROLLO;
     las siguientes, la validación FUERA DE TIEMPO (OOT): el modelo se evalúa en
     créditos que no vio y que son más recientes, como en la vida real.
  2. Tramos: cada variable se corta en tramos y se reemplaza por su peso de
     evidencia  WoE = ln(% de buenos del tramo / % de malos del tramo).
     Los tramos de variables numéricas se fusionan hasta que la tasa de malos
     sea monótona (un puntaje de buró más alto nunca debe dar más riesgo).
  3. Selección: valor de información IV = suma((%buenos - %malos) x WoE);
     se descartan variables con IV < 0,02, muy correlacionadas, con signo
     contrario al esperado o no significativas.
  4. Regresión logística por IRLS (mínimos cuadrados reponderados), sin librerías
     externas: beta_nuevo = beta + (X'WX)^-1 X'(y - p).
  5. Tarjeta de puntos: score = offset + factor x ln(odds buenos/malos), con
     factor = PDO / ln 2. Cada tramo recibe puntos enteros; el score es la suma.
  6. Validación: Gini = 2 x AUC - 1, KS, estabilidad de la población (PSI) y
     tabla de puntos de corte.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from statistics import NormalDist

import numpy as np
import pandas as pd

from . import config as C
from .utilidades import num


# ------------------------------------------------------------ muestra
def muestra_modelo(datos, p: pd.DataFrame) -> pd.DataFrame:
    org = datos.org.copy()
    corte_n = datos.corte.year * 12 + datos.corte.month
    org["mesn"] = org["mes_desembolso"].dt.year * 12 + org["mes_desembolso"].dt.month
    org = org[org["mesn"] + C.VENTANA_DESEMPENO <= corte_n].copy()
    malos = p[(p["dias_mora"] > C.DIAS_INCUMPLIMIENTO) & (p["mob"] <= C.VENTANA_DESEMPENO)]["id"].unique()
    org["malo"] = org["id"].isin(malos).astype(int)
    meses = sorted(org["mesn"].unique())
    n_dev = max(int(round(len(meses) * C.FRACCION_DESARROLLO)), 1)
    org["muestra"] = np.where(org["mesn"].isin(meses[:n_dev]), "Desarrollo", "Fuera de tiempo")
    return org


# ------------------------------------------------------------ tramos
@dataclass
class Variable:
    nombre: str
    tipo: str                     # "num" o "cat"
    cortes: list = field(default_factory=list)      # numéricas: límites internos
    mapa: dict = field(default_factory=dict)        # categóricas: categoría -> tramo
    tabla: pd.DataFrame | None = None
    iv: float = 0.0

    def tramo(self, x: pd.Series) -> pd.Series:
        if self.tipo == "num":
            return pd.Series(np.searchsorted(self.cortes, x.to_numpy(dtype=float), side="right"), index=x.index)
        return x.astype(str).map(self.mapa).fillna(self.mapa.get("__otros__", -1)).astype(int)

    def woe(self, x: pd.Series) -> pd.Series:
        w = self.tabla["woe"].to_dict()
        return self.tramo(x).map(w).fillna(0.0)


def _tabla_woe(t: pd.Series, y: pd.Series, etiquetas: dict) -> pd.DataFrame:
    g = pd.DataFrame({"t": t, "y": y}).groupby("t")["y"].agg(["size", "sum"])
    g.columns = ["n", "malos"]
    g["buenos"] = g["n"] - g["malos"]
    tb, tm = g["buenos"].sum(), g["malos"].sum()
    g["pct_buenos"] = (g["buenos"] + 0.5) / (tb + 0.5 * len(g))
    g["pct_malos"] = (g["malos"] + 0.5) / (tm + 0.5 * len(g))
    g["woe"] = np.log(g["pct_buenos"] / g["pct_malos"])
    g["iv"] = (g["pct_buenos"] - g["pct_malos"]) * g["woe"]
    g["tasa_malos"] = g["malos"] / g["n"]
    g["participacion"] = g["n"] / g["n"].sum()
    g["etiqueta"] = [etiquetas.get(i, str(i)) for i in g.index]
    return g


def _etiquetas_num(cortes: list, nombre: str) -> dict:
    dec = 2 if nombre == "endeudamiento" else 0
    f = (lambda v: num(v / 1e6, 1) + " M") if nombre in ("ingreso_mensual", "monto") else (lambda v: num(v, dec))
    if not cortes:
        return {0: "Todos"}
    et = {0: f"< {f(cortes[0])}"}
    for i in range(1, len(cortes)):
        et[i] = f"{f(cortes[i - 1])} a {f(cortes[i])}"
    et[len(cortes)] = f">= {f(cortes[-1])}"
    return et


def tramos_numerica(x: pd.Series, y: pd.Series, nombre: str) -> Variable:
    q = np.unique(np.quantile(x, np.linspace(0, 1, C.N_TRAMOS + 1)[1:-1]))
    cortes = [c for c in q if x.min() < c <= x.max()]
    signo = np.sign(np.corrcoef(x.rank(), y)[0, 1]) or 1.0
    while True:
        t = np.searchsorted(cortes, x.to_numpy(dtype=float), side="right")
        g = pd.DataFrame({"t": t, "y": y}).groupby("t")["y"].agg(["size", "mean"])
        if len(g) <= 1:
            break
        tasas, part = g["mean"].to_numpy(), g["size"].to_numpy() / len(x)
        dif = np.diff(tasas) * signo
        viola = np.where(dif < 0)[0]
        pequeno = np.where(part < C.MIN_PARTICIPACION_TRAMO)[0]
        if len(viola):
            i = viola[np.argmin(np.abs(dif[viola]))]       # fusiona el par i, i+1
        elif len(pequeno):
            k = pequeno[0]
            if k == 0:
                i = 0
            elif k == len(tasas) - 1:
                i = k - 1
            else:
                i = k - 1 if abs(tasas[k] - tasas[k - 1]) < abs(tasas[k] - tasas[k + 1]) else k
        else:
            break
        del cortes[i]
    v = Variable(nombre, "num", cortes=list(cortes))
    v.tabla = _tabla_woe(v.tramo(x), y, _etiquetas_num(v.cortes, nombre))
    v.iv = float(v.tabla["iv"].sum())
    return v


def tramos_categorica(x: pd.Series, y: pd.Series, nombre: str) -> Variable:
    x = x.astype(str)
    part = x.value_counts(normalize=True)
    grandes = part[part >= C.MIN_PARTICIPACION_TRAMO].index
    x2 = x.where(x.isin(grandes), "Otros")
    tasas = y.groupby(x2).mean().sort_values()
    mapa = {c: i for i, c in enumerate(tasas.index)}
    for c in part.index:
        if c not in grandes:
            mapa[c] = mapa["Otros"]
    mapa["__otros__"] = mapa.get("Otros", int(np.argmin(np.abs(tasas.to_numpy() - y.mean()))))
    v = Variable(nombre, "cat", mapa=mapa)
    etiquetas = {i: c for c, i in zip(tasas.index, range(len(tasas)))}
    v.tabla = _tabla_woe(v.tramo(x), y, etiquetas)
    v.iv = float(v.tabla["iv"].sum())
    return v


# ------------------------------------------------------------ logística
def logistica_irls(X: np.ndarray, y: np.ndarray, iter_max: int = 50):
    beta = np.zeros(X.shape[1])
    beta[0] = np.log(y.mean() / (1 - y.mean()))
    for _ in range(iter_max):
        p = 1 / (1 + np.exp(-X @ beta))
        W = p * (1 - p)
        H = X.T @ (X * W[:, None])
        paso = np.linalg.solve(H, X.T @ (y - p))
        beta += paso
        if np.max(np.abs(paso)) < 1e-8:
            break
    p = 1 / (1 + np.exp(-X @ beta))
    cov = np.linalg.inv(X.T @ (X * (p * (1 - p))[:, None]))
    ee = np.sqrt(np.diag(cov))
    z = beta / ee
    pval = 2 * (1 - np.array([NormalDist().cdf(abs(v)) for v in z]))
    return beta, ee, pval


# ------------------------------------------------------------ métricas
def auc(y: np.ndarray, s: np.ndarray) -> float:
    """AUC por rangos (Mann-Whitney): probabilidad de que un malo tenga más riesgo que un bueno."""
    r = pd.Series(s).rank().to_numpy()
    n1 = y.sum()
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def ks(y: np.ndarray, s: np.ndarray) -> float:
    o = np.argsort(-s)
    yb = y[o]
    cb = np.cumsum(yb) / yb.sum()
    cg = np.cumsum(1 - yb) / (1 - yb).sum()
    return float(np.max(np.abs(cb - cg)))


def psi(base: np.ndarray, actual: np.ndarray, n: int = 10) -> tuple[float, pd.DataFrame]:
    cortes = np.unique(np.quantile(base, np.linspace(0, 1, n + 1)[1:-1]))
    b = np.bincount(np.searchsorted(cortes, base, side="right"), minlength=len(cortes) + 1) / len(base)
    a = np.bincount(np.searchsorted(cortes, actual, side="right"), minlength=len(cortes) + 1) / len(actual)
    b, a = np.clip(b, 1e-4, None), np.clip(a, 1e-4, None)
    contrib = (a - b) * np.log(a / b)
    et = [f"< {num(cortes[0])}"] + [f"{num(cortes[i-1])} a {num(cortes[i])}" for i in range(1, len(cortes))] + \
         [f">= {num(cortes[-1])}"]
    return float(contrib.sum()), pd.DataFrame({"tramo": et, "desarrollo": b, "reciente": a, "contribucion": contrib})


# ------------------------------------------------------------ modelo
@dataclass
class Score:
    variables: list
    beta: np.ndarray
    ee: np.ndarray
    pval: np.ndarray
    ajuste_calibracion: float
    factor: float
    offset: float
    tabla_iv: pd.DataFrame
    tarjeta: pd.DataFrame
    metricas: dict
    psi_tabla: pd.DataFrame
    calificaciones: pd.DataFrame
    cortes: pd.DataFrame
    tasa_malos: float
    muestra: pd.DataFrame

    def puntuar(self, df: pd.DataFrame) -> pd.DataFrame:
        """Devuelve score (puntos), PD de originación calibrada y calificación."""
        W = np.column_stack([np.ones(len(df))] + [v.woe(df[v.nombre]).to_numpy() for v in self.variables])
        logit = W @ self.beta + self.ajuste_calibracion
        pd_ = 1 / (1 + np.exp(-logit))
        puntos = np.zeros(len(df))
        for v in self.variables:
            pts = self.tarjeta[self.tarjeta["variable"] == v.nombre].set_index("tramo")["puntos"]
            puntos += v.tramo(df[v.nombre]).map(pts).fillna(0).to_numpy()
        puntos += self.tarjeta.attrs["puntos_base"]
        return pd.DataFrame({"score": puntos.round(0), "pd_orig": pd_, "calificacion": calificar(pd_)},
                            index=df.index)


def calificar(pd_: np.ndarray) -> np.ndarray:
    limites = [l for _, l in C.ESCALA_PD]
    letras = np.array([g for g, _ in C.ESCALA_PD])
    return letras[np.minimum(np.searchsorted(limites, pd_, side="left"), len(letras) - 1)]


def desarrollar(datos, p: pd.DataFrame) -> Score:
    m = muestra_modelo(datos, p)
    dev = m[m["muestra"] == "Desarrollo"]
    y = dev["malo"]
    candidatas = []
    for v in datos.variables_num:
        if dev[v].nunique() > 1:
            candidatas.append(tramos_numerica(dev[v], y, v))
    for v in datos.variables_cat:
        if dev[v].nunique() > 1:
            candidatas.append(tramos_categorica(dev[v], y, v))
    tabla_iv = pd.DataFrame([{"variable": v.nombre, "nombre": C.NOMBRE_VARIABLE.get(v.nombre, v.nombre),
                              "iv": v.iv, "tramos": len(v.tabla)} for v in candidatas]).sort_values("iv", ascending=False)

    # selección: IV, correlación, signo y significancia
    orden = [v for v in sorted(candidatas, key=lambda v: -v.iv) if v.iv >= C.IV_MINIMO]
    woe_dev = {v.nombre: v.woe(dev[v.nombre]).to_numpy() for v in orden}
    elegidas = []
    for v in orden:
        if all(abs(np.corrcoef(woe_dev[v.nombre], woe_dev[e.nombre])[0, 1]) < 0.7 for e in elegidas):
            elegidas.append(v)
        if len(elegidas) == C.MAX_VARIABLES:
            break
    motivo = {}
    while True:
        X = np.column_stack([np.ones(len(dev))] + [woe_dev[v.nombre] for v in elegidas])
        beta, ee, pval = logistica_irls(X, y.to_numpy(dtype=float))
        malas = [(i, v) for i, v in enumerate(elegidas, start=1) if beta[i] >= 0 or pval[i] > 0.05]
        if not malas:
            break
        i, v = max(malas, key=lambda t: t[0] if beta[t[0]] >= 0 else pval[t[0]])
        motivo[v.nombre] = "signo contrario" if beta[i] >= 0 else f"no significativa (p = {pval[i]:.2f})"
        elegidas.remove(v)
    tabla_iv["estado"] = tabla_iv["variable"].map(
        lambda n: "En el modelo" if n in [v.nombre for v in elegidas] else
        motivo.get(n, "IV bajo" if n not in [v.nombre for v in orden] else "Correlacionada con otra"))

    # calibración en grande: el promedio de PD = tasa de malos de toda la muestra madura
    Xall = np.column_stack([np.ones(len(m))] + [v.woe(m[v.nombre]).to_numpy() for v in elegidas])
    logit = Xall @ beta
    objetivo = m["malo"].mean()
    a = 0.0
    for _ in range(60):
        pm = 1 / (1 + np.exp(-(logit + a)))
        a -= (pm.mean() - objetivo) / max((pm * (1 - pm)).mean(), 1e-9)
    # tarjeta de puntos
    factor = C.PDO / np.log(2)
    offset = C.PUNTOS_BASE - factor * np.log(C.ODDS_BASE)
    k = len(elegidas)
    filas = []
    for i, v in enumerate(elegidas, start=1):
        for t, r in v.tabla.iterrows():
            pts = -(beta[i] * r["woe"] + (beta[0] + a) / k) * factor + offset / k
            filas.append({"variable": v.nombre, "nombre": C.NOMBRE_VARIABLE.get(v.nombre, v.nombre),
                          "tramo": t, "etiqueta": r["etiqueta"], "participacion": r["participacion"],
                          "tasa_malos": r["tasa_malos"], "woe": r["woe"], "puntos": round(pts)})
    tarjeta = pd.DataFrame(filas)
    tarjeta.attrs["puntos_base"] = 0
    sc = Score(elegidas, beta, ee, pval, a, factor, offset, tabla_iv, tarjeta, {}, pd.DataFrame(),
               pd.DataFrame(), pd.DataFrame(), float(objetivo), m)
    # métricas
    pun = sc.puntuar(m)
    m = m.join(pun)
    met = {}
    for nombre, g in m.groupby("muestra"):
        yy, ss = g["malo"].to_numpy(), g["pd_orig"].to_numpy()
        au = auc(yy, ss)
        met[nombre] = {"n": len(g), "malos": int(yy.sum()), "tasa_malos": yy.mean(), "auc": au,
                       "gini": 2 * au - 1, "ks": ks(yy, ss)}
    corte_n = datos.corte.year * 12 + datos.corte.month
    rec = datos.org[(datos.org["mes_desembolso"].dt.year * 12 + datos.org["mes_desembolso"].dt.month)
                    > corte_n - C.MESES_PSI]
    rec_sc = sc.puntuar(rec)
    valor_psi, tabla_psi = psi(m.loc[m["muestra"] == "Desarrollo", "score"].to_numpy(), rec_sc["score"].to_numpy())
    met["psi"] = valor_psi
    met["n_reciente"] = len(rec)
    met["pd_reciente"] = float(rec_sc["pd_orig"].mean())
    met["pd_desarrollo"] = float(m.loc[m["muestra"] == "Desarrollo", "pd_orig"].mean())
    sc.metricas, sc.psi_tabla = met, tabla_psi
    # calificaciones en la muestra madura
    letras = [g for g, _ in C.ESCALA_PD]
    cal = m.groupby("calificacion").agg(creditos=("id", "size"), malos=("malo", "sum"),
                                        pd_modelo=("pd_orig", "mean"), score_min=("score", "min"),
                                        score_max=("score", "max")).reindex(letras).dropna(subset=["creditos"])
    cal["tasa_observada"] = cal["malos"] / cal["creditos"]
    cal["participacion"] = cal["creditos"] / cal["creditos"].sum()
    lim_sup = dict(C.ESCALA_PD)
    cal["pd_hasta"] = [lim_sup[g] for g in cal.index]
    # binomial: ¿la tasa observada es compatible con la PD del modelo? (z a dos colas, 95%)
    z = (cal["malos"] - cal["creditos"] * cal["pd_modelo"]) / np.sqrt(
        cal["creditos"] * cal["pd_modelo"] * (1 - cal["pd_modelo"]))
    cal["prueba_binomial"] = np.where(z.abs() <= 1.96, "Calibrada", np.where(z > 0, "Subestima", "Sobrestima"))
    sc.calificaciones = cal
    # puntos de corte (muestra fuera de tiempo)
    oot = m[m["muestra"] == "Fuera de tiempo"]
    filas = []
    for q in [0, 0.05, 0.10, 0.15, 0.20, 0.25, 0.30]:
        c = np.quantile(oot["score"], q) if q > 0 else oot["score"].min() - 1
        apr = oot[oot["score"] > c] if q > 0 else oot
        filas.append({"rechazo": q, "corte": c if q > 0 else np.nan, "aprobados": len(apr),
                      "tasa_malos": apr["malo"].mean(),
                      "malos_evitados": 1 - apr["malo"].sum() / max(oot["malo"].sum(), 1)})
    sc.cortes = pd.DataFrame(filas)
    sc.muestra = m
    return sc
