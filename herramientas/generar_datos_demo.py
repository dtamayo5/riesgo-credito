"""
Genera las carteras de demostración (entidades ficticias, datos sintéticos):

  entrada/fintech/      Crédito Ágil Ejemplo S.A.S.  (consumo digital y microcrédito)
  entrada/cooperativa/  Cooperativa de Ahorro y Crédito Ejemplo (libranza, consumo, comercial pyme)

Cada carpeta trae lo mismo que entregaría un cliente real:
  originaciones.csv     un registro por crédito con los datos de la solicitud
  desempeno.csv         un registro por crédito y mes: saldo, días de mora, estado, recuperaciones
  politica_credito.xlsx parámetros de negocio: límites, matriz de provisión, escenarios, fondeo

La mora se simula como una cadena mensual (al día -> 1-30 -> 31-60 -> 61-90 -> 91+)
cuya probabilidad de entrada depende del perfil del deudor, de la maduración del
crédito y de un ciclo económico (deterioro en el primer semestre de 2026).

Uso:  python herramientas/generar_datos_demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

RAIZ = Path(__file__).resolve().parent.parent
CORTE = pd.Timestamp("2026-09-30")
MESES = pd.DatetimeIndex([pd.Timestamp(y, m, 1) + pd.offsets.MonthEnd(0)
                          for y, m in [(2023 + (9 + i) // 12, (9 + i) % 12 + 1) for i in range(36)]])
REGIONES = ["Antioquia", "Bogotá", "Valle", "Caribe", "Eje Cafetero", "Otras"]

PERFILES = {
    "fintech": {
        "nombre": "Crédito Ágil Ejemplo S.A.S.", "tipo": "Fintech de crédito (no vigilada)",
        "originaciones_mes": (420, 880), "semilla": 21,
        "productos": {  # nombre: (peso, monto mín/máx en millones, plazos, tasa EA, recuperación esperada)
            "Consumo digital": (0.75, (1.0, 8.0), [6, 9, 12, 18, 24], (0.235, 0.265), 0.22),
            "Microcrédito": (0.25, (2.0, 15.0), [6, 12, 18, 24], (0.42, 0.52), 0.30),
        },
        "intercepto": -2.35, "prepago": 0.022, "deriva_buro": 25, "roll": (0.42, 0.62),
        "patrimonio": 9_500, "deuda": 26_500, "tasa_fondeo": 0.165, "anticipo": 0.85, "opex": 0.09, "comisiones": 0.10,
        "prov_general": 0.0, "prov_registrada": 4_100,
        "estres": ((1.50, 0.04), (2.00, 0.08)),
    },
    "cooperativa": {
        "nombre": "Cooperativa de Ahorro y Crédito Ejemplo", "tipo": "Cooperativa de ahorro y crédito (vigilada por la Supersolidaria)",
        "originaciones_mes": (190, 260), "semilla": 33,
        "productos": {
            "Consumo libranza": (0.50, (8.0, 45.0), [24, 36, 48, 60], (0.165, 0.19), 0.62),
            "Consumo ordinario": (0.35, (3.0, 25.0), [12, 24, 36], (0.20, 0.245), 0.35),
            "Comercial pyme": (0.15, (30.0, 180.0), [12, 24, 36], (0.17, 0.21), 0.50),
        },
        "intercepto": -3.15, "prepago": 0.012, "deriva_buro": 0, "roll": (0.33, 0.55),
        "patrimonio": 46_000, "deuda": 60_000, "tasa_fondeo": 0.105, "anticipo": 0.80, "opex": 0.045, "comisiones": 0.01,
        "prov_general": 0.01, "prov_registrada": 5_200,
        "estres": ((1.60, 0.05), (2.50, 0.10)),
    },
}


def _ciclo(fecha: pd.Timestamp) -> float:
    """Factor macro sobre la entrada en mora (alzas de tasas de 2026)."""
    if pd.Timestamp("2026-01-01") <= fecha <= pd.Timestamp("2026-06-30"):
        return 1.40
    if pd.Timestamp("2026-07-01") <= fecha <= CORTE:
        return 1.15
    return 1.0


def _maduracion(mob: np.ndarray) -> np.ndarray:
    return np.select([mob <= 1, mob <= 3, mob <= 9, mob <= 15], [0.35, 0.9, 1.3, 1.0], 0.75)


def originar(perfil: dict, rng) -> pd.DataFrame:
    filas = []
    n_meses = len(MESES)
    ident = 100000
    for i, mes in enumerate(MESES):
        lo, hi = perfil["originaciones_mes"]
        n = int(lo + (hi - lo) * i / (n_meses - 1) * rng.uniform(0.9, 1.1))
        prods = list(perfil["productos"])
        pesos = np.array([perfil["productos"][p][0] for p in prods])
        prod = rng.choice(prods, n, p=pesos / pesos.sum())
        dia = rng.integers(1, 28, n)
        for k in range(n):
            p = prod[k]
            _, (mmin, mmax), plazos, (tmin, tmax), _ = perfil["productos"][p]
            ident += 1
            filas.append({
                "id": f"C{ident}", "fecha_desembolso": pd.Timestamp(mes.year, mes.month, int(dia[k])),
                "producto": p, "monto": round(rng.uniform(mmin, mmax) * 1e6, -4),
                "plazo_meses": int(rng.choice(plazos)), "tasa_ea": round(rng.uniform(tmin, tmax), 4),
            })
    df = pd.DataFrame(filas)
    n = len(df)
    libranza = (df["producto"] == "Consumo libranza").to_numpy()
    pyme = (df["producto"] == "Comercial pyme").to_numpy()
    df["edad"] = np.clip(rng.normal(38, 10, n), 19, 72).round().astype(int)
    df["ingreso_mensual"] = (np.exp(rng.normal(np.log(3.4e6), 0.5, n)) * np.where(pyme, 6, 1)).round(-3)
    df["antiguedad_laboral_meses"] = np.clip(rng.exponential(48, n), 1, 400).round().astype(int)
    df["puntaje_buro"] = np.clip(rng.normal(np.where(libranza, 700, 655), 95, n), 300, 950).round().astype(int)
    # deriva de población: desde oct-2025 la entidad crece aprobando perfiles de menor puntaje
    reciente = (df["fecha_desembolso"] >= "2025-10-01").to_numpy()
    df["puntaje_buro"] = np.clip(df["puntaje_buro"] - perfil["deriva_buro"] * reciente, 300, 950).astype(int)
    df["endeudamiento"] = np.clip(rng.beta(2.4, 4.5, n), 0.02, 0.92).round(3)
    df["vinculacion"] = np.where(libranza, rng.choice(["Empleado", "Pensionado"], n, p=[0.7, 0.3]),
                                 np.where(pyme, "Independiente",
                                          rng.choice(["Empleado", "Independiente", "Pensionado"], n,
                                                     p=[0.55, 0.35, 0.10])))
    df["canal"] = rng.choice(["Digital", "Aliado comercial", "Oficina"], n, p=[0.55, 0.25, 0.20])
    df["region"] = rng.choice(REGIONES, n, p=[0.30, 0.25, 0.15, 0.12, 0.10, 0.08])
    df["garantia"] = np.where(pyme, "FNG 50%", np.where(libranza, "Libranza", "Sin garantía"))

    # Probabilidad "verdadera" de llegar a 90+ días de mora en 12 meses
    vintage_malo = df["fecha_desembolso"].between("2025-10-01", "2026-03-31").to_numpy()
    logit = (perfil["intercepto"] - 0.0105 * (df["puntaje_buro"] - 650) + 2.2 * (df["endeudamiento"] - 0.35)
             - 0.30 * np.log(df["ingreso_mensual"] / 3.4e6) - 0.012 * (df["edad"] - 38)
             - 0.0035 * df["antiguedad_laboral_meses"] + 0.45 * (df["vinculacion"] == "Independiente")
             - 0.35 * (df["vinculacion"] == "Pensionado") + 0.30 * (df["canal"] == "Aliado comercial")
             + 0.15 * (df["region"] == "Caribe") + 0.45 * (df["producto"] == "Microcrédito")
             - 0.9 * libranza + 0.35 * vintage_malo + rng.normal(0, 0.35, n))
    df["_pd12"] = 1 / (1 + np.exp(-logit))
    return df


def simular_desempeno(org: pd.DataFrame, perfil: dict, rng) -> pd.DataFrame:
    """Cadena mensual de mora y amortización francesa hasta el corte."""
    roll1, roll2 = perfil["roll"]
    recup = {p: v[4] for p, v in perfil["productos"].items()}
    n = len(org)
    estado = np.zeros(n, dtype=int)          # 0 al día, 1..3 buckets de mora, 4 = 91+, 9 = cerrado
    meses_91 = np.zeros(n, dtype=int)
    saldo = org["monto"].to_numpy(dtype=float).copy()
    saldo_default = np.zeros(n)
    activo = np.zeros(n, dtype=bool)
    tasa_m = (1 + org["tasa_ea"].to_numpy()) ** (1 / 12) - 1
    plazo = org["plazo_meses"].to_numpy()
    cuota = saldo * tasa_m / (1 - (1 + tasa_m) ** (-plazo))
    mes_org = org["fecha_desembolso"].dt.to_period("M").to_numpy()
    q_base = org["_pd12"].to_numpy() / (12 * roll1 * roll2 * 0.95)
    prod = org["producto"].to_numpy()
    recup_total = np.array([recup[p] for p in prod]) * rng.uniform(0.5, 1.5, n)
    mob = np.zeros(n, dtype=int)
    salida = []
    for mes in MESES:
        per = mes.to_period("M")
        nuevos = (mes_org == per)
        activo |= nuevos
        vivos = activo & (estado != 9)
        idx = np.where(vivos & ~nuevos)[0]
        mob[idx] += 1
        u = rng.random(n)
        f_ciclo = _ciclo(mes)
        recuperacion = np.zeros(n)
        # transiciones
        e = estado.copy()
        al_dia = idx[e[idx] == 0]
        q = np.minimum(q_base[al_dia] * _maduracion(mob[al_dia]) * f_ciclo, 0.6)
        entra = u[al_dia] < q
        prepaga = (~entra) & (u[al_dia] > 1 - perfil["prepago"])
        estado[al_dia[entra]] = 1
        estado[al_dia[prepaga]] = 9
        saldo[al_dia[prepaga]] = 0
        paga = al_dia[~entra & ~prepaga]
        interes = saldo[paga] * tasa_m[paga]
        saldo[paga] = np.maximum(saldo[paga] - (cuota[paga] - interes), 0)
        termina = paga[(saldo[paga] < 1000) | (mob[paga] >= plazo[paga])]
        saldo[termina] = 0
        estado[termina] = 9
        for b, (p_roll, p_cura) in {1: (roll1, 0.48), 2: (roll2, 0.22), 3: (0.82, 0.08)}.items():
            ids = idx[e[idx] == b]
            uu = u[ids]
            p_r = np.minimum(p_roll * (f_ciclo ** 0.5), 0.95)
            estado[ids[uu < p_r]] = b + 1
            estado[ids[(uu >= p_r) & (uu < p_r + p_cura)]] = 0
        nuevos_def = idx[(e[idx] == 3) & (estado[idx] == 4)]
        saldo_default[nuevos_def] = saldo[nuevos_def]
        en_def = idx[e[idx] == 4]
        meses_91[en_def] += 1
        # recuperaciones: se reparten en 24 meses después del default
        rec = saldo_default[en_def] * recup_total[en_def] / 24 * (meses_91[en_def] <= 24)
        recuperacion[en_def] = rec
        saldo[en_def] = np.where(meses_91[en_def] < 6, np.maximum(saldo[en_def] - rec, 0), 0)  # castigo a 180 días
        cerrar_def = en_def[meses_91[en_def] > 24]
        estado[cerrar_def] = 9
        # nuevos créditos del mes: al día con saldo completo
        reg = np.where(activo & ((estado != 9) | np.isin(np.arange(n), termina) |
                                 np.isin(np.arange(n), al_dia[prepaga])))[0]
        dias = np.select([estado[reg] == 0, estado[reg] == 1, estado[reg] == 2, estado[reg] == 3],
                         [0, 20, 50, 80], 90 + 30 * np.maximum(meses_91[reg], 1) - 10)
        dias = np.where(estado[reg] == 9, 0, dias)
        est_txt = np.where(estado[reg] == 9, "Cancelado",
                           np.where((estado[reg] == 4) & (meses_91[reg] >= 6), "Castigado", "Vigente"))
        salida.append(pd.DataFrame({"id": org["id"].to_numpy()[reg], "mes": mes, "saldo_capital": saldo[reg].round(0),
                                    "dias_mora": dias, "estado": est_txt,
                                    "recuperacion_mes": recuperacion[reg].round(0)}))
    des = pd.concat(salida, ignore_index=True)
    # un crédito cancelado aparece una sola vez como 'Cancelado'
    des = des[~((des["estado"] == "Cancelado") & des.duplicated(["id", "estado"]))]
    return des


def escribir_politica(ruta: Path, perfil: dict, clave: str):
    wb = Workbook()
    enc_font, enc_fill = Font(name="Arial", bold=True, color="FFFFFF", size=9), PatternFill("solid", fgColor="1F3B5C")

    def hoja(nombre, titulo, cols, filas, anchos):
        ws = wb.create_sheet(nombre) if wb.active.title != "Sheet" else wb.active
        ws.title = nombre
        ws["A1"], ws["A1"].font = titulo, Font(name="Arial", bold=True, size=12)
        for j, c in enumerate(cols, start=1):
            cel = ws.cell(3, j, c)
            cel.font, cel.fill = enc_font, enc_fill
            cel.alignment = Alignment(horizontal="center", wrap_text=True)
            ws.column_dimensions[chr(64 + j)].width = anchos[j - 1]
        for i, f in enumerate(filas, start=4):
            for j, v in enumerate(f, start=1):
                ws.cell(i, j, v).font = Font(name="Arial", size=9)

    hoja("Entidad", "Parámetros de la entidad (ficticia)", ["Parámetro", "Valor", "Nota"], [
        ("Nombre de la entidad", perfil["nombre"], "Entidad ficticia de demostración"),
        ("Tipo de entidad", perfil["tipo"], ""),
        ("Patrimonio (COP millones)", perfil["patrimonio"], ""),
        ("Deuda con fondeadores (COP millones)", perfil["deuda"], "Créditos de fondeo respaldados con cartera (borrowing base)"),
        ("Costo promedio del fondeo (EA)", perfil["tasa_fondeo"],
         "Depósitos y obligaciones; se aplica a la cartera no financiada con patrimonio"),
        ("Comisiones y otros ingresos (% anual de la cartera)", perfil["comisiones"],
         "Fianzas, plataforma, seguros; solo la parte recurrente"),
        ("Tasa de anticipo (advance rate)", perfil["anticipo"], "Porcentaje de la cartera elegible que financia el fondeador"),
        ("Gastos operativos (% anual de la cartera)", perfil["opex"], ""),
        ("Días de mora máximos para cartera elegible", 30, "Criterio de elegibilidad del fondeador"),
        ("Provisión general (% de la cartera bruta)", perfil["prov_general"],
         "Referencia regulatoria: aplica a cooperativas; 0 si no aplica"),
        ("Provisión registrada en contabilidad (COP millones)", perfil["prov_registrada"],
         "Saldo de la cuenta de provisiones al corte (la cifra de los estados financieros)"),
        ("Modo demostración", "Sí", ""),
    ], [42, 38, 60])
    limites = [
        ("ICV_30", "Cartera vencida a más de 30 días / cartera bruta", "Calidad de cartera", "Máximo",
         0.16 if clave == "fintech" else 0.07, 0.13 if clave == "fintech" else 0.055, "%"),
        ("ICV_90", "Cartera vencida a más de 90 días / cartera bruta", "Calidad de cartera", "Máximo",
         0.10 if clave == "fintech" else 0.04, 0.08 if clave == "fintech" else 0.03, "%"),
        ("COBERTURA_30", "Provisión NIIF 9 / cartera vencida a más de 30 días", "Provisiones", "Mínimo", 0.90, 1.05, "%"),
        ("COSECHA_MOB6", "Mora 30+ a 6 meses de la cosecha más reciente madura", "Originación", "Máximo",
         0.12 if clave == "fintech" else 0.045, 0.10 if clave == "fintech" else 0.035, "%"),
        ("GINI_OOT", "Poder discriminante del score (Gini fuera de tiempo)", "Modelo", "Mínimo", 0.35, 0.45, "%"),
        ("PSI", "Estabilidad de la población (PSI)", "Modelo", "Máximo", 0.25, 0.10, "número"),
        ("CONC_PRODUCTO", "Mayor producto / cartera bruta", "Concentración", "Máximo", 0.80, 0.75, "%"),
        ("CONC_TOP20", "Veinte mayores deudores / cartera bruta", "Concentración", "Máximo",
         0.05 if clave == "fintech" else 0.12, 0.04 if clave == "fintech" else 0.10, "%"),
        ("COBERTURA_DEUDA", "Cartera elegible x anticipo / deuda con fondeadores", "Fondeo", "Mínimo", 1.00, 1.10, "veces"),
        ("EXCEDENTE_FIN", "Excedente financiero anual (rendimiento - fondeo - gastos - pérdida esperada)",
         "Fondeo", "Mínimo", 0.0, 0.02, "%"),
        ("ESTRES_SEVERO_PAT", "Pérdida adicional en estrés severo / patrimonio", "Estrés", "Máximo", 0.25, 0.18, "%"),
    ]
    hoja("Limites", "Límites (ilustrativos: reemplazar por los aprobados)",
         ["Código", "Indicador", "Categoría", "Tipo de límite", "Límite", "Alerta", "Unidad"], limites,
         [18, 62, 18, 13, 10, 10, 9])
    # Matriz estilo Superfinanciera: categoría por altura de mora y % de provisión (ilustrativos)
    matriz = []
    for prod in perfil["productos"]:
        comercial = prod.startswith("Comercial")
        micro = prod.startswith("Micro")
        tramos = ([("A", 0, 30), ("B", 31, 90), ("C", 91, 150), ("D", 151, 360), ("E", 361, 99999)] if comercial else
                  [("A", 0, 30), ("B", 31, 60), ("C", 61, 90), ("D", 91, 120), ("E", 121, 99999)] if micro else
                  [("A", 0, 30), ("B", 31, 60), ("C", 61, 90), ("D", 91, 180), ("E", 181, 99999)])
        porc = {"A": 0.01, "B": 0.032 if not comercial else 0.025, "C": 0.20 if not comercial else 0.10,
                "D": 0.50 if not comercial else 0.40, "E": 1.0}
        for cat, d0, d1 in tramos:
            matriz.append((prod, cat, d0, d1, porc[cat]))
    hoja("Matriz_provision", "Provisión por altura de mora (estilo Superfinanciera, porcentajes ilustrativos)",
         ["Producto", "Categoría", "Días desde", "Días hasta", "Provisión"], matriz, [22, 11, 11, 11, 11])
    hoja("Escenarios", "Escenarios macroeconómicos (NIIF 9 prospectiva y estrés)",
         ["Escenario", "Uso", "Peso", "Multiplicador PD", "Ajuste LGD (pp)"], [
             ("Optimista", "NIIF 9", 0.15, 0.85, -0.02), ("Base", "NIIF 9", 0.60, 1.00, 0.0),
             ("Adverso", "NIIF 9", 0.25, 1.35, 0.03),
             ("Estrés moderado", "Estrés", None, *perfil["estres"][0]),
             ("Estrés severo", "Estrés", None, *perfil["estres"][1])],
         [20, 10, 8, 16, 15])
    wb.save(ruta)


def ensuciar(org: pd.DataFrame, des: pd.DataFrame, rng):
    """Errores típicos de un archivo real, para que la demo muestre la validación:
    tasas escritas en porcentaje, puntajes de buró vacíos, edades imposibles,
    filas de desempeño duplicadas y un saldo negativo."""
    org, des = org.copy(), des.copy()
    n = len(org)
    i_tasa = rng.choice(n, 25, replace=False)
    org.loc[org.index[i_tasa], "tasa_ea"] = (org["tasa_ea"].iloc[i_tasa] * 100).round(2)
    i_buro = rng.choice(n, int(n * 0.012), replace=False)
    org["puntaje_buro"] = org["puntaje_buro"].astype("float")
    org.loc[org.index[i_buro], "puntaje_buro"] = np.nan
    i_edad = rng.choice(n, 6, replace=False)
    org.loc[org.index[i_edad], "edad"] = [0, 3, 150, 0, 210, 1][:len(i_edad)]
    dup = des.sample(40, random_state=int(rng.integers(1e6)))
    neg = des[(des["estado"] == "Vigente") & (des["saldo_capital"] > 0)].sample(3, random_state=7).index
    des.loc[neg, "saldo_capital"] = -des.loc[neg, "saldo_capital"]
    des = pd.concat([des, dup]).sort_values(["mes", "id"], kind="stable").reset_index(drop=True)
    return org, des


def main():
    for clave, perfil in PERFILES.items():
        rng = np.random.default_rng(perfil["semilla"])
        carpeta = RAIZ / "entrada" / clave
        carpeta.mkdir(parents=True, exist_ok=True)
        org = originar(perfil, rng)
        des = simular_desempeno(org, perfil, rng)
        org, des = ensuciar(org.drop(columns="_pd12"), des, rng)
        org.to_csv(carpeta / "originaciones.csv", index=False, encoding="utf-8-sig")
        des.to_csv(carpeta / "desempeno.csv", index=False, encoding="utf-8-sig")
        escribir_politica(carpeta / "politica_credito.xlsx", perfil, clave)
        print(f"{clave}: {len(org):,} créditos y {len(des):,} registros de desempeño".replace(",", "."))
    print("Listo. Siguiente paso: python generar_informes.py")


if __name__ == "__main__":
    sys.exit(main())
