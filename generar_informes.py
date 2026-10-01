"""
Motor de riesgo de crédito para entidades pequeñas.

Uso:
  python generar_informes.py                     procesa todas las entidades de entrada/
  python generar_informes.py --perfil fintech    solo una carpeta de entrada/
  python generar_informes.py --corte 2026-09-30  fija la fecha de corte
  python generar_informes.py --debug             muestra el detalle técnico de un error

Cada subcarpeta de entrada/ es una entidad con sus tres archivos:
originaciones.csv, desempeno.csv y politica_credito.xlsx.
"""
from __future__ import annotations

import argparse
import sys
import traceback

import pandas as pd

from credito import config as C
from credito.lectura import ErrorEntrada
from credito.utilidades import millones, num, pct


def main() -> int:
    ap = argparse.ArgumentParser(description="Genera los informes de riesgo de crédito.")
    ap.add_argument("--perfil", default="todos", help="carpeta dentro de entrada/ (o 'todos')")
    ap.add_argument("--corte", default=None, help="fecha de corte AAAA-MM-DD (por defecto, el último mes del archivo)")
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    if not C.DIR_ENTRADA.exists():
        print("No existe la carpeta 'entrada'. Para la demostración ejecute primero:\n"
              "  python herramientas/generar_datos_demo.py")
        return 1
    carpetas = sorted(p for p in C.DIR_ENTRADA.iterdir() if p.is_dir() and (p / C.ARCHIVO_POLITICA).exists())
    if a.perfil != "todos":
        carpetas = [p for p in carpetas if p.name == a.perfil]
    if not carpetas:
        print(f"No se encontraron entidades en {C.DIR_ENTRADA} (cada una necesita {C.ARCHIVO_POLITICA}).")
        return 1
    corte = pd.Timestamp(a.corte) + pd.offsets.MonthEnd(0) if a.corte else None
    errores = 0
    for carpeta in carpetas:
        print(f"\n=== {carpeta.name} ===")
        try:
            from credito import proceso
            r = proceso.generar(carpeta, corte)
        except ErrorEntrada as e:
            print(f"  ERROR: {e}")
            errores += 1
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  ERROR INESPERADO: {e}")
            if a.debug:
                traceback.print_exc()
            else:
                print("  Repita con --debug para ver el detalle técnico.")
            errores += 1
            continue
        ind, n = r["indicadores"], r["limites"]["estado"].value_counts()
        print(f"  {r['entidad']['nombre']} | corte {r['corte']:%Y-%m-%d}")
        print(f"  Cartera {millones(r['foto']['cartera'])} | ICV30 {pct(ind['ICV_30'])} | ECL NIIF 9 "
              f"{millones(r['niif9'].ecl)} | límites: {n.get('ROJO', 0)} rojo, {n.get('ÁMBAR', 0)} ámbar, "
              f"{n.get('VERDE', 0)} verde")
        for k, ruta in r["archivos_salida"].items():
            print(f"  -> {ruta.relative_to(C.RAIZ)}")
        print(f"  ({num(r['traza']['segundos'], 1)} segundos)")
    return 1 if errores else 0


if __name__ == "__main__":
    sys.exit(main())
