# Importación de niveles mensuales revisados

La importación administra archivos originales JSON de la API INEGI 2.0. No descarga datos, no necesita guardar un token y no determina por sí sola que un archivo sea auténtico. El superadministrador revisa el origen y los catálogos de metadatos antes de habilitar una serie. La aplicación verifica después que los bytes, metadatos, meses y niveles coincidan con esa revisión.

## Evidencia consultada y límites

- [API oficial y ejemplos de INEGI](https://www.inegi.org.mx/servicios/api_indicadores.html): `Series`, metadatos separados de observaciones y catálogos `CL_*`. La API requiere un token propio. No usar tokens de ejemplos o de terceros.
- [Programa actualizado INPP 2025](https://www.inegi.org.mx/programas/inpp/2019a/): conserva base julio de 2019, pero corresponde a una metodología actualizada. No unir ediciones únicamente por compartir la base.
- [Calendario oficial 2026](https://www.inegi.org.mx/contenidos/saladeprensa/doc/cal_2026.pdf): septiembre se publica el 8 de octubre. Al corte del 5 de octubre no se registra septiembre como observado publicado.
- La descarga abierta del [programa anterior](https://www.inegi.org.mx/programas/inpp/2019/) fue inspeccionada: `conjunto_de_datos_inpp_mensual_csv.zip`, 31 427 bytes, SHA256 `4898ba79d3af12f0259241e8678bdeb3f8d5f2a9a1a47fdd208ca6ea05aaf9ca`. Contiene 1626 filas, seis agregados nacionales, enero de 2003 a julio de 2025 y celdas iniciales vacías. **No contiene las familias de materiales de 2026 requeridas; no se activó.** Algunos valores conservan 17 decimales, motivo de ampliar la columna de niveles.
- El informe CEICO de junio adjunto comunica variaciones anuales mayo 2025–mayo 2026 y condiciones diferentes para precios productor y construcción. No convertir esos porcentajes en una trayectoria enero–septiembre. El informe de simulación APU adjunto tampoco acredita niveles oficiales.
- [SQLAlchemy: transacciones](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html), [FastAPI: formularios y archivos](https://fastapi.tiangolo.com/tutorial/request-forms-and-files/) y [Python: JSON](https://docs.python.org/3/library/json.html) fundamentan la separación entre contrato, archivo acotado y transacción. Se rechazan claves duplicadas y constantes no finitas que el decodificador JSON de Python permite por defecto.

## Registro y carga

1. Crear una nueva versión de serie mediante `POST /api/v1/indices-costos/series`. `codigo` debe coincidir con el indicador original. `contrato_inegi` fija los códigos originales de frecuencia, unidad, multiplicador, tema, fuente, notas, estatus y cobertura; la revisión acredita nivel mensual de material a escala unidad. Conservar evidencia de los catálogos usados. No deducir códigos por el nombre de un material.
2. Preparar el archivo JSON original, una referencia pública del programa INPP, su SHA256 calculado sobre los bytes, fecha de publicación de esa edición, texto exacto `LASTUPDATE` y meses inicial/final. `LASTUPDATE` no se interpreta como la fecha original de publicación de cada mes.
3. `POST /api/v1/indices-costos/cargas/inegi` recibe multipart: `archivo` y `metadatos` (JSON de `CargaINEGIInput`). Con `confirmar=false`, valor predeterminado, valida sin escribir. Con `confirmar=true`, valida otra vez y registra archivo y todas las observaciones en una sola transacción. El preview no reserva una edición.
4. Seleccionar IDs explícitos de observaciones y correspondencia en el flujo de presupuesto existente. Una carga no crea correspondencias por nombre, no cambia el catálogo y no repricia presupuestos emitidos.
5. `GET /api/v1/indices-costos/cargas/{carga_id}/archivo` permite al superadministrador descargar exactamente los bytes auditados. No se publica el archivo en GitHub ni se expone a otros roles.

## Rechazos y revisiones

El límite es 2 MiB y 5000 observaciones por archivo. Se exige exactamente una serie, campos del formato documentado, metadatos y estados revisados, periodos mensuales, cobertura completa del intervalo elegido y niveles positivos finitos menores a 10 mil millones. Se admiten hasta 20 decimales sin convertir a `float`. Una observación ausente, provisional no revisada, un duplicado o una colisión revierte el lote completo; no se interpola ni se sustituye por inflación global. Los meses fuera del intervalo explícito no se activan.

Una repetición del mismo archivo y revisión devuelve la carga existente. Cambiar fechas, intervalo o evidencia del mismo archivo provoca conflicto: primero revisar la edición deseada. La retirada es independiente y permanece vigente aunque se repita la carga; la respuesta distingue cargas con observaciones retiradas. Una publicación oficial distinta conserva su propio archivo y hash, y no borra ediciones anteriores. Las correcciones de captura conservan el mecanismo explícito de retiro y sucesión existente.

La migración `20261005_ingesta_inegi` amplía niveles de `NUMERIC(18,8)` a `NUMERIC(30,20)`, conserva los datos anteriores, agrega contratos opcionales a las series y archivos inmutables. No crea contratos para series históricas ni inventa niveles. Las tablas de evidencia rechazan UPDATE, DELETE y TRUNCATE en PostgreSQL. La recuperación compara valores históricos con su escala original al verificar esta ampliación.

PostgreSQL también calcula el SHA256 de los bytes con su función nativa y exige coincidencia con la huella registrada. Una clave foránea compuesta exige que cada observación importada coincida en archivo, serie, SHA y fecha de edición. Estas restricciones cubren inserciones SQL que no pasan por el servicio.

## Pendiente para activar costos reales

Obtener archivos de las series materiales actuales y sus metadatos, acreditar fecha y condiciones de cada catálogo, y revisar correspondencias por insumo. No hay códigos o niveles oficiales precargados en este bloque. Las pruebas usan códigos y documentos expresamente sintéticos. La carga validada no acredita cobertura de los catálogos ni disponibilidad de salarios/FASAR, maquinaria o divisas: requieren sus modelos y fuentes propios.
