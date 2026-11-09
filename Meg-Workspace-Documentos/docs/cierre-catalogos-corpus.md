# Cierre de catálogos y corpus — 6 de octubre de 2026

El usuario mantiene el frontend actual y pospone el motor DWG propio hasta el final.
Este bloque verifica el workspace y la automatización existentes, muestra el inventario
de la base conectada y permite obtener la última estimación observada de un material.

Interfaces de verificación: API HTTP autenticada de índices y consultas públicas del
motor de búsqueda legal. Se reutilizan los contratos y ensayos anteriores de workspace.

La selección automática utiliza la misma serie y versión metodológica revisada del
material, su mes base y publicaciones disponibles hasta una fecha de corte. Se rechazan
ediciones ambiguas; se conserva la selección explícita. El precio original, los
presupuestos existentes y sus instantáneas no cambian. No se extrapola el mes actual.

El inventario distingue conceptos, insumos, materiales y correspondencias del tenant.
Activo no significa certificado: estos modelos no contienen una revisión documental
uniforme. No se da por recuperado el catálogo de Supabase sin consultar esa base.

La cobertura del corpus se calcula sobre los archivos efectivamente consultados.
Informa textos sin segmentar, saltos y huellas; no certifica vigencia normativa ni
convierte artículos extraídos en reglas ejecutables. Los textos DOF almacenados por
separado no se cuentan como artículos consultables en LEGL.

El recorrido real debe abrir Costos tras recargar sin errores de render ni pérdida
del expediente seleccionado. La selección se consulta por identidad cuando queda
fuera de la primera página; un error de red no se interpreta como eliminación.
