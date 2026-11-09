# © 2026 Carl Own Megalodon
"""Complete explicitly mapped, inline Word content controls in a draft."""
from dataclasses import dataclass, field as dataclass_field
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
import re
from zipfile import BadZipFile, ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

from lxml import etree


WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
MAIN_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
EDITABLE_PART = re.compile(r"word/(?:document|header[0-9]+|footer[0-9]+)\.xml")
MAX_ARCHIVE = 16 * 1024 * 1024
MAX_EXPANDED = 64 * 1024 * 1024
MAX_ENTRIES = 1000
MAX_VALUE = 2048
INVALID_TEXT = re.compile(r"[\x00-\x1f\x7f\ud800-\udfff\ufffe\uffff]")


class TemplateError(ValueError):
    """The template or supplied values exceed the supported draft profile."""


@dataclass(frozen=True)
class Field:
    tag: str
    required: bool = True


@dataclass(frozen=True)
class Draft:
    content: bytes
    source_sha256: str
    content_sha256: str
    renderer: str = "word-inline-sdt-v1"
    submission_eligible: bool = dataclass_field(default=False, init=False)


def parse_xml(content: bytes):
    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True)
    try:
        root = etree.fromstring(content, parser)
    except etree.XMLSyntaxError as exc:
        raise TemplateError("XML inválido en la plantilla.") from exc
    if root.getroottree().docinfo.doctype:
        raise TemplateError("No se admiten declaraciones DTD.")
    return root


def read_parts(source: ZipFile):
    entries = source.infolist()
    if len(entries) > MAX_ENTRIES or sum(entry.file_size for entry in entries) > MAX_EXPANDED:
        raise TemplateError("La plantilla supera el límite de descompresión.")
    parts = {}
    seen = set()
    for entry in entries:
        name = entry.filename
        path = PurePosixPath(name)
        canonical = name.casefold().rstrip("/")
        if (path.is_absolute() or ".." in path.parts or "\\" in name
                or name.rstrip("/") != path.as_posix() or canonical in seen
                or entry.flag_bits & 1 or entry.compress_type not in (ZIP_STORED, ZIP_DEFLATED)):
            raise TemplateError("La plantilla contiene una entrada ZIP incompatible.")
        seen.add(canonical)
        if (canonical.startswith(("_xmlsignatures/", "word/activex/", "word/embeddings/"))
                or "vbaproject" in canonical or canonical.startswith("word/webextensions/")):
            raise TemplateError("La plantilla contiene firmas o componentes activos.")
        if not entry.is_dir():
            parts[name] = source.read(entry)
    return parts


def validate_package(parts: dict[str, bytes]):
    if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"} <= parts.keys():
        raise TemplateError("El paquete DOCX está incompleto.")
    types = parse_xml(parts["[Content_Types].xml"])
    if not any(node.get("PartName") == "/word/document.xml"
               and node.get("ContentType") == MAIN_TYPE for node in types):
        raise TemplateError("Se requiere un documento DOCX sin macros.")
    for name, content in parts.items():
        if not name.casefold().endswith(".rels"):
            continue
        for relation in parse_xml(content):
            relation_type = relation.get("Type", "").casefold()
            mode = relation.get("TargetMode", "Internal")
            target = relation.get("Target", "")
            if (mode != "Internal" or ":" in target or "\\" in target or target.startswith("//")
                    or relation_type.endswith(("/afchunk", "/oleobject", "/attachedtemplate",
                                               "/package", "/control", "/vbaproject"))):
                raise TemplateError("La plantilla contiene relaciones externas o activas.")


def fill_parts(parts: dict[str, bytes], changes: dict[str, str]):
    found = set()
    for name, content in parts.items():
        if not EDITABLE_PART.fullmatch(name):
            continue
        root = parse_xml(content)
        modified = False
        for control in root.iter(WORD + "sdt"):
            props = control.find(WORD + "sdtPr")
            tag = props.find(WORD + "tag") if props is not None else None
            key = tag.get(WORD + "val") if tag is not None else None
            if key not in changes:
                continue
            body = control.find(WORD + "sdtContent")
            run = body.find(WORD + "r") if body is not None else None
            value = run.find(WORD + "t") if run is not None else None
            text_type = props.find(WORD + "text")
            if (key in found or text_type is None or text_type.get(WORD + "multiLine") in ("1", "true", "on")
                    or props.find(WORD + "dataBinding") is not None
                    or props.find(WORD + "lock") is not None
                    or control.getparent().tag != WORD + "p"
                    or body is None or len(body) != 1 or value is None
                    or [child.tag for child in run] not in
                    ([WORD + "t"], [WORD + "rPr", WORD + "t"])):
                raise TemplateError(f"Control Word incompatible o duplicado: {key}.")
            value.text = changes[key]
            value.set(XML_SPACE, "preserve")
            placeholder = props.find(WORD + "showingPlcHdr")
            if placeholder is not None:
                props.remove(placeholder)
            found.add(key)
            modified = True
        if modified:
            parts[name] = etree.tostring(root.getroottree(), encoding="UTF-8", xml_declaration=True)
    if changes.keys() - found:
        raise TemplateError("Faltan controles Word mapeados en el archivo.")


def render_draft(original: bytes, fields: dict[str, Field], values: dict[str, str]) -> Draft:
    """Render a draft without mutating the original or assigning delivery authority."""
    if not 0 < len(original) <= MAX_ARCHIVE:
        raise TemplateError("El tamaño del DOCX original está fuera de rango.")
    tags = {field.tag for field in fields.values()}
    if not fields or len(fields) > 100 or len(tags) != len(fields) or "" in tags:
        raise TemplateError("El mapa de campos es inválido.")
    if values.keys() - fields.keys():
        raise TemplateError("Se recibieron campos fuera del mapa autorizado.")
    changes = {}
    for key, field in fields.items():
        value = values.get(key, "")
        if not isinstance(value, str) or len(value) > MAX_VALUE or INVALID_TEXT.search(value):
            raise TemplateError(f"El campo {key} requiere texto de una sola línea.")
        if field.required and not value.strip():
            raise TemplateError(f"Falta el campo obligatorio {key}.")
        changes[field.tag] = value
    try:
        with ZipFile(BytesIO(original)) as source:
            parts = read_parts(source)
    except (BadZipFile, EOFError, RuntimeError, OSError) as exc:
        raise TemplateError("No se pudo leer el paquete DOCX.") from exc
    validate_package(parts)
    fill_parts(parts, changes)
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as target:
        for name, content in parts.items():
            target.writestr(ZipInfo(name), content, compress_type=ZIP_DEFLATED)
    content = output.getvalue()
    return Draft(content, sha256(original).hexdigest(), sha256(content).hexdigest())
