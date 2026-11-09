# Planos IFC en PDF A3

Esta entrega parte del respaldo completo del 3 de noviembre. Los tres
archivos modificados por la PR46 en ese respaldo coincidían con su cabeza
`6f0751e6c84a4a1e28644244c654cb5e9c25e675` antes de integrar el PDF.

## Solicitud y descarga

Solicita el formato `PDF` en el arreglo `formatos` de
`POST /api/v1/bim/{expediente_id}/modelos/{modelo_id}/dibujos`. Se puede
combinar con `SVG` y `DXF`. Para clientes existentes, omitir el arreglo
sigue solicitando SVG y DXF. La elevación de planta o el plano de corte
se especifican con los parámetros normales de la API, en metros.

El worker genera una lámina A3 horizontal usando la geometría IFC
cuantificada del modelo, los datos del expediente y el título solicitado.
La escala se elige según la extensión de la geometría. Los cortes sin
geometría generan un error explícito al solicitar PDF. Las cotas exteriores
se basan en la extensión del dibujo. La lámina omite orientación norte
hasta que pueda derivarse de una referencia verificada del modelo.

Cuando el dibujo esté completado, solicita
`GET /api/v1/bim/{expediente_id}/modelos/{modelo_id}/dibujos/{dibujo_id}/descarga?formato=PDF`.
La descarga aplica los permisos del expediente y devuelve la URL firmada
del PDF en el bucket privado. El estado del dibujo expone `sha256_pdf`.
La generación y limpieza usan el mismo trabajo durable de SVG y DXF.

## Verificación y despliegue

1. Aplica `alembic upgrade head` con la conexión de migraciones. La revisión
   `20261105_bim_drawing_pdf` añade dos columnas anulables para conservar
   compatibilidad con los dibujos existentes.
2. Despliega API, dispatcher y workers de la misma revisión. Comprueba que
   el bucket privado BIM permita `application/pdf`.
3. Ejecuta las pruebas de dibujo y costeo en PostgreSQL/PostGIS y verifica
   carga, job, descarga firmada y denegación entre tenants con el bucket
   de preproducción. La comprobación local usa SQLite y storage simulado.
4. Para cargas públicas de IFC, valida el despliegue del worker con límites
   de recursos y prueba el aislamiento con archivos adversos.

Los presupuestos siguen usando el flujo existente de cantidades BIM, APU
y cantidades complementarias. El PDF de dibujo es un artefacto del modelo.
