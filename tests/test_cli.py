import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from pathcraft.cli import (
    InteractiveConfig,
    OperationResult,
    _find_scoped_files,
    _print_status_message,
    _run_pdf2png,
    _run_rename_plan,
    main,
)
from pathcraft.config import DEFAULT_PDF_DPI
from pathcraft.exceptions import ExitProgram
from pathcraft.rename import build_plan
from pathcraft.rules import RenameRule


class CliTests(unittest.TestCase):
    def test_status_message_uses_green_in_a_terminal(self) -> None:
        class TerminalOutput(StringIO):
            def isatty(self) -> bool:
                return True

        output = TerminalOutput()
        with redirect_stdout(output):
            _print_status_message("处理完成：成功 28 个 PDF，生成 28 张 PNG，失败 0 个。")

        rendered = output.getvalue()
        self.assertIn("\033[1;32m", rendered)
        self.assertIn("处理完成：成功 28 个 PDF，生成 28 张 PNG，失败 0 个。", rendered)
        self.assertNotIn("╭", rendered)

        failure_output = TerminalOutput()
        with redirect_stdout(failure_output):
            _print_status_message("处理完成：失败 1 个。", has_failures=True)
        self.assertIn("\033[1;33m", failure_output.getvalue())

    def test_rename_runs_directly_with_progress_and_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "a.jpg"
            source.touch()
            plan = build_plan([source], RenameRule(prefix="new-"))
            output = StringIO()
            config = InteractiveConfig(
                root,
                "rename",
                RenameRule(prefix="new-"),
                menu_index=1,
            )

            with redirect_stdout(output):
                result = _run_rename_plan(config, plan)

            self.assertEqual(result.exit_code, 0)
            self.assertIn("处理文件 1/1", output.getvalue())
            self.assertNotIn("预览", output.getvalue())
            self.assertEqual(
                result.workspace[:4],
                ("处理结果", "成功：1 个", "跳过：0 个", "失败：0 个"),
            )

    def test_command_line_arguments_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.touch()

            errors = StringIO()
            with redirect_stderr(errors):
                status = main([str(root), "--prefix", "new-"])

            self.assertEqual(status, 2)
            self.assertIn("请直接运行：uv run main.py", errors.getvalue())
            self.assertTrue(source.exists())
            self.assertFalse((root / "new-photo.jpg").exists())

    def test_interactive_mode_can_replace_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "旧名称.jpg"
            source.touch()
            answers = ["4", "旧名称", "新名称", "q"]
            output = StringIO()

            with (
                patch("pathcraft.cli.choose_directory", return_value=root),
                patch("builtins.input", side_effect=answers),
                redirect_stdout(output),
            ):
                status = main([])

            self.assertEqual(status, 0)
            self.assertTrue((root / "新名称.jpg").exists())
            self.assertNotIn("预览", output.getvalue())
            self.assertNotIn("确认执行", output.getvalue())

    def test_interactive_mode_selects_prefix_position_from_menu(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.touch()
            answers = ["2", "1", "new-", "q"]

            with (
                patch("pathcraft.cli.choose_directory", return_value=root),
                patch("builtins.input", side_effect=answers),
            ):
                status = main([])

            self.assertEqual(status, 0)
            self.assertTrue((root / "new-photo.jpg").exists())

    def test_interactive_mode_can_select_pdf_conversion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            answers = ["1", "q"]

            with (
                patch("pathcraft.cli.choose_directory", return_value=root),
                patch("builtins.input", side_effect=answers),
                patch(
                    "pathcraft.cli._run_pdf2png",
                    return_value=OperationResult(0, ()),
                ) as run_pdf2png,
            ):
                status = main([])

            self.assertEqual(status, 0)
            config = run_pdf2png.call_args.args[0]
            self.assertIsInstance(config, InteractiveConfig)
            self.assertEqual(config.root, root)

    def test_pdf_conversion_uses_configured_default_dpi(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "invoice.pdf"
            source.touch()
            plan = SimpleNamespace(source=source, outputs=(root / "output.png",))
            config = InteractiveConfig(root=root, action="pdf2png")
            output = StringIO()

            with (
                patch(
                    "pathcraft.pdf.build_conversion_plans",
                    return_value=([plan], []),
                ),
                patch(
                    "pathcraft.pdf.execute_conversion_plans",
                    return_value=SimpleNamespace(completed=[plan], failed=[]),
                ) as execute,
                redirect_stdout(output),
            ):
                result = _run_pdf2png(config)

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(execute.call_args.kwargs["dpi"], DEFAULT_PDF_DPI)
            self.assertNotIn("PDF 已移至", output.getvalue())
            self.assertNotIn(source.name, output.getvalue())
            self.assertIn("成功 1 个 PDF", output.getvalue())
            self.assertEqual(
                result.workspace[:4],
                (
                    "处理结果",
                    "成功 PDF：1 个",
                    "生成 PNG：1 张",
                    "失败：0 个",
                ),
            )

    def test_scan_includes_current_and_all_nested_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            current_file = root / "current.txt"
            current_file.touch()
            selected = root / "selected"
            selected.mkdir()
            selected_file = selected / "selected.txt"
            selected_file.touch()
            nested = root / "nested"
            nested.mkdir()
            nested_file = nested / "nested.txt"
            nested_file.touch()
            hidden = root / ".hidden"
            hidden.mkdir()
            (hidden / "ignored.txt").touch()
            config = InteractiveConfig(root=root, action="rename")

            files = _find_scoped_files(config)

            self.assertEqual(files, [current_file, nested_file, selected_file])

    def test_interactive_loop_preserves_earlier_failure_status(self) -> None:
        config = InteractiveConfig(Path.cwd(), "rename", RenameRule(prefix="new-"))

        with (
            patch(
                "pathcraft.cli._interactive_configuration",
                side_effect=[config, config, ExitProgram],
            ),
            patch(
                "pathcraft.cli._dispatch",
                side_effect=[OperationResult(1, ()), OperationResult(0, ())],
            ),
        ):
            status = main([])

        self.assertEqual(status, 1)

    def test_interactive_main_menu_keeps_last_operation_result(self) -> None:
        config = InteractiveConfig(Path.cwd(), "pdf2png")

        def dispatch(_config: InteractiveConfig) -> OperationResult:
            return OperationResult(0, ("处理结果", "成功 PDF：2 个"))

        with (
            patch(
                "pathcraft.cli._interactive_configuration",
                side_effect=[config, ExitProgram],
            ) as configure,
            patch("pathcraft.cli._dispatch", side_effect=dispatch),
        ):
            status = main([])

        self.assertEqual(status, 0)
        self.assertEqual(
            configure.call_args_list[1].args[0],
            ["处理结果", "成功 PDF：2 个"],
        )


if __name__ == "__main__":
    unittest.main()
