# Servicio: modelo de riesgo de crédito para entidades sin equipo cuantitativo

**En una frase:** con la historia de la cartera que la entidad ya tiene, le
entrego un score propio, provisiones NIIF 9 defendibles, pruebas de estrés y dos
informes listos: uno para su comité y otro para conseguir o renovar fondeo.

---

## Para quién

- **Fintechs de crédito** (consumo digital, nómina, microcrédito, BNPL,
  factoring): necesitan levantar deuda y los fondeadores les piden cosechas,
  base de préstamo y estrés.
- **Cooperativas de ahorro y crédito y fondos de empleados**: necesitan provisionar
  bien, explicar la cartera a la Junta y al revisor fiscal, y compararse con la
  referencia de su supervisor.
- **Financieras no vigiladas, originadoras de libranza y operadores de
  microcrédito** que fondean con bancos, fondos de deuda o Bancóldex/Findeter.

La señal de que el cliente encaja:
- la provisión se calcula con una tabla por días de mora;
- el "score" es el puntaje del buró con un punto de corte heredado;
- cada fondeador pide un Excel distinto que alguien arma a mano.

## El problema que resuelve

1. **Provisiones que llegan tarde:** la matriz por altura de mora solo reacciona
   cuando el crédito ya está en mora. Cuando las cosechas empeoran, la pérdida
   aparece en el estado de resultados meses después, de golpe.
2. **Originación a ciegas:** sin un score propio validado no se sabe cuánto
   riesgo se compra al crecer ni dónde poner el punto de corte.
3. **Conversaciones difíciles con fondeadores:** sin cosechas, rodamientos, base
   de préstamo ni estrés, la entidad negocia con desventaja (más tasa, menos
   anticipo, más garantías).
4. **Junta y revisor fiscal sin respuesta:** "¿cuánto aguantamos si la mora sube?"
   no tiene una cifra.
5. **Sin trazabilidad:** nadie puede rehacer cómo salió la provisión.

## Qué recibe el cliente

- **Score de originación propio:**
  - tarjeta de puntos interpretable;
  - validación fuera de tiempo, calibración y estabilidad;
  - tabla de punto de corte (cuánto se rechaza y cuánta mora se evita).
- **Provisión NIIF 9 crédito por crédito:**
  - etapas 1-2-3 y escenarios prospectivos;
  - PD con la realidad actual de la cartera y LGD con sus propias
    recuperaciones;
  - comparación con la referencia regulatoria y con lo registrado.
- **Cosechas, rodamientos y concentración.**
- **Estrés y estrés inverso:** cuánto tendría que empeorar la cartera para
  consumir el patrimonio, llevar el excedente a cero o romper la cobertura de
  la deuda.
- **Informe del comité** (13 páginas): mensajes clave y **acciones con montos**.
- **Informe para fondeadores** (6 páginas): tesis con fortalezas y riesgos, base
  de préstamo, excedente financiero y punto de equilibrio.
- **Anexo Excel** con detalle por crédito y fórmulas vivas para el revisor
  fiscal.
- **Instalación en el computador de la entidad:** los datos de los deudores
  nunca salen de ella.

## Cómo se implementa

| Fase | Duración | Qué pasa | Entregable |
|---|---|---|---|
| 0. Diagnóstico | 1-2 semanas | Se carga la historia de cartera del cliente y se corre el motor | Informe con su propia cartera: cosechas, brecha de provisión, primer score |
| 1. Implementación | 4-6 semanas | Mapeo de su software de cartera, variables de originación, matriz de su supervisor, límites y escenarios con la gerencia, documentación del modelo | Motor configurado + documento metodológico |
| 2. Paralelo | 1-2 cierres | Conciliación con contabilidad y con el informe actual | Acta de conciliación |
| 3. Operación | Mensual | Ejecución, informe, presentación al comité, recalibración anual del score | Informes mensuales |

**Proyecto puntual para levantar deuda:** diagnóstico más un informe para
fondeadores con la cartera real, entregado en 2-3 semanas. Es la puerta de
entrada natural con fintechs: se paga sola si mejora en un punto la tasa o
el anticipo.

## Modelo comercial (hipótesis a validar con los primeros clientes)

| Componente | Alcance | Rango de referencia |
|---|---|---|
| Diagnóstico | Corrida con la cartera real + reunión de hallazgos | COP 0 a 4 M (acreditable) |
| Informe para fondeadores | Diagnóstico + data pack de fondeo | COP 8 a 15 M |
| Implementación completa | Fases 1 y 2, precio fijo | COP 25 a 50 M según productos y calidad de datos |
| Retainer estándar | Ejecución mensual, informes, soporte | COP 4 a 7 M / mes |
| Retainer premium | Estándar + comité + recalibración + nuevos análisis | COP 8 a 12 M / mes |

Referencias de valor para el cliente:
- un punto de tasa en una línea de fondeo de COP 30.000 M equivale a
  COP 300 M al año;
- una brecha de provisión que aparece de golpe puede costar varios meses de
  utilidad;
- un analista cuantitativo de crédito cuesta más que el retainer y tarda meses
  en llegar a este punto.

## Qué necesita el cliente

- **Originaciones:** un registro por crédito con fecha, producto, monto, plazo,
  tasa y las variables de la solicitud que tenga (buró, ingreso,
  endeudamiento, canal...).
- **Desempeño mensual:** saldo, días de mora, estado y recuperaciones, con al
  menos 24 meses de historia. Normalmente sale del cierre mensual del software
  de cartera.
- **Política:** límites, matriz de provisión de su supervisor, datos de fondeo
  (deuda, anticipo, costo, criterio de elegibilidad) y provisión registrada.
- **Equipo:** un computador con Windows y Python.

## Módulos adicionales

- Score de comportamiento (para renovaciones, cupos y cobranza preventiva).
- Modelo de referencia oficial de la Superfinanciera por modalidad, o el de
  la Supersolidaria para cooperativas.
- Reestructuraciones, castigos parciales y prepagos en la EAD.
- Rentabilidad ajustada por riesgo y pricing por calificación.
- Data pack automático en el formato de cada fondeador.
- Conexión con el informe de tesorería (`reporting-riesgo`) para un informe
  integral de riesgos.

## Guion de la demostración (20 minutos)

1. **Problema.** "¿Cómo calcula hoy su provisión? ¿Qué le pidió su último
   fondeador?"
2. **Velocidad.** `demo.bat`: dos entidades procesadas en segundos.
3. **Fintech, página 1.** La mora sube y la cosecha del primer trimestre de
   2026 tiene 1,7 veces más mora que las anteriores. La PD de originación
   subió porque se aprobaron perfiles peores. La provisión registrada se queda
   COP 1.996 M corta: 21% del patrimonio.
4. **Score.** Gini fuera de tiempo de 45%. Subir el corte a 555 puntos rechaza
   15% de las solicitudes y baja la tasa de malos de 11,9% a 8,7%.
5. **Fondeadores.** Base de préstamo con 1,01 veces de cobertura (holgura de
   COP 178 M). El excedente financiero llega a cero si la PD sube 25%. "¿Su
   fondeador ya lo sabe? Mejor que lo sepa por usted."
6. **Cooperativa, por contraste.** Sana y bien fondeada, pero la matriz
   regulatoria subestima la pérdida de comercial pyme.
7. **Anexo Excel.** Cambiar la tasa de anticipo en la hoja Fondeo y ver cómo
   se recalcula la cobertura.
8. **Cierre.** "Hagamos el diagnóstico con su cartera."

## Preguntas difíciles

1. **¿Por qué no usar solo el puntaje del buró?**
   - El buró ordena el riesgo del país, no el de su producto y su canal.
   - En la demo, el buró es la variable más fuerte, pero endeudamiento y
     vinculación agregan poder.
   - Y solo el score propio produce una PD calibrada a su cartera, que es lo
     que necesita la provisión.
2. **¿Qué es el Gini y cuánto es bueno?** Mide qué tan bien separa el score a
   buenos de malos (0 = azar). En consumo, entre 40% y 60% es habitual. Lo
   importante es medirlo **fuera de tiempo**, en créditos que el modelo no vio.
3. **¿Cómo sabe que el modelo no está sobreajustado?**
   - Validación fuera de tiempo, prueba binomial por calificación y PSI.
   - Además, pocas variables con signo esperado y tramos monótonos.
4. **¿Por qué la PD sale de una cadena de Markov?**
   - Porque refleja cómo está rodando la cartera hoy (punto en el tiempo),
     como pide la NIIF 9.
   - El score reparte ese nivel entre los créditos según su riesgo relativo.
5. **¿Cómo definen el aumento significativo del riesgo?**
   - Más de 30 días de mora (presunción de la norma).
   - O PD actual al menos 2 veces la de originación y 3 puntos mayor.
   - O curado de mora 31+ hace menos de 6 meses.
   - Todo es configurable y queda documentado.
6. **¿Por qué la NIIF 9 da más que la matriz regulatoria?**
   - La matriz espera a la mora; la NIIF 9 anticipa con la PD y usa la
     severidad real.
   - En un producto con recuperaciones bajas o con cosechas empeorando, la
     brecha es la señal.
7. **¿Esto reemplaza el modelo de referencia de la Superfinanciera?** No. Las
   entidades vigiladas deben aplicar el modelo de referencia; el motor lo
   complementa con la visión NIIF 9 y la gestión. La referencia del informe es
   configurable y en la implementación se ajusta a la norma exacta.
8. **¿Qué pasa si no tenemos recuperaciones registradas?**
   - Se usa un supuesto de LGD documentado mientras se construye la historia.
   - El informe lo advierte.
9. **¿Y si tenemos poca historia o pocos incumplimientos?**
   - Con menos de 24 meses o pocos incumplimientos, el score se reemplaza por
     un modelo experto o por segmentos.
   - La LGD de los productos pequeños usa la de toda la cartera.
   - Se dice con claridad.
10. **¿Cómo se calcula la base de préstamo?** Cartera con mora menor o igual al
    máximo del fondeador, multiplicada por la tasa de anticipo. En la
    implementación se replican exactamente los criterios de cada contrato:
    concentración, plazo, producto.
11. **¿Dónde quedan los datos de nuestros deudores?** En su computador. El
    motor no se conecta a internet.
12. **¿Cada cuánto se recalibra el score?**
    - Una vez al año, o antes si el PSI supera 0,10 o el Gini cae por debajo
      de la alerta.
    - El informe avisa solo.

## Honestidad comercial

- La demostración usa entidades ficticias y datos sintéticos.
- La matriz regulatoria de la demo es ilustrativa.
- El motor apoya al área de riesgos. Las decisiones de provisión, los reportes
  regulatorios y la debida diligencia de los fondeadores siguen siendo de cada
  responsable.
- Las cifras de estrés dependen de supuestos que se documentan y se discuten
  con la gerencia.
