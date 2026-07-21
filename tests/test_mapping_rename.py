import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import openpyxl

from pathcraft.cli import main
from pathcraft.mapping_rename import build_mapping_plan, load_mapping_table
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

    def test_plan_honors_recursion_and_file_type_options(self) -> None:
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
                [("photo", "renamed"), ("notes", "ignored"), ("nested", "ignored")],
                recursive=False,
                all_files=False,
            )

            self.assertIsNone(plan[0].problem)
            self.assertEqual(plan[1].problem, "未找到原文件")
            self.assertEqual(plan[2].problem, "未找到原文件")

    def test_interactive_mapping_rename(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.txt"
            source.touch()
            mapping_file = root / "mapping.csv"
            mapping_file.write_text("旧列,新列\nold.txt,new.txt\n", encoding="utf-8")
            output = StringIO()

            with (
                patch("pathcraft.cli.choose_directory", return_value=root),
                patch("pathcraft.cli.choose_mapping_file", return_value=mapping_file),
                patch(
                    "builtins.input",
                    side_effect=["5", "1", "1", "q"],
                ),
                redirect_stdout(output),
            ):
                status = main([])

            self.assertEqual(status, 0)
            self.assertTrue((root / "new.txt").exists())
            rendered = output.getvalue()
            self.assertIn("映射文件：mapping.csv", rendered)
            self.assertIn("检测到列标题：旧列、新列", rendered)
            self.assertIn("请选择原名称所在列：", rendered)
            self.assertIn("➤ 1. 旧列", rendered)
            self.assertIn("请选择新名称所在列：", rendered)

    def test_manual_mapping_path_is_entered_in_main_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "old.txt"
            source.touch()
            mapping_file = root / "mapping.csv"
            mapping_file.write_text("旧列,新列\nold.txt,new.txt\n", encoding="utf-8")

            def choose_file(_root: Path, *, manual_path_reader):
                entered = manual_path_reader(
                    "请输入映射文件路径：",
                    ["映射文件不存在：missing.csv"],
                )
                return Path(entered)

            with (
                patch("pathcraft.cli.choose_directory", return_value=root),
                patch("pathcraft.cli.choose_mapping_file", side_effect=choose_file),
                patch(
                    "pathcraft.cli.ask_workspace_text",
                    return_value=str(mapping_file),
                ) as workspace_editor,
                patch("builtins.input", side_effect=["5", "1", "1", "q"]),
                redirect_stdout(StringIO()),
            ):
                status = main([])

            self.assertEqual(status, 0)
            self.assertTrue((root / "new.txt").exists())
            call = workspace_editor.call_args
            self.assertEqual(call.args[0], "请输入映射文件路径：")
            self.assertEqual(call.kwargs["selected"], 4)
            self.assertIn(
                "映射文件不存在：missing.csv",
                call.kwargs["completed_lines"],
            )


if __name__ == "__main__":
    unittest.main()
