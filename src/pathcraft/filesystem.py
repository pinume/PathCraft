"""跨功能共享的无覆盖文件移动能力。"""

import os
from pathlib import Path


def path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def move_without_overwrite(source: Path, destination: Path) -> None:
    """使用 Windows 的 no-replace rename 语义移动文件。"""
    source.rename(destination)

