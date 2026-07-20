import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pathcraft.exceptions import ExitProgram, PreviousStep, ReturnToMainMenu
from pathcraft.prompts import (
    MENU_LOGO,
    MENU_TAGLINE,
    _ask_menu_choice,
    _choose_directory,
    _menu_frame,
)


class PromptMenuTests(unittest.TestCase):
    def test_directory_picker_uses_each_platform_system_dialog(self) -> None:
        selected = Path.cwd()

        with (
            patch("pathcraft.prompts.os.name", "nt"),
            patch("pathcraft.prompts._choose_windows_directory", return_value=selected) as chooser,
        ):
            self.assertEqual(_choose_directory(), selected)
            chooser.assert_called_once_with()

        with (
            patch("pathcraft.prompts.os.name", "posix"),
            patch("pathcraft.prompts.sys.platform", "darwin"),
            patch("pathcraft.prompts._choose_macos_directory", return_value=selected) as chooser,
        ):
            self.assertEqual(_choose_directory(), selected)
            chooser.assert_called_once_with()

        with (
            patch("pathcraft.prompts.os.name", "posix"),
            patch("pathcraft.prompts.sys.platform", "linux"),
            patch("pathcraft.prompts._choose_linux_directory", return_value=selected) as chooser,
        ):
            self.assertEqual(_choose_directory(), selected)
            chooser.assert_called_once_with()

    def test_menu_uses_logo_pointer_and_shortcuts_without_box(self) -> None:
        options = [
            ("1", "PDF 转 PNG", "识别购买方并生成 PNG"),
            ("2", "批量重命名", "处理文件名称"),
        ]

        lines, selected_row = _menu_frame(options, selected=0, width=72)

        rendered = "\n".join(lines)
        self.assertIn(MENU_LOGO[0].strip(), rendered)
        self.assertIn(MENU_TAGLINE, rendered)
        self.assertTrue(lines[selected_row].startswith("➤ 1. PDF 转 PNG"))
        self.assertIn("识别购买方并生成 PNG", lines[selected_row])
        self.assertIn("↑↓ | Enter 确认", rendered)
        self.assertIn("Z 返回主菜单", rendered)
        self.assertIn("U 上一步", rendered)
        self.assertIn("Q/Esc 退出程序", rendered)
        self.assertNotIn("╭", rendered)

        compact_lines, _ = _menu_frame(
            [("1", "返回主菜单"), ("2", "退出程序")],
            selected=0,
            width=72,
        )
        self.assertNotIn(MENU_LOGO[0].strip(), "\n".join(compact_lines))

    def test_menu_shortcuts_are_anchored_to_terminal_bottom(self) -> None:
        lines, _ = _menu_frame(
            [("1", "PDF 转 PNG", "识别购买方并生成 PNG")],
            selected=0,
            width=100,
            height=24,
        )

        self.assertEqual(len(lines), 24)
        self.assertIn("Q/Esc 退出程序", lines[-1])

    def test_menu_has_separators_around_progress_area(self) -> None:
        lines, _ = _menu_frame(
            [("1", "PDF 转 PNG", "识别购买方并生成 PNG")],
            selected=0,
            width=72,
            height=20,
            content_lines=["处理 PDF 1/2：a.pdf", "处理 PDF 2/2：b.pdf"],
        )
        separators = [
            index for index, line in enumerate(lines) if line == "─" * 72
        ]

        self.assertEqual(len(separators), 2)
        self.assertEqual(separators[-1], len(lines) - 2)
        progress_area = lines[separators[0] + 1 : separators[1]]
        self.assertIn("处理 PDF 1/2：a.pdf", progress_area)
        self.assertIn("处理 PDF 2/2：b.pdf", progress_area)

    def test_menu_navigation_shortcuts_have_distinct_actions(self) -> None:
        options = [("1", "测试功能")]
        output = StringIO()

        with redirect_stdout(output), patch("builtins.input", return_value="z"):
            with self.assertRaises(ReturnToMainMenu):
                _ask_menu_choice(options)
        with redirect_stdout(output), patch("builtins.input", return_value="u"):
            with self.assertRaises(PreviousStep):
                _ask_menu_choice(options)
        with redirect_stdout(output), patch("builtins.input", return_value="q"):
            with self.assertRaises(ExitProgram):
                _ask_menu_choice(options)

    def test_main_menu_ignores_back_navigation(self) -> None:
        output = StringIO()
        with (
            redirect_stdout(output),
            patch("builtins.input", side_effect=["z", "u", "1"]),
        ):
            selected = _ask_menu_choice(
                [("1", "测试功能")],
                is_main_menu=True,
            )

        self.assertEqual(selected, "1")


if __name__ == "__main__":
    unittest.main()
