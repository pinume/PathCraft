import os
import re
import stat
from collections.abc import Iterator
from pathlib import Path

from .config import IMAGE_EXTENSIONS


def is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    if os.name == "nt":
        try:
            import ctypes

            attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        except (AttributeError, OSError):
            return False
        return attributes != -1 and bool(attributes & 0x2)
    try:
        hidden_flag = getattr(stat, "UF_HIDDEN", 0)
        if not hidden_flag:
            return False
        return bool(getattr(path.stat(), "st_flags", 0) & hidden_flag)
    except OSError:
        return False


def is_hidden_within(path: Path, root: Path) -> bool:
    """检查路径本身或从根目录开始的任一层级是否隐藏。"""
    try:
        relative = path.relative_to(root)
    except ValueError:
        return is_hidden(path)

    current = root
    if is_hidden(current):
        return True
    for part in relative.parts:
        current /= part
        if is_hidden(current):
            return True
    return False


def find_files(
    root: Path,
    recursive: bool = True,
    all_files: bool = True,
) -> list[Path]:
    if is_hidden(root):
        return []
    if recursive:
        candidates = _walk_files(root)
    else:
        candidates = root.iterdir()
    files = (
        path
        for path in candidates
        if path.is_file()
        and not is_hidden_within(path, root)
        and (all_files or path.suffix.lower() in IMAGE_EXTENSIONS)
    )
    return sorted(files, key=lambda path: _natural_sort_key(path.relative_to(root)))


def _walk_files(root: Path) -> Iterator[Path]:
    for directory, directories, filenames in os.walk(root):
        parent = Path(directory)
        directories[:] = [
            name for name in directories if not is_hidden(parent / name)
        ]
        yield from (
            parent / name
            for name in filenames
            if not is_hidden(parent / name)
        )


def _natural_sort_key(path: Path) -> tuple[tuple[int, object], ...]:
    parts = re.split(r"(\d+)", str(path).casefold())
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in parts
    )


def find_images(root: Path, recursive: bool = True) -> list[Path]:
    return find_files(root, recursive, all_files=False)
