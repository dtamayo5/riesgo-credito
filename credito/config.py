"""
Parámetros TÉCNICOS del motor de riesgo de crédito.

Igual que en el motor de tesorería, hay una separación deliberada:
  - Aquí viven las decisiones metodológicas (definición de incumplimiento,
    ventanas de desarrollo del score, reglas de etapas NIIF 9, escala de
    calificación) que mantiene el consultor.
  - Los parámetros de NEGOCIO (límites, matriz de provisión regulatoria,
    escenarios, datos de fondeo) viven en entrada/<perfil>/politica_credito.xlsx,
    porque los aprueba la entidad.
"""
from pathlib import Path

VERSION = "1.0.0"
MARCA = "David - Consultoría Cuantitativa de Riesgo"

# --------------------------------------------------------------------------
# Rutas
# --------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DIR_ENTRADA = RAIZ / "entrada"
DIR_SALIDAS = RAIZ / "salidas"
ARCHIVO_POLITICA = "politica_credito.xlsx"
ARCHIVOS_ORIGINACIONES = ["originaciones.csv", "originaciones.xlsx"]
ARCHIVOS_DESEMPENO = ["desempeno.csv", "desempeno.xlsx"]

# --------------------------------------------------------------------------
# Columnas: nombre interno -> nombres con que puede venir en el archivo del
# cliente (normalizados: minúsculas, sin tildes ni puntuación)
# --------------------------------------------------------------------------
COLUMNAS_ORIGINACIONES = {
    "id": ["id", "id credito", "numero credito", "no credito", "obligacion", "pagare", "credito"],
    "id_deudor": ["id deudor", "deudor", "cliente", "id cliente", "documento", "documento cliente", "nit"],
    "fecha_desembolso": ["fecha desembolso", "fecha de desembolso", "desembolso", "fecha"],
    "producto": ["producto", "linea", "linea de credito", "modalidad"],
    "monto": ["monto", "monto desembolsado", "valor desembolsado", "valor", "monto inicial"],
    "plazo_meses": ["plazo meses", "plazo", "plazo en meses", "numero cuotas"],
    "tasa_ea": ["tasa ea", "tasa", "tasa efectiva anual", "tasa de interes"],
}
COLUMNAS_DESEMPENO = {
    "id": ["id", "id credito", "numero credito", "no credito", "obligacion", "pagare", "credito"],
    "mes": ["mes", "fecha corte", "corte", "periodo", "fecha"],
    "saldo_capital": ["saldo capital", "saldo", "capital", "saldo de capital"],
    "dias_mora": ["dias mora", "dias de mora", "altura mora", "altura de mora", "mora"],
    "estado": ["estado", "estado credito", "situacion"],
    "recuperacion_mes": ["recuperacion mes", "recuperaciones", "recuperacion", "recaudo castigada"],
}
ESTADOS = {"vigente": "Vigente", "activo": "Vigente", "al dia": "Vigente",
           "cancelado": "Cancelado", "pagado": "Cancelado", "saldado": "Cancelado",
           "castigado": "Castigado", "castigo": "Castigado"}

# Variables candidatas para el score (se usan las que existan en el archivo)
VARIABLES_NUMERICAS = ["puntaje_buro", "endeudamiento", "ingreso_mensual", "edad",
                       "antiguedad_laboral_meses", "monto", "plazo_meses"]
VARIABLES_CATEGORICAS = ["vinculacion", "canal", "region", "producto", "garantia"]
RANGOS_VALIDOS = {"edad": (18, 90), "puntaje_buro": (150, 999), "endeudamiento": (0, 1.5),
                  "ingreso_mensual": (1, 5e9), "antiguedad_laboral_meses": (0, 720)}
NOMBRE_VARIABLE = {
    "puntaje_buro": "Puntaje de buró", "endeudamiento": "Endeudamiento (cuota/ingreso)",
    "ingreso_mensual": "Ingreso mensual", "edad": "Edad", "antiguedad_laboral_meses": "Antigüedad laboral",
    "monto": "Monto", "plazo_meses": "Plazo", "vinculacion": "Tipo de vinculación", "canal": "Canal",
    "region": "Región", "producto": "Producto", "garantia": "Garantía",
}

# --------------------------------------------------------------------------
# Definición de incumplimiento y ventanas
# --------------------------------------------------------------------------
DIAS_INCUMPLIMIENTO = 90        # "malo" = llega a más de 90 días de mora
VENTANA_DESEMPENO = 12          # ... dentro de los primeros 12 meses de vida
FRACCION_DESARROLLO = 0.6       # primeras cosechas maduras: desarrollo; resto: fuera de tiempo (OOT)
MESES_PSI = 6                   # originaciones recientes comparadas contra el desarrollo
MESES_RODAMIENTO = 6            # meses promedio de la matriz de rodamientos
MESES_HISTORIA = 12             # meses de evolución en los informes

# --------------------------------------------------------------------------
# Score (WoE + regresión logística + tarjeta de puntos)
# --------------------------------------------------------------------------
N_TRAMOS = 6                    # tramos iniciales por cuantiles (variables numéricas)
MIN_PARTICIPACION_TRAMO = 0.05  # ningún tramo con menos del 5% de la muestra
IV_MINIMO = 0.02                # por debajo, la variable no discrimina
MAX_VARIABLES = 8
PUNTOS_BASE, ODDS_BASE, PDO = 600, 20, 20   # 600 puntos = 20 buenos por cada malo; +20 puntos duplica los odds

# Escala maestra de calificación: límite superior de PD de cada grado
ESCALA_PD = [("A", 0.02), ("B", 0.04), ("C", 0.07), ("D", 0.11), ("E", 0.17),
             ("F", 0.25), ("G", 0.40), ("H", 1.00)]

# --------------------------------------------------------------------------
# NIIF 9
# --------------------------------------------------------------------------
DIAS_ETAPA_2 = 30               # presunción refutable: más de 30 días -> etapa 2
DIAS_ETAPA_3 = 90               # más de 90 días -> etapa 3 (incumplimiento)
SICR_MULTIPLO = 2.0             # PD actual >= 2 x PD de originación ...
SICR_ABSOLUTO = 0.03            # ... y al menos 3 pp más alta -> aumento significativo del riesgo
SICR_MESES_CURA = 6             # curado de 31+ días en los últimos 6 meses -> sigue en etapa 2
MESES_RECUPERACION = 24         # horizonte de la curva de recuperaciones
MIN_INCUMPLIMIENTOS_LGD = 30    # por debajo, la LGD del producto usa la de toda la cartera
LGD_PISO = 0.10
TRAMOS_MORA = [("Al día", -1, 0), ("1-30", 1, 30), ("31-60", 31, 60), ("61-90", 61, 90), ("91+", 91, 10**6)]
MESES_DETERIORO_ESTRES = 3      # meses de deterioro acelerado al estresar la cartera elegible
