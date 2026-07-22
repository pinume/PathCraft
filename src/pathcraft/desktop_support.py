"""Shared helpers for PathCraft desktop presentation layers."""

from __future__ import annotations

from pathlib import Path
import sys

from .rules import RenameRule


OPERATIONS = {
    "prefix": "添加前缀",
    "suffix": "添加后缀",
    "remove": "删除内容",
    "replace": "替换内容",
    "mapping": "映射表重命名",
    "pdf": "PDF 转 PNG",
}


def ensure_windows(platform_name: str | None = None) -> None:
    current = sys.platform if platform_name is None else platform_name
    if current != "win32":
        raise RuntimeError("PathCraft 仅支持 Windows 10 和 Windows 11")


def bundle_root(bundle_directory: Path | None = None) -> Path:
    if bundle_directory is not None:
        return bundle_directory
    frozen_directory = getattr(sys, "_MEIPASS", None)
    if frozen_directory is not None:
        return Path(frozen_directory)
    return Path(__file__).resolve().parents[2]


def application_icon_path(bundle_directory: Path | None = None) -> Path:
    return _required_asset(
        bundle_root(bundle_directory) / "assets" / "pathcraft.ico",
        "应用图标",
    )


def ui_asset_path(name: str, bundle_directory: Path | None = None) -> Path:
    return _required_asset(
        bundle_root(bundle_directory) / "assets" / "ui" / name,
        f"界面资源 {name}",
    )


def _required_asset(path: Path, description: str) -> Path:
    if not path.is_file():
        raise FileNotFoundError(f"缺少{description}：{path}")
    return path


def build_rename_rule(operation: str, primary: str, secondary: str = "") -> RenameRule:
    if not primary:
        raise ValueError("规则内容不能为空")
    if operation == "prefix":
        return RenameRule(prefix=primary)
    if operation == "suffix":
        return RenameRule(suffix=primary)
    if operation == "remove":
        return RenameRule(remove=primary)
    if operation == "replace":
        if not secondary:
            raise ValueError("替换后的内容不能为空")
        return RenameRule(replace=primary, replacement=secondary)
    raise ValueError(f"未知重命名操作：{operation}")
