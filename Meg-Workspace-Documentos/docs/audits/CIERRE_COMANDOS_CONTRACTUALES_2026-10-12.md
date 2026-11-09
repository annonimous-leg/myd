# Comandos contractuales y cierre transaccional

Sobre `73e8fc42330e1c7dcd71ce20773a2d35db8f9c80` se completa otro bloque de
integridad. No implica que la preevaluación/fallo ni todos los módulos estén
listos para producción.

ContratoUpdate rechaza campos extra y ya no admite estado, avances ni
finiquito. El monto/plazo de un contrato vigente cambia mediante convenio,
no edición general. El convenio comprueba estado y valores anteriores cuando
se aportan. Ningún convenio o nueva estimación modifica un contrato cerrado.

Los comandos de edición, transición, convenio, alta y aprobación de estimación
y finiquito toman el bloqueo de la fila contractual. Las dos interfaces de
terminación llaman al mismo servicio: estimaciones presentes y aprobadas,
avance físico y financiero completo. Una terminación sin esas condiciones
se rechaza antes de cambiar el estado.

El finiquito tiene comando propio y exige rol aprobador, estado TERMINADO o
RESCINDIDO y todas las estimaciones aprobadas. Calcula en Decimal la suma de
los importes ejecutados registrados; fecha, importe y CERRADO se guardan en
un solo commit. No acepta un importe libre desde PATCH. Esta suma representa
el cierre administrativo implementado actualmente; no certifica por sí sola
un finiquito oficial, pagos, retenciones o penalizaciones de una autoridad.
La separación documental de actos oficiales sigue pendiente.

La aprobación de una estimación hace flush antes de consultar el agregado:
producción desactiva autoflush, por lo que antes la consulta podía omitir la
estimación recién aprobada y mantener un avance atrasado. Se verifica con
sesión sin autoflush, no solamente con la configuración más permisiva del test.

19 pruebas locales aprobadas: recorrido autenticado por ambas interfaces,
rechazo de campos sensibles, creación, estimación, aprobación, terminación,
finiquito y protección después del cierre, además de esquemas/API existentes.
Los UUID y enums de contratos también se serializan según los valores realmente
leídos de la base. La CI ejecuta la integración con PostgreSQL; esto no demuestra
por sí solo ausencia de carreras. No se ha ensayado carga concurrente de este
comando en producción.

La CI del bloque anterior encontró una expectativa antigua de mensaje en una
prueba topográfica: el presupuesto aprobado ahora se rechaza antes por
inmutabilidad. Se actualiza esa expectativa y se comprueba adicionalmente que
una revisión borrador conserva la evidencia topográfica y sigue impidiendo
editar/borrar las cantidades medidas. No se elimina esa protección.

La ejecución 38238529495 aprobó siete de ocho jobs, incluida la aceptación en
navegador. El único fallo fue la regla estructural contra `pass` en producto:
el workspace declaraba una subclase vacía de FiniquitoCreate. Se elimina esa
declaración redundante y ambas rutas usan directamente el mismo esquema.
