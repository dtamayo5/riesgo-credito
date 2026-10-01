"""Utilidades transversales: normalización de texto, formatos colombianos,
registro de hallazgos de calidad de datos y trazabilidad."""
from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
                "oct", "nov", "dic"]


# ---------------------------------------------------------------- texto ----
def sin_tildes(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def normalizar(texto) -> str:
    """'Fecha de Vencimiento (dd/mm)' -> 'fecha de vencimiento dd mm'."""
    if texto is None or (isinstance(texto, float) and math.isnan(texto)):
        return ""
    s = sin_tildes(str(texto)).lower()
    s = re.sub(r"[^a-z0-9+]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def texto_pdf(texto: str) -> str:
    """Reemplaza caracteres que las fuentes estándar del PDF no dibujan."""
    reemplazos = {"≈": "aprox.", "≥": ">=", "≤": "<=", "√": "raíz de ",
                  "→": "->", "×": "x", "−": "-", "…": "...", " ": " "}
    for a, b in reemplazos.items():
        texto = texto.replace(a, b)
    return texto


# -------------------------------------------------------------- formatos ----
def num(x, dec: int = 0) -> str:
    """Formato colombiano: miles con punto y decimales con coma."""
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "-"
    s = f"{x:,.{dec}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, dec: int = 1) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "-"
    return num(100 * x, dec) + "%"


def millones(x_pesos, dec: int = 0) -> str:
    """Pesos -> 'COP 1.234 M'."""
    if x_pesos is None or (isinstance(x_pesos, float) and math.isnan(x_pesos)):
        return "-"
    return f"COP {num(x_pesos / 1e6, dec)} M"


def fecha_larga(f) -> str:
    f = pd.Timestamp(f)
    return f"{f.day} de {MESES[f.month - 1]} de {f.year}"


def fecha_corta(f) -> str:
    f = pd.Timestamp(f)
    return f"{MESES_CORTOS[f.month - 1]}-{str(f.year)[2:]}"


def sha256(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as fh:
        for bloque in iter(lambda: fh.read(65536), b""):
            h.update(bloque)
    return h.hexdigest()


# ------------------------------------------------------ calidad de datos ----
SEVERIDADES = ("ERROR", "ADVERTENCIA", "INFO")


@dataclass
class Hallazgos:
    """Bitácora de calidad de datos. Cada hallazgo apunta a la hoja y fila de
    Excel exactas, para que el analista pueda corregir el origen."""
    registros: list = field(default_factory=list)

    def agregar(self, severidad: str, hoja: str, fila, campo: str, valor,
                detalle: str, accion: str = "") -> None:
        assert severidad in SEVERIDADES
        if valor is not None and not isinstance(valor, str):
            valor = "" if (isinstance(valor, float) and math.isnan(valor)) else str(valor)
        self.registros.append({
            "severidad": severidad, "hoja": hoja,
            "fila_excel": int(fila) if fila not in (None, "") else None,
            "campo": campo, "valor_original": (valor or "")[:60],
            "detalle": detalle, "accion": accion,
        })

    def tabla(self) -> pd.DataFrame:
        cols = ["severidad", "hoja", "fila_excel", "campo", "valor_original",
                "detalle", "accion"]
        if not self.registros:
            return pd.DataFrame(columns=cols)
        orden = {s: i for i, s in enumerate(SEVERIDADES)}
        df = pd.DataFrame(self.registros, columns=cols)
        df["_o"] = df["severidad"].map(orden)
        df["_f"] = df["fila_excel"].fillna(0)
        return df.sort_values(["_o", "hoja", "_f"]).drop(columns=["_o", "_f"]).reset_index(drop=True)

    def conteo(self, severidad: str) -> int:
        return sum(1 for r in self.registros if r["severidad"] == severidad)
