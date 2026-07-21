"""跨功能共享的无覆盖文件移动能力。"""

import errno
import os
from pathlib import Path


def path_exists(path: Path) -> bool:
    return os.path.lexists(path)


def move_without_overwrite(source: Path, destination: Path) -> None:
    """移动文件或符号链接，并保证已有目标不会被覆盖。"""
    if os.name == "nt":
        source.rename(destination)
        return

    if source.is_symlink():
        os.symlink(os.readlink(source), destination)
    else:
        try:
            os.link(source, destination)
        except OSError as error:
            unsupported = {errno.EPERM, errno.ENOSYS, errno.EOPNOTSUPP}
            if error.errno not in unsupported:
                raise
            if path_exists(destination):
                raise FileExistsError(f"目标文件已存在：{destination}")
            source.rename(destination)
            return
    try:
        source.unlink()
    except OSError as unlink_error:
        try:
            destination.unlink()
        except OSError as cleanup_error:
            raise OSError(
                f"无法删除源文件（{unlink_error}），也无法清理目标文件（{cleanup_error}）"
            ) from unlink_error
        raise

