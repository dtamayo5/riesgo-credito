"""
Analítica de cartera: foto al corte, evolución mensual, cosechas, rodamientos
y concentración.

Convenciones:
  - Cartera bruta = saldo de capital de los créditos vigentes (incluye los que
    están en mora y aún no se castigan).
  - ICV30 / ICV90 = saldo con más de 30 / 90 días de mora sobre cartera bruta
    (indicador de calidad por altura de mora, como lo reporta el sector).
  - MOB (months on book) = meses desde el desembolso.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def tramo(dias: pd.Series) -> pd.Series:
    etiquetas = [t[0] for t in C.TRAMOS_MORA]
    limites = [-np.inf] + [t[2] for t in C.TRAMOS_MORA]
    return pd.cut(dias, bins=limites, labels=etiquetas).astype(str)


def _mesnum(f: pd.Series) -> pd.Series:
    return f.dt.year * 12 + f.dt.month


def panel(datos) -> pd.DataFrame:
    """Desempeño enriquecido con los datos de originación."""
    cols = ["id", "id_deudor", "producto", "fecha_desembolso", "mes_desembolso", "monto", "plazo_meses", "tasa_ea"]
    cols += [c for c in ("region",) if c in datos.org.columns]
    p = datos.des.merge(datos.org[cols], on="id", how="left")
    p["mob"] = _mesnum(p["mes"]) - _mesnum(p["mes_desembolso"])
    p["vivo"] = (p["estado"] == "Vigente") & (p["saldo_capital"] > 0)
    p["tramo"] = tramo(p["dias_mora"])
    return p


def foto(p: pd.DataFrame, mes) -> pd.DataFrame:
    return p[(p["mes"] == mes) & p["vivo"]].copy()


def resumen_foto(f: pd.DataFrame, dias_elegible: int = 30) -> dict:
    total = f["saldo_capital"].sum()
    s30 = f.loc[f["dias_mora"] > 30, "saldo_capital"].sum()
    s90 = f.loc[f["dias_mora"] > 90, "saldo_capital"].sum()
    eleg = f.loc[f["dias_mora"] <= dias_elegible, "saldo_capital"].sum()
    al_dia = f.loc[f["dias_mora"] <= 30]
    tasa = np.average(al_dia["tasa_ea"], weights=al_dia["saldo_capital"]) if len(al_dia) else np.nan
    return {"cartera": total, "n_creditos": int(len(f)), "saldo_30": s30, "saldo_90": s90,
            "icv30": s30 / total if total else np.nan, "icv90": s90 / total if total else np.nan,
            "elegible": eleg, "tasa_promedio": tasa,
            "ticket_promedio": total / len(f) if len(f) else np.nan}


def por_producto(f: pd.DataFrame) -> pd.DataFrame:
    g = f.groupby("producto").agg(creditos=("id", "size"), saldo=("saldo_capital", "sum"),
                                  tasa=("tasa_ea", lambda s: np.average(s, weights=f.loc[s.index, "saldo_capital"])))
    g["participacion"] = g["saldo"] / g["saldo"].sum()
    g["icv30"] = f[f["dias_mora"] > 30].groupby("producto")["saldo_capital"].sum().reindex(g.index).fillna(0) / g["saldo"]
    g["icv90"] = f[f["dias_mora"] > 90].groupby("producto")["saldo_capital"].sum().reindex(g.index).fillna(0) / g["saldo"]
    return g.sort_values("saldo", ascending=False)


def por_tramo(f: pd.DataFrame) -> pd.DataFrame:
    orden = [t[0] for t in C.TRAMOS_MORA]
    g = f.groupby("tramo").agg(creditos=("id", "size"), saldo=("saldo_capital", "sum")).reindex(orden).fillna(0)
    g["participacion"] = g["saldo"] / g["saldo"].sum()
    return g


# ------------------------------------------------------------- evolución
def evolucion(p: pd.DataFrame, org: pd.DataFrame, corte, meses: int, dias_elegible: int) -> pd.DataFrame:
    """Serie mensual: cartera, ICV, desembolsos, castigos, recuperaciones."""
    todos = sorted(p["mes"].unique())
    todos = [m for m in todos if m <= corte][-meses:]
    # castigo: el primer mes en que el crédito aparece como castigado; monto = saldo del mes anterior
    prim_cast = p[p["estado"] == "Castigado"].groupby("id")["mes"].min()
    prev = p[["id", "mes", "saldo_capital"]].copy()
    prev["mes"] = prev["mes"] + pd.offsets.MonthEnd(1)
    cast = prim_cast.reset_index().merge(prev, on=["id", "mes"], how="left")
    castigos = cast.groupby("mes")["saldo_capital"].sum()
    desemb = org.groupby("mes_desembolso")["monto"].sum()
    recup = p.groupby("mes")["recuperacion_mes"].sum()
    filas = []
    for m in todos:
        r = resumen_foto(p[(p["mes"] == m) & p["vivo"]], dias_elegible)
        r.update({"mes": m, "desembolsos": desemb.get(m, 0.0), "castigos": castigos.get(m, 0.0),
                  "recuperaciones": recup.get(m, 0.0)})
        filas.append(r)
    ev = pd.DataFrame(filas).set_index("mes")
    # pérdida neta anualizada: (castigos - recuperaciones) de 12 meses / cartera promedio
    ev["perdida_neta_12m"] = ((ev["castigos"] - ev["recuperaciones"]).rolling(12, min_periods=1).sum()
                              / ev["cartera"].rolling(12, min_periods=1).mean())
    return ev


# --------------------------------------------------------------- cosechas
def cosechas(p: pd.DataFrame, org: pd.DataFrame, corte, umbral: int = 30, max_mob: int = 18) -> pd.DataFrame:
    """Curvas acumuladas: % de créditos de cada trimestre de desembolso que alguna
    vez superó `umbral` días de mora, por meses desde el desembolso (MOB)."""
    malo = p[p["dias_mora"] > umbral].groupby("id")["mob"].min()
    o = org[["id", "mes_desembolso"]].copy()
    o["trimestre"] = o["mes_desembolso"].dt.to_period("Q")
    o["mob_malo"] = o["id"].map(malo)
    corte_n = corte.year * 12 + corte.month
    filas = {}
    for q, g in o.groupby("trimestre"):
        ult = q.end_time.normalize() + pd.offsets.MonthEnd(0)
        mob_obs = corte_n - (ult.year * 12 + ult.month)       # MOB que ya cumplió todo el trimestre
        if mob_obs < 1:
            continue
        curva = {m: (g["mob_malo"] <= m).mean() if m <= mob_obs else np.nan for m in range(1, max_mob + 1)}
        filas[str(q)] = curva
    return pd.DataFrame(filas).T.rename_axis("cosecha")


def indicador_cosecha(cos: pd.DataFrame, mob: int = 6) -> tuple[str, float, float]:
    """Cosecha más reciente que ya cumplió `mob` meses, su valor y el promedio histórico."""
    validas = cos[cos[mob].notna()]
    if validas.empty:
        return "", np.nan, np.nan
    ultima = validas.index[-1]
    referencia = validas[mob].iloc[:-1].tail(8).mean()
    return ultima, float(validas[mob].iloc[-1]), float(referencia)


# ------------------------------------------------------------- rodamientos
ESTADOS_ROD = ["Al día", "1-30", "31-60", "61-90", "91+"]
DESTINOS_ROD = ESTADOS_ROD + ["Pagado", "Castigado"]


def rodamientos(p: pd.DataFrame, corte, meses: int = 6, por: str = "saldo") -> pd.DataFrame:
    """Matriz de transición mes a mes entre tramos de mora (promedio de los
    últimos `meses`). Fila = tramo del mes t; columna = destino en t+1.
    Ponderada por saldo (lo que se rueda en pesos) o por número de créditos."""
    todos = sorted(m for m in p["mes"].unique() if m <= corte)[-(meses + 1):]
    acum = pd.DataFrame(0.0, index=ESTADOS_ROD, columns=DESTINOS_ROD)
    for m0, m1 in zip(todos[:-1], todos[1:]):
        a = p[(p["mes"] == m0) & p["vivo"]][["id", "tramo", "saldo_capital"]]
        b = p[p["mes"] == m1][["id", "tramo", "estado", "saldo_capital"]].rename(
            columns={"tramo": "destino", "saldo_capital": "saldo1"})
        t = a.merge(b, on="id", how="left")
        t["destino"] = np.where(t["estado"].isna() | (t["estado"] == "Cancelado") |
                                ((t["estado"] == "Vigente") & (t["saldo1"] <= 0)), "Pagado",
                                np.where(t["estado"] == "Castigado", "Castigado", t["destino"]))
        w = t["saldo_capital"] if por == "saldo" else pd.Series(1.0, index=t.index)
        acum = acum.add(pd.crosstab(t["tramo"], t["destino"], values=w, aggfunc="sum")
                        .reindex(index=ESTADOS_ROD, columns=DESTINOS_ROD).fillna(0), fill_value=0)
    return acum.div(acum.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)


def flujo_a_mora(p: pd.DataFrame, corte, meses: int = 6) -> float:
    """Saldo promedio mensual que pasa de 0-30 días a 31-60 días (entrada a mora 30+)."""
    todos = sorted(m for m in p["mes"].unique() if m <= corte)[-(meses + 1):]
    flujos = []
    for m0, m1 in zip(todos[:-1], todos[1:]):
        a = p[(p["mes"] == m0) & p["vivo"] & (p["dias_mora"] <= 30)][["id"]]
        b = p[(p["mes"] == m1) & p["vivo"] & (p["dias_mora"] > 30)][["id", "saldo_capital"]]
        flujos.append(a.merge(b, on="id")["saldo_capital"].sum())
    return float(np.mean(flujos)) if flujos else 0.0


# ------------------------------------------------------------ concentración
def concentracion(f: pd.DataFrame) -> dict:
    total = f["saldo_capital"].sum()
    deud = f.groupby("id_deudor")["saldo_capital"].sum().sort_values(ascending=False)
    top20 = deud.head(20)
    prod = f.groupby("producto")["saldo_capital"].sum().sort_values(ascending=False) / total
    reg = (f.groupby("region")["saldo_capital"].sum().sort_values(ascending=False) / total
           if "region" in f.columns else pd.Series(dtype=float))
    hhi = float(((deud / total) ** 2).sum() * 10_000)
    return {"top20": float(top20.sum() / total), "mayor_deudor": float(deud.iloc[0] / total),
            "top20_tabla": top20, "producto": prod, "producto_max": float(prod.iloc[0]),
            "producto_max_nombre": prod.index[0], "region": reg, "hhi_deudores": hhi}
