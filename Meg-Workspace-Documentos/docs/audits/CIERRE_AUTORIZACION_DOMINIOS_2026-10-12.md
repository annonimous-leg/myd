# Autoridad de comandos y estado de expedientes

Base: `cd9bf27c82e6c2e872cc57313ed703c803c14ad3`, cuya ejecución
Security Hardening 38185439703 terminó correctamente en sus ocho jobs.
Las dos auditorías aportadas por el usuario se contrastaron con el código.

## Decisión de arquitectura

Se reutilizan los roles existentes del producto mediante una política común
pequeña (`core.authorization`). No se crea un motor monolítico ni se mueven
los cálculos de los servicios de dominio. Escribir requiere técnico, revisor
o administrador; aprobar requiere revisor o administrador. Superadmin sigue
limitado a la organización explícita del comando. Acciones desconocidas,
identidad ausente, actor inactivo u organización inactiva se deniegan.

Las llamadas internas resuelven el actor persistido; los identificadores de
autor no sirven únicamente como metadatos de auditoría. La política no
sustituye las consultas por recurso y tenant ni los entitlements existentes.

## Cambios de este bloque

- Los routers de expedientes normal y avanzado, catálogo APU, licitaciones,
  workspace de licitaciones, contratos y programación declaran la misma
  dependencia de autorización de escrituras.
- Los comandos de catálogo, licitaciones y contratos comprueban el actor
  también dentro del servicio. Aprobaciones de entregables, convenios,
  penalizaciones y transiciones contractuales requieren rol aprobador.
- Programación recibe actor explícito tanto desde HTTP como desde BIM 4D;
  creación, edición, avances y cálculos que persisten resultados usan la
  misma política. La consulta del programa conserva el tenant del servicio.
- Los dos caminos de estado de expediente llaman al mismo comando del
  servicio. Se elimina el mapa que referenciaba estados inexistentes. El
  comando bloquea la fila, conserva historial y registra al actor. Cerrar
  requiere aprobación, mientras las transiciones de trabajo admiten técnico.

## Verificación local

33 pruebas de política, adaptadores, expedientes y contratos/licitaciones
aprobadas. Dos pruebas de programación aprobadas: grafo mixto PERT con
persistencia real y rollback al rechazar un ciclo. La prueba PERT anterior
usaba objetos simulados; ahora crea usuario, expediente, programa y tareas
en la base de prueba y ejecuta los servicios reales.

La matriz cubre los seis roles, acciones desconocidas, organización
incorrecta, actor ausente, organización inactiva, conservación del acceso de
lectura y respuestas 403 para lector e invitado. Se verifica además que
todas las rutas de mutación de esos siete routers declaran la dependencia.
Esto no constituye una auditoría de todos los routers del repositorio.

Estas pruebas locales usan SQLite y el modo de desarrollo sin Redis; la
concurrencia y las migraciones PostgreSQL deben validarse en la CI del nuevo
commit. No se ejecutaron acciones contra datos de producción.

## Pendientes distintos de autorización

La actualización genérica de estados de licitaciones/contratos, los contratos
Pydantic de planeación, los snapshots de evaluación, la distinción entre
preevaluación y resultado oficial, y la inmutabilidad/revisión de presupuestos
requieren sus propios cambios de dominio. Este bloque no los declara cerrados.

La observación consolidada sobre contratos es correcta: en la base revisada
`EN_FIRMA → CERRADO` sí figura en la tabla de transiciones. El problema de
la escritura genérica sigue existiendo, pero aquel ejemplo no lo demuestra.
También se confirmó que la CI tiene ocho jobs, no nueve.
