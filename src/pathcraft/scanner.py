import os
import re
from collections.abc import Iterator
from pathlib import Path


def is_hidden(path: Path) -> bool:
    if path.name.startswith("."):
        return True
    try:
        import ctypes

        attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
    except (AttributeError, OSError):
        return False
    return attributes != -1 and bool(attributes & 0x2)


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
) -> list[Path]:
    return sorted(
        iter_files(root, recursive=recursive),
        key=lambda path: _natural_sort_key(path.relative_to(root)),
    )


def iter_files(root: Path, recursive: bool = True) -> Iterator[Path]:
    """Yield visible files without sorting or retaining the full directory tree."""
    if is_hidden(root):
        return
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        if _entry_is_hidden(entry):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if recursive:
                                pending.append(Path(entry.path))
                        elif entry.is_file():
                            yield Path(entry.path)
                    except OSError:
                        continue
        except OSError:
            if directory == root and not recursive:
                raise


def _entry_is_hidden(entry: os.DirEntry[str]) -> bool:
    if entry.name.startswith("."):
        return True
    status = entry.stat(follow_symlinks=False)
    return bool(getattr(status, "st_file_attributes", 0) & 0x2)


def _natural_sort_key(path: Path) -> tuple[tuple[int, object], ...]:
    parts = re.split(r"(\d+)", str(path).casefold())
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part)
        for part in parts
    )
