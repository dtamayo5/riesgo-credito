"""
Lectura y validación de los archivos del cliente.

Entradas por entidad (carpeta entrada/<perfil>/):
  originaciones   un registro por crédito con los datos de la solicitud
  desempeno       un registro por crédito y mes (saldo, días de mora, estado, recuperaciones)
  politica_credito.xlsx  parámetros de negocio aprobados por la entidad

Cada corrección queda en la bitácora de hallazgos con el archivo y la fila,
para que el área dueña del dato corrija el origen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .utilidades import Hallazgos, normalizar, num, sha256


class ErrorEntrada(Exception):
    """Error que impide procesar: se muestra al usuario sin traza técnica."""


@dataclass
class Datos:
    perfil: str
    carpeta: Path
    corte: pd.Timestamp
    org: pd.DataFrame
    des: pd.DataFrame
    entidad: dict
    limites: pd.DataFrame
    matriz: pd.DataFrame
    escenarios: pd.DataFrame
    hallazgos: Hallazgos
    huellas: dict = field(default_factory=dict)
    variables_num: list = field(default_factory=list)
    variables_cat: list = field(default_factory=list)


# ---------------------------------------------------------------- utilidades
def _buscar(carpeta: Path, nombres: list[str]) -> Path:
    for n in nombres:
        if (carpeta / n).exists():
            return carpeta / n
    raise ErrorEntrada(f"No se encontró {' ni '.join(nombres)} en {carpeta}")


def _leer_tabla(ruta: Path) -> pd.DataFrame:
    try:
        if ruta.suffix.lower() == ".csv":
            df = pd.read_csv(ruta, encoding="utf-8-sig", sep=None, engine="python") \
                if ruta.stat().st_size < 2e5 else pd.read_csv(ruta, encoding="utf-8-sig")
        else:
            df = pd.read_excel(ruta)
    except PermissionError:
        raise ErrorEntrada(f"No se pudo abrir {ruta.name}: ciérrelo en Excel y repita.")
    df["fila"] = np.arange(len(df)) + 2       # fila del archivo (la 1 es el encabezado)
    return df


def _renombrar(df: pd.DataFrame, alias: dict, archivo: str, obligatorias: list[str]) -> pd.DataFrame:
    mapa = {}
    norm = {normalizar(c): c for c in df.columns}
    for interno, opciones in alias.items():
        for o in [interno.replace("_", " ")] + opciones:
            if o in norm and norm[o] not in mapa:
                mapa[norm[o]] = interno
                break
    df = df.rename(columns=mapa)
    faltan = [c for c in obligatorias if c not in df.columns]
    if faltan:
        raise ErrorEntrada(f"{archivo}: faltan las columnas {', '.join(faltan)}. "
                           f"Agregue el nombre que usa la entidad como alias en credito/config.py.")
    df.columns = [normalizar(c).replace(" ", "_") if c not in alias and c != "fila" else c for c in df.columns]
    return df


def _grupo(h: Hallazgos, sev: str, archivo: str, filas, campo: str, valores, detalle: str, accion: str):
    """Registra un hallazgo por fila si son pocos, o uno agregado si son muchos."""
    filas = list(filas)
    valores = [num(v, 0) if isinstance(v, (int, float, np.integer, np.floating)) and not pd.isna(v)
               and float(v) == int(v) else v for v in valores]
    if not filas:
        return
    if len(filas) <= 5:
        for f, v in zip(filas, valores):
            h.agregar(sev, archivo, f, campo, v, detalle, accion)
    else:
        muestra = ", ".join(str(f) for f in filas[:5])
        h.agregar(sev, archivo, filas[0], campo, valores[0],
                  f"{detalle} ({len(filas)} filas; primeras: {muestra})", accion)


def _a_fecha(s: pd.Series) -> pd.Series:
    f = pd.to_datetime(s, errors="coerce", dayfirst=False, format="mixed")
    malas = f.isna() & s.notna()
    if malas.any():
        f[malas] = pd.to_datetime(s[malas], errors="coerce", dayfirst=True, format="mixed")
    return f


# ------------------------------------------------------------- originaciones
def leer_originaciones(ruta: Path, corte: pd.Timestamp, h: Hallazgos):
    nombre = ruta.name
    df = _renombrar(_leer_tabla(ruta), C.COLUMNAS_ORIGINACIONES, nombre,
                    ["id", "fecha_desembolso", "producto", "monto", "plazo_meses", "tasa_ea"])
    df["id"] = df["id"].astype(str).str.strip()
    dup = df.duplicated("id", keep="first")
    _grupo(h, "ERROR", nombre, df.loc[dup, "fila"], "id", df.loc[dup, "id"],
           "Crédito repetido", "Se conserva el primer registro")
    df = df[~dup].copy()

    df["fecha_desembolso"] = _a_fecha(df["fecha_desembolso"])
    for c in ["monto", "plazo_meses", "tasa_ea"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    malos = df["fecha_desembolso"].isna() | (df["fecha_desembolso"] > corte)
    _grupo(h, "ERROR", nombre, df.loc[malos, "fila"], "fecha_desembolso", df.loc[malos, "fecha_desembolso"],
           "Fecha de desembolso vacía o posterior al corte", "Crédito excluido")
    malos2 = ~malos & ((df["monto"] <= 0) | df["monto"].isna() | (df["plazo_meses"] <= 0) | df["plazo_meses"].isna())
    _grupo(h, "ERROR", nombre, df.loc[malos2, "fila"], "monto/plazo", df.loc[malos2, "monto"],
           "Monto o plazo vacío o no positivo", "Crédito excluido")
    df = df[~malos & ~malos2].copy()

    # tasas escritas en porcentaje (24,5 en lugar de 0,245)
    enpct = df["tasa_ea"] > 1
    _grupo(h, "ADVERTENCIA", nombre, df.loc[enpct, "fila"], "tasa_ea", df.loc[enpct, "tasa_ea"],
           "Tasa escrita en porcentaje", "Se divide entre 100")
    df.loc[enpct, "tasa_ea"] = df.loc[enpct, "tasa_ea"] / 100
    if "id_deudor" not in df.columns:
        df["id_deudor"] = df["id"]
        h.agregar("INFO", nombre, None, "id_deudor", "", "No viene identificación del deudor",
                  "La concentración se mide por crédito")

    num = [v for v in C.VARIABLES_NUMERICAS if v in df.columns]
    cat = [v for v in C.VARIABLES_CATEGORICAS if v in df.columns]
    for v in num:
        df[v] = pd.to_numeric(df[v], errors="coerce")
        if v in C.RANGOS_VALIDOS:
            lo, hi = C.RANGOS_VALIDOS[v]
            fuera = df[v].notna() & ((df[v] < lo) | (df[v] > hi))
            _grupo(h, "ADVERTENCIA", nombre, df.loc[fuera, "fila"], v, df.loc[fuera, v],
                   f"Valor fuera del rango posible ({lo:g} a {hi:g})", "Se imputa la mediana")
            df.loc[fuera, v] = np.nan
        else:
            fuera = pd.Series(False, index=df.index)
        vac = df[v].isna() & ~fuera
        if vac.any():
            mediana = df[v].median()
            _grupo(h, "ADVERTENCIA", nombre, df.loc[vac, "fila"], v, [""] * int(vac.sum()),
                   "Dato faltante", f"Se imputa la mediana ({mediana:,.0f})".replace(",", "."))
            df.loc[vac | fuera, v] = mediana
        elif fuera.any():
            df.loc[fuera, v] = df[v].median()
    for v in cat:
        vac = df[v].isna() | (df[v].astype(str).str.strip() == "")
        _grupo(h, "ADVERTENCIA", nombre, df.loc[vac, "fila"], v, [""] * int(vac.sum()),
               "Dato faltante", "Se asigna la categoría 'Sin dato'")
        df[v] = df[v].astype(str).str.strip().where(~vac, "Sin dato")
    df["producto"] = df["producto"].astype(str).str.strip()
    df["mes_desembolso"] = df["fecha_desembolso"] + pd.offsets.MonthEnd(0)
    return df.reset_index(drop=True), num, cat


# ----------------------------------------------------------------- desempeño
def leer_desempeno(ruta: Path, org: pd.DataFrame, corte: pd.Timestamp, h: Hallazgos) -> pd.DataFrame:
    nombre = ruta.name
    df = _renombrar(_leer_tabla(ruta), C.COLUMNAS_DESEMPENO, nombre, ["id", "mes", "saldo_capital", "dias_mora"])
    df["id"] = df["id"].astype(str).str.strip()
    df["mes"] = _a_fecha(df["mes"])
    if (df["mes"] != df["mes"] + pd.offsets.MonthEnd(0)).any():
        h.agregar("INFO", nombre, None, "mes", "", "Fechas de corte que no son fin de mes",
                  "Se llevan al último día del mes")
    df["mes"] = df["mes"] + pd.offsets.MonthEnd(0)
    for c in ["saldo_capital", "dias_mora"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "recuperacion_mes" not in df.columns:
        df["recuperacion_mes"] = 0.0
        h.agregar("ADVERTENCIA", nombre, None, "recuperacion_mes", "", "No vienen recuperaciones",
                  "La LGD usará el supuesto de la política")
    df["recuperacion_mes"] = pd.to_numeric(df["recuperacion_mes"], errors="coerce").fillna(0)
    if "estado" not in df.columns:
        df["estado"] = "Vigente"
    df["estado"] = df["estado"].map(lambda x: C.ESTADOS.get(normalizar(x), "Vigente"))

    cols_clave = ["id", "mes", "saldo_capital", "dias_mora", "estado", "recuperacion_mes"]
    dup = df.duplicated(cols_clave, keep="first")
    _grupo(h, "ADVERTENCIA", nombre, df.loc[dup, "fila"], "id/mes", df.loc[dup, "id"],
           "Registro duplicado (mismo crédito, mes y valores)", "Se elimina la copia")
    df = df[~dup]
    dup2 = df.duplicated(["id", "mes"], keep="last")
    _grupo(h, "ERROR", nombre, df.loc[dup2, "fila"], "id/mes", df.loc[dup2, "id"],
           "Dos registros distintos para el mismo crédito y mes", "Se conserva el último")
    df = df[~dup2]

    sin_org = ~df["id"].isin(org["id"])
    if sin_org.any():
        _grupo(h, "ERROR", nombre, df.loc[sin_org, "fila"], "id", df.loc[sin_org, "id"],
               "Crédito sin registro de originación", "Registro excluido")
    fuera = df["mes"].isna() | (df["mes"] > corte)
    _grupo(h, "ERROR", nombre, df.loc[fuera & ~sin_org, "fila"], "mes", df.loc[fuera & ~sin_org, "mes"],
           "Mes vacío o posterior al corte", "Registro excluido")
    df = df[~sin_org & ~fuera].copy()

    neg = df["saldo_capital"] < 0
    _grupo(h, "ADVERTENCIA", nombre, df.loc[neg, "fila"], "saldo_capital", df.loc[neg, "saldo_capital"],
           "Saldo negativo (probable error de signo)", "Se toma el valor absoluto; confirmar con contabilidad")
    df["saldo_capital"] = df["saldo_capital"].abs().fillna(0)
    mneg = df["dias_mora"].isna() | (df["dias_mora"] < 0)
    _grupo(h, "ADVERTENCIA", nombre, df.loc[mneg, "fila"], "dias_mora", df.loc[mneg, "dias_mora"],
           "Días de mora vacíos o negativos", "Se asume al día")
    df.loc[mneg, "dias_mora"] = 0
    df["dias_mora"] = df["dias_mora"].astype(int)
    return df.drop(columns=[c for c in df.columns if c not in cols_clave + ["fila"]]) \
             .sort_values(["id", "mes"]).reset_index(drop=True)


# ------------------------------------------------------------------ política
def _hoja(ruta: Path, nombre: str) -> pd.DataFrame:
    try:
        crudo = pd.read_excel(ruta, sheet_name=nombre, header=None)
    except ValueError:
        raise ErrorEntrada(f"{ruta.name}: falta la hoja '{nombre}'.")
    except PermissionError:
        raise ErrorEntrada(f"No se pudo abrir {ruta.name}: ciérrelo en Excel y repita.")
    fila_enc = crudo.notna().sum(axis=1).ne(0).idxmax()
    for i in range(min(10, len(crudo))):
        if crudo.iloc[i].notna().sum() >= 2:
            fila_enc = i
            break
    df = crudo.iloc[fila_enc + 1:].copy()
    df.columns = [normalizar(c).replace(" ", "_") for c in crudo.iloc[fila_enc]]
    return df.dropna(how="all").reset_index(drop=True)


def leer_politica(ruta: Path) -> tuple[dict, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ent = _hoja(ruta, "Entidad")
    v = {normalizar(p): val for p, val in zip(ent["parametro"], ent["valor"])}

    def tomar(clave_parcial, defecto=None, numero=True):
        for k, val in v.items():
            if k.startswith(clave_parcial):
                if numero:
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return defecto
                return val
        return defecto

    entidad = {
        "nombre": tomar("nombre", "Entidad", numero=False),
        "tipo": tomar("tipo de entidad", "", numero=False),
        "patrimonio": tomar("patrimonio", 0.0) * 1e6,
        "deuda": tomar("deuda con fondeadores", 0.0) * 1e6,
        "costo_fondeo": tomar("costo promedio del fondeo", tomar("tasa de fondeo", 0.0)),
        "comisiones": tomar("comisiones", 0.0),
        "anticipo": tomar("tasa de anticipo", 0.8),
        "opex": tomar("gastos operativos", 0.0),
        "dias_elegible": int(tomar("dias de mora maximos", 30)),
        "prov_general": tomar("provision general", 0.0),
        "prov_registrada": (tomar("provision registrada", np.nan) or np.nan) * 1e6,
        "demo": normalizar(tomar("modo demostracion", "No", numero=False)) in ("si", "s", "yes", "1"),
    }
    lim = _hoja(ruta, "Limites")
    lim = lim.rename(columns={"codigo": "codigo", "tipo_de_limite": "tipo"})
    lim["limite"] = pd.to_numeric(lim["limite"], errors="coerce")
    lim["alerta"] = pd.to_numeric(lim["alerta"], errors="coerce")
    mat = _hoja(ruta, "Matriz_provision")
    for c in ["dias_desde", "dias_hasta", "provision"]:
        mat[c] = pd.to_numeric(mat[c], errors="coerce")
    esc = _hoja(ruta, "Escenarios")
    esc = esc.rename(columns={"multiplicador_pd": "mult_pd", "ajuste_lgd_pp": "ajuste_lgd"})
    for c in ["peso", "mult_pd", "ajuste_lgd"]:
        esc[c] = pd.to_numeric(esc[c], errors="coerce")
    pesos = esc.loc[esc["uso"].map(normalizar) == "niif 9", "peso"]
    if abs(pesos.sum() - 1) > 1e-6:
        raise ErrorEntrada(f"{ruta.name}: los pesos de los escenarios NIIF 9 suman {pesos.sum():.2f}; deben sumar 1.")
    return entidad, lim, mat, esc


# ------------------------------------------------------------------- todo
def leer_entidad(carpeta: Path, corte: pd.Timestamp | None = None) -> Datos:
    h = Hallazgos()
    r_org = _buscar(carpeta, C.ARCHIVOS_ORIGINACIONES)
    r_des = _buscar(carpeta, C.ARCHIVOS_DESEMPENO)
    r_pol = _buscar(carpeta, [C.ARCHIVO_POLITICA])
    entidad, lim, mat, esc = leer_politica(r_pol)
    if corte is None:
        meses = pd.read_csv(r_des, usecols=[0, 1], encoding="utf-8-sig").iloc[:, 1] \
            if r_des.suffix == ".csv" else pd.read_excel(r_des, usecols=[0, 1]).iloc[:, 1]
        corte = _a_fecha(meses).max() + pd.offsets.MonthEnd(0)
    org, num, cat = leer_originaciones(r_org, corte, h)
    des = leer_desempeno(r_des, org, corte, h)
    if not (des["mes"] == corte).any():
        raise ErrorEntrada(f"El archivo de desempeño no trae registros del corte {corte.date()}.")
    huellas = {r.name: sha256(r) for r in (r_org, r_des, r_pol)}
    return Datos(carpeta.name, carpeta, corte, org, des, entidad, lim, mat, esc, h, huellas, num, cat)
