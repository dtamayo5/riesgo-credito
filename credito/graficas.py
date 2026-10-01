"""Gráficas de los informes (PNG).

Reglas de diseño (las mismas del motor de tesorería): una serie = un color; el
texto siempre en tinta; rojo y ámbar solo cuando significan estado; rejilla
tenue; líneas punteadas solo para umbrales.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

from .utilidades import fecha_corta, num  # noqa: E402

AZUL, NARANJA = "#2a78d6", "#eb6834"
AZUL_OSCURO, GRIS = "#104281", "#b9c0c8"
CRITICO, ALERTA, BIEN = "#d03b3b", "#fab219", "#0ca30c"
TINTA, TINTA_2, TENUE = "#0b0b0b", "#52514e", "#898781"
REJILLA, BASE = "#e1e0d9", "#c3c2b7"
ANCHO = 6.6

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.titlesize": 9,
    "axes.titleweight": "bold", "axes.titlelocation": "left", "axes.titlecolor": TINTA,
    "axes.edgecolor": BASE, "axes.labelcolor": TINTA_2, "axes.linewidth": 0.8,
    "xtick.color": TINTA_2, "ytick.color": TINTA_2, "xtick.labelsize": 7.5, "ytick.labelsize": 7.5,
    "axes.grid": True, "grid.color": REJILLA, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "legend.frameon": False, "legend.fontsize": 7.5, "figure.dpi": 100, "savefig.dpi": 200,
    "axes.spines.top": False, "axes.spines.right": False,
})
FMT_MILES = FuncFormatter(lambda x, _: num(x, 0))
FMT_PCT0 = FuncFormatter(lambda x, _: num(100 * x, 0) + "%")
FMT_PCT1 = FuncFormatter(lambda x, _: num(100 * x, 1) + "%")
FMT_PCT = FuncFormatter(lambda x, _: num(100 * x, 0 if abs(100 * x - round(100 * x)) < 1e-6 else 1) + "%")


def etiqueta_cosecha(q: str) -> str:
    """'2026Q1' -> 'T1-2026'."""
    return f"T{q[-1]}-{q[:4]}" if len(q) == 6 and q[4] == "Q" else q


def _guardar(fig, ruta: Path) -> Path:
    fig.savefig(ruta, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return ruta


def _umbral(ax, valor, texto, color, x_texto=None):
    if valor is None or np.isnan(valor):
        return
    ax.axhline(valor, color=color, lw=1, ls="--", zorder=2)
    xmin, xmax = ax.get_xlim()
    ax.text(x_texto if x_texto is not None else xmin + 0.01 * (xmax - xmin), valor, f" {texto}",
            color=TINTA_2, fontsize=7, va="bottom")


def _lim(limites, codigo):
    t = limites[limites["codigo"] == codigo]
    return (float(t["limite"].iloc[0]), float(t["alerta"].iloc[0])) if len(t) else (np.nan, np.nan)


def evolucion_mora(ev: pd.DataFrame, limites: pd.DataFrame, ruta: Path) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(ANCHO, 2.6), gridspec_kw={"wspace": 0.3})
    x = np.arange(len(ev))
    et = [fecha_corta(m) for m in ev.index]
    for ax, col, cod, titulo in [(a1, "icv30", "ICV_30", "Cartera vencida a más de 30 días"),
                                 (a2, "icv90", "ICV_90", "Cartera vencida a más de 90 días")]:
        ax.plot(x, ev[col], color=AZUL, lw=2, marker="o", ms=3, zorder=3)
        ax.set_title(titulo)
        lim, ale = _lim(limites, cod)
        top = np.nanmax([ev[col].max(), lim if not np.isnan(lim) else 0]) * 1.25
        ax.set_ylim(0, top)
        _umbral(ax, lim, "límite", CRITICO)
        _umbral(ax, ale, "alerta", ALERTA)
        ax.set_xticks(x[::3], et[::3])
        ax.yaxis.set_major_formatter(FMT_PCT)
        ax.annotate(num(100 * ev[col].iloc[-1], 1) + "%", (x[-1], ev[col].iloc[-1]), xytext=(4, 6),
                    textcoords="offset points", fontsize=7.5, color=TINTA)
    return _guardar(fig, ruta)


def cosechas(cos: pd.DataFrame, ruta: Path, titulo: str) -> Path:
    fig, ax = plt.subplots(figsize=(ANCHO, 2.9))
    recientes = list(cos.index[-3:])
    for q in cos.index:
        s = cos.loc[q].dropna()
        if q in recientes:
            continue
        ax.plot(s.index, s.values, color=GRIS, lw=1.1, zorder=2)
    colores = [AZUL_OSCURO, AZUL, NARANJA]
    for q, c in zip(recientes, colores):
        s = cos.loc[q].dropna()
        ax.plot(s.index, s.values, color=c, lw=2.2, marker="o", ms=3, zorder=3, label=etiqueta_cosecha(q))
    ax.plot([], [], color=GRIS, lw=1.1, label="Cosechas anteriores")
    ax.set_title(titulo)
    ax.set_xlabel("Meses desde el desembolso")
    ax.yaxis.set_major_formatter(FMT_PCT0)
    ax.set_xlim(0.5, cos.columns.max() + 0.5)
    ax.set_ylim(0, np.nanmax(cos.to_numpy()) * 1.28)
    ax.legend(loc="upper left", ncol=4)
    return _guardar(fig, ruta)


def score_desempeno(sc, ruta: Path) -> Path:
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(ANCHO, 2.7), gridspec_kw={"wspace": 0.3})
    cal = sc.calificaciones
    x = np.arange(len(cal))
    a1.bar(x, cal["tasa_observada"], color=AZUL, width=0.6, zorder=3, label="Tasa de malos observada")
    a1.plot(x, cal["pd_modelo"], color=NARANJA, marker="o", ms=4, lw=1.6, zorder=4, label="PD del modelo")
    a1.set_xticks(x, cal.index)
    a1.yaxis.set_major_formatter(FMT_PCT0)
    a1.set_title("Calibración por calificación")
    a1.legend(loc="upper left")
    a1.grid(axis="x", visible=False)
    m = sc.muestra
    for nombre, color in [("Desarrollo", AZUL), ("Fuera de tiempo", NARANJA)]:
        g = m[m["muestra"] == nombre].sort_values("pd_orig", ascending=False)
        y = g["malo"].to_numpy()
        tpr = np.concatenate([[0], np.cumsum(y) / y.sum()])
        fpr = np.concatenate([[0], np.cumsum(1 - y) / (1 - y).sum()])
        a2.plot(fpr, tpr, color=color, lw=1.8, label=f"{nombre} (Gini {num(100 * sc.metricas[nombre]['gini'], 0)}%)")
    a2.plot([0, 1], [0, 1], color=TENUE, lw=0.8, ls="--")
    a2.set_title("Curva ROC")
    a2.set_xlabel("% de buenos rechazados")
    a2.set_ylabel("% de malos detectados")
    a2.xaxis.set_major_formatter(FMT_PCT0)
    a2.yaxis.set_major_formatter(FMT_PCT0)
    a2.legend(loc="lower right")
    return _guardar(fig, ruta)


def provisiones_producto(tabla: pd.DataFrame, registrada: float, ruta: Path) -> Path:
    fig, ax = plt.subplots(figsize=(ANCHO, 2.5))
    x = np.arange(len(tabla))
    ax.bar(x - 0.18, tabla["ecl"] / 1e6, width=0.36, color=AZUL, zorder=3, label="Pérdida esperada NIIF 9")
    ax.bar(x + 0.18, tabla["ref"] / 1e6, width=0.36, color=NARANJA, zorder=3, label="Referencia por altura de mora")
    for xi, v in zip(x, tabla["ecl"] / 1e6):
        ax.text(xi - 0.18, v, num(v), ha="center", va="bottom", fontsize=7, color=TINTA)
    for xi, v in zip(x, tabla["ref"] / 1e6):
        ax.text(xi + 0.18, v, num(v), ha="center", va="bottom", fontsize=7, color=TINTA)
    ax.set_xticks(x, tabla.index)
    ax.yaxis.set_major_formatter(FMT_MILES)
    ax.set_ylabel("COP millones")
    ax.set_title("Provisión por producto")
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper right")
    ax.set_ylim(0, max((tabla["ecl"] / 1e6).max(), (tabla["ref"] / 1e6).max()) * 1.2)
    return _guardar(fig, ruta)


def estres_inverso(curva: pd.DataFrame, tabla: pd.DataFrame, umbral: float, ruta: Path) -> Path:
    fig, ax = plt.subplots(figsize=(ANCHO, 2.6))
    c = curva[curva["mult_pd"] <= 4]
    ax.plot(c["mult_pd"], c["pct_patrimonio"], color=AZUL, lw=2, zorder=3, label="Solo multiplicador de PD")
    for k, (_, e) in enumerate(tabla.iterrows()):
        ax.scatter([e["mult_pd"]], [e["pct_patrimonio"]], color=AZUL_OSCURO, s=28, zorder=4,
                   label="Escenarios de la política (PD y LGD)" if k == 0 else None)
        ax.annotate(e["escenario"], (e["mult_pd"], e["pct_patrimonio"]), xytext=(6, -10),
                    textcoords="offset points", fontsize=7.5, color=TINTA)
    ax.set_ylim(0, max(c["pct_patrimonio"].max(), umbral) * 1.15)
    _umbral(ax, umbral, "límite de la política", CRITICO)
    ax.set_xlabel("Multiplicador de la PD")
    ax.yaxis.set_major_formatter(FMT_PCT0)
    ax.set_title("Provisión adicional como % del patrimonio")
    ax.legend(loc="lower right")
    return _guardar(fig, ruta)


def recuperaciones(curva: pd.DataFrame, ruta: Path) -> Path:
    fig, ax = plt.subplots(figsize=(ANCHO, 2.4))
    colores = [AZUL, NARANJA, AZUL_OSCURO, TENUE]
    for col, c in zip([k for k in curva.columns if k != "Toda la cartera"], colores):
        ax.plot(curva.index, curva[col], color=c, lw=1.8, label=col)
    ax.set_title("Recuperación acumulada después del incumplimiento (% del saldo incumplido)")
    ax.set_xlabel("Meses desde el incumplimiento")
    ax.yaxis.set_major_formatter(FMT_PCT0)
    ax.set_ylim(0, None)
    ax.legend(loc="upper left")
    return _guardar(fig, ruta)


def originacion(des: pd.DataFrame, ev: pd.DataFrame, ruta: Path, meses: int = 24) -> Path:
    d = des.tail(meses)
    fig, ax = plt.subplots(figsize=(ANCHO, 2.5))
    x = np.arange(len(d))
    ax.bar(x, d["monto"] / 1e6, color=AZUL, width=0.7, zorder=3)
    ax.set_xticks(x[::3], [fecha_corta(m) for m in d.index[::3]])
    ax.yaxis.set_major_formatter(FMT_MILES)
    ax.set_ylabel("COP millones")
    ax.set_title("Desembolsos mensuales")
    ax.grid(axis="x", visible=False)
    return _guardar(fig, ruta)


def cobertura_deuda(hist: pd.DataFrame, limites: pd.DataFrame, ruta: Path) -> Path:
    """Proporción de la cartera que cumple el criterio de elegibilidad del fondeador."""
    fig, ax = plt.subplots(figsize=(ANCHO, 2.0))
    x = np.arange(len(hist))
    ax.plot(x, hist["pct_elegible"], color=AZUL, lw=2, marker="o", ms=3, zorder=3)
    ax.set_ylim(hist["pct_elegible"].min() - 0.05, min(hist["pct_elegible"].max() + 0.03, 1.0))
    ax.set_xticks(x[::2], [fecha_corta(m) for m in hist.index[::2]])
    ax.yaxis.set_major_formatter(FMT_PCT0)
    ax.annotate(num(100 * hist["pct_elegible"].iloc[-1], 1) + "%", (x[-1], hist["pct_elegible"].iloc[-1]),
                xytext=(4, 6), textcoords="offset points", fontsize=7.5, color=TINTA)
    ax.set_title("Cartera elegible como % de la cartera bruta")
    return _guardar(fig, ruta)


def cascada_excedente(fon: dict, ruta: Path) -> Path:
    pasos = [("Rendimiento\ncartera al día", fon["rendimiento"]), ("Comisiones", fon["comisiones"]),
             ("Costo del\nfondeo", -fon["costo_fondeo"]), ("Gastos\noperativos", -fon["opex"]),
             ("Pérdida\nesperada", -fon["perdida_esperada"])]
    fig, ax = plt.subplots(figsize=(ANCHO, 2.3))
    nivel = 0.0
    for i, (n, v) in enumerate(pasos):
        ax.bar(i, abs(v), bottom=nivel if v >= 0 else nivel + v, color=AZUL if v >= 0 else NARANJA, width=0.6,
               zorder=3)
        ax.text(i, max(nivel, nivel + v) + 0.004, ("+" if v >= 0 else "-") + num(100 * abs(v), 1) + "%",
                ha="center", fontsize=7.5, color=TINTA)
        nivel += v
    i = len(pasos)
    ax.bar(i, nivel, color=AZUL_OSCURO if nivel >= 0 else CRITICO, width=0.6, zorder=3)
    ax.text(i, max(nivel, 0) + 0.004, num(100 * nivel, 1) + "%", ha="center", fontsize=8, color=TINTA,
            fontweight="bold")
    ax.set_xticks(range(i + 1), [p[0] for p in pasos] + ["Excedente"])
    ax.axhline(0, color=BASE, lw=0.8)
    ax.yaxis.set_major_formatter(FMT_PCT0)
    ax.set_title("Excedente financiero anual (% de la cartera bruta)")
    ax.grid(axis="x", visible=False)
    return _guardar(fig, ruta)


def generar(r: dict, carpeta: Path) -> dict:
    carpeta.mkdir(parents=True, exist_ok=True)
    g = {}
    g["mora"] = evolucion_mora(r["evolucion"], r["limites"], carpeta / "01_evolucion_mora.png")
    g["cosechas"] = cosechas(r["cosechas30"], carpeta / "02_cosechas.png",
                             "Créditos que alguna vez superaron 30 días de mora, por trimestre de desembolso")
    g["score"] = score_desempeno(r["score"], carpeta / "03_score.png")
    from .niif9 import por_producto
    g["provisiones"] = provisiones_producto(por_producto(r["niif9"]), r["entidad"]["prov_registrada"],
                                            carpeta / "04_provisiones.png")
    g["estres"] = estres_inverso(r["estres"]["curva"], r["estres"]["tabla"], r["estres"]["inverso"]["umbral_patrimonio"],
                                 carpeta / "05_estres.png")
    g["recuperaciones"] = recuperaciones(r["niif9"].curva_recuperacion, carpeta / "06_recuperaciones.png")
    g["originacion"] = originacion(r["desembolsos"], r["evolucion"], carpeta / "07_originacion.png")
    g["cobertura"] = cobertura_deuda(r["fondeo"]["historia"], r["limites"], carpeta / "08_cobertura_deuda.png")
    g["excedente"] = cascada_excedente(r["fondeo"], carpeta / "09_excedente.png")
    return g
