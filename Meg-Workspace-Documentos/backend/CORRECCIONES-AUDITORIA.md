# Correcciones de auditoría

Base de origen: `Meg-BIM-PDF-A3.zip`. La entrega conserva el proyecto completo.

## Cambios

- El presupuesto BIM guarda cabecera, partidas y enlaces de elementos en una transacción. La API admite `Idempotency-Key`: conserva el mismo resultado para una repetición del cuerpo con la misma clave y devuelve 409 si el cuerpo cambia. La clave se acota a usuario, tenant, expediente y modelo. El cliente que reintenta debe conservarla.
- Las partidas BIM en m² requieren cantidad revisada y referencia. El área IFC sigue disponible para consulta. No se usa como superficie intercambiable de APU. Las partidas pendientes permanecen en borrador. Los presupuestos BIM históricos en m² requieren revisión antes de avanzar a estados de cálculo, validación o aprobación. La programación 4D deja de imputar el área genérica a partidas con cobertura BIM.
- Ante una excepción en el commit de la carga IFC, otra sesión comprueba si se guardó el modelo antes de borrar el objeto. Si el resultado sigue sin poder determinarse, se conserva el objeto y se registra el incidente.
- Checkout y cancelación requieren administración activa del tenant. Stripe correlaciona Checkout Session con Subscription y toma su periodo de la respuesta del proveedor, con soporte para campos de periodo a nivel de ítem. Configurar los eventos de checkout y suscripción y ensayar el flujo en modo de prueba antes de activar facturación. Los checkouts históricos con sesión sin correlacionar necesitan reproducir el evento correspondiente.
- Compose de producción declara una cola y un contenedor IFC dedicados, con una tarea simultánea, CPU y memoria configurables. El dispatcher aplica `IFC_PROCESSING_TIMEOUT_SECONDS`. La API de producción recibe un tope IFC configurable, con 100 MiB por defecto. Los otros trabajos conservan su cola general.
- El visor BIM permite solicitar una planta PDF A3 con título y cota de corte, consultar su estado y descargarla. Se mantiene el API existente para los otros tipos de dibujo.
- La bitácora normaliza la fecha antes de compararla en el control de orden temporal.

## Verificación y pendientes de operación

- La verificación local usa SQLite y adaptadores simulados para Storage y Stripe. No se ejecutaron migraciones, pagos ni operaciones de Storage contra un proyecto real.
- Validar el Compose con Docker, ejecutar migrations y probar la cola dedicada con PostgreSQL/PostGIS, Redis y Supabase de preproducción. El límite de contenedor reduce el impacto sobre el resto del servicio. La descarga IFC aún se materializa completa y el parser sigue en un proceso con credenciales del worker. Un sandbox del parser con menores privilegios y la limpieza durable de objetos ante indisponibilidad siguen pendientes.
- La generación 4D aún usa los vínculos actuales del modelo. La selección de revisión histórica de presupuesto y un juego multipágina de planos siguen pendientes.
- La vigencia de Mercado Pago conserva la política anterior. Hace falta validar su periodo autoritativo y ensayar el proveedor antes de monetizar.
