"""跨功能共享的无覆盖文件移动能力。"""

import hashlib
import os
from pathlib import Path


FileSignature = tuple[int, int, int, int, int]
FileContentSignature = tuple[FileSignature, str]


def path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def file_signature(path: Path) -> FileSignature:
    """返回足以检测预览后文件替换或修改的轻量签名。"""
    status = path.stat()
    return (
        status.st_dev,
        status.st_ino,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def file_matches_signature(path: Path, expected: FileSignature) -> bool:
    try:
        return file_signature(path) == expected
    except OSError:
        return False


def file_content_signature(path: Path) -> FileContentSignature:
    before = file_signature(path)
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    after = file_signature(path)
    if before != after:
        raise OSError(f"文件在读取期间发生变化：{path}")
    return after, digest.hexdigest()


def file_matches_content_signature(
    path: Path,
    expected: FileContentSignature,
) -> bool:
    try:
        return file_content_signature(path) == expected
    except OSError:
        return False


def move_without_overwrite(source: Path, destination: Path) -> None:
    """使用 Windows 的 no-replace rename 语义移动文件。"""
    source.rename(destination)

