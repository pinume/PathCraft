"""Windows 与 Linux 的目录及映射文件选择器。"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from .config import MAPPING_EXTENSIONS
from .exceptions import UserCancelled
from .terminal_menu import TerminalUnavailable, ask
from .utils import path_from_input


def existing_directory(path: Path) -> Path:
    path = path.resolve()
    if not path.exists():
        raise ValueError(f"目录不存在：{path}")
    if not path.is_dir():
        raise ValueError(f"路径不是目录：{path}")
    return path


def choose_windows_directory() -> Path:
    script = """
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = '请选择处理目录'
$dialog.SelectedPath = [Environment]::GetEnvironmentVariable('PATHCRAFT_INITIAL_DIRECTORY')
$dialog.ShowNewFolderButton = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Out.Write($dialog.SelectedPath)
}
"""
    environment = os.environ.copy()
    environment["PATHCRAFT_INITIAL_DIRECTORY"] = str(Path.cwd())
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
    except OSError as error:
        raise TerminalUnavailable from error
    if result.returncode != 0:
        raise TerminalUnavailable(result.stderr.strip())
    selected = result.stdout.strip().lstrip("\ufeff")
    if not selected:
        raise UserCancelled
    return existing_directory(Path(selected))


def choose_linux_directory() -> Path:
    initial_directory = str(Path.cwd().resolve())
    if shutil.which("zenity"):
        command = [
            "zenity",
            "--file-selection",
            "--directory",
            "--title=请选择处理目录",
            f"--filename={initial_directory}/",
        ]
    elif shutil.which("kdialog"):
        command = [
            "kdialog",
            "--getexistingdirectory",
            initial_directory,
            "--title",
            "请选择处理目录",
        ]
    else:
        raise TerminalUnavailable("未找到系统目录选择器")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        raise TerminalUnavailable from error
    if result.returncode == 1:
        raise UserCancelled
    if result.returncode != 0:
        raise TerminalUnavailable(result.stderr.strip())
    selected = result.stdout.strip()
    if not selected:
        raise UserCancelled
    return existing_directory(Path(selected))


def choose_tk_directory() -> Path:
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise TerminalUnavailable from error

    window = None
    try:
        window = tkinter.Tk()
        window.withdraw()
        window.attributes("-topmost", True)
        selected = filedialog.askdirectory(
            parent=window,
            title="请选择处理目录",
            initialdir=Path.cwd(),
            mustexist=True,
        )
    except tkinter.TclError as error:
        raise TerminalUnavailable from error
    finally:
        if window is not None:
            window.destroy()
    if not selected:
        raise UserCancelled
    return existing_directory(Path(selected))


def choose_terminal_directory() -> Path:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise TerminalUnavailable("当前输入输出不是交互终端")
    try:
        import curses
    except ImportError as error:
        raise TerminalUnavailable from error

    def select(screen: object) -> Path:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.keypad(True)
        current = Path.home().resolve()
        selected_index = 0

        while True:
            try:
                directories = sorted(
                    (path for path in current.iterdir() if path.is_dir()),
                    key=lambda path: path.name.casefold(),
                )
            except OSError:
                directories = []
            entries = [
                ("[选择当前目录]", current),
                ("[..]", current.parent),
                *((f"{path.name}/", path) for path in directories),
            ]
            selected_index = min(selected_index, len(entries) - 1)
            height, width = screen.getmaxyx()
            list_height = max(1, height - 4)
            offset = min(
                max(0, selected_index - list_height + 1),
                max(0, len(entries) - list_height),
            )

            screen.erase()
            try:
                screen.addnstr(0, 0, "终端目录选择器", max(1, width - 1), curses.A_BOLD)
                screen.addnstr(1, 0, str(current), max(1, width - 1))
                screen.addnstr(
                    2,
                    0,
                    "↑/↓ 移动  → 进入子目录  ← 返回父目录  Enter 选择  Q/Esc 取消",
                    max(1, width - 1),
                )
                for row, (label, _) in enumerate(
                    entries[offset : offset + list_height],
                    start=3,
                ):
                    index = offset + row - 3
                    style = curses.A_REVERSE if index == selected_index else curses.A_NORMAL
                    screen.addnstr(row, 0, label, max(1, width - 1), style)
            except curses.error:
                pass
            screen.refresh()
            key = screen.getch()

            if key == curses.KEY_UP:
                selected_index = (selected_index - 1) % len(entries)
            elif key == curses.KEY_DOWN:
                selected_index = (selected_index + 1) % len(entries)
            elif key == curses.KEY_LEFT:
                current = current.parent
                selected_index = 0
            elif key == curses.KEY_RIGHT:
                current = entries[selected_index][1].resolve()
                selected_index = 0
            elif key in {curses.KEY_ENTER, 10, 13}:
                return existing_directory(entries[selected_index][1])
            elif key in {ord("q"), ord("Q"), 27}:
                raise UserCancelled

    try:
        return curses.wrapper(select)
    except UserCancelled:
        raise
    except (curses.error, OSError) as error:
        raise TerminalUnavailable from error


def choose_directory() -> Path:
    if os.name != "nt" and not sys.platform.startswith("linux"):
        raise ValueError("PathCraft 仅支持 Windows 和 Linux")
    try:
        if os.name == "nt":
            return choose_windows_directory()
        return choose_linux_directory()
    except TerminalUnavailable:
        if sys.platform.startswith("linux"):
            try:
                return choose_tk_directory()
            except TerminalUnavailable:
                pass
            try:
                return choose_terminal_directory()
            except TerminalUnavailable:
                pass
        print("当前环境无法打开目录选择窗口，请手动输入路径。")
        while True:
            raw_path = ask(
                f"处理目录（直接回车使用 {Path.cwd()}）：",
                allow_empty=True,
            )
            try:
                return existing_directory(path_from_input(raw_path))
            except ValueError as error:
                print(error)


def existing_mapping_file(path: Path) -> Path:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"映射文件不存在：{path}")
    return path


def choose_windows_mapping_file(initial_directory: Path) -> Path:
    script = """
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Title = '请选择名称映射文件'
$dialog.InitialDirectory = [Environment]::GetEnvironmentVariable('PATHCRAFT_MAPPING_DIRECTORY')
$dialog.Filter = '映射文件 (*.xlsx;*.xlsm;*.csv;*.txt)|*.xlsx;*.xlsm;*.csv;*.txt|所有文件 (*.*)|*.*'
$dialog.Multiselect = $false
if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
    [Console]::Out.Write($dialog.FileName)
}
"""
    environment = os.environ.copy()
    environment["PATHCRAFT_MAPPING_DIRECTORY"] = str(initial_directory)
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
    except OSError as error:
        raise TerminalUnavailable from error
    if result.returncode != 0:
        raise TerminalUnavailable(result.stderr.strip())
    selected = result.stdout.strip().lstrip("\ufeff")
    if not selected:
        raise UserCancelled
    return existing_mapping_file(Path(selected))


def choose_linux_mapping_file(initial_directory: Path) -> Path:
    initial_directory = initial_directory.resolve()
    if shutil.which("zenity"):
        command = [
            "zenity",
            "--file-selection",
            "--title=请选择名称映射文件",
            f"--filename={initial_directory}/",
            "--file-filter=映射文件 | *.xlsx *.xlsm *.csv *.txt",
            "--file-filter=所有文件 | *",
        ]
    elif shutil.which("kdialog"):
        command = [
            "kdialog",
            "--getopenfilename",
            str(initial_directory),
            "*.xlsx *.xlsm *.csv *.txt|映射文件",
            "--title",
            "请选择名称映射文件",
        ]
    else:
        raise TerminalUnavailable("未找到系统文件选择器")

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except OSError as error:
        raise TerminalUnavailable from error
    if result.returncode == 1:
        raise UserCancelled
    if result.returncode != 0:
        raise TerminalUnavailable(result.stderr.strip())
    selected = result.stdout.strip()
    if not selected:
        raise UserCancelled
    return existing_mapping_file(Path(selected))


def choose_tk_mapping_file(initial_directory: Path) -> Path:
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise TerminalUnavailable from error

    window = None
    try:
        window = tkinter.Tk()
        window.withdraw()
        window.attributes("-topmost", True)
        selected = filedialog.askopenfilename(
            parent=window,
            title="请选择名称映射文件",
            initialdir=initial_directory,
            filetypes=(
                ("映射文件", "*.xlsx *.xlsm *.csv *.txt"),
                ("所有文件", "*.*"),
            ),
        )
    except tkinter.TclError as error:
        raise TerminalUnavailable from error
    finally:
        if window is not None:
            window.destroy()
    if not selected:
        raise UserCancelled
    return existing_mapping_file(Path(selected))


def choose_terminal_mapping_file(initial_directory: Path) -> Path:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise TerminalUnavailable("当前输入输出不是交互终端")
    try:
        import curses
    except ImportError as error:
        raise TerminalUnavailable from error

    def select(screen: object) -> Path:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.keypad(True)
        current = initial_directory.resolve()
        selected_index = 0

        while True:
            try:
                directories = sorted(
                    (path for path in current.iterdir() if path.is_dir()),
                    key=lambda path: path.name.casefold(),
                )
                files = sorted(
                    (
                        path
                        for path in current.iterdir()
                        if path.is_file()
                        and path.suffix.lower() in MAPPING_EXTENSIONS
                    ),
                    key=lambda path: path.name.casefold(),
                )
            except OSError:
                directories = []
                files = []
            entries = [
                ("[..]", current.parent, True),
                *((f"{path.name}/", path, True) for path in directories),
                *((path.name, path, False) for path in files),
            ]
            selected_index = min(selected_index, len(entries) - 1)
            height, width = screen.getmaxyx()
            list_height = max(1, height - 4)
            offset = min(
                max(0, selected_index - list_height + 1),
                max(0, len(entries) - list_height),
            )

            screen.erase()
            try:
                screen.addnstr(0, 0, "终端映射文件选择器", max(1, width - 1), curses.A_BOLD)
                screen.addnstr(1, 0, str(current), max(1, width - 1))
                screen.addnstr(
                    2,
                    0,
                    "↑/↓ 移动  →/Enter 打开或选择  ← 返回父目录  Q/Esc 取消",
                    max(1, width - 1),
                )
                for row, (label, _, _) in enumerate(
                    entries[offset : offset + list_height],
                    start=3,
                ):
                    index = offset + row - 3
                    style = curses.A_REVERSE if index == selected_index else curses.A_NORMAL
                    screen.addnstr(row, 0, label, max(1, width - 1), style)
            except curses.error:
                pass
            screen.refresh()
            key = screen.getch()

            if key == curses.KEY_UP:
                selected_index = (selected_index - 1) % len(entries)
            elif key == curses.KEY_DOWN:
                selected_index = (selected_index + 1) % len(entries)
            elif key == curses.KEY_LEFT:
                current = current.parent
                selected_index = 0
            elif key in {curses.KEY_RIGHT, curses.KEY_ENTER, 10, 13}:
                _, selected, is_directory = entries[selected_index]
                if is_directory:
                    current = selected.resolve()
                    selected_index = 0
                elif key in {curses.KEY_ENTER, 10, 13}:
                    return existing_mapping_file(selected)
            elif key in {ord("q"), ord("Q"), 27}:
                raise UserCancelled

    try:
        return curses.wrapper(select)
    except UserCancelled:
        raise
    except (curses.error, OSError) as error:
        raise TerminalUnavailable from error


def choose_mapping_file(
    initial_directory: Path,
    manual_path_reader: Callable[[str, list[str]], str] | None = None,
) -> Path:
    if os.name != "nt" and not sys.platform.startswith("linux"):
        raise ValueError("PathCraft 仅支持 Windows 和 Linux")
    print("请选择 Excel、CSV 或 TXT 名称映射文件。")
    try:
        if os.name == "nt":
            return choose_windows_mapping_file(initial_directory)
        return choose_linux_mapping_file(initial_directory)
    except TerminalUnavailable:
        if sys.platform.startswith("linux"):
            try:
                return choose_tk_mapping_file(initial_directory)
            except TerminalUnavailable:
                pass
            try:
                return choose_terminal_mapping_file(initial_directory)
            except TerminalUnavailable:
                pass
        error_lines: list[str] = []
        while True:
            prompt = "请输入映射文件路径："
            raw_path = (
                manual_path_reader(prompt, error_lines)
                if manual_path_reader is not None
                else ask(prompt)
            )
            try:
                candidate = path_from_input(raw_path)
                if not candidate.is_absolute():
                    candidate = initial_directory / candidate
                return existing_mapping_file(candidate)
            except ValueError as error:
                if manual_path_reader is None:
                    print(error)
                else:
                    error_lines = [str(error)]
