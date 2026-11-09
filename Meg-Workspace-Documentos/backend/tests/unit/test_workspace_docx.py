# © 2026 Carl Own Megalodon
from hashlib import sha256
from io import BytesIO
from unittest import TestCase
from zipfile import ZipFile

from docx import Document
from lxml import etree

from app.engines.procurement.workspace_docx import Field, TemplateError, WORD, render_draft

FIELDS = {"name": Field("signer"), "role": Field("title")}


def with_parts(source, replacements):
    output = BytesIO()
    with ZipFile(BytesIO(source)) as initial, ZipFile(output, "w") as result:
        for entry in initial.infolist():
            result.writestr(entry, replacements.get(entry.filename, initial.read(entry)))
    return output.getvalue()


def package_parts(source):
    with ZipFile(BytesIO(source)) as docx:
        return {entry: docx.read(entry) for entry in docx.namelist()}


def tag_run(run, key):
    parent = run.getparent()
    control = etree.Element(WORD + "sdt")
    props = etree.SubElement(control, WORD + "sdtPr")
    etree.SubElement(props, WORD + "tag").set(WORD + "val", key)
    etree.SubElement(props, WORD + "text")
    etree.SubElement(props, WORD + "showingPlcHdr")
    body = etree.SubElement(control, WORD + "sdtContent")
    parent.replace(run, control)
    body.append(run)


def fixture():
    doc = Document()
    doc.sections[0].header.paragraphs[0].text = "Encabezado"
    doc.add_paragraph("Firma")
    doc.add_paragraph().add_run("Nombre").bold = True
    doc.add_table(rows=1, cols=1).cell(0, 0).text = "Cargo"
    doc.add_page_break()
    doc.add_paragraph("Texto libre")
    output = BytesIO()
    doc.save(output)
    source = output.getvalue()
    root = etree.fromstring(package_parts(source)["word/document.xml"])
    for run in root.iter(WORD + "r"):
        node = run.find(WORD + "t")
        if node is not None and node.text in ("Nombre", "Cargo"):
            tag_run(run, {"Nombre": "signer", "Cargo": "title"}[node.text])
    return with_parts(source, {"word/document.xml": etree.tostring(root)})


class DocxTemplateTests(TestCase):
    def setUp(self):
        self.original = fixture()
        self.values = {"name": " Ana & José ", "role": "Supervisión"}

    def test_changes_only_selected_nodes_and_keeps_package_readable(self):
        draft = render_draft(self.original, FIELDS, self.values)
        self.assertFalse(draft.submission_eligible)
        self.assertEqual(draft.source_sha256, sha256(self.original).hexdigest())
        self.assertEqual(draft.content_sha256, sha256(draft.content).hexdigest())
        self.assertEqual(draft.content, render_draft(self.original, FIELDS, self.values).content)
        before = package_parts(self.original)
        after = package_parts(draft.content)
        self.assertEqual(before.keys(), after.keys())
        self.assertEqual([key for key in before if before[key] != after[key]], ["word/document.xml"])
        root = etree.fromstring(after["word/document.xml"])
        controls = list(root.iter(WORD + "sdt"))
        self.assertEqual([item.find(".//" + WORD + "t").text for item in controls],
                         list(self.values.values()))
        self.assertIsNotNone(controls[0].find(".//" + WORD + "b"))
        self.assertFalse(list(root.iter(WORD + "showingPlcHdr")))
        doc = Document(BytesIO(draft.content))
        self.assertEqual(doc.paragraphs[-1].text, "Texto libre")
        self.assertEqual(doc.sections[0].header.paragraphs[0].text, "Encabezado")
        self.assertEqual(len(doc.tables), 1)

    def test_missing_unknown_invalid_or_unmapped_fields(self):
        cases = [
            (FIELDS, {"name": "Ana"}),
            (FIELDS, {**self.values, "unknown": "value"}),
            (FIELDS, {**self.values, "role": "Una\nLínea"}),
            ({**FIELDS, "name": Field("unknown")}, self.values),
        ]
        for fields, values in cases:
            with self.subTest(values=values), self.assertRaises(TemplateError):
                render_draft(self.original, fields, values)

    def test_rejects_external_relationship(self):
        relationships = package_parts(self.original)["_rels/.rels"]
        root = etree.fromstring(relationships)
        root[0].set("TargetMode", "External")
        root[0].set("Target", "https://example.invalid")
        changed = with_parts(self.original, {"_rels/.rels": etree.tostring(root)})
        with self.assertRaisesRegex(TemplateError, "externas"):
            render_draft(changed, FIELDS, self.values)

    def test_rejects_duplicate_and_locked_controls(self):
        for lock in (False, True):
            root = etree.fromstring(package_parts(self.original)["word/document.xml"])
            controls = list(root.iter(WORD + "sdt"))
            props = controls[1].find(WORD + "sdtPr")
            if lock:
                etree.SubElement(props, WORD + "lock").set(WORD + "val", "sdtContentLocked")
            else:
                props.find(WORD + "tag").set(WORD + "val", "signer")
            changed = with_parts(self.original, {"word/document.xml": etree.tostring(root)})
            with self.assertRaisesRegex(TemplateError, "incompatible o duplicado"):
                render_draft(changed, FIELDS, self.values)

    def test_rejects_malformed_package(self):
        with self.assertRaises(TemplateError):
            render_draft(b"not a docx", FIELDS, self.values)
