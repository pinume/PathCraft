import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

from pathcraft.mapping_rename import _detect_dialect, build_mapping_plan, load_mapping_table
from pathcraft.rename import execute_plan


class MappingTableTests(unittest.TestCase):
    def test_csv_columns_are_selected_by_user_title(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "mapping.csv"
            source.write_text(
                "当前文件,修改之后,备注\nold.txt,new.txt,示例\n",
                encoding="utf-8",
            )

            table = load_mapping_table(source)

            self.assertEqual(table.columns, ("当前文件", "修改之后", "备注"))
            self.assertEqual(
                table.mappings("当前文件", "修改之后"),
                [("old.txt", "new.txt")],
            )

    def test_tab_separated_txt_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "mapping.txt"
            source.write_text("旧值\t新值\na.jpg\tb.jpg\n", encoding="utf-8")

            table = load_mapping_table(source)

            self.assertEqual(table.mappings("旧值", "新值"), [("a.jpg", "b.jpg")])

    def test_dialect_fallback_uses_the_delimiter_present_in_short_text(self) -> None:
        with patch(
            "pathcraft.mapping_rename.csv.Sniffer.sniff",
            side_effect=csv.Error,
        ):
            dialect = _detect_dialect("旧值;新值", ".txt")

        self.assertEqual(dialect.delimiter, ";")

    def test_excel_is_supported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "mapping.xlsx"
            workbook = openpyxl.Workbook()
            worksheet = workbook.active
            worksheet.append(["原文件", "新文件"])
            worksheet.append(["before.pdf", "after.pdf"])
            workbook.save(source)
            workbook.close()

            table = load_mapping_table(source)

            self.assertEqual(
                table.mappings("原文件", "新文件"),
                [("before.pdf", "after.pdf")],
            )


class MappingRenameTests(unittest.TestCase):
    def test_plan_matches_stem_and_preserves_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.txt"
            source.touch()

            plan = build_mapping_plan(root, [("old", "new")])
            result = execute_plan(plan)

            self.assertFalse(result.failed)
            self.assertTrue((root / "new.txt").exists())
            self.assertFalse(source.exists())

    def test_duplicate_basenames_are_reported_as_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one"
            second = root / "two"
            first.mkdir()
            second.mkdir()
            (first / "same.txt").touch()
            (second / "same.txt").touch()

            plan = build_mapping_plan(root, [("same.txt", "new.txt")])

            self.assertEqual(plan[0].problem, "原名称匹配多个文件")

    def test_hidden_duplicate_does_not_make_mapping_ambiguous(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "same.txt"
            visible.touch()
            hidden_directory = root / ".hidden"
            hidden_directory.mkdir()
            (hidden_directory / "same.txt").touch()

            plan = build_mapping_plan(root, [("same.txt", "new.txt")])

            self.assertIsNone(plan[0].problem)
            self.assertEqual(plan[0].source, visible)

    def test_plan_honors_recursion_option(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "photo.jpg"
            image.touch()
            text = root / "notes.txt"
            text.touch()
            nested = root / "nested"
            nested.mkdir()
            nested_image = nested / "nested.jpg"
            nested_image.touch()

            plan = build_mapping_plan(
                root,
                [("photo", "renamed"), ("notes", "notes-new"), ("nested", "ignored")],
                recursive=False,
            )

            self.assertIsNone(plan[0].problem)
            self.assertIsNone(plan[1].problem)
            self.assertEqual(plan[2].problem, "未找到原文件")

if __name__ == "__main__":
    unittest.main()
