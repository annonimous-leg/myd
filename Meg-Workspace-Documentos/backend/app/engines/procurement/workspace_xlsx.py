# © 2026 Carl Own Megalodon
"""Fill explicitly mapped cells while keeping the other XLSX parts intact."""
from hashlib import sha256
from io import BytesIO
from math import isfinite
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile

from lxml import etree
from openpyxl import load_workbook
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE, MergedCell

from .workspace_docx import Draft, TemplateError, parse_xml, read_parts

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def render_xlsx(original, config, values):
    try:
        return _render(original, config, values)
    except TemplateError:
        raise
    except (BadZipFile, ValueError, KeyError, OSError, SyntaxError, RuntimeError, TypeError) as exc:
        raise TemplateError("El archivo o mapa XLSX no es compatible.") from exc


def _invalidate_formula_caches(workbook, paths, parts, changed):
    has_formulas = False
    for path in paths:
        if not path.startswith("xl/worksheets/"):
            continue
        root = changed[path] if path in changed else parse_xml(parts[path])
        for cell in root.findall(f"./{NS}sheetData/{NS}row/{NS}c"):
            if cell.find(NS + "f") is None:
                continue
            has_formulas = True
            cached = cell.find(NS + "v")
            if cached is not None:
                cell.remove(cached)
                changed[path] = root
    if not has_formulas:
        return
    calculation = workbook.find(NS + "calcPr")
    if calculation is None:
        calculation = etree.Element(NS + "calcPr", calcId="0")
        successors = {NS + name for name in (
            "oleSize", "customWorkbookViews", "pivotCaches", "smartTagPr",
            "smartTagTypes", "webPublishing", "fileRecoveryPr", "webPublishObjects", "extLst",
        )}
        position = next((i for i, child in enumerate(workbook) if child.tag in successors), len(workbook))
        workbook.insert(position, calculation)
    calculation.set("calcMode", "auto")
    calculation.set("fullCalcOnLoad", "1")
    calculation.set("forceFullCalc", "1")
    changed["xl/workbook.xml"] = workbook


def _render(original, config, values):
    with ZipFile(BytesIO(original)) as archive:
        parts = read_parts(archive)
    for name in parts:
        if name.lower().startswith(("xl/externallinks/", "xl/activex/", "xl/embeddings/")):
            raise TemplateError("El libro contiene vínculos externos o componentes activos.")
        if name.lower().endswith(".rels") and any(
            relation.get("TargetMode", "Internal") != "Internal"
            and not (relation.get("Type") == REL[1:-1] + "/hyperlink"
                     and relation.get("Target", "").startswith("https://"))
            for relation in parse_xml(parts[name])
        ):
            raise TemplateError("El libro contiene relaciones externas.")

    workbook = parse_xml(parts["xl/workbook.xml"])
    sheets = workbook.find(NS + "sheets")
    relationships = {r.get("Id"): r.get("Target") for r in parse_xml(parts["xl/_rels/workbook.xml.rels"])}
    paths = {}
    for sheet in sheets:
        target = relationships[sheet.get(REL + "id")]
        paths[sheet.get("name")] = target.lstrip("/") if target.startswith("/") else "xl/" + target

    book = load_workbook(BytesIO(original), data_only=False, keep_links=False)
    changed = {}
    for key, field in config["fields"].items():
        value = values[key]
        if not value.strip() and field.get("required", True):
            raise TemplateError(f"Falta el campo obligatorio {key}.")
        sheet = book[field["sheet"]]
        address = field["cell"]
        cell = sheet[address]
        if (isinstance(cell, MergedCell) or cell.data_type == "f"
                or address in sheet.merged_cells or sheet.protection.sheet
                or sheet.array_formulae):
            raise TemplateError(f"La celda {address} está protegida, combinada o contiene fórmulas.")
        path = paths[sheet.title]
        if path not in changed:
            changed[path] = parse_xml(parts[path])
        node = changed[path].find(f'.//{NS}sheetData/{NS}row/{NS}c[@r="{address}"]')
        if node is None or node.find(NS + "f") is not None:
            raise TemplateError(f"La celda {address} no está preparada para captura.")
        for child in list(node):
            if child.tag in (NS + "v", NS + "is"):
                node.remove(child)
        if not value.strip():
            node.attrib.pop("t", None)
        elif field.get("type", "text") == "number":
            number = float(value)
            if not isfinite(number):
                raise TemplateError(f"Valor numérico inválido en {address}.")
            node.set("t", "n")
            etree.SubElement(node, NS + "v").text = str(number)
        else:
            if ILLEGAL_CHARACTERS_RE.search(value):
                raise TemplateError(f"Texto inválido en {address}.")
            node.set("t", "inlineStr")
            inline = etree.SubElement(node, NS + "is")
            text = etree.SubElement(inline, NS + "t")
            text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            text.text = value

    _invalidate_formula_caches(workbook, paths.values(), parts, changed)
    for path, root in changed.items():
        parts[path] = etree.tostring(root, encoding="UTF-8", xml_declaration=True)
    result = BytesIO()
    with ZipFile(result, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in parts.items():
            archive.writestr(name, content)
    content = result.getvalue()
    return Draft(content, sha256(original).hexdigest(), sha256(content).hexdigest(), "xlsx-cell-v2")
