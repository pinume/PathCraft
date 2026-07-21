import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
from types import ModuleType
from unittest.mock import patch

from pathcraft.dialogs import (
    choose_directory,
    choose_linux_mapping_file,
    choose_mapping_file,
    choose_terminal_mapping_file,
)
from pathcraft.exceptions import ExitProgram
from pathcraft.terminal_editor import (
    EditorCommand,
    EditorState,
    ask_curses_workspace_text,
    curses_event,
    editor_frame,
    read_windows_event,
)
from pathcraft.terminal_layout import (
    MENU_LOGO,
    menu_frame,
    move_vertical_cursor,
    terminal_text_width,
    wrapped_input_layout,
    workspace_choice_frame,
)
from pathcraft.terminal_menu import (
    TerminalUnavailable,
    ask_menu_choice,
    choose_curses_menu,
)


class FakeCurses(ModuleType):
    KEY_ENTER = 343
    KEY_LEFT = 260
    KEY_RIGHT = 261
    KEY_UP = 259
    KEY_DOWN = 258
    KEY_HOME = 262
    KEY_END = 360
    KEY_BACKSPACE = 263
    KEY_DC = 330
    A_REVERSE = 1
    A_BOLD = 2
    A_NORMAL = 0
    error = OSError

    def __init__(self) -> None:
        super().__init__("curses")
        self.wrapper = lambda function: function(None)

    @staticmethod
    def curs_set(_visibility: int) -> None:
        pass


class PromptMenuTests(unittest.TestCase):
    def test_linux_mapping_file_uses_system_file_picker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "mapping.csv"
            selected.touch()
            result = type(
                "Result",
                (),
                {"returncode": 0, "stdout": str(selected), "stderr": ""},
            )()

            with (
                patch(
                    "pathcraft.dialogs.shutil.which",
                    side_effect=lambda name: (
                        "/usr/bin/zenity" if name == "zenity" else None
                    ),
                ),
                patch("pathcraft.dialogs.subprocess.run", return_value=result) as run,
            ):
                chosen = choose_linux_mapping_file(root)

            self.assertEqual(chosen, selected.resolve())
            command = run.call_args.args[0]
            self.assertEqual(command[0], "zenity")
            self.assertIn("--file-filter=映射文件 | *.xlsx *.xlsm *.csv *.txt", command)

    def test_mapping_file_falls_back_to_terminal_picker_before_text_input(self) -> None:
        selected = Path.cwd() / "mapping.csv"

        with (
            patch("pathcraft.dialogs.os.name", "posix"),
            patch("pathcraft.dialogs.sys.platform", "linux"),
            patch(
                "pathcraft.dialogs.choose_linux_mapping_file",
                side_effect=TerminalUnavailable,
            ),
            patch(
                "pathcraft.dialogs.choose_tk_mapping_file",
                side_effect=TerminalUnavailable,
            ),
            patch(
                "pathcraft.dialogs.choose_terminal_mapping_file",
                return_value=selected,
            ) as terminal_picker,
            patch("pathcraft.dialogs.ask") as ask,
        ):
            chosen = choose_mapping_file(Path.cwd())

        self.assertEqual(chosen, selected)
        terminal_picker.assert_called_once_with(Path.cwd())
        ask.assert_not_called()

    def test_manual_mapping_path_reader_receives_errors_for_workspace_display(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "mapping.csv"
            selected.touch()
            answers = iter(["missing.csv", "mapping.csv"])
            calls: list[tuple[str, list[str]]] = []

            def read_path(prompt: str, messages: list[str]) -> str:
                calls.append((prompt, list(messages)))
                return next(answers)

            with (
                patch("pathcraft.dialogs.os.name", "posix"),
                patch("pathcraft.dialogs.sys.platform", "linux"),
                patch(
                    "pathcraft.dialogs.choose_linux_mapping_file",
                    side_effect=TerminalUnavailable,
                ),
                patch(
                    "pathcraft.dialogs.choose_tk_mapping_file",
                    side_effect=TerminalUnavailable,
                ),
                patch(
                    "pathcraft.dialogs.choose_terminal_mapping_file",
                    side_effect=TerminalUnavailable,
                ),
            ):
                chosen = choose_mapping_file(root, manual_path_reader=read_path)

            self.assertEqual(chosen, selected.resolve())
            self.assertEqual(calls[0], ("请输入映射文件路径：", []))
            self.assertEqual(calls[1][0], "请输入映射文件路径：")
            self.assertIn("映射文件不存在", calls[1][1][0])

    def test_terminal_mapping_picker_selects_supported_file(self) -> None:
        class TerminalStream(StringIO):
            def isatty(self) -> bool:
                return True

        class Screen:
            def __init__(self, curses: FakeCurses) -> None:
                self.keys = iter([curses.KEY_DOWN, curses.KEY_ENTER])

            def keypad(self, _enabled: bool) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 24, 80

            def erase(self) -> None:
                pass

            def addnstr(self, *_args: object) -> None:
                pass

            def refresh(self) -> None:
                pass

            def getch(self) -> int:
                return next(self.keys)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "mapping.csv"
            selected.touch()
            (root / "ignored.pdf").touch()
            curses = FakeCurses()
            screen = Screen(curses)
            curses.wrapper = lambda selector: selector(screen)

            with (
                patch.dict(sys.modules, {"curses": curses}),
                patch("pathcraft.dialogs.sys.stdin", TerminalStream()),
                patch("pathcraft.dialogs.sys.stdout", TerminalStream()),
            ):
                chosen = choose_terminal_mapping_file(root)

            self.assertEqual(chosen, selected.resolve())

    def test_windows_and_curses_keys_use_the_same_editor_commands(self) -> None:
        curses = FakeCurses()

        class WindowsKeys:
            def __init__(self, *keys: str) -> None:
                self.keys = iter(keys)

            def getwch(self) -> str:
                return next(self.keys)

        key_pairs = [
            (curses.KEY_LEFT, ("\xe0", "K"), EditorCommand.LEFT),
            (curses.KEY_RIGHT, ("\xe0", "M"), EditorCommand.RIGHT),
            (curses.KEY_UP, ("\xe0", "H"), EditorCommand.UP),
            (curses.KEY_DOWN, ("\xe0", "P"), EditorCommand.DOWN),
            (curses.KEY_HOME, ("\xe0", "G"), EditorCommand.HOME),
            (curses.KEY_END, ("\xe0", "O"), EditorCommand.END),
            (curses.KEY_DC, ("\xe0", "S"), EditorCommand.DELETE),
        ]

        for curses_key, windows_keys, expected in key_pairs:
            with self.subTest(command=expected):
                self.assertIs(curses_event(curses_key, curses).command, expected)
                self.assertIs(
                    read_windows_event(WindowsKeys(*windows_keys)).command,
                    expected,
                )

        self.assertIs(curses_event("\n", curses).command, EditorCommand.CONFIRM)
        self.assertIs(
            read_windows_event(WindowsKeys("\r")).command,
            EditorCommand.CONFIRM,
        )

    def test_curses_workspace_editor_handles_all_arrow_keys(self) -> None:
        curses = FakeCurses()

        class Screen:
            def __init__(self) -> None:
                self.keys = iter(
                    [
                        *"abcdefghijklmnopqrst",
                        curses.KEY_UP,
                        "X",
                        curses.KEY_LEFT,
                        curses.KEY_RIGHT,
                        curses.KEY_DOWN,
                        "\n",
                    ]
                )

            def keypad(self, _enabled: bool) -> None:
                pass

            def getmaxyx(self) -> tuple[int, int]:
                return 24, 18

            def erase(self) -> None:
                pass

            def addnstr(self, *_args: object) -> None:
                pass

            def move(self, *_args: object) -> None:
                pass

            def refresh(self) -> None:
                pass

            def get_wch(self) -> str | int:
                return next(self.keys)

        screen = Screen()
        curses.wrapper = lambda editor: editor(screen)
        with patch.dict(sys.modules, {"curses": curses}):
            value = ask_curses_workspace_text(
                "请输入内容：",
                [("1", "添加前缀", "测试")],
                selected=0,
                validate_filename=False,
                completed_lines=None,
            )

        self.assertEqual(value, "abcdefXghijklmnopqrst")

    def test_wrapped_input_supports_vertical_cursor_movement(self) -> None:
        lines, positions = wrapped_input_layout("abcdefghij", width=8)

        self.assertEqual(lines, ["➤ abcde", "  fghij"])
        cursor, preferred_column = move_vertical_cursor(
            positions,
            cursor=8,
            direction=-1,
            preferred_column=None,
        )
        self.assertEqual(cursor, 3)
        cursor, _ = move_vertical_cursor(
            positions,
            cursor=cursor,
            direction=1,
            preferred_column=preferred_column,
        )
        self.assertEqual(cursor, 8)

    def test_nested_choice_is_rendered_in_menu_workspace(self) -> None:
        separator = "─" * 79
        lines, selected_row = workspace_choice_frame(
            [
                ("1", "PDF 转 PNG", "识别购买方并生成 PNG"),
                ("2", "添加前缀或后缀", "批量添加固定文字"),
            ],
            parent_selected=1,
            options=[
                ("1", "添加到文件名称前面"),
                ("2", "添加到文件名称后面"),
            ],
            selected=1,
            width=79,
            height=24,
        )

        first_separator = lines.index(separator)
        second_separator = lines.index(separator, first_separator + 1)
        self.assertTrue(lines[selected_row].startswith("➤ 2. 添加到文件名称后面"))
        self.assertLess(first_separator, selected_row)
        self.assertLess(selected_row, second_separator)

    def test_workspace_choice_keeps_context_above_current_options(self) -> None:
        lines, selected_row = workspace_choice_frame(
            [
                ("1", "PDF 转 PNG", "识别购买方并生成 PNG"),
                ("5", "映射表批量重命名", "使用 Excel、CSV 或 TXT"),
            ],
            parent_selected=1,
            options=[("1", "旧名称"), ("2", "新名称"), ("3", "备注")],
            selected=1,
            width=79,
            height=24,
            completed_lines=[
                "映射文件：mapping.csv",
                "检测到列标题：旧名称、新名称、备注",
                "请选择原名称所在列：",
            ],
        )

        self.assertIn("映射文件：mapping.csv", lines)
        self.assertIn("请选择原名称所在列：", lines)
        self.assertEqual(lines[selected_row], "➤ 2. 新名称")

    def test_workspace_choice_scroll_keeps_current_option_visible(self) -> None:
        options = [(str(index), f"第 {index} 列") for index in range(1, 11)]

        lines, selected_row = workspace_choice_frame(
            [("5", "映射表批量重命名", "使用 Excel、CSV 或 TXT")],
            parent_selected=0,
            options=options,
            selected=0,
            width=79,
            height=14,
            completed_lines=["很早以前的提示", "请选择原名称所在列："],
        )

        self.assertGreaterEqual(selected_row, 0)
        self.assertEqual(lines[selected_row], "➤ 1. 第 1 列")
        self.assertIn("请选择原名称所在列：", lines)
        self.assertNotIn("很早以前的提示", lines)

    def test_text_input_is_rendered_in_menu_workspace(self) -> None:
        separator = "─" * 79
        state = EditorState(list("合同"), cursor=2)
        lines, _, _, _, _ = editor_frame(
            state,
            "请输入要删除的文字或字符：",
            [
                ("1", "添加前缀或后缀", "批量添加固定文字"),
                ("2", "删除指定内容", "批量清理文件名文字"),
            ],
            selected=1,
            completed_lines=[
                "  1. 添加到文件名称前面",
                "➤ 2. 添加到文件名称后面",
            ],
            width=79,
            height=24,
        )

        first_separator = lines.index(separator)
        second_separator = lines.index(separator, first_separator + 1)
        prompt_position = lines.index("请输入要删除的文字或字符：")
        self.assertLess(first_separator, prompt_position)
        self.assertLess(prompt_position, second_separator)
        self.assertLess(
            lines.index("➤ 2. 添加到文件名称后面"),
            prompt_position,
        )
        self.assertIn("方向键移动光标 | Enter 确认", lines[-1])

    def test_workspace_scrolls_oldest_completed_lines_out(self) -> None:
        lines, _ = menu_frame(
            [
                ("1", "PDF 转 PNG", "识别购买方并生成 PNG"),
                ("2", "添加前缀或后缀", "批量添加固定文字"),
                ("3", "删除指定内容", "批量清理文件名文字"),
                ("4", "替换指定内容", "批量替换文件名文字"),
                ("5", "映射表批量重命名", "使用 Excel、CSV 或 TXT"),
            ],
            selected=1,
            width=79,
            height=16,
            content_lines=["已完成步骤 1", "已完成步骤 2", "当前步骤"],
        )

        self.assertNotIn("已完成步骤 1", lines)
        self.assertIn("已完成步骤 2", lines)
        self.assertIn("当前步骤", lines)

    def test_curses_menu_clears_restored_screen_before_text_input(self) -> None:
        output = StringIO()
        curses = FakeCurses()
        curses.wrapper = lambda _selector: "1"

        with redirect_stdout(output), patch.dict(sys.modules, {"curses": curses}):
            selected = choose_curses_menu([("1", "测试功能")])

        self.assertEqual(selected, "1")
        self.assertEqual(output.getvalue(), "\033[2J\033[H")

    def test_directory_picker_uses_each_platform_system_dialog(self) -> None:
        selected = Path.cwd()

        with (
            patch("pathcraft.dialogs.os.name", "nt"),
            patch("pathcraft.dialogs.choose_windows_directory", return_value=selected) as chooser,
        ):
            self.assertEqual(choose_directory(), selected)
            chooser.assert_called_once_with()

        with (
            patch("pathcraft.dialogs.os.name", "posix"),
            patch("pathcraft.dialogs.sys.platform", "linux"),
            patch("pathcraft.dialogs.choose_linux_directory", return_value=selected) as chooser,
        ):
            self.assertEqual(choose_directory(), selected)
            chooser.assert_called_once_with()

        with (
            patch("pathcraft.dialogs.os.name", "posix"),
            patch("pathcraft.dialogs.sys.platform", "darwin"),
        ):
            with self.assertRaisesRegex(ValueError, "仅支持 Windows 和 Linux"):
                choose_directory()

    def test_menu_uses_logo_pointer_and_shortcuts_without_box(self) -> None:
        options = [
            ("1", "PDF 转 PNG", "识别购买方并生成 PNG"),
            ("2", "批量重命名", "处理文件名称"),
        ]

        lines, selected_row = menu_frame(options, selected=0, width=72)

        rendered = "\n".join(lines)
        self.assertIn(MENU_LOGO[0].strip(), rendered)
        self.assertEqual(lines[len(MENU_LOGO)], "")
        self.assertTrue(lines[selected_row].startswith("➤ 1. PDF 转 PNG"))
        self.assertIn("识别购买方并生成 PNG", lines[selected_row])
        self.assertIn("↑↓ | Enter 确认", rendered)
        self.assertNotIn("Z 返回主菜单", rendered)
        self.assertNotIn("U 上一步", rendered)
        self.assertIn("Q/Esc 退出程序", rendered)
        self.assertNotIn("╭", rendered)

        compact_lines, _ = menu_frame(
            [("1", "返回主菜单"), ("2", "退出程序")],
            selected=0,
            width=72,
        )
        self.assertNotIn(MENU_LOGO[0].strip(), "\n".join(compact_lines))

    def test_menu_shortcuts_are_anchored_to_terminal_bottom(self) -> None:
        lines, _ = menu_frame(
            [("1", "PDF 转 PNG", "识别购买方并生成 PNG")],
            selected=0,
            width=100,
            height=24,
        )

        self.assertEqual(len(lines), 24)
        self.assertIn("Q/Esc 退出程序", lines[-1])

    def test_menu_has_separators_around_progress_area(self) -> None:
        lines, _ = menu_frame(
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

    def test_removed_navigation_shortcuts_are_invalid_choices(self) -> None:
        options = [("1", "测试功能")]
        output = StringIO()

        with (
            redirect_stdout(output),
            patch("builtins.input", side_effect=["z", "u", "1"]),
        ):
            selected = ask_menu_choice(options)

        self.assertEqual(selected, "1")
        self.assertEqual(output.getvalue().count("请输入 1。"), 2)

    def test_q_still_exits_menu(self) -> None:
        options = [("1", "测试功能")]
        output = StringIO()

        with redirect_stdout(output), patch("builtins.input", return_value="q"):
            with self.assertRaises(ExitProgram):
                ask_menu_choice(options)

    def test_unicode_width_handles_combining_emoji_and_zero_width(self) -> None:
        self.assertEqual(terminal_text_width("e\u0301"), 1)
        self.assertEqual(terminal_text_width("🙂"), 2)
        self.assertEqual(terminal_text_width("\u200d"), 0)


if __name__ == "__main__":
    unittest.main()
