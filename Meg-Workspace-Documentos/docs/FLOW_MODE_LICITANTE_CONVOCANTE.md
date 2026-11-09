# flow_mode: LICITANTE vs CONVOCANTE

## Contrato API

`POST /procurement/recommend-procedure`

```json
{
  "jurisdiction_code": "MX-FED-OBRA",
  "monto": 2500000,
  "es_obra_publica": true,
  "presupuesto_dependencia_miles": 20000,
  "flow_mode": "CONVOCANTE",
  "procedure_type_declared": null
}
```

| flow_mode | presupuesto Anexo 9 | materializa procedure_type | uso |
|-----------|---------------------|----------------------------|-----|
| **LICITANTE** | No requerido | **Nunca** | Armar propuesta ante convocatoria publicada |
| **CONVOCANTE** | Obligatorio si federal | Sí, si VERIFICADO y no CANDIDATO | Planeación antes de publicar |

Si LICITANTE + `procedure_type_declared` (o tender ya tiene procedure_type):
respuesta inmediata `fuente=CONVOCATORIA_DECLARADA` sin recalcular umbrales.

## Seriedad

LegalRule `GARANTIA-SERIEDAD-PROPUESTA`:
- `activation=CONVOCATORIA_OR_CASE_PACK`
- `MotorGarantias.resolve_seriedad(seriedad_required=False)` → no aplica
- Solo calcula monto si `seriedad_required=True` **y** hay `%` de la convocatoria

No existe 5% hardcodeado.
