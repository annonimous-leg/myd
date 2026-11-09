# Parámetros de costeo explícitos y trazables

Presupuesto, BIM y topografía ya no aplican porcentajes económicos implícitos.
Todo cálculo nuevo recibe un `ParametrosCosteoSnapshot` inmutable con los
factores de indirectos, utilidad, impuesto y riesgo; fuente, referencia,
vigencia, jurisdicción, evidencia y una huella SHA-256 determinista.

Los cuatro factores se limitan a cuatro decimales, igual que las columnas
`NUMERIC(8,4)`, para que el valor firmado, calculado y persistido sea idéntico.
La evidencia se copia a una estructura profundamente inmutable antes de
calcular la huella.

El presupuesto conserva las columnas numéricas y el snapshot completo en
`metadatos.parametros_costeo`. Recalcular o exportar verifica la huella y la
igualdad de las cuatro columnas; cualquier divergencia falla cerrado.

La migración no adjudica procedencia ficticia a históricos. Éstos conservan
sus montos y deben regularizarse mediante:

`PUT /api/v1/presupuestos/{expediente_id}/presupuestos/{presupuesto_id}/parametros-costeo`

Un presupuesto `VALIDADO` o `APROBADO` no admite sustitución en sitio.
Procurement exige los cuatro factores y `economic.source` cuando hay partidas.
El puente presupuesto → procurement verifica y reutiliza el mismo snapshot;
un histórico sin procedencia se detiene con instrucciones de regularización.

