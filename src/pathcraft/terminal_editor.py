"""Windows 与 Linux 共享状态模型的工作区文字编辑器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
import os
import shutil
import sys

from .exceptions import ExitProgram, UserCancelled
from .terminal_layout import (
    MenuOption,
    menu_frame,
    move_vertical_cursor,
    wrapped_input_layout,
)
from .terminal_menu import TerminalUnavailable, ask, enable_windows_virtual_terminal
from .utils import raise_if_cancelled, validate_filename_text


class EditorCommand(Enum):
    INSERT = auto()
    LEFT = auto()
    RIGHT = auto()
    UP = auto()
    DOWN = auto()
    HOME = auto()
    END = auto()
    BACKSPACE = auto()
    DELETE = auto()
    CONFIRM = auto()
    EXIT = auto()
    INTERRUPT = auto()
    IGNORE = auto()


@dataclass(frozen=True)
class EditorEvent:
    command: EditorCommand
    text: str = ""


@dataclass
class EditorState:
    characters: list[str] = field(default_factory=list)
    cursor: int = 0
    preferred_column: int | None = None
    error_message: str = ""

    @property
    def value(self) -> str:
        return "".join(self.characters)

    def apply(
        self,
        event: EditorEvent,
        positions: list[tuple[int, int]],
    ) -> None:
        command = event.command
        if command is EditorCommand.INSERT:
            self.characters.insert(self.cursor, event.text)
            self.cursor += 1
            self.preferred_column = None
            self.error_message = ""
        elif command is EditorCommand.LEFT:
            self.cursor = max(0, self.cursor - 1)
            self.preferred_column = None
        elif command is EditorCommand.RIGHT:
            self.cursor = min(len(self.characters), self.cursor + 1)
            self.preferred_column = None
        elif command is EditorCommand.UP:
            self.cursor, self.preferred_column = move_vertical_cursor(
                positions,
                self.cursor,
                -1,
                self.preferred_column,
            )
        elif command is EditorCommand.DOWN:
            self.cursor, self.preferred_column = move_vertical_cursor(
                positions,
                self.cursor,
                1,
                self.preferred_column,
            )
        elif command is EditorCommand.HOME:
            self.cursor = 0
            self.preferred_column = None
        elif command is EditorCommand.END:
            self.cursor = len(self.characters)
            self.preferred_column = None
        elif command is EditorCommand.BACKSPACE:
            if self.cursor:
                del self.characters[self.cursor - 1]
                self.cursor -= 1
            self.preferred_column = None
        elif command is EditorCommand.DELETE:
            if self.cursor < len(self.characters):
                del self.characters[self.cursor]
            self.preferred_column = None


def validate_editor_value(
    state: EditorState,
    validate_filename: bool,
) -> str | None:
    value = state.value.strip()
    raise_if_cancelled(value)
    if not value:
        state.error_message = "输入不能为空。"
        return None
    if validate_filename:
        invalid = validate_filename_text(value)
        if invalid:
            printable = [
                "NUL" if character == "\0" else character
                for character in invalid
            ]
            state.error_message = (
                "内容包含当前系统不允许的文件名字符："
                f"{' '.join(printable)}"
            )
            return None
    return value


def editor_frame(
    state: EditorState,
    prompt: str,
    options: list[MenuOption],
    selected: int,
    completed_lines: list[str] | None,
    width: int,
    height: int,
) -> tuple[list[str], int, int, int, list[tuple[int, int]]]:
    input_lines, positions = wrapped_input_layout(state.value, width)
    content_lines = list(completed_lines or [])
    if state.error_message:
        content_lines.append(state.error_message)
    content_lines.append(prompt)
    input_start = len(content_lines)
    content_lines.extend(input_lines)
    cursor_content_row = input_start + positions[state.cursor][0]

    empty_frame, _ = menu_frame(
        options,
        selected,
        width,
        height=height,
        content_lines=[],
    )
    separator = "─" * width
    try:
        first_separator = empty_frame.index(separator)
        second_separator = empty_frame.index(separator, first_separator + 1)
    except ValueError as error:
        raise TerminalUnavailable("终端尺寸不足") from error
    content_height = second_separator - first_separator - 1
    if content_height < 1:
        raise TerminalUnavailable("终端高度不足")

    start = max(0, len(content_lines) - content_height)
    if cursor_content_row < start:
        start = cursor_content_row
    elif cursor_content_row >= start + content_height:
        start = cursor_content_row - content_height + 1
    visible_content = content_lines[start : start + content_height]
    lines, selected_row = menu_frame(
        options,
        selected,
        width,
        height=height,
        content_lines=visible_content,
        hint="方向键移动光标 | Enter 确认 | Backspace/Delete 删除 | Ctrl+C 退出",
    )
    first_separator = lines.index(separator)
    cursor_row = first_separator + 1 + cursor_content_row - start
    cursor_column = positions[state.cursor][1]
    return lines, selected_row, cursor_row, cursor_column, positions


def curses_event(key: str | int, curses_module: object) -> EditorEvent:
    if key in {"\n", "\r"} or key == curses_module.KEY_ENTER:
        return EditorEvent(EditorCommand.CONFIRM)
    mappings = {
        curses_module.KEY_LEFT: EditorCommand.LEFT,
        curses_module.KEY_RIGHT: EditorCommand.RIGHT,
        curses_module.KEY_UP: EditorCommand.UP,
        curses_module.KEY_DOWN: EditorCommand.DOWN,
        curses_module.KEY_HOME: EditorCommand.HOME,
        curses_module.KEY_END: EditorCommand.END,
        curses_module.KEY_BACKSPACE: EditorCommand.BACKSPACE,
        curses_module.KEY_DC: EditorCommand.DELETE,
    }
    try:
        command = mappings.get(key)
    except TypeError:
        command = None
    if command is not None:
        return EditorEvent(command)
    if key in {"\b", "\x7f"}:
        return EditorEvent(EditorCommand.BACKSPACE)
    if key == "\x03":
        return EditorEvent(EditorCommand.INTERRUPT)
    if key == "\x1b":
        return EditorEvent(EditorCommand.EXIT)
    if isinstance(key, str) and key.isprintable():
        return EditorEvent(EditorCommand.INSERT, key)
    return EditorEvent(EditorCommand.IGNORE)


def read_windows_event(msvcrt_module: object) -> EditorEvent:
    key = msvcrt_module.getwch()
    if key in {"\x00", "\xe0"}:
        extended = msvcrt_module.getwch()
        command = {
            "K": EditorCommand.LEFT,
            "M": EditorCommand.RIGHT,
            "H": EditorCommand.UP,
            "P": EditorCommand.DOWN,
            "G": EditorCommand.HOME,
            "O": EditorCommand.END,
            "S": EditorCommand.DELETE,
        }.get(extended, EditorCommand.IGNORE)
        return EditorEvent(command)
    if key == "\r":
        return EditorEvent(EditorCommand.CONFIRM)
    if key == "\b":
        return EditorEvent(EditorCommand.BACKSPACE)
    if key == "\x03":
        return EditorEvent(EditorCommand.INTERRUPT)
    if key == "\x1b":
        return EditorEvent(EditorCommand.EXIT)
    if key.isprintable():
        return EditorEvent(EditorCommand.INSERT, key)
    return EditorEvent(EditorCommand.IGNORE)


def handle_terminal_event(
    state: EditorState,
    event: EditorEvent,
    positions: list[tuple[int, int]],
    validate_filename: bool,
) -> str | None:
    if event.command is EditorCommand.CONFIRM:
        return validate_editor_value(state, validate_filename)
    if event.command is EditorCommand.EXIT:
        raise ExitProgram
    if event.command is EditorCommand.INTERRUPT:
        raise KeyboardInterrupt
    state.apply(event, positions)
    return None


def ask_curses_workspace_text(
    prompt: str,
    options: list[MenuOption],
    selected: int,
    validate_filename: bool,
    completed_lines: list[str] | None,
) -> str:
    try:
        import curses
    except ImportError as error:
        raise TerminalUnavailable from error

    def edit(screen: object) -> str:
        screen.keypad(True)
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        state = EditorState()

        while True:
            height, screen_width = screen.getmaxyx()
            width = max(1, screen_width - 1)
            lines, selected_row, cursor_row, cursor_column, positions = editor_frame(
                state,
                prompt,
                options,
                selected,
                completed_lines,
                width,
                height,
            )
            screen.erase()
            try:
                for row, line in enumerate(lines):
                    if row >= height:
                        break
                    style = (
                        curses.A_REVERSE | curses.A_BOLD
                        if row == selected_row
                        else curses.A_NORMAL
                    )
                    screen.addnstr(row, 0, line, max(1, screen_width - 1), style)
                screen.move(cursor_row, min(cursor_column, max(0, screen_width - 2)))
            except curses.error:
                pass
            screen.refresh()
            value = handle_terminal_event(
                state,
                curses_event(screen.get_wch(), curses),
                positions,
                validate_filename,
            )
            if value is not None:
                return value

    try:
        return curses.wrapper(edit)
    except (ExitProgram, UserCancelled, KeyboardInterrupt):
        raise
    except (curses.error, OSError) as error:
        raise TerminalUnavailable from error


def ask_windows_workspace_text(
    prompt: str,
    options: list[MenuOption],
    selected: int,
    validate_filename: bool,
    completed_lines: list[str] | None,
) -> str:
    try:
        import msvcrt
    except ImportError as error:
        raise TerminalUnavailable from error

    enable_windows_virtual_terminal()
    state = EditorState()
    try:
        while True:
            terminal_size = shutil.get_terminal_size(fallback=(80, 24))
            width = max(1, terminal_size.columns - 1)
            height = max(2, terminal_size.lines)
            lines, selected_row, cursor_row, cursor_column, positions = editor_frame(
                state,
                prompt,
                options,
                selected,
                completed_lines,
                width,
                height,
            )
            sys.stdout.write("\033[?25l\033[2J\033[H")
            for index, line in enumerate(lines):
                if index == selected_row:
                    line = f"\033[1;36m{line}\033[0m"
                ending = "\n" if index < len(lines) - 1 else ""
                sys.stdout.write(f"\033[2K{line}{ending}")
            sys.stdout.write(
                f"\033[{cursor_row + 1};{cursor_column + 1}H\033[?25h"
            )
            sys.stdout.flush()
            value = handle_terminal_event(
                state,
                read_windows_event(msvcrt),
                positions,
                validate_filename,
            )
            if value is not None:
                return value
    finally:
        sys.stdout.write("\033[?25h")
        sys.stdout.flush()


def ask_valid_text(prompt: str, allow_empty: bool = False) -> str:
    while True:
        value = ask(prompt, allow_empty=allow_empty)
        invalid = validate_filename_text(value)
        if not invalid:
            return value
        printable = ["NUL" if character == "\0" else character for character in invalid]
        print(f"内容包含当前系统不允许的文件名字符：{' '.join(printable)}")


def ask_workspace_text(
    prompt: str,
    options: list[MenuOption],
    selected: int,
    *,
    validate_filename: bool = False,
    completed_lines: list[str] | None = None,
) -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if validate_filename:
            return ask_valid_text(prompt)
        return ask(prompt)
    try:
        if os.name == "nt":
            return ask_windows_workspace_text(
                prompt,
                options,
                selected,
                validate_filename,
                completed_lines,
            )
        return ask_curses_workspace_text(
            prompt,
            options,
            selected,
            validate_filename,
            completed_lines,
        )
    except TerminalUnavailable:
        if validate_filename:
            return ask_valid_text(prompt)
        return ask(prompt)
