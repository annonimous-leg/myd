"""Carga el corpus jurídico verificado a legal_sources/legal_articles reales,
y siembra las LegalRule que sí tienen fundamento verificado por lectura
directa del texto -- no copiado de un README ni de una cita hardcodeada sin
revisar.

Reemplaza al loader-skeleton que trae 05_roadmaps_integracion/scripts/
load_corpus_from_csv.py en el paquete MEGALODON_CORPUS_COBERTURA_TOTAL --
ese termina en `print("OK skeleton — conectar engine y UPSERT reales")` y no
conecta a nada. Este sí conecta, sí hace UPSERT idempotente, y corre dentro
de una sola transacción (todo o nada).

USO:
    python -m scripts.load_legal_corpus_articles \
        --corpus-dir /ruta/a/01_corpus_legal/csv

DATOS QUE CARGA (verificados por inspección directa antes de escribir esto):
  - LOPSRM federal: 131 artículos con texto real, 0 vacíos, todos con
    estado_dato VERIFICADO/VERIFIED_PRIMARY en el CSV origen.
  - LAASSP federal: 120 artículos, mismas condiciones.
  - RLOPSRM Art. 91 (garantía de cumplimiento, mínimo legal 10%): NO está
    segmentado en el CSV del corpus, solo en fulltext. Se agrega a mano,
    copiado literal de 01_corpus_legal/fulltext/RLOPSRM_completo.txt,
    línea 3805.
  - CFF Art. 32-D (impedimento de contratar sin opinión SAT positiva): NO
    está en el corpus original -- se agrega a mano desde el PDF oficial
    CFF_DOF_09-04-2026.pdf (Cámara de Diputados) que se aportó por
    separado. Texto extraído con pdftotext y verificado por lectura
    directa, no por búsqueda de palabra clave únicamente.

LegalRule que siembra (fundamento verificado, ver abajo qué NO se sembró
y por qué):

  Garantías / penas:
  - GARANTIA-CUMPLIMIENTO-OBRA-MIN10  → RLOPSRM Art. 91
  - GARANTIA-ANTICIPO-OBRA-100        → LOPSRM Art. 48, fracción I
  - GARANTIA-ANTICIPO-ADQ-100         → LAASSP Art. 69, fracción I
  - TOPE-PENAS-CONVENCIONALES-OBRA    → LOPSRM Art. 46 Bis
  - TOPE-PENAS-CONVENCIONALES-ADQ     → LAASSP Art. 75

  Requisitos documentales (reemplazan REQ-004/REQ-005 de motor_juridico.py,
  cuyas citas -- LOPSRM Art. 33/34, LAASSP Art. 48/49 -- están mal; los
  artículos correctos se identificaron leyendo el texto completo de LOPSRM
  y LAASSP, no adivinando):
  - BASES-LICITACION-OBRA   → LOPSRM Art. 31 ("la convocatoria... en la
    cual se establecerán las bases...")
  - AVISO-PUBLICACION-OBRA  → LOPSRM Art. 32 ("la publicación de la
    convocatoria... se realizará a través de la Plataforma")
  - BASES-LICITACION-ADQ    → LAASSP Art. 40 (mismo texto, ley espejo)
  - AVISO-PUBLICACION-ADQ   → LAASSP Art. 41 (mismo texto, ley espejo)

  Requisito SAT (reemplaza REQ-001 de motor_juridico.py, que citaba CFF
  Art. 29-A -- ese artículo es sobre requisitos de comprobantes fiscales
  digitales, no sobre impedimento de contratar; está mal):
  - OPINION-CUMPLIMIENTO-SAT → CFF Art. 32-D ("...en ningún caso
    contratarán adquisiciones, arrendamientos, servicios u obra pública
    con las personas físicas, morales o entes jurídicos que: I. Tengan a
    su cargo créditos fiscales firmes...")

REQ-002/REQ-003 (IMSS/INFONAVIT) -- RESUELTOS con normativa secundaria real,
no con la LSS ni la Ley del INFONAVIT (esas se descartaron como fuente
correcta: LSS Art. 15-A es sobre REPSE, "Art. 136" de la Ley del INFONAVIT
ni existe como tal -- ver commits anteriores):

  - IMSS: "Reglas de carácter general para la obtención de la opinión del
    cumplimiento de obligaciones fiscales en materia de seguridad social"
    (Acuerdo ACDO.AS2.HCT.270422/107.P.DIR, DOF 22-09-2022), modificadas
    por el Acuerdo ACDO.AS2.HCT.300925/288.P.DIR (DOF 06-10-2025, vigente
    desde 01-10-2025). Ancladas expresamente al artículo 32-D del CFF
    (verificado, aparece varias veces en el texto). Canal único desde la
    modificación 2025: Buzón IMSS (Regla Quinta modificada).

    CORRECCIÓN IMPORTANTE sobre la vigencia: el texto que se aportó como
    "validez 15 días hábiles/naturales para LAASSP/LOPSRM" NO aparece en
    ninguno de los dos documentos -- ni "LAASSP" ni "LOPSRM" se mencionan
    ahí. Lo que el documento SÍ dice, literal, en la Regla Novena: *"La
    opinión del cumplimiento... gozará de vigencia durante el día de la
    fecha en que haya sido generada."* Es decir, la opinión es válida
    únicamente el día en que se genera -- no 15 días. Este loader carga
    la vigencia tal como está en el documento (mismo día), no la cifra de
    15 días que no pude verificar en el texto. Si en la práctica LAASSP/
    LOPSRM aceptan una opinión generada hasta N días antes de cierto acto,
    eso sería una regla distinta (de esas leyes, sobre cuándo se acepta un
    documento), no la vigencia de la opinión en sí -- y esa regla todavía
    no está confirmada.

  - INFONAVIT: "Reglas para la obtención de la constancia de situación
    fiscal en materia de aportaciones patronales y entero de descuentos",
    modificadas por Resolución RCA-13138-01/24 (DOF 22-04-2024). Ancladas
    también al Art. 32-D CFF (verificado en el texto). Regla Sexta: *"La
    Constancia de Situación Fiscal... tendrá una vigencia de 30 días
    naturales..."* -- esta sí se confirmó tal cual en el documento.

Con esto, de los 5 requisitos hardcodeados originales en motor_juridico.py
(REQ-001 a REQ-005), las CINCO citas resultaron incorrectas al verificarlas
contra el texto real. Las 5 ya están resueltas con fundamento verificado.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
from pathlib import Path

from sqlalchemy import select

from app.models.base import AsyncSessionLocal
from app.models.procurement import LegalArticle, LegalRule, LegalSource

_VERIFIED_PREFIXES = ("VERIFICADO", "VERIFIED_PRIMARY")

_SOURCES = {
    "LOPSRM": dict(
        authority="Cámara de Diputados",
        title="Ley de Obras Públicas y Servicios Relacionados con las Mismas",
        citation="LOPSRM",
        version="DOF 14-11-2025",
        effective_from="2025-11-14",
        jurisdiction_code="MX-FED-OBRA",
    ),
    "LAASSP": dict(
        authority="Cámara de Diputados",
        title="Ley de Adquisiciones, Arrendamientos y Servicios del Sector Público",
        citation="LAASSP",
        version="DOF 16-04-2025",
        effective_from="2025-04-16",
        jurisdiction_code="MX-FED-ADQ",
    ),
    "RLOPSRM": dict(
        authority="Poder Ejecutivo Federal",
        title="Reglamento de la Ley de Obras Públicas y Servicios Relacionados con las Mismas",
        citation="RLOPSRM",
        version="DOF 24-02-2023",
        effective_from="2023-02-24",
        jurisdiction_code="MX-FED-OBRA",
    ),
    "CFF": dict(
        authority="Cámara de Diputados",
        title="Código Fiscal de la Federación",
        citation="CFF",
        version="DOF 09-04-2026",
        effective_from="2026-04-09",
        jurisdiction_code=None,  # aplica a obra y adquisiciones por igual
    ),
    "IMSS-OPINION": dict(
        authority="H. Consejo Técnico del IMSS",
        title="Reglas de carácter general para la obtención de la opinión del cumplimiento de obligaciones fiscales en materia de seguridad social",
        citation="IMSS-RCG-OPINION-CUMPLIMIENTO",
        version="Acuerdo ACDO.AS2.HCT.270422/107.P.DIR (DOF 22-09-2022), mod. ACDO.AS2.HCT.300925/288.P.DIR (DOF 06-10-2025, vigente 01-10-2025)",
        effective_from="2022-09-22",
        jurisdiction_code=None,
    ),
    "INFONAVIT-CONSTANCIA": dict(
        authority="INFONAVIT (órgano fiscal autónomo)",
        title="Reglas para la obtención de la constancia de situación fiscal en materia de aportaciones patronales y entero de descuentos",
        citation="INFONAVIT-REGLAS-CONSTANCIA-SF",
        version="Resolución RCA-13138-01/24 (DOF 22-04-2024)",
        effective_from="2024-04-22",
        jurisdiction_code=None,
    ),
}

# No segmentados en ningún CSV del corpus -- copiados literal de fulltext u
# oficial, verificados por lectura directa antes de incluirlos aquí.

_RLOPSRM_ART_91_TEXT = (
    "Artículo 91.- La garantía de cumplimiento de las obligaciones derivadas "
    "del contrato no podrá ser menor al diez por ciento del monto total "
    "autorizado al contrato en cada ejercicio, sin perjuicio de lo dispuesto "
    "en la demás normativa aplicable."
)

_CFF_ART_32D_TEXT = (
    "Artículo 32-D. Cualquier autoridad, ente público, entidad, órgano u "
    "organismo de los poderes Legislativo, Ejecutivo y Judicial, de la "
    "Federación, de las entidades federativas y de los municipios, órganos "
    "autónomos, partidos políticos, fideicomisos y fondos, así como "
    "cualquier persona física, moral o sindicato, que reciban y ejerzan "
    "recursos públicos federales, en ningún caso contratarán adquisiciones, "
    "arrendamientos, servicios u obra pública con las personas físicas, "
    "morales o entes jurídicos que: I. Tengan a su cargo créditos fiscales "
    "firmes. II. Tengan a su cargo créditos fiscales determinados, firmes o "
    "no, que no se encuentren pagados o garantizados en alguna de las "
    "formas permitidas por este Código. III. No se encuentren inscritos en "
    "el Registro Federal de Contribuyentes. IV. Habiendo vencido el plazo "
    "para presentar alguna declaración, provisional o no, ésta no haya "
    "sido presentada. V. Estando inscritos en el registro federal de "
    "contribuyentes, se encuentren como no localizados. VI. Tengan "
    "sentencia condenatoria firme por algún delito fiscal. VII. No hayan "
    "desvirtuado la presunción de emitir comprobantes fiscales que amparan "
    "operaciones inexistentes. VIII. Hayan manifestado ingresos y "
    "retenciones que no concuerden con sus CFDI. IX. Incumplan con las "
    "obligaciones establecidas en los artículos 32-B Ter y 32-B Quinquies "
    "de este Código."
)

# IMSS -- Acuerdo ACDO.AS2.HCT.270422/107.P.DIR, DOF 22-09-2022. Extraído
# del HTML del DOF (no PDF binario oficial -- ver disclaimer del zip
# 'opiniones_cumplimiento_IMSS_INFONAVIT_vigentes'), verificado por lectura
# directa antes de incluirlo aquí.
_IMSS_REGLA_TERCERA_TEXT = (
    "Tercera.- Consideraciones para la Opinión del cumplimiento. La "
    "opinión del cumplimiento de obligaciones fiscales en materia de "
    "seguridad social se emite tomando en consideración la situación del "
    "particular registrada en los sistemas electrónicos del IMSS, por lo "
    "que no constituye resolución en sentido favorable para el mismo "
    "sobre el cálculo y montos de créditos fiscales en materia de "
    "seguridad social o cuotas obrero patronales declaradas o pagadas. "
    "Se emite en relación con lo previsto en el párrafo primero del "
    "artículo 32-D del Código Fiscal de la Federación."
)

_IMSS_REGLA_NOVENA_TEXT = (
    "Novena.- Vigencia. La opinión del cumplimiento de obligaciones "
    "fiscales en materia de seguridad social gozará de vigencia durante "
    "el día de la fecha en que haya sido generada."
)

# Modificación DOF 06-10-2025 (Acuerdo ACDO.AS2.HCT.300925/288.P.DIR),
# vigente desde 01-10-2025.
_IMSS_REGLA_QUINTA_MOD_TEXT = (
    "Quinta.- Opinión generada por la persona titular de la Opinión del "
    "cumplimiento (texto modificado, vigente desde 01-10-2025). Los "
    "particulares que para realizar algún trámite requieran obtener la "
    "opinión del cumplimiento de obligaciones fiscales en materia de "
    "seguridad social, deberán hacerlo a través del Buzón IMSS "
    "(www.imss.gob.mx/buzonimss), seleccionando la opción 'Cobranza' y "
    "después '32D Consultar Mi Opinión'. Es la única modalidad vigente de "
    "obtención."
)

# INFONAVIT -- Resolución RCA-13138-01/24, DOF 22-04-2024.
_INFONAVIT_REGLA_SEXTA_TEXT = (
    "Sexta. La Constancia de Situación Fiscal a que se refieren las "
    "presentes Reglas tendrá una vigencia de 30 días naturales contados "
    "a partir del día de su emisión, en ejercicio de las facultades del "
    "INFONAVIT como órgano fiscal autónomo."
)


def _hash_text(text: str) -> str:
    normalized = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def _get_or_create_source(session, codigo: str) -> LegalSource:
    meta = _SOURCES[codigo]
    existing = (
        await session.execute(
            select(LegalSource).where(
                LegalSource.citation == meta["citation"],
                LegalSource.tenant_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    source = LegalSource(
        tenant_id=None,
        authority=meta["authority"],
        title=meta["title"],
        citation=meta["citation"],
        version=meta["version"],
        effective_from=meta["effective_from"],
        jurisdiction_code=meta["jurisdiction_code"],
        status="ACTIVE",
    )
    session.add(source)
    await session.flush()
    return source


async def _upsert_article(session, source: LegalSource, article_code: str, text: str) -> LegalArticle:
    content_hash = _hash_text(text)
    existing = (
        await session.execute(
            select(LegalArticle).where(
                LegalArticle.source_id == source.id,
                LegalArticle.article_code == article_code,
            )
        )
    ).scalar_one_or_none()
    if existing:
        existing.summary = text
        existing.content_hash = content_hash
        existing.status = "ACTIVE"
        return existing
    article = LegalArticle(
        source_id=source.id,
        article_code=article_code,
        title=None,
        summary=text,
        content_hash=content_hash,
        status="ACTIVE",
    )
    session.add(article)
    await session.flush()
    return article


def _read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


async def load_federal_articles(session, corpus_dir: Path) -> dict[str, dict[str, LegalArticle]]:
    """Carga LOPSRM + LAASSP desde CSV (solo filas VERIFICADO), más
    RLOPSRM Art. 91 y CFF Art. 32-D a mano. Devuelve
    {ley: {numero_articulo: LegalArticle}}.
    """
    by_law: dict[str, dict[str, LegalArticle]] = {"LOPSRM": {}, "LAASSP": {}, "RLOPSRM": {}, "CFF": {}}

    lopsrm_source = await _get_or_create_source(session, "LOPSRM")
    laassp_source = await _get_or_create_source(session, "LAASSP")
    rlopsrm_source = await _get_or_create_source(session, "RLOPSRM")
    cff_source = await _get_or_create_source(session, "CFF")

    for codigo, fname, source in (
        ("LOPSRM", "articulos_lopsrm_federal.csv", lopsrm_source),
        ("LAASSP", "articulos_laassp_federal.csv", laassp_source),
    ):
        rows = _read_csv(corpus_dir / fname)
        loaded = skipped_empty = skipped_unverified = 0
        for row in rows:
            texto = (row.get("texto") or "").strip()
            numero = (row.get("articulo") or "").strip()
            estado = (row.get("estado_dato") or "").strip()
            if not texto or not numero:
                skipped_empty += 1
                continue
            if not estado.startswith(_VERIFIED_PREFIXES):
                skipped_unverified += 1
                continue
            article = await _upsert_article(session, source, numero, texto)
            by_law[codigo][numero] = article
            loaded += 1
        print(
            f"{codigo}: {loaded} artículos cargados, {skipped_empty} vacíos, "
            f"{skipped_unverified} no-verificados omitidos, de {len(rows)} filas totales"
        )

    art91 = await _upsert_article(session, rlopsrm_source, "91", _RLOPSRM_ART_91_TEXT)
    by_law["RLOPSRM"]["91"] = art91
    print("RLOPSRM: 1 artículo cargado a mano (Art. 91 — no segmentado en el CSV del corpus)")

    art32d = await _upsert_article(session, cff_source, "32-D", _CFF_ART_32D_TEXT)
    by_law["CFF"]["32-D"] = art32d
    print("CFF: 1 artículo cargado a mano (Art. 32-D — ley no incluida en el corpus original)")

    imss_source = await _get_or_create_source(session, "IMSS-OPINION")
    by_law["IMSS-OPINION"] = {
        "Tercera": await _upsert_article(session, imss_source, "Tercera", _IMSS_REGLA_TERCERA_TEXT),
        "Novena": await _upsert_article(session, imss_source, "Novena", _IMSS_REGLA_NOVENA_TEXT),
        "Quinta-mod-2025": await _upsert_article(session, imss_source, "Quinta-mod-2025", _IMSS_REGLA_QUINTA_MOD_TEXT),
    }
    print("IMSS-OPINION: 3 reglas cargadas a mano (Tercera, Novena, Quinta modificada 2025)")

    infonavit_source = await _get_or_create_source(session, "INFONAVIT-CONSTANCIA")
    by_law["INFONAVIT-CONSTANCIA"] = {
        "Sexta": await _upsert_article(session, infonavit_source, "Sexta", _INFONAVIT_REGLA_SEXTA_TEXT),
    }
    print("INFONAVIT-CONSTANCIA: 1 regla cargada a mano (Sexta — vigencia)")

    return by_law


_REQUIRED_ARTICLES = (
    ("LOPSRM", "48"), ("LOPSRM", "46 Bis"), ("LOPSRM", "31"), ("LOPSRM", "32"),
    ("LAASSP", "69"), ("LAASSP", "75"), ("LAASSP", "40"), ("LAASSP", "41"),
    ("RLOPSRM", "91"), ("CFF", "32-D"),
    ("IMSS-OPINION", "Tercera"), ("IMSS-OPINION", "Novena"), ("IMSS-OPINION", "Quinta-mod-2025"),
    ("INFONAVIT-CONSTANCIA", "Sexta"),
)


def _rule(rule_id, jurisdiction_code, domain, article, condition, description, citation, mandatory=True, extra=None):
    return dict(
        rule_id=rule_id, jurisdiction_code=jurisdiction_code, domain=domain, article=article,
        condition=condition,
        requirement={
            "code": rule_id, "category": domain, "description": description,
            "mandatory": mandatory, "citation": citation, **(extra or {}),
        },
    )


async def seed_verified_rules(session, articles: dict[str, dict[str, LegalArticle]]) -> None:
    lopsrm, laassp, rlopsrm, cff = articles["LOPSRM"], articles["LAASSP"], articles["RLOPSRM"], articles["CFF"]
    imss, infonavit = articles["IMSS-OPINION"], articles["INFONAVIT-CONSTANCIA"]

    rules = [
        _rule(
            "GARANTIA-CUMPLIMIENTO-OBRA-MIN10", "MX-FED-OBRA", "GARANTIAS", rlopsrm["91"],
            {"field": "contract_type", "op": "eq", "value": "OBRA_PUBLICA"},
            "La garantía de cumplimiento no puede ser menor al 10% del monto total autorizado al contrato en cada ejercicio.",
            "RLOPSRM Art. 91",
            extra={"params": {"min_percentage": 0.10}, "evidence_required": ["poliza_fianza_cumplimiento"]},
        ),
        _rule(
            "GARANTIA-ANTICIPO-OBRA-100", "MX-FED-OBRA", "GARANTIAS", lopsrm["48"],
            {"field": "has_anticipo", "op": "eq", "value": True},
            "Los anticipos deben garantizarse por la totalidad de su monto.",
            "LOPSRM Art. 48, fracción I",
            extra={"params": {"percentage": 1.00}, "evidence_required": ["poliza_fianza_anticipo"]},
        ),
        _rule(
            "GARANTIA-ANTICIPO-ADQ-100", "MX-FED-ADQ", "GARANTIAS", laassp["69"],
            {"field": "has_anticipo", "op": "eq", "value": True},
            "Los anticipos deben garantizarse por la totalidad de su monto.",
            "LAASSP Art. 69, fracción I",
            extra={"params": {"percentage": 1.00}, "evidence_required": ["poliza_fianza_anticipo"]},
        ),
        _rule(
            "TOPE-PENAS-CONVENCIONALES-OBRA", "MX-FED-OBRA", "PENALIZACIONES", lopsrm["46 Bis"],
            {"field": "contract_type", "op": "eq", "value": "OBRA_PUBLICA"},
            "En ningún caso las penas convencionales, en su conjunto, podrán ser superiores al monto de la garantía de cumplimiento.",
            "LOPSRM Art. 46 Bis",
            extra={"params": {"cap_reference": "GARANTIA-CUMPLIMIENTO-OBRA-MIN10"}},
        ),
        _rule(
            "TOPE-PENAS-CONVENCIONALES-ADQ", "MX-FED-ADQ", "PENALIZACIONES", laassp["75"],
            {"field": "contract_type", "op": "eq", "value": "ADQUISICIONES"},
            "Las penas convencionales no excederán del monto de la garantía de cumplimiento del contrato.",
            "LAASSP Art. 75",
        ),
        # -- Requisitos documentales: reemplazan REQ-004/REQ-005 con cita correcta --
        _rule(
            "BASES-LICITACION-OBRA", "MX-FED-OBRA", "REQUISITOS_DOCUMENTALES", lopsrm["31"],
            {"field": "procedure_type", "op": "eq", "value": "LICITACION_PUBLICA"},
            "La convocatoria a la licitación pública debe establecer las bases del procedimiento y los requisitos de participación.",
            "LOPSRM Art. 31",
            extra={"artifact_required": ["bases_licitacion"]},
        ),
        _rule(
            "AVISO-PUBLICACION-OBRA", "MX-FED-OBRA", "REQUISITOS_DOCUMENTALES", lopsrm["32"],
            {"field": "procedure_type", "op": "eq", "value": "LICITACION_PUBLICA"},
            "La convocatoria y sus bases deben publicarse a través de la Plataforma (CompraNet).",
            "LOPSRM Art. 32",
            extra={"evidence_required": ["constancia_publicacion_plataforma"]},
        ),
        _rule(
            "BASES-LICITACION-ADQ", "MX-FED-ADQ", "REQUISITOS_DOCUMENTALES", laassp["40"],
            {"field": "procedure_type", "op": "eq", "value": "LICITACION_PUBLICA"},
            "La convocatoria a la licitación pública debe establecer las bases del procedimiento y los requisitos de participación.",
            "LAASSP Art. 40",
            extra={"artifact_required": ["bases_licitacion"]},
        ),
        _rule(
            "AVISO-PUBLICACION-ADQ", "MX-FED-ADQ", "REQUISITOS_DOCUMENTALES", laassp["41"],
            {"field": "procedure_type", "op": "eq", "value": "LICITACION_PUBLICA"},
            "La convocatoria debe publicarse a través de la Plataforma (CompraNet).",
            "LAASSP Art. 41",
            extra={"evidence_required": ["constancia_publicacion_plataforma"]},
        ),
        # -- SAT: reemplaza REQ-001 con cita correcta --
        _rule(
            "OPINION-CUMPLIMIENTO-SAT", None, "REQUISITOS_DOCUMENTALES", cff["32-D"],
            {"field": "uses_federal_public_funds", "op": "eq", "value": True},
            "No podrá contratarse con quien tenga créditos fiscales firmes, no esté inscrito en el RFC, o incumpla otras fracciones del Art. 32-D CFF. Se acredita con opinión de cumplimiento positiva del SAT.",
            "CFF Art. 32-D",
            extra={"evidence_required": ["opinion_cumplimiento_sat_32d"]},
        ),
        # -- IMSS: reemplaza REQ-002 con cita correcta --
        # OJO con evidence_timing: la opinión IMSS vale solo el día en que
        # se genera (Regla Novena) -- no 15 días como se propuso en un
        # primer borrador y que no pude verificar en el texto real. Si el
        # validador de evidencia solo checa "existe el documento" sin
        # checar la fecha de generación contra la fecha de uso, esta regla
        # dejaría pasar exactamente el tipo de descartamiento que se
        # quiere prevenir.
        _rule(
            "OPINION-CUMPLIMIENTO-IMSS", None, "REQUISITOS_DOCUMENTALES", imss["Novena"],
            {"field": "uses_federal_public_funds", "op": "eq", "value": True},
            "Se requiere opinión positiva del cumplimiento de obligaciones fiscales en materia de seguridad social, obtenida vía Buzón IMSS. La opinión solo es válida el día en que se genera -- debe volver a obtenerse el día en que se integre/presente la propuesta, no basta con tenerla de días antes.",
            "Reglas de carácter general IMSS, Acuerdo ACDO.AS2.HCT.270422/107.P.DIR (DOF 22-09-2022), Regla Novena; canal Buzón IMSS por modificación ACDO.AS2.HCT.300925/288.P.DIR (DOF 06-10-2025), Regla Quinta",
            extra={
                "evidence_required": ["opinion_cumplimiento_imss"],
                "evidence_timing": {"vigencia_dias": 0, "nota": "válida únicamente el día de generación (Regla Novena)"},
            },
        ),
        # -- INFONAVIT: reemplaza REQ-003 con cita correcta --
        _rule(
            "OPINION-CUMPLIMIENTO-INFONAVIT", None, "REQUISITOS_DOCUMENTALES", infonavit["Sexta"],
            {"field": "uses_federal_public_funds", "op": "eq", "value": True},
            "Se requiere Constancia de Situación Fiscal INFONAVIT vigente, obtenida vía Portal Empresarial/Institucional con e.firma.",
            "Reglas para la obtención de la constancia de situación fiscal INFONAVIT, Resolución RCA-13138-01/24 (DOF 22-04-2024), Regla Sexta",
            extra={
                "evidence_required": ["constancia_situacion_fiscal_infonavit"],
                "evidence_timing": {"vigencia_dias": 30},
            },
        ),
    ]

    for r in rules:
        existing = (
            await session.execute(
                select(LegalRule).where(
                    LegalRule.rule_id == r["rule_id"],
                    LegalRule.tenant_id.is_(None),
                    LegalRule.rule_version == 1,
                )
            )
        ).scalar_one_or_none()
        if existing:
            print(f"LegalRule {r['rule_id']} ya existe (v1), no se duplica.")
            continue
        session.add(
            LegalRule(
                tenant_id=None,
                rule_id=r["rule_id"],
                jurisdiction_code=r["jurisdiction_code"],
                domain=r["domain"],
                procedure_type=None,
                source_id=r["article"].source_id,
                article_id=r["article"].id,
                source_version=None,
                condition=r["condition"],
                requirement=r["requirement"],
                validation={},
                severity="BLOCKER",
                rule_version=1,
                active=True,
            )
        )
        print(f"LegalRule {r['rule_id']} creada → fundamento {r['requirement']['citation']}.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Carga corpus jurídico verificado a legal_sources/legal_articles/legal_rules.")
    parser.add_argument("--corpus-dir", type=Path, required=True, help="Ruta a 01_corpus_legal/csv del paquete de corpus")
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            articles = await load_federal_articles(session, args.corpus_dir)
            faltantes = [f"{ley} {num}" for ley, num in _REQUIRED_ARTICLES if num not in articles[ley]]
            if faltantes:
                raise RuntimeError(
                    "No se sembraron las LegalRule: faltan estos artículos esperados "
                    f"en el CSV: {faltantes}. Revisa el valor exacto de 'articulo' "
                    "(mayúsculas/espacios) antes de reintentar."
                )
            await seed_verified_rules(session, articles)
        print("Commit OK — todo dentro de una sola transacción.")


if __name__ == "__main__":
    asyncio.run(main())
