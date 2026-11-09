# Copyright © 2026 Cristian Rodriguez
# All rights reserved.
# Unauthorized copying, modification, distribution, or use is prohibited
# without prior written permission.

"""
Motor de costeo y presupuestos programables.
Portado de Megalodon v3.1 (megalodon_costos_v3_1.py, clases ConceptoAPU /
MotorPreciosBIM) hacia una arquitectura de dataclasses con Decimal.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from decimal import Decimal, ROUND_HALF_UP
import math

from app.core.constants import CONSTANTES
from app.core.errors import MegalodonException, ErrorCode
from app.engines.costos.parametros import ParametrosCosteoSnapshot

TWO_PLACES = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class InsumoCosteo:
    """Insumo para cálculo de costos (material, mano de obra, equipo...)."""
    clave: str
    descripcion: str
    tipo: str  # MATERIAL, MANO_OBRA, EQUIPO, SUBCONTRATO, HERRAMIENTA
    unidad: str
    cantidad: Decimal
    precio_unitario: Decimal
    rendimiento: Decimal = Decimal("1.0")
    actualizacion_precio: Optional[dict] = None

    @property
    def importe(self) -> Decimal:
        return _money(self.cantidad * self.precio_unitario)


@dataclass
class ConceptoCosteo:
    """Concepto APU (Análisis de Precios Unitarios).

    `cantidad` es la relación de este concepto dentro de la partida que lo
    contiene (p.ej. 1 m2 de muro puede requerir 1.0 de "block" + 0.02 de
    "acero de refuerzo" como conceptos separados). Para el caso simple de
    un solo concepto por partida, cantidad=1.0 (default).
    """
    clave: str
    descripcion: str
    unidad: str
    cantidad: Decimal = Decimal("1.0")
    insumos: List[InsumoCosteo] = field(default_factory=list)

    @property
    def costo_directo_unitario(self) -> Decimal:
        if not self.insumos:
            return Decimal("0.00")
        return _money(sum((i.importe for i in self.insumos), Decimal("0.00")))

    @property
    def costo_directo(self) -> Decimal:
        """Alias retrocompatible: costo directo unitario de este concepto."""
        return self.costo_directo_unitario


@dataclass
class PartidaCosteo:
    """Partida de presupuesto para costeo.

    precio_unitario_manual: cuando la partida viene de un tabulador
    gubernamental (p.ej. el tabulador CDMX importado) el precio unitario
    YA es un dato final del catálogo oficial — no debe recalcularse desde
    conceptos/insumos. En ese caso se fija este campo y la propiedad
    `precio_unitario` lo respeta tal cual, sin tocar indirectos/utilidad
    a nivel de concepto (esos factores se aplican una sola vez, a nivel
    de todo el presupuesto, para evitar doble aplicación de indirectos).
    """
    numero: int
    descripcion: str
    unidad: str
    cantidad: Decimal
    conceptos: List[ConceptoCosteo] = field(default_factory=list)
    precio_unitario_manual: Optional[Decimal] = None
    origen_catalogo: Optional[dict] = None

    @property
    def precio_unitario(self) -> Decimal:
        if self.precio_unitario_manual is not None:
            return _money(self.precio_unitario_manual)
        if not self.conceptos:
            return Decimal("0.00")
        # BUG ORIGINAL: solo usaba self.conceptos[0].costo_directo, así que
        # cualquier partida con más de un concepto (ej. "muro" = block +
        # acero + aplanado como conceptos separados) perdía silenciosamente
        # el costo de todos los conceptos menos el primero.
        total = sum(
            (c.costo_directo_unitario * c.cantidad for c in self.conceptos),
            Decimal("0.00"),
        )
        return _money(total)

    @property
    def importe(self) -> Decimal:
        return _money(self.cantidad * self.precio_unitario)


@dataclass
class PresupuestoCosteo:
    """Presupuesto completo para costeo."""
    identificador: str
    nombre: str
    parametros: ParametrosCosteoSnapshot
    partidas: List[PartidaCosteo] = field(default_factory=list)
    cobertura_bim: Optional[dict] = None
    evidencia_topografia: Optional[dict] = None

    @property
    def factor_indirecto(self) -> Decimal:
        return self.parametros.factor_indirecto

    @property
    def factor_financiamiento(self) -> Decimal:
        return self.parametros.factor_financiamiento

    @property
    def factor_utilidad(self) -> Decimal:
        return self.parametros.factor_utilidad

    @property
    def factor_cargos_adicionales(self) -> Decimal:
        return self.parametros.factor_cargos_adicionales

    @property
    def factor_impuesto(self) -> Decimal:
        return self.parametros.factor_impuesto

    @property
    def factor_riesgo(self) -> Decimal:
        return self.parametros.factor_riesgo

    @property
    def monto_directo(self) -> Decimal:
        if not self.partidas:
            return Decimal("0.00")
        return _money(sum((p.importe for p in self.partidas), Decimal("0.00")))

    @property
    def monto_indirecto(self) -> Decimal:
        return _money(self.monto_directo * self.factor_indirecto)

    @property
    def subtotal(self) -> Decimal:
        """Costo directo + indirecto, base del financiamiento."""
        return _money(self.monto_directo + self.monto_indirecto)

    @property
    def monto_financiamiento(self) -> Decimal:
        # RLOPSRM art. 214: porcentaje sobre costos directos + indirectos.
        return _money(self.subtotal * self.factor_financiamiento)

    @property
    def base_utilidad(self) -> Decimal:
        # RLOPSRM art. 219: utilidad sobre directo + indirecto + financiamiento.
        return _money(self.subtotal + self.monto_financiamiento)

    @property
    def monto_utilidad(self) -> Decimal:
        return _money(self.base_utilidad * self.factor_utilidad)

    @property
    def monto_riesgo(self) -> Decimal:
        # Contingencia contractual/empresarial separada del esquema
        # reglamentario; se conserva por compatibilidad y trazabilidad.
        return _money(self.subtotal * self.factor_riesgo)

    @property
    def base_cargos_adicionales(self) -> Decimal:
        # RLOPSRM art. 220: cargos adicionales se calculan después de la utilidad.
        # La reserva de riesgo del modelo es contingencia empresarial y no forma
        # parte de esta base reglamentaria.
        return _money(self.base_utilidad + self.monto_utilidad)

    @property
    def monto_cargos_adicionales(self) -> Decimal:
        return _money(self.base_cargos_adicionales * self.factor_cargos_adicionales)

    @property
    def base_impuesto(self) -> Decimal:
        # La contingencia de riesgo permanece como componente separado de la base
        # fiscal del modelo, pero no compone el porcentaje de cargos adicionales.
        return _money(self.base_cargos_adicionales + self.monto_cargos_adicionales + self.monto_riesgo)

    @property
    def monto_impuesto(self) -> Decimal:
        return _money(self.base_impuesto * self.factor_impuesto)

    @property
    def monto_total(self) -> Decimal:
        return _money(self.base_impuesto + self.monto_impuesto)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "identificador": self.identificador,
            "nombre": self.nombre,
            "monto_directo": float(self.monto_directo),
            "monto_indirecto": float(self.monto_indirecto),
            "monto_financiamiento": float(self.monto_financiamiento),
            "monto_utilidad": float(self.monto_utilidad),
            "monto_riesgo": float(self.monto_riesgo),
            "monto_cargos_adicionales": float(self.monto_cargos_adicionales),
            "monto_impuesto": float(self.monto_impuesto),
            "monto_total": float(self.monto_total),
            "factor_indirecto": float(self.factor_indirecto),
            "factor_financiamiento": float(self.factor_financiamiento),
            "factor_utilidad": float(self.factor_utilidad),
            "factor_cargos_adicionales": float(self.factor_cargos_adicionales),
            "factor_impuesto": float(self.factor_impuesto),
            "factor_riesgo": float(self.factor_riesgo),
            "parametros_costeo": self.parametros.to_dict(),
            "partidas": [
                {
                    "numero": p.numero,
                    "descripcion": p.descripcion,
                    "unidad": p.unidad,
                    "cantidad": float(p.cantidad),
                    "precio_unitario": float(p.precio_unitario),
                    "importe": float(p.importe),
                }
                for p in self.partidas
            ],
        }


class MotorCosteo:
    """Motor principal de costeo."""

    def __init__(self):
        self.constantes = CONSTANTES

    def calcular_presupuesto(self, presupuesto: PresupuestoCosteo) -> PresupuestoCosteo:
        """Fuerza la evaluación de todas las propiedades calculadas.

        Las propiedades ya son la fuente de verdad (se recalculan solas
        cada vez que se leen), así que esto solo sirve para "tocar" el
        objeto y detectar errores de datos temprano.
        """
        _ = presupuesto.monto_total
        return presupuesto

    def validar_sobrecostos(
        self,
        presupuesto_actual: PresupuestoCosteo,
        presupuesto_base: PresupuestoCosteo,
    ) -> Dict[str, Any]:
        """Valida sobrecostos vs presupuesto base."""
        sobrecosto = presupuesto_actual.monto_total - presupuesto_base.monto_total
        factor = (
            sobrecosto / presupuesto_base.monto_total
            if presupuesto_base.monto_total
            else Decimal("0")
        )

        return {
            "presupuesto_base": float(presupuesto_base.monto_total),
            "presupuesto_actual": float(presupuesto_actual.monto_total),
            "sobrecosto": float(sobrecosto),
            "factor_sobrecosto": float(factor),
            "dentro_tolerancia": factor <= Decimal(str(self.constantes.TOLERANCIA_FACTOR_SOBRECOSTO)),
            "tolerancia_permitida": self.constantes.TOLERANCIA_FACTOR_SOBRECOSTO,
        }

    def generar_excel(self, presupuesto: PresupuestoCosteo) -> bytes:
        """Genera archivo Excel del presupuesto."""
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Font, Alignment, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Presupuesto"

        headers = ["No.", "Descripción", "Unidad", "Cantidad", "P.U.", "Importe"]
        ws.append(headers)

        header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        for p in presupuesto.partidas:
            ws.append([
                p.numero,
                p.descripcion,
                p.unidad,
                float(p.cantidad),
                float(p.precio_unitario),
                float(p.importe),
            ])

        ws.append(["", "", "", "", "COSTO DIRECTO:", float(presupuesto.monto_directo)])
        ws.append(["", "", "", "", "INDIRECTO:", float(presupuesto.monto_indirecto)])
        if presupuesto.factor_financiamiento:
            ws.append(["", "", "", "", "FINANCIAMIENTO:", float(presupuesto.monto_financiamiento)])
        ws.append(["", "", "", "", "UTILIDAD:", float(presupuesto.monto_utilidad)])
        if presupuesto.factor_riesgo:
            ws.append(["", "", "", "", "RIESGO:", float(presupuesto.monto_riesgo)])
        if presupuesto.factor_cargos_adicionales:
            ws.append(["", "", "", "", "CARGOS ADICIONALES:", float(presupuesto.monto_cargos_adicionales)])
        ws.append(["", "", "", "", "IVA:", float(presupuesto.monto_impuesto)])
        ws.append(["", "", "", "", "TOTAL:", float(presupuesto.monto_total)])

        ws.column_dimensions["A"].width = 8
        ws.column_dimensions["B"].width = 50
        ws.column_dimensions["C"].width = 12
        ws.column_dimensions["D"].width = 15
        ws.column_dimensions["E"].width = 15
        ws.column_dimensions["F"].width = 18
        for row in ws.iter_rows(min_row=2):
            # Catalogue text is data, never an executable spreadsheet formula.
            for column in (1, 2):
                if isinstance(row[column].value, str):
                    row[column].data_type = 's'

        actualizaciones = [i for p in presupuesto.partidas for c in p.conceptos
                           for i in c.insumos if i.actualizacion_precio]
        if any(p.origen_catalogo for p in presupuesto.partidas):
            sources = wb.create_sheet('Fuentes de precio')
            sources.append(['Partida', 'Catálogo ID', 'Clave', 'Descripción', 'Unidad', 'Fuente',
                'Vigencia inicio', 'Vigencia fin', 'Zona', 'Precio observado MXN', 'Precio aplicado MXN', 'Evidencia SHA256',
                'PDF original SHA256', 'Páginas PDF', 'Paquete SHA256', 'Fila SHA256', 'Revisión'])
            for p in sorted(presupuesto.partidas, key=lambda p: p.numero):
                source = p.origen_catalogo
                if source:
                    origin = source.get('origen_importacion') or {}
                    sources.append([p.numero, *[source[key] for key in ('catalogo_id', 'clave', 'descripcion', 'unidad',
                        'fuente', 'vigencia_inicio', 'vigencia_fin', 'zona_economica', 'precio_observado', 'precio_aplicado', 'sha256')],
                        (origin.get('fuente') or {}).get('sha256'), ','.join(origin.get('paginas', [])),
                        origin.get('paquete_sha256'), origin.get('fila_sha256'), origin.get('revision')])
            for row in sources:
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = 's'
            sources.column_dimensions['D'].width = 55
            sources.column_dimensions['F'].width = 35
        if actualizaciones:
            evidencia = wb.create_sheet('Actualizacion materiales')
            evidencia.append(['Insumo', 'Serie', 'Mes base', 'Mes destino', 'Precio original MXN',
                              'Precio estimado MXN', 'Nivel base', 'Nivel destino',
                              'Documento base SHA256', 'Documento destino SHA256', 'Snapshot SHA256'])
            for i in actualizaciones:
                s = i.actualizacion_precio
                evidencia.append([i.clave, s['serie']['codigo'], s['base']['mes'], s['destino']['mes'],
                                  s['precio_original'], s['precio_actualizado'], s['base']['valor'],
                                  s['destino']['valor'], s['base']['documento_sha256'],
                                  s['destino']['documento_sha256'], s['sha256']])
            # Evidence is literal text, including identifiers that start with '='.
            for row in evidencia:
                for cell in row:
                    cell.data_type = 's'

        buffer = io.BytesIO()
        if presupuesto.cobertura_bim is not None:
            coverage = presupuesto.cobertura_bim
            evidence = wb.create_sheet('Cobertura BIM', 0)
            evidence.append(['MEDICIONES COMPLETAS' if coverage['completa'] else 'PRESUPUESTO PARCIAL: faltan mediciones BIM'])
            evidence.append(['Modelo', coverage['modelo_id']])
            evidence.append(['Elementos medidos', coverage['elementos_medidos'], 'Total', coverage['elementos_totales']])
            evidence.append(['Elementos pendientes', ', '.join(coverage['elementos_pendientes'])])
            evidence.append(['Elemento', 'Unidad', 'Cantidad capturada', 'Referencia', 'Usuario', 'Fecha'])
            for capture in coverage['capturas']:
                evidence.append([capture['elemento_id'], capture['unidad'], capture['cantidad'],
                    capture['referencia'], capture['usuario_id'], capture['capturado_en']])
            for row in evidence:
                for cell in row:
                    if isinstance(cell.value, str): cell.data_type = 's'
            evidence.column_dimensions['A'].width = 65
            evidence.column_dimensions['D'].width = 60
            wb.active = 0
        if presupuesto.evidencia_topografia is not None:
            source = presupuesto.evidencia_topografia
            coverage = source['cobertura']
            evidence = wb.create_sheet('Topografía', 0)
            evidence.append(['MEDICIONES COMPLETAS' if coverage['completa'] else 'PRESUPUESTO PARCIAL: falta cobertura topográfica'])
            evidence.append(['Cálculo', source['calculo_id'], 'Algoritmo', source['algoritmo']])
            evidence.append(['Huella de evidencia', source['sha256']])
            evidence.append(['Área común (m2)', coverage['area_comun_m2']])
            evidence.append(['Terreno sin analizar (m2)', coverage['area_existente_pendiente_m2']])
            evidence.append(['Proyecto sin analizar (m2)', coverage['area_proyecto_pendiente_m2']])
            evidence.append(['Corte medido (m3)', source['resultados']['volumen_corte_m3']])
            evidence.append(['Relleno medido (m3)', source['resultados']['volumen_terraplen_m3']])
            evidence.append(['Elevación de referencia (m)', source['elevacion_referencia']])
            evidence.append(['Fuente', 'Superficie', 'Levantamiento', 'CRS', 'Huella de malla'])
            for key in ('existente', 'proyecto'):
                surface = source[key]
                if surface:
                    evidence.append([key, surface['superficie_id'], surface['levantamiento_id'], surface['crs'], surface['malla_sha256']])
            for row in evidence:
                for cell in row:
                    if isinstance(cell.value, str):
                        cell.data_type = 's'
            evidence.column_dimensions['A'].width = 50
            evidence.column_dimensions['B'].width = 70
            wb.active = 0
        wb.save(buffer)
        return buffer.getvalue()

    def generar_pdf(self, presupuesto: PresupuestoCosteo) -> bytes:
        """Genera PDF del presupuesto -- mismo contenido que generar_excel()
        (tabla de partidas + resumen de totales), con reportlab.

        Antes esto no existía: app/workers/pdf_tasks.py era un stub que
        devolvía pdf_url="" con status SUCCESS falso. reportlab ya estaba
        en pyproject.toml (declarado para PAdES-LT de firma electrónica)
        pero nunca se usaba en ningún lado del proyecto -- confirmado con
        grep antes de escribir esto."""
        import io as _io
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from xml.sax.saxutils import escape

        buffer = _io.BytesIO()
        doc = SimpleDocTemplate(
            buffer, pagesize=letter,
            topMargin=1.5 * cm, bottomMargin=1.5 * cm,
            leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        )
        styles = getSampleStyleSheet()
        titulo_style = ParagraphStyle("TituloPresupuesto", parent=styles["Heading1"], fontSize=14, spaceAfter=2)
        subtitulo_style = ParagraphStyle("Subtitulo", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#555555"))
        celda_desc_style = ParagraphStyle("CeldaDesc", parent=styles["Normal"], fontSize=8, leading=10)

        elementos = []
        elementos.append(Paragraph(presupuesto.nombre, titulo_style))
        elementos.append(Paragraph(f"Identificador: {presupuesto.identificador}", subtitulo_style))
        if presupuesto.evidencia_topografia is not None:
            source = presupuesto.evidencia_topografia
            coverage = source['cobertura']
            elementos.append(Paragraph(
                f"Topografía: cálculo {source['calculo_id']}. Área común: {coverage['area_comun_m2']:.3f} m². "
                f"Pendiente en terreno: {coverage['area_existente_pendiente_m2']:.3f} m²; "
                f"en proyecto: {coverage['area_proyecto_pendiente_m2']:.3f} m².", subtitulo_style))
        elementos.append(Spacer(1, 0.5 * cm))

        header = ["No.", "Descripción", "Unidad", "Cantidad", "P.U.", "Importe"]
        filas = [header]
        for p in presupuesto.partidas:
            descripcion = escape(p.descripcion)
            if p.origen_catalogo:
                source = p.origen_catalogo
                descripcion += '<br/>Fuente: ' + escape(str(source['fuente'])) + ' · ' + escape(str(source['clave']))
                descripcion += ' · Vigencia: ' + escape(str(source['vigencia_inicio'] or 'sin registrar'))
                origin = source.get('origen_importacion')
                if origin:
                    descripcion += '<br/>PDF: ' + escape(origin['fuente']['archivo_original'])
                    descripcion += ' · Páginas: ' + escape(','.join(origin['paginas']))
                    descripcion += '<br/>SHA256 PDF: ' + escape(origin['fuente']['sha256'])
            filas.append([
                str(p.numero),
                Paragraph(descripcion, celda_desc_style),
                p.unidad,
                f"{p.cantidad:,.4f}",
                f"${p.precio_unitario:,.2f}",
                f"${p.importe:,.2f}",
            ])

        tabla = Table(filas, colWidths=[1.2 * cm, 8 * cm, 2 * cm, 2.3 * cm, 2.5 * cm, 2.7 * cm], repeatRows=1)
        tabla.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1F4E78")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (0, -1), "CENTER"),
            ("ALIGN", (3, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#CCCCCC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F5F7FA")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        elementos.append(tabla)
        elementos.append(Spacer(1, 0.6 * cm))

        filas_totales = [
            ["Monto directo:", f"${presupuesto.monto_directo:,.2f}"],
            [f"Indirecto ({presupuesto.factor_indirecto:.1%}):", f"${presupuesto.monto_indirecto:,.2f}"],
        ]
        if presupuesto.factor_financiamiento:
            filas_totales.append([f"Financiamiento ({presupuesto.factor_financiamiento:.1%}):", f"${presupuesto.monto_financiamiento:,.2f}"])
        filas_totales.append([f"Utilidad ({presupuesto.factor_utilidad:.1%}):", f"${presupuesto.monto_utilidad:,.2f}"])
        if presupuesto.factor_riesgo:
            filas_totales.append([f"Riesgo ({presupuesto.factor_riesgo:.1%}):", f"${presupuesto.monto_riesgo:,.2f}"])
        if presupuesto.factor_cargos_adicionales:
            filas_totales.append([f"Cargos adicionales ({presupuesto.factor_cargos_adicionales:.1%}):", f"${presupuesto.monto_cargos_adicionales:,.2f}"])
        filas_totales.append([f"IVA ({presupuesto.factor_impuesto:.1%}):", f"${presupuesto.monto_impuesto:,.2f}"])
        filas_totales.append(["TOTAL:", f"${presupuesto.monto_total:,.2f}"])

        tabla_totales = Table(filas_totales, colWidths=[5 * cm, 3.5 * cm], hAlign="RIGHT")
        tabla_totales.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, -1), (-1, -1), 11),
            ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
            ("TOPPADDING", (0, -1), (-1, -1), 6),
        ]))
        elementos.append(tabla_totales)

        doc.build(elementos)
        return buffer.getvalue()
