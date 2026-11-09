"""Actualización de estimaciones a partir de niveles de una misma serie."""
import hashlib
import json
from decimal import ROUND_HALF_UP, Decimal, localcontext


def actualizar_precio(precio: Decimal, base: Decimal, destino: Decimal) -> Decimal:
    if any(not value.is_finite() or value <= 0 for value in (precio, base, destino)):
        raise ValueError('Precio y niveles deben ser positivos y finitos')
    with localcontext() as context:
        context.prec = 50
        resultado = (precio * destino / base).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    if resultado <= 0 or resultado >= Decimal('10000000000000000'):
        raise ValueError('Precio actualizado fuera del rango monetario del presupuesto')
    return resultado


def sellar_snapshot(datos: dict) -> dict:
    datos = {key: value for key, value in datos.items() if key != 'sha256'}
    digest = hashlib.sha256(json.dumps(datos, sort_keys=True, ensure_ascii=False,
                                      separators=(',', ':'), allow_nan=False).encode()).hexdigest()
    return {**datos, 'sha256': digest}


def verificar_snapshot(snapshot: dict, precio: Decimal) -> None:
    if snapshot.get('version') != 1 or snapshot.get('sha256') != sellar_snapshot(snapshot)['sha256']:
        raise ValueError('Instantánea de actualización alterada o incompatible')
    calculado = actualizar_precio(Decimal(snapshot['precio_original']),
                                 Decimal(snapshot['base']['valor']), Decimal(snapshot['destino']['valor']))
    if calculado != precio or calculado != Decimal(snapshot['precio_actualizado']):
        raise ValueError('El precio persistido no corresponde a su evidencia de actualización')
