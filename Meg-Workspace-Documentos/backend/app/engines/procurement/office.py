# © 2026 Carl Own Megalodon
"""Run an isolated Office conversion before committing a Workspace revision."""
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook

from .workspace_docx import TemplateError, parse_xml, read_parts


def recalculate_xlsx(content: bytes, max_bytes: int) -> bytes:
    executable = shutil.which("soffice")
    if not executable:
        raise TemplateError("LibreOffice no está disponible en el servidor.")
    with ZipFile(BytesIO(content)) as archive:
        parts = read_parts(archive)
    for name, data in parts.items():
        if any(token in name.lower() for token in (
            "vbaproject", "activex", "embeddings", "externallinks", "connections.xml",
        )):
            raise TemplateError("El libro contiene componentes activos o conexiones externas.")
        if name.endswith(".rels") and any(
            relation.get("TargetMode") == "External" for relation in parse_xml(data)
        ):
            raise TemplateError("El libro contiene relaciones externas.")
    original = load_workbook(BytesIO(content))
    for sheet in original:
        for cell in sheet._cells.values():
            if cell.data_type == "f" and (
                not isinstance(cell.value, str) or any(
                    token in cell.value.upper()
                    for token in ("WEBSERVICE", "DDE", "RTD(", "HYPERLINK(", "[", "|")
                )
            ):
                raise TemplateError("El libro contiene fórmulas externas o no admitidas.")
    with TemporaryDirectory(prefix="megalodon-calc-") as temporary:
        root = Path(temporary)
        source = root / "revision.xlsx"
        source.write_bytes(content)
        output = root / "output"
        output.mkdir()
        try:
            process = subprocess.run(
                [executable, f"-env:UserInstallation={(root / 'profile').as_uri()}",
                 "--headless", "--convert-to", "xlsx", "--outdir", str(output), str(source)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=45,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TemplateError("No se pudo completar el recálculo en el servidor.") from exc
        result = output / source.name
        if process.returncode or not result.is_file() or not 0 < result.stat().st_size <= max_bytes:
            raise TemplateError("LibreOffice no generó un XLSX válido dentro del límite.")
        converted = result.read_bytes()
    try:
        recalculated = load_workbook(BytesIO(converted))
        cached = load_workbook(BytesIO(converted), data_only=True)
    except (ValueError, BadZipFile, OSError) as exc:
        raise TemplateError("El resultado del recálculo no se puede leer.") from exc
    if original.sheetnames != recalculated.sheetnames:
        raise TemplateError("El recálculo cambió las hojas del libro.")
    for sheet in original:
        after = recalculated[sheet.title]
        if sheet.merged_cells.ranges != after.merged_cells.ranges:
            raise TemplateError("El recálculo cambió las combinaciones de celdas.")
        coordinates = sheet._cells.keys() | after._cells.keys()
        for row, column in coordinates:
            cell = sheet.cell(row, column)
            if cell.value != after.cell(row, column).value:
                raise TemplateError(f"El recálculo modificó {sheet.title}!{cell.coordinate}.")
            if cell.data_type == "f":
                value = cached[sheet.title][cell.coordinate]
                if value.data_type == "e" or value.value is None:
                    raise TemplateError(f"Error de cálculo en {sheet.title}!{cell.coordinate}.")
    return converted
