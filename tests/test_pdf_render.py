import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pathcraft.config import MINIMUM_PDF_DPI
from pathcraft.exceptions import PdfPageCountChangedError, PdfRenderError
from pathcraft.pdf.extract import (
    PdfConversionPlan,
    PdfDependencyError,
    build_conversion_plans,
    load_pymupdf,
)
from pathcraft.pdf import render
from pathcraft.pdf.render import convert_pdf_plan, execute_conversion_plans
from tests.pdf_fakes import FakePage, FakePixmap, FakePyMuPDF

try:
    pymupdf = load_pymupdf()
except PdfDependencyError:
    pymupdf = None


class PdfRenderTests(unittest.TestCase):
    def test_conversion_writes_next_to_source_and_archives_pdf(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            module = FakePyMuPDF()
            plans, _ = build_conversion_plans(root, pymupdf_module=module)

            result = execute_conversion_plans(plans, 300, pymupdf_module=module)

            self.assertFalse(result.failed)
            self.assertFalse(source.exists())
            self.assertTrue((root / "示例公司.png").exists())
            self.assertTrue((root / ".pdf" / "invoice.pdf").exists())
            self.assertFalse((root / "png").exists())

    def test_conversion_reports_file_and_page_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.pdf"
            second = root / "b.pdf"
            first.touch()
            second.touch()
            module = FakePyMuPDF()
            plans, _ = build_conversion_plans(root, pymupdf_module=module)
            file_progress = []
            page_progress = []

            result = execute_conversion_plans(
                plans,
                300,
                pymupdf_module=module,
                on_progress=lambda index, total, path: file_progress.append(
                    (index, total, path)
                ),
                on_page_progress=lambda index, total, path: page_progress.append(
                    (index, total, path)
                ),
            )

            self.assertFalse(result.failed)
            self.assertEqual(file_progress, [(1, 2, first), (2, 2, second)])
            self.assertEqual(page_progress, [(1, 1, first), (1, 1, second)])

    def test_file_progress_is_reported_only_after_a_pdf_succeeds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            planning_module = FakePyMuPDF()
            plans, _ = build_conversion_plans(root, pymupdf_module=planning_module)
            progress = []

            result = execute_conversion_plans(
                plans,
                300,
                pymupdf_module=FakePyMuPDF([FakePage(fail_render=True)]),
                on_progress=lambda index, total, path: progress.append((index, total, path)),
            )

            self.assertTrue(result.failed)
            self.assertEqual(progress, [])

    def test_render_failure_cleans_outputs_and_keeps_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            planning_module = FakePyMuPDF([FakePage(), FakePage()])
            plans, _ = build_conversion_plans(root, pymupdf_module=planning_module)
            failing_module = FakePyMuPDF([FakePage(), FakePage(fail_render=True)])

            with patch("pathcraft.pdf.render.report_exception") as report:
                result = execute_conversion_plans(
                    plans,
                    300,
                    pymupdf_module=failing_module,
                )

            self.assertEqual(len(result.failed), 1)
            report.assert_called_once()
            self.assertTrue(source.exists())
            self.assertFalse(list(root.rglob("*.png")))
            self.assertFalse((root / ".pdf").exists())

    def test_source_changed_after_preview_is_not_converted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            module = FakePyMuPDF()
            plans, _ = build_conversion_plans(root, pymupdf_module=module)

            source.write_bytes(b"replacement content")
            result = execute_conversion_plans(plans, 300, pymupdf_module=module)

            self.assertEqual(len(result.failed), 1)
            self.assertIn("预览后发生变化", result.failed[0][1])
            self.assertTrue(source.exists())
            self.assertFalse(list(root.glob("*.png")))
            self.assertFalse((root / ".pdf").exists())

    def test_render_failure_raises_domain_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            plan = PdfConversionPlan(
                source,
                "示例公司",
                (root / "示例公司.png",),
                root / ".pdf" / "invoice.pdf",
            )

            with self.assertRaisesRegex(PdfRenderError, "第 1 页渲染失败"):
                convert_pdf_plan(
                    plan,
                    300,
                    pymupdf_module=FakePyMuPDF([FakePage(fail_render=True)]),
                )

            self.assertTrue(source.exists())
            self.assertFalse(list(root.rglob("*.png")))

    def test_partial_render_file_is_removed_after_save_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            plan = PdfConversionPlan(
                source,
                "示例公司",
                (root / "示例公司.png",),
                root / ".pdf" / "invoice.pdf",
            )

            def partial_save(_pixmap, path: Path) -> None:
                Path(path).write_bytes(b"partial")
                raise OSError("模拟部分写入失败")

            with patch.object(FakePixmap, "save", partial_save):
                with self.assertRaisesRegex(PdfRenderError, "第 1 页渲染失败"):
                    convert_pdf_plan(
                        plan,
                        300,
                        pymupdf_module=FakePyMuPDF([FakePage()]),
                    )

            self.assertTrue(source.exists())
            self.assertFalse(
                [path for path in root.iterdir() if path.name.endswith(".working.png")]
            )

    def test_archive_failure_rolls_back_images_and_keeps_source(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            module = FakePyMuPDF()
            plans, _ = build_conversion_plans(root, pymupdf_module=module)
            move_without_overwrite = render.move_without_overwrite

            def fail_archive_move(current: Path, destination: Path) -> None:
                if destination.parent.name == ".pdf":
                    raise PermissionError("模拟归档失败")
                move_without_overwrite(current, destination)

            with patch(
                "pathcraft.pdf.render.move_without_overwrite",
                side_effect=fail_archive_move,
            ):
                result = execute_conversion_plans(
                    plans,
                    300,
                    pymupdf_module=module,
                )

            self.assertEqual(len(result.failed), 1)
            self.assertTrue(source.exists())
            self.assertFalse(list(root.glob("*.png")))
            self.assertFalse((root / ".pdf").exists())

    def test_invalid_dpi_does_not_create_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            plan = PdfConversionPlan(
                source,
                "示例公司",
                (root / "示例公司.png",),
                root / ".pdf" / "invoice.pdf",
            )

            with self.assertRaisesRegex(
                ValueError,
                f"DPI 不能低于 {MINIMUM_PDF_DPI}",
            ):
                convert_pdf_plan(
                    plan,
                    MINIMUM_PDF_DPI - 1,
                    pymupdf_module=FakePyMuPDF(),
                )

            self.assertFalse((root / ".pdf").exists())

    def test_changed_page_count_cleans_created_output_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            plan = PdfConversionPlan(
                source,
                "示例公司",
                (root / "示例公司.png",),
                root / ".pdf" / "invoice.pdf",
            )

            with self.assertRaisesRegex(
                PdfPageCountChangedError,
                "PDF 页数在识别后发生变化",
            ):
                convert_pdf_plan(
                    plan,
                    300,
                    pymupdf_module=FakePyMuPDF([FakePage(), FakePage()]),
                )

            self.assertFalse((root / ".pdf").exists())


@unittest.skipUnless(pymupdf is not None, "需要 PyMuPDF 依赖")
class RealPdfIntegrationTests(unittest.TestCase):
    def test_real_pdf_page_is_rendered_as_png(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            output = root / "Example Company.png"
            document = pymupdf.open()
            page = document.new_page()
            page.insert_text((72, 72), "Invoice")
            document.save(source)
            document.close()
            archive = root / ".pdf" / source.name
            plan = PdfConversionPlan(source, "Example Company", (output,), archive)

            convert_pdf_plan(plan, 150, pymupdf_module=pymupdf)

            self.assertFalse(source.exists())
            self.assertTrue(archive.exists())
            self.assertEqual(output.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
