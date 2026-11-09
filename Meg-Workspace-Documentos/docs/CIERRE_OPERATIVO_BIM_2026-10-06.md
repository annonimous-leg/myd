# Cierre operativo BIM

Base de revisión: `009dd6755abfb81aa4d0f2e849efcb8aa9eab931`.

Solicitud: cerrar PostgreSQL/PostGIS, recuperación de trabajos y el recorrido
completo en pantalla. Mantener el centro de mando actual; facilitar la operación
sin sustituir todo el frontend ni incorporar DWG en este bloque.

## Criterios

- Modelo/análisis/generación y orden de trabajo se guardan en una transacción.
- Un publicador independiente de Redis recupera órdenes después de una caída.
- Entrega repetida no duplica elementos, análisis ni programas; el resultado y
  la finalización del trabajo se confirman juntos.
- Errores temporales tienen reintentos acotados; fallos definitivos visibles y
  reintento explícito conservando la identidad del trabajo.
- Pruebas en las interfaces autorizadas: HTTP BIM, publicador/ejecutor durable
  con DB y Redis, y navegador con API/worker/archivos reales. Sin sustituciones
  de endpoints en el recorrido de aceptación.
- Reabrir BIM recupera modelos del expediente y presenta el siguiente paso.
- Cantidades → catálogo → presupuesto → validación/aprobación → Excel/PDF →
  cronograma accesibles con etiquetas claras y controles según permisos.
- Validación migrada PostgreSQL/PostGIS y evidencia de navegador en CI.

Datos de aceptación sintéticos identificados como tales; no son catálogos ni
precios de obra certificados. Supabase real requiere credenciales del entorno.

## Costeo de grupos incompletos

Un grupo incompleto conserva el subtotal de sus elementos medidos; los
elementos sin la cantidad requerida forman una partida pendiente separada.
El presupuesto guarda cobertura por modelo y permanece parcial/BORRADOR.
Editar cantidades o recalcular no borra esa cobertura ni habilita aprobación.
Excel y PDF muestran explícitamente el carácter parcial.

Cada faltante puede completarse en pantalla en la unidad del APU con una
referencia de medición. El servidor valida pertenencia al modelo/tenant,
unidad, cantidad positiva finita y usuario responsable. Guarda usuario,
fecha y referencia en la nueva versión sin modificar las cantidades IFC.
Las capturas también alimentan el costo de las actividades 4D vinculadas.
No se fabrican cantidades para elementos sin QTO ni geometría válida.

No están certificados por este bloque: Supabase real sin credenciales,
catálogos adjuntos ni publicaciones INEGI, todos los motores de topografía,
interferencias, jurídico, fiscalización y Tezcatlipoca, ni carga de modelos
grandes/múltiples usuarios en un despliegue completo.
