"""可选的调试诊断输出。"""

import os
from pathlib import Path
import sys
import traceback


DEBUG_ENVIRONMENT_VARIABLE = "PATHCRAFT_DEBUG"
_ENABLED_VALUES = {"1", "true", "yes", "on"}


def debug_enabled() -> bool:
    return os.environ.get(DEBUG_ENVIRONMENT_VARIABLE, "").strip().casefold() in _ENABLED_VALUES


def report_exception(context: str, path: Path, error: Exception) -> None:
    """调试模式下输出完整异常链；正常模式保持简洁失败信息。"""
    if not debug_enabled():
        return
    print(f"[PathCraft DEBUG] {context}：{path}", file=sys.stderr)
    traceback.print_exception(error, file=sys.stderr)

