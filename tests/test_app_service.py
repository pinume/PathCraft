import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pathcraft.app_service import (
    execute_operation,
    load_mapping_columns,
    list_current_files,
    prepare_mapping_rename,
    prepare_pdf_conversion,
    prepare_rule_rename,
)
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

    def test_current_files_reflect_completed_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.touch()
            prepared = prepare_rule_rename(root, RenameRule(prefix="new-"))

            execute_operation(prepared)

            self.assertEqual(list_current_files(root), (root / "new-photo.jpg",))

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


if __name__ == "__main__":
    unittest.main()
