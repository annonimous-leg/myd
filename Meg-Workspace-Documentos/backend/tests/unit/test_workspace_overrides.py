"""Contrato de integración para ediciones humanas de Workspace."""
import unittest

from app.engines.procurement.workspace_overrides import model_with_workspace_overrides


class WorkspaceOverrideContractTests(unittest.TestCase):
    def setUp(self):
        self.original = {"bidder": {"legal_name": "Original"}, "economic": {"importe": 100}}
        self.binding = {
            "canonical_paths": ["bidder.legal_name", "economic.importe"],
            "workspace_docx": {"fields": {
                "bidder.legal_name": {"tag": "empresa"},
                "economic.importe": {"tag": "importe", "partida_numero": "1"},
            }},
        }

    def run_model(self, content, **kwargs):
        return model_with_workspace_overrides(
            self.original, kwargs.get("binding", self.binding), content,
            human_modified=kwargs.get("human_modified", True),
            document_tender_revision=kwargs.get("document_tender_revision", 4),
            current_tender_revision=kwargs.get("current_tender_revision", 4),
        )

    def test_docx_overrides_are_applied_and_do_not_mutate_original(self):
        result, paths = self.run_model({"docx_field_overrides": {"bidder.legal_name": "Nueva"}})
        self.assertEqual(paths, ["bidder.legal_name"])
        self.assertEqual(result["bidder"]["legal_name"], "Nueva")
        self.assertEqual(self.original["bidder"]["legal_name"], "Original")

    def test_docx_does_not_read_foreign_xlsx_overrides(self):
        model, paths = self.run_model({"xlsx_field_overrides": {"bidder.legal_name": "Otra"}})
        self.assertIs(model, self.original)
        self.assertEqual(paths, [])

    def test_xlsx_uses_xlsx_specific_key(self):
        binding = {"canonical_paths": ["bidder.legal_name"],
                   "workspace_xlsx": {"fields": {"bidder.legal_name": {"sheet": "A", "cell": "B4"}}}}
        model, paths = self.run_model({"xlsx_field_overrides": {"bidder.legal_name": "XLSX"}}, binding=binding)
        self.assertEqual(model["bidder"]["legal_name"], "XLSX")
        self.assertEqual(paths, ["bidder.legal_name"])

    def test_pdf_legacy_key_remains_supported(self):
        binding = {"canonical_paths": ["bidder.legal_name"], "compiler": "compile_annex_pdf"}
        model, paths = self.run_model({"field_overrides": {"bidder.legal_name": "PDF"}}, binding=binding)
        self.assertEqual(model["bidder"]["legal_name"], "PDF")
        self.assertEqual(paths, ["bidder.legal_name"])

    def test_legacy_field_overrides_still_work_for_templates(self):
        model, paths = self.run_model({"field_overrides": {"bidder.legal_name": "Legado"}})
        self.assertEqual(model["bidder"]["legal_name"], "Legado")
        self.assertEqual(paths, ["bidder.legal_name"])

    def test_stale_revision_blocks_projection(self):
        with self.assertRaisesRegex(ValueError, "otra revisión"):
            self.run_model({"docx_field_overrides": {"bidder.legal_name": "Vieja"}}, document_tender_revision=3)

    def test_undeclared_canonical_path_rejected(self):
        with self.assertRaisesRegex(ValueError, "fuera del catálogo"):
            self.run_model({"docx_field_overrides": {"bidder.id": "intrusión"}})

    def test_template_field_not_declared_rejected(self):
        binding = {"canonical_paths": ["bidder.legal_name"], "workspace_docx": {"fields": {}}}
        with self.assertRaisesRegex(ValueError, "no editable"):
            self.run_model({"docx_field_overrides": {"bidder.legal_name": "Cambio"}}, binding=binding)

    def test_read_only_budget_field_rejected(self):
        with self.assertRaisesRegex(ValueError, "solo lectura"):
            self.run_model({"docx_field_overrides": {"economic.importe": "999"}})

    def test_invalid_type_rejected(self):
        with self.assertRaisesRegex(ValueError, "texto validado"):
            self.run_model({"docx_field_overrides": {"bidder.legal_name": 123}})

    def test_unmodified_document_does_not_override(self):
        model, paths = self.run_model({"docx_field_overrides": {"bidder.legal_name": "X"}}, human_modified=False)
        self.assertIs(model, self.original)
        self.assertEqual(paths, [])

    def test_existing_scalar_cannot_be_used_as_nested_object(self):
        binding = {"canonical_paths": ["bidder.legal_name.part"],
                   "workspace_docx": {"fields": {"bidder.legal_name.part": {"tag": "x"}}}}
        with self.assertRaisesRegex(ValueError, "incompatible"):
            self.run_model({"docx_field_overrides": {"bidder.legal_name.part": "X"}}, binding=binding)


    def test_template_fields_without_duplicate_canonical_paths_are_editable(self):
        binding = {"workspace_docx": {"fields": {"bidder.legal_name": {"tag": "legal"}}}}
        model, paths = self.run_model(
            {"docx_field_overrides": {"bidder.legal_name": "Empresa de prueba"}},
            binding=binding,
        )
        self.assertEqual(model["bidder"]["legal_name"], "Empresa de prueba")
        self.assertEqual(paths, ["bidder.legal_name"])

    def test_template_fields_without_canonical_paths_reject_foreign_field(self):
        binding = {"workspace_docx": {"fields": {"bidder.legal_name": {"tag": "legal"}}}}
        with self.assertRaisesRegex(ValueError, "fuera del catálogo"):
            self.run_model({"docx_field_overrides": {"bidder.unknown": "X"}}, binding=binding)

    def test_stale_revision_blocks_even_empty_human_edits(self):
        with self.assertRaisesRegex(ValueError, "otra revisión"):
            self.run_model({"docx_field_overrides": {}}, document_tender_revision=3)

    def test_reviewed_edit_reaches_compiled_pdf_bytes(self):
        from io import BytesIO
        from pypdf import PdfReader
        from app.engines.procurement.compiler import ProcurementArtifactCompiler

        binding = {
            "format_code": "ANX-01", "title": "Carta empresarial",
            "compiler": "compile_annex_pdf",
            "canonical_paths": ["bidder.legal_name"],
        }
        reviewed, paths = self.run_model(
            {"field_overrides": {"bidder.legal_name": "Empresa Revisada"}},
            binding=binding,
        )
        original_bytes = ProcurementArtifactCompiler().compile_from_binding(binding, self.original)
        reviewed_bytes = ProcurementArtifactCompiler().compile_from_binding(binding, reviewed)
        reviewed_text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(reviewed_bytes)).pages)
        self.assertEqual(paths, ["bidder.legal_name"])
        self.assertNotEqual(original_bytes, reviewed_bytes)
        self.assertIn("Empresa Revisada", reviewed_text)

    def test_reviewed_edit_reaches_compiled_xlsx_cell(self):
        from io import BytesIO
        from openpyxl import load_workbook
        from app.engines.procurement.compiler import ProcurementArtifactCompiler

        original = {
            "facts": {"authority": "Dependencia", "object": "Proyecto original"},
            "economic": {"budget_total": 100},
        }
        binding = {
            "format_code": "FP-01", "title": "Oferta económica",
            "compiler": "compile_proposal_letter_xlsx",
            "canonical_paths": ["facts.object"],
        }
        reviewed, paths = model_with_workspace_overrides(
            original, binding, {"field_overrides": {"facts.object": "Proyecto modificado"}},
            human_modified=True, document_tender_revision=4,
            current_tender_revision=4,
        )
        xlsx = ProcurementArtifactCompiler().compile_from_binding(binding, reviewed)
        values = [cell.value for row in load_workbook(BytesIO(xlsx)).active for cell in row]
        self.assertIn("Proyecto modificado", values)
        self.assertNotIn("Proyecto original", values)
        self.assertEqual(paths, ["facts.object"])


if __name__ == "__main__":
    unittest.main()
