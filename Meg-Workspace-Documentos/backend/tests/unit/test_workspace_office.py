from io import BytesIO
from shutil import which

import pytest
from openpyxl import Workbook, load_workbook

from app.engines.procurement.office import recalculate_xlsx
from app.engines.procurement.workspace_docx import TemplateError


@pytest.mark.skipif(not which("soffice"), reason="Requiere LibreOffice")
@pytest.mark.parametrize("formula,expected", [("=A1*B1", 60), ("=1/0", None)])
def test_recalculate_formula_before_saving(formula, expected):
    book = Workbook()
    book.active.append([5, 12, formula])
    source = BytesIO()
    book.save(source)
    if expected is None:
        with pytest.raises(TemplateError, match="Error de cálculo"):
            recalculate_xlsx(source.getvalue(), 512 * 1024)
        return
    result = recalculate_xlsx(source.getvalue(), 512 * 1024)
    assert load_workbook(BytesIO(result)).active["C1"].value == formula
    assert load_workbook(BytesIO(result), data_only=True).active["C1"].value == expected
