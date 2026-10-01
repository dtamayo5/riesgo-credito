# Cómo funciona el motor, módulo por módulo

Guía de estudio del código. Orden recomendado de lectura: el mismo en que corre
`proceso.calcular()`.

```
generar_informes.py
  └─ proceso.generar(carpeta)
       1. lectura.leer_entidad()      archivos -> tablas limpias + bitácora de hallazgos
       2. cartera.*                   foto, evolución, cosechas, rodamientos, concentración
       3. scoring.desarrollar()       score: WoE, IV, logística, tarjeta, validación
       4. niif9.calcular()            PD, LGD, EAD, etapas, ECL, referencia regulatoria
       5. fondeo.calcular()           base de préstamo, excedente financiero
       6. estres.calcular()           escenarios y estrés inverso
       7. limites / narrativa         semáforo, mensajes, acciones, fortalezas y riesgos
  └─ graficas, informe_comite, informe_fondeadores, anexo_excel
```

---

## 0. Los datos de demostración (`herramientas/generar_datos_demo.py`)

Conviene entender cómo se fabricaron los datos, para saber qué debe encontrar
el motor.

- Cada crédito tiene una **PD "verdadera"** a 12 meses que sale de un logit con
  el buró, el endeudamiento, el ingreso, la edad, la vinculación, el canal y
  el producto.
- A eso se suman dos efectos: una **cosecha mala** (oct-2025 a mar-2026) y, en
  la fintech, una **deriva de población** (desde oct-2025 aprueba puntajes 25
  puntos menores).
- La mora se simula mes a mes como una **cadena**: al día -> 1-30 -> 31-60 ->
  61-90 -> 91+.
  - La entrada depende de la PD, de la maduración del crédito y de un **ciclo**
    (×1,40 en el primer semestre de 2026).
  - Hay curas, prepagos, amortización francesa, castigo a los 6 meses en 91+ y
    recuperaciones repartidas en 24 meses.
- La función `ensuciar()` mete errores típicos para que la validación tenga
  qué encontrar: tasas en porcentaje, buró vacío, edades imposibles, filas
  duplicadas y saldos negativos.

Ejercicio: el motor debe redescubrir lo que se sembró, sin conocer la
simulación:
- el buró como variable más fuerte;
- el deterioro de las cosechas 2025-T4 y 2026-T1;
- la deriva de la PD de originación (PSI y PD reciente);
- el factor del ciclo (factor PIT mayor que 1).

## 1. `lectura.py`: validar antes de calcular

- Las columnas se reconocen por alias (`config.COLUMNAS_*`). Para un cliente
  nuevo basta agregar el nombre que use su sistema.
- **Originaciones:**
  - créditos repetidos;
  - fechas posteriores al corte;
  - montos o plazos no positivos;
  - tasas escritas en porcentaje (24,5 se divide entre 100);
  - valores fuera de rango (edad de 210 años) y faltantes, que se imputan con
    la mediana.
- **Desempeño:**
  - duplicados exactos (se borra la copia);
  - dos registros distintos del mismo crédito y mes (gana el último);
  - créditos sin originación;
  - saldos negativos (valor absoluto con advertencia);
  - meses que no son fin de mes.
- `_grupo()`: si el mismo problema se repite en 279 filas, deja **una** línea
  con el número de filas y las primeras cinco, en lugar de 279 líneas.
- `leer_politica()`: lee las hojas de la política por el nombre del parámetro
  (no por la posición de la celda) y verifica que los pesos de los escenarios
  NIIF 9 sumen 1.

## 2. `cartera.py`: lo que el comité mira primero

- `panel()`: une desempeño y originación y calcula el **MOB** (meses desde el
  desembolso) y el tramo de mora.
- **ICV30 / ICV90:** saldo con más de 30 / 90 días sobre la cartera bruta
  vigente.
- `evolucion()`:
  - Serie mensual de cartera, desembolsos y recuperaciones.
  - Castigos: saldo del mes anterior de los créditos que pasan a castigados.
  - Pérdida neta 12m = (castigos - recuperaciones) de 12 meses / cartera
    promedio.
- `cosechas()`:
  - Para cada trimestre de desembolso, el % acumulado de créditos que
    *alguna vez* superó 30 (o 90) días, por MOB.
  - Solo se muestran los MOB que **todo** el trimestre ya cumplió; si no, la
    última cosecha se vería artificialmente buena.
  - **Por qué cosechas y no solo ICV:** si la cartera crece rápido, los
    créditos nuevos (que aún no han tenido tiempo de caer en mora) diluyen el
    ICV. La cosecha compara créditos a la misma edad.
- `rodamientos()`:
  - Matriz de transición mes a mes entre tramos, ponderada por saldo y
    promediada en 6 meses.
  - Destinos adicionales: Pagado y Castigado. Cada fila suma 100%.
- `flujo_a_mora()`: saldo promedio que pasa de 0-30 a 31+ cada mes. Lo usa el
  estrés de la cartera elegible.

## 3. `scoring.py`: el score de originación

**Muestra (`muestra_modelo`):**
- Créditos con al menos 12 meses desde el desembolso.
- Malo = superó 90 días de mora en sus primeros 12 meses.
- 60% de los meses más antiguos = desarrollo; el resto = **fuera de tiempo**.
  El modelo se evalúa con créditos más recientes que no vio, como en la vida
  real.

**Tramos y WoE:**
```
WoE_tramo = ln( %buenos del tramo / %malos del tramo )
IV = suma( (%buenos - %malos) x WoE )
```
- WoE positivo = tramo mejor que el promedio.
- IV < 0,02: no sirve; 0,02-0,1: débil; 0,1-0,3: medio; más de 0,3: fuerte.
- Se suma 0,5 a los conteos para evitar ln(0).
- `tramos_numerica()`:
  - Corta por cuantiles.
  - Si la tasa de malos no es monótona en la dirección de la correlación,
    fusiona el par de tramos vecinos más parecido.
  - Repite hasta que sea monótona y ningún tramo tenga menos del 5%.
- `tramos_categorica()`: agrupa en "Otros" las categorías de menos del 5% y
  ordena por tasa de malos.

**Selección:**
1. IV mayor o igual a 0,02.
2. Si dos WoE tienen correlación mayor a 0,7, queda la de mayor IV.
3. Regresión.
4. Se retira la variable con signo contrario (con WoE, todos los coeficientes
   deben ser negativos) o, si no hay, la de mayor valor p (mayor a 0,05).
5. Se repite hasta que todas cumplan.

En la cooperativa:
- *producto* y *garantía* tienen IV alto pero salen por correlación y
  significancia, porque el buró y la vinculación ya capturan esa información.
- *plazo* sale con p = 0,05.

**Logística por IRLS (`logistica_irls`), Newton-Raphson sobre la verosimilitud:**
```
p = 1 / (1 + e^(-Xb))      W = p(1-p)
b_nuevo = b + (X'WX)^-1 X'(y - p)
```
- Los errores estándar salen de la diagonal de (X'WX)^-1.
- z = b / ee; el valor p se calcula con la normal.

**Calibración en grande:** se ajusta el intercepto (Newton en una variable)
para que la PD promedio iguale la tasa de malos de **toda** la muestra madura
(desarrollo + fuera de tiempo). Es la PD "promedio del ciclo" de originación.

**Tarjeta de puntos:**
```
factor = PDO / ln 2            offset = 600 - factor x ln(20)
puntos del tramo = -(b_j x WoE + (b0 + ajuste)/k) x factor + offset/k
```
- k es el número de variables. La suma de los puntos da 600 cuando los odds
  son 20:1, y cada 20 puntos duplican los odds.
- Ejercicio: suma los puntos de un crédito en la hoja *Score* del anexo y
  compáralos con su score en *Creditos_NIIF9*.

**Validación:**
- AUC por rangos (Mann-Whitney); Gini = 2·AUC - 1; KS = máxima distancia
  entre las distribuciones acumuladas de buenos y malos.
- Prueba binomial por calificación:
  `z = (malos - n·PD) / raíz(n·PD·(1-PD))`; |z| ≤ 1,96 = calibrada.
- PSI = suma((%reciente - %desarrollo) × ln(%reciente / %desarrollo)) sobre
  deciles del score de desarrollo.
- Puntos de corte: en la muestra fuera de tiempo, qué pasa con la tasa de
  malos si se rechaza además el 5%, 10%... de menor score.

## 4. `niif9.py`: la provisión

**PD punto en el tiempo (la parte más importante de entender):**

1. `matriz_markov()`:
   - Transiciones mensuales de los últimos 12 meses entre los estados 0, 1-30,
     31-60, 61-90, D (91+ o castigado, absorbente) y P (pagado, absorbente).
   - Una matriz por producto; si un producto tiene menos de 2.000
     transiciones, usa la de toda la cartera.
2. `pd_markov()`:
   - P^12 da la probabilidad de estar en D al cabo de 12 meses desde cada
     estado. Es la PD a 12 meses por tramo.
   - Ejemplo (consumo digital de la fintech): al día 12%, 1-30 41%, 31-60 72%, 61-90 94%.
3. Para un crédito **al día**: `PD12 = PD originación × factor PIT`, con
   `factor PIT = PD al día de la cadena / PD de originación promedio` de los
   créditos al día del producto.
   - El score dice *quién* es más riesgoso.
   - La cadena dice *cuánto* riesgo hay hoy.
   - En la fintech el factor de microcrédito es 1,32: la cartera está rodando
     más que el promedio histórico.
4. Para un crédito **en mora**: la PD de su tramo según la cadena (nunca
   menor que la de un crédito al día).

**LGD (`curva_lgd`):**
- Para cada incumplimiento (primer mes en más de 90 días), la EAD es el saldo
  en ese mes. `r_m` = recuperaciones del mes m / EAD de los incumplimientos que
  ya llevan al menos m meses (método de cadena: no se descartan los
  incumplimientos recientes).
- `LGD = 1 - suma r_m / (1 + tasa)^(m/12)`. Se descuenta a la tasa del producto
  porque recuperar un peso dentro de dos años vale menos que hoy.
- Piso de 10%. Los productos con menos de 30 incumplimientos usan la LGD de
  toda la cartera.

**EAD y ECL (`ecl_creditos`), totalmente vectorizado (matriz créditos × meses):**
```
saldo al inicio del mes t:  B_(t-1) = B0 · ((1+i)^n - (1+i)^(t-1)) / ((1+i)^n - 1)
riesgo mensual:             h = 1 - (1 - PD12)^(1/12)   (año 1)
                            h = 1 - (1 - PD al día)^(1/12)   (años 2+)
PD marginal del mes t:      h_t · supervivencia_(t-1)
ECL = suma_t PD marginal_t · LGD · B_(t-1) · (1 + tasa)^(-t/12)
```
- Etapa 1 suma hasta 12 meses; etapa 2, hasta el vencimiento.
- Etapa 3: `saldo × LGD`.

**Etapas:**
- 3: más de 90 días.
- 2: más de 30 días, o (PD12 ≥ 2 × PD de originación **y** al menos 3 pp
  mayor), o curado de 31+ días en los últimos 6 meses.
- El umbral absoluto evita que un crédito de PD 0,5% pase a etapa 2 por subir
  a 1,1%.

**Escenarios:**
- La ECL final es el promedio ponderado de los escenarios NIIF 9 (optimista
  15%, base 60%, adverso 25%).
- En cada escenario la PD se multiplica, la LGD se ajusta y **las etapas se
  recalculan**. Por eso el adverso pesa más que su multiplicador: más créditos
  pasan a pérdida de toda la vida (efecto acantilado).

**Referencia regulatoria (`referencia_regulatoria`):**
- Categoría A-E por días de mora según el producto y el % de la matriz de la
  política.
- Más la provisión general (1% en la cooperativa).
- Es una referencia configurable, no el modelo de referencia oficial.

## 5. `fondeo.py`: lo que mira quien presta

```
cartera elegible   = saldo con mora <= 30 días
base de préstamo   = elegible × anticipo           cobertura = base / deuda
excedente = rendimiento al día + comisiones - costo fondeo - gastos - pérdida esperada 12m
costo fondeo       = costo promedio × (cartera - patrimonio) / cartera
equilibrio         = 1 + excedente / pérdida esperada
```
- El rendimiento se toma solo sobre la cartera que paga (tasa promedio × %
  al día).
- La pérdida esperada a 12 meses excluye la etapa 3, que ya está perdida y
  provisionada.

## 6. `estres.py`

- Escenarios de estrés de la política: ECL estresada con etapas nuevas, menos
  la ECL actual, como % del patrimonio.
- Cobertura e ICV estresados: durante 3 meses entra a mora un flujo (m - 1)
  veces mayor al promedio reciente.
- **Estrés inverso:** rejilla de multiplicadores de 1 a 10. Se interpola dónde
  la provisión adicional cruza el límite de la política o el 100% del
  patrimonio. La cobertura y el excedente tienen solución cerrada.

## 7. `limites.py`, `narrativa.py`

- Semáforo igual al del motor de tesorería. Se compara la cifra **redondeada
  como se muestra** (un Gini de 44,995% se muestra como 45,0% y cumple una
  alerta de 45%).
- Mensajes: cada regla mira los resultados y escribe una frase con cifras. El
  color sale del límite relacionado.
- Acciones con montos:
  - provisión faltante = ECL - registrada;
  - punto de corte = menor rechazo que lleva la tasa de malos al nivel del
    desarrollo;
  - cartera para cobertura = alerta × deuda / anticipo - elegible;
  - capital = provisión adicional del estrés severo / límite - patrimonio;
  - excedente: los pb de tasa que faltan para la alerta.
- `fortalezas_riesgos()`: la misma información, dicha como la escucha un
  fondeador. Cada punto va a fortalezas o a riesgos según el semáforo.

## 8. Salidas

- `pdf_base.py`: estilos, tablas, chips de estado y plantilla de página
  comunes a los dos informes.
- `informe_comite.py` e `informe_fondeadores.py`: cada sección es una función
  que devuelve una lista de elementos de ReportLab.
- `anexo_excel.py`:
  - los resultados del modelo se escriben como valores;
  - totales por etapa, provisión de referencia, base de préstamo y excedente
    son fórmulas (`SUMIF`, `COUNTIF`) sobre la hoja *Creditos_NIIF9*.

## Ejercicios para dominarlo

1. En el anexo, filtra la hoja *Creditos_NIIF9* por etapa 2 y verifica que la
   suma de la ECL coincide con la hoja *Provisiones*.
2. Toma un crédito de etapa 1 y recalcula su ECL a mano en Excel con la
   fórmula de la sección 4 (debe cuadrar al peso).
3. Cambia `SICR_ABSOLUTO` a 0 en `config.py` y explica por qué el saldo en
   etapa 2 del estrés severo de la cooperativa se dispara.
4. Cambia el anticipo de la fintech a 80% en su política y predice la nueva
   cobertura y la acción sugerida antes de correr el motor.
5. Explica en voz alta por qué la cosecha es mejor indicador que el ICV en una
   cartera que crece 29% al año.
6. En la demo, ¿por qué la PD del tramo 61-90 es cercana a 94% y no a 100%?
   (Pista: curas y la fila 61-90 de la matriz de rodamientos.)
