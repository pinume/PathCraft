import os
import platform
from pathlib import Path
import sys

from .exceptions import UserCancelled


CANCEL_WORDS = {"q", "quit", "exit", "取消", "退出"}
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def configure_console_encoding() -> None:
    """让 CLI 在 Windows 旧代码页和重定向输出中稳定写出中文。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (AttributeError, OSError, ValueError):
            # StringIO、已关闭流或第三方流不一定支持重新配置。
            pass


def path_from_input(value: str, current_dir: Path | None = None) -> Path:
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return current_dir or Path.cwd()
    return Path(cleaned).expanduser()


def invalid_filename_characters(system: str | None = None) -> set[str]:
    current_system = system or platform.system()
    if current_system == "Windows":
        return set('<>:"/\\|?*\0')
    if current_system == "Darwin":
        return {":", "/", "\0"}
    return {"/", "\0"}


def validate_filename_text(text: str, system: str | None = None) -> list[str]:
    invalid = invalid_filename_characters(system)
    return sorted({character for character in text if character in invalid})


def filename_validation_error(name: str, system: str | None = None) -> str | None:
    current_system = system or platform.system()
    invalid = validate_filename_text(name, current_system)
    if invalid:
        return "文件名包含当前系统不允许的字符"
    if not name:
        return "文件名不能为空"
    if current_system == "Windows":
        if name.endswith((" ", ".")):
            return "Windows 文件名不能以空格或句点结尾"
        base_name = name.split(".", 1)[0].rstrip(" .").upper()
        if base_name in WINDOWS_RESERVED_NAMES:
            return "Windows 保留文件名"
        if len(name) > 255:
            return "文件名超过 255 个字符"
    elif len(os.fsencode(name)) > 255:
        return "文件名超过 255 字节"
    return None


def raise_if_cancelled(value: str) -> None:
    if value.strip().casefold() in CANCEL_WORDS:
        raise UserCancelled
