import os
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from .exceptions import ExitProgram, PreviousStep, ReturnToMainMenu, UserCancelled
from .utils import (
    path_from_input,
    raise_if_cancelled,
    validate_filename_text,
)


class _DirectorySelectionUnavailable(Exception):
    pass


MENU_LOGO = (
    r" ____       _   _      ____            __ _",
    r"|  _ \ __ _| |_| |__  / ___|_ __ __ _ / _| |_",
    r"| |_) / _` | __| '_ \| |   | '__/ _` | |_| __|",
    r"|  __/ (_| | |_| | | | |___| | | (_| |  _| |_",
    r"|_|   \__,_|\__|_| |_|\____|_|  \__,_|_|  \__|",
)
MENU_TAGLINE = "安全、跨平台的文件处理工具"
MenuOption = tuple[str, str] | tuple[str, str, str]


def _menu_option_parts(option: MenuOption) -> tuple[str, str, str]:
    if len(option) == 2:
        value, label = option
        return value, label, ""
    return option


def _existing_directory(path: Path) -> Path:
    path = path.resolve()
    if not path.exists():
        raise ValueError(f"目录不存在：{path}")
    if not path.is_dir():
        raise ValueError(f"路径不是目录：{path}")
    return path


def _choose_windows_directory() -> Path:
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
        raise _DirectorySelectionUnavailable from error
    if result.returncode != 0:
        raise _DirectorySelectionUnavailable(result.stderr.strip())
    selected = result.stdout.strip().lstrip("\ufeff")
    if not selected:
        raise UserCancelled
    return _existing_directory(Path(selected))


def _choose_macos_directory() -> Path:
    script = """
try
    set initialDirectory to system attribute "PATHCRAFT_INITIAL_DIRECTORY"
    set selectedFolder to choose folder with prompt "请选择处理目录" default location (POSIX file initialDirectory)
    return POSIX path of selectedFolder
on error number -128
    return ""
end try
"""
    environment = os.environ.copy()
    environment["PATHCRAFT_INITIAL_DIRECTORY"] = str(Path.home())
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
    except OSError as error:
        raise _DirectorySelectionUnavailable from error
    if result.returncode != 0:
        raise _DirectorySelectionUnavailable(result.stderr.strip())
    selected = result.stdout.strip()
    if not selected:
        raise UserCancelled
    return _existing_directory(Path(selected))


def _choose_linux_directory() -> Path:
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
        raise _DirectorySelectionUnavailable("未找到系统目录选择器")

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
        raise _DirectorySelectionUnavailable from error
    if result.returncode == 1:
        raise UserCancelled
    if result.returncode != 0:
        raise _DirectorySelectionUnavailable(result.stderr.strip())
    selected = result.stdout.strip()
    if not selected:
        raise UserCancelled
    return _existing_directory(Path(selected))


def _choose_tk_directory() -> Path:
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise _DirectorySelectionUnavailable from error

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
        raise _DirectorySelectionUnavailable from error
    finally:
        if window is not None:
            window.destroy()
    if not selected:
        raise UserCancelled
    return _existing_directory(Path(selected))


def _choose_terminal_directory() -> Path:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        raise _DirectorySelectionUnavailable("当前输入输出不是交互终端")
    try:
        import curses
    except ImportError as error:
        raise _DirectorySelectionUnavailable from error

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
                return _existing_directory(entries[selected_index][1])
            elif key in {ord("q"), ord("Q"), 27}:
                raise UserCancelled

    try:
        return curses.wrapper(select)
    except UserCancelled:
        raise
    except (curses.error, OSError) as error:
        raise _DirectorySelectionUnavailable from error


def _choose_directory() -> Path:
    try:
        if os.name == "nt":
            return _choose_windows_directory()
        if sys.platform == "darwin":
            return _choose_macos_directory()
        if sys.platform.startswith("linux"):
            return _choose_linux_directory()
        return _choose_tk_directory()
    except _DirectorySelectionUnavailable:
        if sys.platform == "darwin":
            try:
                return _choose_tk_directory()
            except _DirectorySelectionUnavailable:
                pass
        if sys.platform.startswith("linux"):
            try:
                return _choose_tk_directory()
            except _DirectorySelectionUnavailable:
                pass
        if os.name != "nt":
            try:
                return _choose_terminal_directory()
            except _DirectorySelectionUnavailable:
                pass
        print("当前环境无法打开目录选择窗口，请手动输入路径。")
        while True:
            raw_path = _ask(
                f"处理目录（直接回车使用 {Path.cwd()}）：",
                allow_empty=True,
            )
            try:
                return _existing_directory(path_from_input(raw_path))
            except ValueError as error:
                print(error)


def _existing_mapping_file(path: Path) -> Path:
    path = path.resolve()
    if not path.is_file():
        raise ValueError(f"映射文件不存在：{path}")
    return path


def _choose_windows_mapping_file(initial_directory: Path) -> Path:
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
        raise _DirectorySelectionUnavailable from error
    if result.returncode != 0:
        raise _DirectorySelectionUnavailable(result.stderr.strip())
    selected = result.stdout.strip().lstrip("\ufeff")
    if not selected:
        raise UserCancelled
    return _existing_mapping_file(Path(selected))


def _choose_macos_mapping_file(initial_directory: Path) -> Path:
    script = """
try
    set initialDirectory to system attribute "PATHCRAFT_MAPPING_DIRECTORY"
    set selectedFile to choose file with prompt "请选择名称映射文件" default location (POSIX file initialDirectory)
    return POSIX path of selectedFile
on error number -128
    return ""
end try
"""
    environment = os.environ.copy()
    environment["PATHCRAFT_MAPPING_DIRECTORY"] = str(initial_directory)
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            check=False,
        )
    except OSError as error:
        raise _DirectorySelectionUnavailable from error
    if result.returncode != 0:
        raise _DirectorySelectionUnavailable(result.stderr.strip())
    selected = result.stdout.strip()
    if not selected:
        raise UserCancelled
    return _existing_mapping_file(Path(selected))


def _choose_tk_mapping_file(initial_directory: Path) -> Path:
    try:
        import tkinter
        from tkinter import filedialog
    except ImportError as error:
        raise _DirectorySelectionUnavailable from error

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
        raise _DirectorySelectionUnavailable from error
    finally:
        if window is not None:
            window.destroy()
    if not selected:
        raise UserCancelled
    return _existing_mapping_file(Path(selected))


def _choose_mapping_file(initial_directory: Path) -> Path:
    print("请选择 Excel、CSV 或 TXT 名称映射文件。")
    try:
        if os.name == "nt":
            return _choose_windows_mapping_file(initial_directory)
        if sys.platform == "darwin":
            return _choose_macos_mapping_file(initial_directory)
        return _choose_tk_mapping_file(initial_directory)
    except _DirectorySelectionUnavailable:
        while True:
            raw_path = _ask("请输入映射文件路径：")
            try:
                candidate = path_from_input(raw_path)
                if not candidate.is_absolute():
                    candidate = initial_directory / candidate
                return _existing_mapping_file(candidate)
            except ValueError as error:
                print(error)


def _fit_terminal_text(text: str, width: int) -> str:
    fitted = []
    used = 0
    for character in text:
        character_width = 2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1
        if used + character_width > width:
            break
        fitted.append(character)
        used += character_width
    return f"{''.join(fitted)}{' ' * (width - used)}"


def _truncate_terminal_text(text: str, width: int) -> str:
    if _terminal_text_width(text) <= width:
        return _fit_terminal_text(text, width)
    if width <= 1:
        return "…"[:width]
    truncated = _fit_terminal_text(text, width - 1).rstrip()
    return _fit_terminal_text(f"{truncated}…", width)


def _center_terminal_text(text: str, width: int) -> str:
    remaining = max(0, width - _terminal_text_width(text))
    left = remaining // 2
    return _fit_terminal_text(f"{' ' * left}{text}", width)


def _menu_frame(
    options: list[MenuOption],
    selected: int | None,
    width: int,
    height: int | None = None,
    content_lines: list[str] | None = None,
) -> tuple[list[str], int]:
    unpacked = [_menu_option_parts(option) for option in options]
    branded = any(description for _, _, description in unpacked)
    lines = (
        [
            *(_truncate_terminal_text(line, width).rstrip() for line in MENU_LOGO),
            f"  {MENU_TAGLINE}",
            "",
        ]
        if branded
        else []
    )
    selected_row = len(lines) + selected if selected is not None else -1
    label_width = min(
        30,
        max((_terminal_text_width(label) for _, label, _ in unpacked), default=0) + 4,
    )
    for index, (value, label, description) in enumerate(unpacked):
        marker = "➤" if index == selected else " "
        item = f"{marker} {value}. "
        if description:
            item += f"{_fit_terminal_text(label, label_width)}{description}"
        else:
            item += label
        lines.append(
            _truncate_terminal_text(item, width).rstrip()
        )
    separator = "─" * width
    hint = (
        "↑↓ | Enter 确认 | Z 返回主菜单 | U 上一步 | Q/Esc 退出程序"
        if selected is not None
        else "输入编号 | Z 返回主菜单 | U 上一步 | Q 退出程序"
    )
    lines.append(separator)
    content = list(content_lines or [])
    if height is not None:
        available = max(1, height)
        content_height = max(0, available - len(lines) - 2)
        if not content_height:
            lines = lines[: max(0, available - 2)]
            if selected_row >= len(lines):
                selected_row = -1
        else:
            content = content[-content_height:]
            lines.extend(content)
            lines.extend([""] * (content_height - len(content)))
        lines.append(separator)
    else:
        lines.extend(content or [""])
        lines.append(separator)
    lines.append(_truncate_terminal_text(hint, width).rstrip())
    return lines, selected_row


def _choose_windows_menu(
    options: list[MenuOption],
    content_lines: list[str] | None = None,
) -> str:
    try:
        import ctypes
        import msvcrt
    except ImportError as error:
        raise _DirectorySelectionUnavailable from error

    try:
        kernel32 = ctypes.windll.kernel32
        output_handle = kernel32.GetStdHandle(-11)
        console_mode = ctypes.c_uint()
        if kernel32.GetConsoleMode(output_handle, ctypes.byref(console_mode)):
            kernel32.SetConsoleMode(output_handle, console_mode.value | 0x0004)
    except (AttributeError, OSError):
        pass

    selected = 0
    terminal_size = shutil.get_terminal_size(fallback=(80, 24))
    menu_width = max(1, terminal_size.columns - 1)
    menu_height = max(2, terminal_size.lines)
    line_count = menu_height

    def draw(move_up: bool = False) -> None:
        lines, selected_row = _menu_frame(
            options,
            selected,
            menu_width,
            height=menu_height,
            content_lines=content_lines,
        )
        if move_up:
            sys.stdout.write(f"\033[{line_count - 1}F")
        for index, line in enumerate(lines):
            if index == selected_row:
                line = f"\033[1;36m{line}\033[0m"
            ending = "\n" if index < len(lines) - 1 else ""
            sys.stdout.write(f"\033[2K{line}{ending}")
        sys.stdout.flush()

    def finish() -> None:
        sys.stdout.write("\n")
        sys.stdout.flush()

    draw()
    while True:
        key = msvcrt.getwch()
        if key in {"\x00", "\xe0"}:
            arrow = msvcrt.getwch()
            if arrow == "H":
                selected = (selected - 1) % len(options)
                draw(move_up=True)
            elif arrow == "P":
                selected = (selected + 1) % len(options)
                draw(move_up=True)
        elif key == "\r":
            finish()
            return options[selected][0]
        elif key in {"q", "Q", "\x1b"}:
            finish()
            raise ExitProgram
        elif key in {"z", "Z"}:
            finish()
            raise ReturnToMainMenu
        elif key in {"u", "U"}:
            finish()
            raise PreviousStep


def _choose_curses_menu(
    options: list[MenuOption],
    content_lines: list[str] | None = None,
) -> str:
    try:
        import curses
    except ImportError as error:
        raise _DirectorySelectionUnavailable from error

    def select(screen: object) -> str:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        screen.keypad(True)
        selected = 0
        while True:
            height, width = screen.getmaxyx()
            menu_width = max(16, width - 1)
            lines, selected_row = _menu_frame(
                options,
                selected,
                menu_width,
                height=height,
                content_lines=content_lines,
            )
            screen.erase()
            try:
                for row, line in enumerate(lines):
                    if row >= height:
                        break
                    style = curses.A_REVERSE | curses.A_BOLD if row == selected_row else curses.A_NORMAL
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
            elif key in {ord("z"), ord("Z")}:
                raise ReturnToMainMenu
            elif key in {ord("u"), ord("U")}:
                raise PreviousStep

    try:
        return curses.wrapper(select)
    except (ExitProgram, PreviousStep, ReturnToMainMenu, UserCancelled):
        raise
    except (curses.error, OSError) as error:
        raise _DirectorySelectionUnavailable from error


def _ask_menu_choice(
    options: list[MenuOption],
    *,
    is_main_menu: bool = False,
    content_lines: list[str] | None = None,
) -> str:
    if sys.stdin.isatty() and sys.stdout.isatty():
        while True:
            try:
                selected = (
                    _choose_windows_menu(options, content_lines)
                    if os.name == "nt"
                    else _choose_curses_menu(options, content_lines)
                )
                return selected
            except (PreviousStep, ReturnToMainMenu):
                if is_main_menu:
                    continue
                raise
            except _DirectorySelectionUnavailable:
                break

    menu_width = max(24, min(72, shutil.get_terminal_size(fallback=(72, 24)).columns))
    lines, _ = _menu_frame(
        options,
        None,
        menu_width,
        content_lines=content_lines,
    )
    print("\n".join(lines))
    choices = {_menu_option_parts(option)[0] for option in options}
    values = [_menu_option_parts(option)[0] for option in options]
    while True:
        try:
            value = _ask(f"请选择模式（{'/'.join(values)}）：")
        except UserCancelled as error:
            raise ExitProgram from error
        if value in choices:
            return value
        command = value.casefold()
        if command == "z":
            if is_main_menu:
                continue
            raise ReturnToMainMenu
        if command == "u":
            if is_main_menu:
                continue
            raise PreviousStep
        print(f"请输入 {' 或 '.join(sorted(choices))}。")


def _ask(prompt: str, allow_empty: bool = False) -> str:
    while True:
        value = input(prompt).strip()
        raise_if_cancelled(value)
        if value or allow_empty:
            return value
        print("输入不能为空。")


def _ask_choice(prompt: str, choices: set[str]) -> str:
    while True:
        value = _ask(prompt)
        if value in choices:
            return value
        print(f"请输入 {' 或 '.join(sorted(choices))}。")


def _terminal_text_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(character) in {"W", "F"} else 1 for character in text)


def _ask_valid_text(prompt: str, allow_empty: bool = False) -> str:
    while True:
        value = _ask(prompt, allow_empty=allow_empty)
        invalid = validate_filename_text(value)
        if not invalid:
            return value
        printable = ["NUL" if character == "\0" else character for character in invalid]
        print(f"内容包含当前系统不允许的文件名字符：{' '.join(printable)}")
