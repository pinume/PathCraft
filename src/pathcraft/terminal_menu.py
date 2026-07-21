"""Windows 与 Linux 共用的终端菜单交互。"""

from __future__ import annotations

import os
import shutil
import sys

from .exceptions import ExitProgram, UserCancelled
from .terminal_layout import (
    MenuOption,
    menu_frame,
    menu_option_parts,
    workspace_choice_frame,
)
from .utils import raise_if_cancelled


class TerminalUnavailable(Exception):
    """当前环境无法提供所需的交互终端。"""


def enable_windows_virtual_terminal() -> None:
    """尽力启用 Windows 控制台的 ANSI 转义序列支持。"""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        output_handle = kernel32.GetStdHandle(-11)
        console_mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(output_handle, ctypes.byref(console_mode)):
            kernel32.SetConsoleMode(output_handle, console_mode.value | 0x0004)
    except (AttributeError, OSError):
        pass


def ask(prompt: str, allow_empty: bool = False) -> str:
    while True:
        value = input(prompt).strip()
        raise_if_cancelled(value)
        if value or allow_empty:
            return value
        print("输入不能为空。")


def ask_choice(prompt: str, choices: set[str]) -> str:
    while True:
        value = ask(prompt)
        if value in choices:
            return value
        print(f"请输入 {' 或 '.join(sorted(choices))}。")


def choose_windows_menu(
    options: list[MenuOption],
    content_lines: list[str] | None = None,
    parent_options: list[MenuOption] | None = None,
    parent_selected: int = 0,
    completed_lines: list[str] | None = None,
) -> str:
    try:
        import msvcrt
    except ImportError as error:
        raise TerminalUnavailable from error

    enable_windows_virtual_terminal()

    selected = 0
    terminal_size = shutil.get_terminal_size(fallback=(80, 24))
    menu_width = max(1, terminal_size.columns - 1)
    menu_height = max(2, terminal_size.lines)

    def draw() -> None:
        if parent_options is None:
            lines, selected_row = menu_frame(
                options,
                selected,
                menu_width,
                height=menu_height,
                content_lines=content_lines,
            )
        else:
            lines, selected_row = workspace_choice_frame(
                parent_options,
                parent_selected,
                options,
                selected,
                menu_width,
                menu_height,
                completed_lines,
            )
        sys.stdout.write("\033[?25l\033[2J\033[H")
        for index, line in enumerate(lines):
            if index == selected_row:
                line = f"\033[1;36m{line}\033[0m"
            ending = "\n" if index < len(lines) - 1 else ""
            sys.stdout.write(f"\033[2K{line}{ending}")
        sys.stdout.flush()

    def finish() -> None:
        sys.stdout.write("\033[?25h\033[2J\033[H")
        sys.stdout.flush()

    draw()
    try:
        while True:
            key = msvcrt.getwch()
            if key in {"\x00", "\xe0"}:
                arrow = msvcrt.getwch()
                if arrow == "H":
                    selected = (selected - 1) % len(options)
                    draw()
                elif arrow == "P":
                    selected = (selected + 1) % len(options)
                    draw()
            elif key == "\r":
                return options[selected][0]
            elif key in {"q", "Q", "\x1b"}:
                raise ExitProgram
    finally:
        finish()


def choose_curses_menu(
    options: list[MenuOption],
    content_lines: list[str] | None = None,
    parent_options: list[MenuOption] | None = None,
    parent_selected: int = 0,
    completed_lines: list[str] | None = None,
) -> str:
    try:
        import curses
    except ImportError as error:
        raise TerminalUnavailable from error

    def select(screen: object) -> str:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.keypad(True)
        selected = 0
        while True:
            height, width = screen.getmaxyx()
            menu_width = max(1, width - 1)
            if parent_options is None:
                lines, selected_row = menu_frame(
                    options,
                    selected,
                    menu_width,
                    height=height,
                    content_lines=content_lines,
                )
            else:
                lines, selected_row = workspace_choice_frame(
                    parent_options,
                    parent_selected,
                    options,
                    selected,
                    menu_width,
                    height,
                    completed_lines,
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
                    screen.addnstr(row, 0, line, max(1, width - 1), style)
            except curses.error:
                pass
            screen.refresh()
            key = screen.getch()
            if key == curses.KEY_UP:
                selected = (selected - 1) % len(options)
            elif key == curses.KEY_DOWN:
                selected = (selected + 1) % len(options)
            elif key in {curses.KEY_ENTER, 10, 13}:
                return options[selected][0]
            elif key in {ord("q"), ord("Q"), 27}:
                raise ExitProgram

    try:
        selected = curses.wrapper(select)
    except (ExitProgram, UserCancelled):
        raise
    except (curses.error, OSError) as error:
        raise TerminalUnavailable from error
    sys.stdout.write("\033[2J\033[H")
    sys.stdout.flush()
    return selected


def ask_workspace_choice(
    options: list[MenuOption],
    parent_options: list[MenuOption],
    parent_selected: int,
    completed_lines: list[str] | None = None,
) -> str:
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            if os.name == "nt":
                return choose_windows_menu(
                    options,
                    parent_options=parent_options,
                    parent_selected=parent_selected,
                    completed_lines=completed_lines,
                )
            return choose_curses_menu(
                options,
                parent_options=parent_options,
                parent_selected=parent_selected,
                completed_lines=completed_lines,
            )
        except TerminalUnavailable:
            pass
    return ask_menu_choice(options, content_lines=completed_lines)


def ask_menu_choice(
    options: list[MenuOption],
    *,
    content_lines: list[str] | None = None,
) -> str:
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            selected = (
                choose_windows_menu(options, content_lines)
                if os.name == "nt"
                else choose_curses_menu(options, content_lines)
            )
            return selected
        except TerminalUnavailable:
            pass

    menu_width = max(24, min(72, shutil.get_terminal_size(fallback=(72, 24)).columns))
    lines, _ = menu_frame(
        options,
        None,
        menu_width,
        content_lines=content_lines,
    )
    print("\n".join(lines))
    choices = {menu_option_parts(option)[0] for option in options}
    values = [menu_option_parts(option)[0] for option in options]
    while True:
        try:
            value = ask(f"请选择模式（{'/'.join(values)}）：")
        except UserCancelled as error:
            raise ExitProgram from error
        if value in choices:
            return value
        print(f"请输入 {' 或 '.join(sorted(choices))}。")
