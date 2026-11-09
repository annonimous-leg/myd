# Revisiones económicas y contratos de planeación

Base: `8693ef3880e11b342bbb169f0b3bf2bd94859917`.

## Comportamiento implementado

Los seis comandos económicos de PresupuestoService consultan y bloquean el
mismo agregado antes de comprobar su estado. VALIDADO y APROBADO rechazan
recálculo, cantidades, eliminación, asignación/adición de catálogo y cambio
de parámetros. La aprobación original ya no se sustituye por CALCULADO.

`POST /presupuestos/{expediente}/presupuestos/{id}/revisiones` crea un agregado
independiente en BORRADOR, con motivo, actor y referencia al presupuesto de
origen. Copia partidas, conceptos e insumos con identificadores nuevos;
conserva fuentes, mediciones y parámetros. Remapea el manifiesto de índices
a los insumos nuevos, sin cambiar sus snapshots ni actualizar precios por
publicaciones posteriores. Los resultados de Monte Carlo no se copian.
La edición de cantidades BIM/topográficas sigue exigiendo revisar la medición
original; crear una revisión no elimina esa condición.

CostOS abre presupuestos persistidos, muestra el análisis anidado, guarda
cantidades mediante comandos del backend, recarga, crea revisiones, compara
con el origen, valida y aprueba. Los importes mostrados son los guardados.
No aplana los APU a precios manuales ni recrea el presupuesto al editarlo.

La comparación de sobrecostos exige que ambos presupuestos pertenezcan al
expediente solicitado. Una base no positiva o un importe no finito produce
409 y explica que la comparación no es calculable; nunca devuelve un falso
resultado dentro de tolerancia.

Crear una licitación exige dependencia convocante explícita, normalizada.
Actualizarla parcialmente no exige reenviarla, pero no permite borrarla.
Los UUID de entrada/salida y los enums leídos de columnas String mantienen
un contrato compatible con la persistencia real. El workspace crea y edita
la planeación con folio, objeto, procedimiento y metadatos en el mismo commit.
El formulario captura y recupera la dependencia. PATCH general excluye estado,
dictamen, fechas del resultado y congelación de bases; rechaza campos extra.
Edición y transición toman el bloqueo de la licitación.

## Verificación

60 pruebas locales aprobadas, 6 omitidas: regresiones nuevas de revisiones y
planeación, autorización, recuperación BIM, índices, SICT y esquemas de
licitaciones. SQLite local; las omisiones incluyen condiciones específicas de
PostgreSQL y paquetes privados. El frontend compila con TypeScript y Vite.

Las pruebas de recuperación BIM ahora registran al actor de la generación,
igual que el router de producción. Se añadió aceptación negativa: una
generación sin actor no puede crear programa. No se relajó la política para
hacer pasar fixtures antiguos.

La aceptación de navegador existente se amplió para abrir el presupuesto de
catálogo, aprobarlo, crear una revisión, modificar su cantidad, recargar y
comparar, verificando que el original conserva importe/cantidad/aprobación y
la revisión conserva consumos y procedencia. Su resultado debe consultarse
en la CI de este commit; no se atribuye a una ejecución local del navegador.

## Límites explícitos

Esto protege los comandos económicos revisados, no instala triggers de
inmutabilidad sobre cada tabla. La referencia entre revisiones se almacena
como procedencia en metadatos, no como una nueva clave foránea. No constituye
una prueba de toda escritura ORM/SQL ni de todos los resultados derivados.

Quedan abiertos los comandos contractuales de finiquito y transición, la
preevaluación vacía/incompleta y sus snapshots, la separación entre simulación
y acto oficial externo, folios concurrentes, costos reales y validación de
storage externo. No se declara el flujo completo de licitación ni la
plataforma listos para producción. No se fusionó ni desplegó este cambio.
