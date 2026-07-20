import tempfile
import unittest
from pathlib import Path

from pathcraft.exceptions import BuyerNameRecognitionError
from pathcraft.pdf.extract import (
    build_conversion_plans,
    find_pdf_files,
    recognize_buyer_name,
)
from tests.pdf_fakes import FakeDocument, FakePage, FakePyMuPDF


class PdfExtractTests(unittest.TestCase):
    def test_scanner_is_recursive_and_case_insensitive(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.PDF"
            first.touch()
            nested = root / "nested"
            nested.mkdir()
            second = nested / "b.pdf"
            second.touch()
            (root / ".hidden.pdf").touch()
            hidden_directory = root / ".hidden"
            hidden_directory.mkdir()
            (hidden_directory / "ignored.pdf").touch()
            self.assertEqual(find_pdf_files(root), [first, second])
            self.assertEqual(find_pdf_files(root, recursive=False), [first])

    def test_plans_recognize_buyer_and_reserve_duplicate_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.pdf").touch()
            (root / "b.pdf").touch()

            plans, failures = build_conversion_plans(root, pymupdf_module=FakePyMuPDF())

            self.assertFalse(failures)
            self.assertEqual([plan.buyer_name for plan in plans], ["示例公司", "示例公司"])
            self.assertEqual(plans[0].outputs[0].name, "示例公司.png")
            self.assertEqual(plans[1].outputs[0].name, "示例公司_2.png")
            self.assertEqual(plans[0].outputs[0].parent, root)
            self.assertEqual(plans[0].archive, root / ".pdf" / "a.pdf")
            self.assertEqual(plans[1].archive, root / ".pdf" / "b.pdf")

    def test_archive_name_does_not_overwrite_an_existing_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            archive_directory = root / ".pdf"
            archive_directory.mkdir()
            (archive_directory / "invoice.pdf").touch()

            plans, failures = build_conversion_plans(
                root,
                pymupdf_module=FakePyMuPDF(),
            )

            self.assertFalse(failures)
            self.assertEqual(plans[0].archive, archive_directory / "invoice_2.pdf")

    def test_buyer_name_is_sanitized_for_a_filename(self) -> None:
        words = [
            (20, 10, 60, 30, "名称："),
            (62, 10, 150, 30, "示例/公司"),
        ]

        buyer_name = recognize_buyer_name(FakeDocument([FakePage(words)]))

        self.assertEqual(buyer_name, "示例_公司")

    def test_missing_buyer_label_raises_domain_error(self) -> None:
        with self.assertRaisesRegex(
            BuyerNameRecognitionError,
            "未找到购买方",
        ):
            recognize_buyer_name(FakeDocument([FakePage([])]))

    def test_plans_report_encrypted_and_empty_pdfs_without_stopping(self) -> None:
        class PlanningModule:
            def open(self, path):
                if Path(path).name == "encrypted.pdf":
                    document = FakeDocument([FakePage()])
                    document.needs_pass = True
                    return document
                if Path(path).name == "empty.pdf":
                    return FakeDocument([])
                return FakeDocument([FakePage()])

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ("empty.pdf", "encrypted.pdf", "valid.pdf"):
                (root / name).touch()

            plans, failures = build_conversion_plans(
                root,
                pymupdf_module=PlanningModule(),
            )

            self.assertEqual([plan.source.name for plan in plans], ["valid.pdf"])
            self.assertEqual(
                [(path.name, reason) for path, reason in failures],
                [
                    ("empty.pdf", "PDF 不包含页面"),
                    ("encrypted.pdf", "PDF 已加密，需要密码"),
                ],
            )

if __name__ == "__main__":
    unittest.main()
