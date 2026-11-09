# Producción: aceptación de firma e.firma / PAdES-LTA

Una firma con CA efímera de CI **no** acredita una e.firma del SAT ni una TSA pública.

## Material de confianza

Mantener el material fuera del repositorio y suministrarlo al host por un canal administrado:

- `roots.pem`: únicamente anclas raíz aprobadas para los certificados FIEL y TSA.
- `intermediates.pem`: certificados intermedios para construir ambas cadenas; nunca convertirlos en trust anchors.
- No almacenar aquí certificados privados, archivos `.key`, contraseñas ni exportaciones privadas.

Montar el directorio en `/run/megalodon/fiel-trust` como solo lectura. Antes de habilitar la firma, inventariar sujeto, emisor, serial, vigencia, huella SHA-256, restricciones CA, usos de clave y EKU de cada certificado, y obtener aprobación del responsable de PKI.

## TSA y revocación

La configuración de ejemplo permite el endpoint RFC 3161 de DigiCert `http://timestamp.digicert.com`. DigiCert informó una sustitución de tres certificados de timestamp el 3 de septiembre de 2026. Antes de producción, descargar desde DigiCert los certificados actuales del responder y su cadena CA, comprobar huellas y vigencias y añadir las anclas/intermedios adecuados al bundle. No fijar un certificado de responder antiguo como raíz.

`FIEL_ALLOW_REVOCATION_FETCHING=false` se mantiene por defecto. Para PAdES-LT/LTA real hay que autorizar expresamente el acceso saliente a endpoints AIA/OCSP/CRL de los certificados de firma y TSA; solo entonces configurar `true`. La política es `require`: falta de evidencia, timeout, estado revocado, cadena no confiable o timestamp inválido impiden la firma.

## Matriz de aceptación antes de Go

1. Ejecutar la prueba de CI con CA efímera y TSA local: tres firmas LT y tres LTA, una actualización de timestamp de archivo y un PDF alterado. Esto valida el código, no la FIEL SAT real.
2. En un entorno aislado con e.firma de pruebas autorizada, firmar tres PDFs con DigiCert RFC 3161 y verificar independientemente la firma CMS, cadena del firmante, cadena TSA, OCSP/CRL incrustados, DSS y DocumentTimeStamp. Repetir cofirma y actualización de timestamp.
3. Probar PDF alterado, certificado expirado, certificado revocado, CA desconocida, respuesta TSA ausente/malformada y OCSP/CRL vencida. Cada caso debe fallar cerrado y no dejar versión firmada publicada.
4. Abrir PDFs con un validador independiente compatible con PAdES y conservar informe, PDFs original/firmado, huellas SHA-256, huellas de certificados y respuesta timestamp. La validación interna de pyHanko no sustituye la aceptación del portal receptor.
5. Ejecutar con los certificados y políticas oficiales del despliegue. El responsable de PKI debe aprobar trust anchors, TSA, egress de revocación y resultados.

Sin e.firma de pruebas autorizada ni bundle oficial aprobado, la prueba real queda bloqueada por insumos de confianza, no por la prueba sintética. Nunca colocar el archivo privado `.key` ni su contraseña en tickets, chats, logs o artefactos CI.
