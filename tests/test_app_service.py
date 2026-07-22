import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pathcraft.undo as undo_module
from pathcraft.app_service import (
    PreparedOperation,
    execute_operation,
    execute_undo_operation,
    load_mapping_columns,
    list_current_files,
    prepare_mapping_rename,
    prepare_pdf_conversion,
    prepare_rule_rename,
)
from pathcraft.pdf.extract import build_conversion_plans
from tests.pdf_fakes import FakePyMuPDF
from pathcraft.rules import RenameRule


class AppServiceTests(unittest.TestCase):
    def test_rule_preview_and_execution_preserve_blocked_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.touch()
            conflict = root / "new-blocked.jpg"
            conflict.touch()
            blocked = root / "blocked.jpg"
            blocked.touch()

            with patch(
                "pathcraft.app_service.find_files",
                return_value=[source, blocked],
            ):
                prepared = prepare_rule_rename(root, RenameRule(prefix="new-"))

            rows = {row.source.name: row for row in prepared.preview_entries}
            self.assertEqual(rows["photo.jpg"].status, "ready")
            self.assertEqual(rows["blocked.jpg"].status, "blocked")
            self.assertEqual(rows["blocked.jpg"].detail, "目标文件已存在")
            self.assertTrue(source.exists(), "preview must not mutate files")

            summary = execute_operation(prepared)

            self.assertEqual((summary.succeeded, summary.skipped, summary.failed), (1, 1, 0))
            self.assertTrue((root / "new-photo.jpg").exists())
            self.assertTrue(blocked.exists())
            self.assertTrue(conflict.exists())

    def test_execution_rechecks_destination_created_after_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.touch()
            prepared = prepare_rule_rename(root, RenameRule(prefix="new-"))
            destination = root / "new-photo.jpg"
            destination.write_text("occupied", encoding="utf-8")

            summary = execute_operation(prepared)

            self.assertEqual(summary.succeeded, 0)
            self.assertEqual(summary.failed, 1)
            self.assertTrue(source.exists())
            self.assertEqual(destination.read_text(encoding="utf-8"), "occupied")

    def test_execution_rejects_source_replaced_after_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.write_text("original", encoding="utf-8")
            prepared = prepare_rule_rename(root, RenameRule(prefix="new-"))

            source.unlink()
            source.write_text("replacement content", encoding="utf-8")
            summary = execute_operation(prepared)

            self.assertEqual(summary.succeeded, 0)
            self.assertEqual(summary.failed, 1)
            self.assertTrue(source.exists())
            self.assertEqual(source.read_text(encoding="utf-8"), "replacement content")
            self.assertFalse((root / "new-photo.jpg").exists())
            self.assertIn("预览后发生变化", summary.details[0])

    def test_current_files_reflect_completed_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.touch()
            prepared = prepare_rule_rename(root, RenameRule(prefix="new-"))

            execute_operation(prepared)

            self.assertEqual(list_current_files(root), (root / "new-photo.jpg",))

    def test_last_rename_operation_can_be_undone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.write_text("original", encoding="utf-8")

            execution = execute_operation(
                prepare_rule_rename(root, RenameRule(prefix="new-"))
            )
            self.assertIsNotNone(execution.undo)
            undo = execute_undo_operation(execution.undo)

            self.assertEqual((undo.succeeded, undo.skipped, undo.failed), (1, 0, 0))
            self.assertIsNone(undo.undo)
            self.assertEqual(source.read_text(encoding="utf-8"), "original")
            self.assertFalse((root / "new-photo.jpg").exists())

    def test_rename_undo_never_overwrites_recreated_original_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.write_text("original", encoding="utf-8")
            execution = execute_operation(
                prepare_rule_rename(root, RenameRule(prefix="new-"))
            )
            source.write_text("occupied", encoding="utf-8")

            undo = execute_undo_operation(execution.undo)

            self.assertEqual(undo.succeeded, 0)
            self.assertGreaterEqual(undo.skipped + undo.failed, 1)
            self.assertIsNotNone(undo.undo)
            self.assertEqual(source.read_text(encoding="utf-8"), "occupied")
            self.assertTrue((root / "new-photo.jpg").exists())

    def test_rename_undo_restores_a_name_dependency_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.jpg"
            second = root / "new-a.jpg"
            first.write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            execution = execute_operation(
                prepare_rule_rename(root, RenameRule(prefix="new-"))
            )

            undo = execute_undo_operation(execution.undo)

            self.assertEqual((undo.succeeded, undo.skipped, undo.failed), (2, 0, 0))
            self.assertEqual(first.read_text(encoding="utf-8"), "first")
            self.assertEqual(second.read_text(encoding="utf-8"), "second")
            self.assertFalse((root / "new-new-a.jpg").exists())

    def test_rename_undo_preserves_replaced_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.write_text("original", encoding="utf-8")
            execution = execute_operation(
                prepare_rule_rename(root, RenameRule(prefix="new-"))
            )
            result = root / "new-photo.jpg"
            result.unlink()
            result.write_text("modified", encoding="utf-8")

            undo = execute_undo_operation(execution.undo)

            self.assertEqual(undo.succeeded, 0)
            self.assertEqual(undo.failed, 1)
            self.assertIsNotNone(undo.undo)
            self.assertFalse(source.exists())
            self.assertEqual(result.read_text(encoding="utf-8"), "modified")

    def test_mapping_columns_preview_and_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "old.txt").touch()
            mapping = root / "mapping.csv"
            mapping.write_text("old,new\nold.txt,new.txt\n", encoding="utf-8")

            self.assertEqual(load_mapping_columns(mapping), ("old", "new"))
            prepared = prepare_mapping_rename(root, mapping, "old", "new")
            self.assertEqual(prepared.preview_entries[0].destination.name, "new.txt")

            summary = execute_operation(prepared)

            self.assertEqual(summary.succeeded, 1)
            self.assertTrue((root / "new.txt").exists())

    def test_mapping_execution_rejects_source_replaced_after_preview(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.txt"
            source.write_text("original", encoding="utf-8")
            mapping = root / "mapping.csv"
            mapping.write_text("old,new\nold.txt,new.txt\n", encoding="utf-8")
            prepared = prepare_mapping_rename(root, mapping, "old", "new")

            source.unlink()
            source.write_text("replacement content", encoding="utf-8")
            summary = execute_operation(prepared)

            self.assertEqual(summary.failed, 1)
            self.assertTrue(source.exists())
            self.assertFalse((root / "new.txt").exists())

    def test_mapping_columns_must_be_distinct(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mapping = root / "mapping.csv"
            mapping.write_text("old,new\na,b\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "不能相同"):
                prepare_mapping_rename(root, mapping, "old", "old")

    def test_mapping_columns_only_reads_excel_header(self) -> None:
        def rows():
            yield ("old", "new")
            raise AssertionError("column discovery must not read data rows")

        worksheet = Mock()
        worksheet.iter_rows.return_value = rows()
        workbook = Mock(active=worksheet)

        with patch("openpyxl.load_workbook", return_value=workbook):
            columns = load_mapping_columns(Path("mapping.xlsx"))

        self.assertEqual(columns, ("old", "new"))
        workbook.close.assert_called_once_with()

    def test_pdf_preview_and_execution_summary_include_planning_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            invalid = root / "invalid.pdf"
            invalid.touch()
            plan = SimpleNamespace(
                source=source,
                outputs=(root / "buyer.png",),
                archive=root / ".pdf" / source.name,
            )

            with patch(
                "pathcraft.app_service.build_conversion_plans",
                return_value=([plan], [(invalid, "无法识别")]),
            ):
                prepared = prepare_pdf_conversion(root)

            self.assertEqual([row.status for row in prepared.preview_entries], ["ready", "blocked"])

            with patch(
                "pathcraft.app_service.execute_conversion_plans",
                return_value=SimpleNamespace(completed=[plan], failed=[]),
            ):
                summary = execute_operation(prepared)

            self.assertEqual((summary.succeeded, summary.skipped, summary.failed), (1, 1, 0))
            self.assertIn("invalid.pdf：无法识别", summary.details)

    def test_last_pdf_conversion_can_be_undone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            module = FakePyMuPDF()
            plans, failures = build_conversion_plans(root, pymupdf_module=module)
            prepared = PreparedOperation(
                "pdf",
                root,
                (),
                pdf_plans=tuple(plans),
                planning_failures=tuple(failures),
            )

            with patch("pathcraft.pdf.render.load_pymupdf", return_value=module):
                execution = execute_operation(prepared)
            self.assertIsNotNone(execution.undo)
            output = root / "示例公司.png"
            self.assertTrue(output.exists())

            undo = execute_undo_operation(execution.undo)

            self.assertEqual((undo.succeeded, undo.skipped, undo.failed), (1, 0, 0))
            self.assertTrue(source.exists())
            self.assertFalse(output.exists())
            self.assertFalse((root / ".pdf").exists())

    def test_pdf_undo_preserves_modified_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            module = FakePyMuPDF()
            plans, failures = build_conversion_plans(root, pymupdf_module=module)
            prepared = PreparedOperation(
                "pdf",
                root,
                (),
                pdf_plans=tuple(plans),
                planning_failures=tuple(failures),
            )
            with patch("pathcraft.pdf.render.load_pymupdf", return_value=module):
                execution = execute_operation(prepared)
            output = root / "示例公司.png"
            output.write_bytes(b"x" * output.stat().st_size)

            undo = execute_undo_operation(execution.undo)

            self.assertEqual(undo.succeeded, 0)
            self.assertEqual(undo.failed, 1)
            self.assertIsNotNone(undo.undo)
            self.assertTrue(output.read_bytes().startswith(b"x"))
            self.assertFalse(source.exists())
            self.assertTrue((root / ".pdf" / "invoice.pdf").exists())

    def test_pdf_undo_restores_staged_images_when_archive_restore_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            module = FakePyMuPDF()
            plans, failures = build_conversion_plans(root, pymupdf_module=module)
            prepared = PreparedOperation(
                "pdf",
                root,
                (),
                pdf_plans=tuple(plans),
                planning_failures=tuple(failures),
            )
            with patch("pathcraft.pdf.render.load_pymupdf", return_value=module):
                execution = execute_operation(prepared)
            output = root / "示例公司.png"

            original_move = undo_module.move_without_overwrite

            def fail_archive_restore(current: Path, destination: Path) -> None:
                if destination == source:
                    raise PermissionError("模拟归档恢复失败")
                original_move(current, destination)

            with patch.object(
                undo_module,
                "move_without_overwrite",
                side_effect=fail_archive_restore,
            ):
                undo = execute_undo_operation(execution.undo)

            self.assertEqual(undo.failed, 1)
            self.assertIsNotNone(undo.undo)
            self.assertFalse(source.exists())
            self.assertTrue(output.exists())
            self.assertTrue((root / ".pdf" / "invoice.pdf").exists())
            self.assertFalse(list(root.glob(".pathcraft-undo-*.tmp")))


if __name__ == "__main__":
    unittest.main()
