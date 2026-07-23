"""pywebview presentation bridge for the PathCraft desktop application."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
from threading import Lock, Thread
from time import monotonic
from typing import Any

import webview
from webview.dom import DOMEventHandler

from . import __version__
from .app_service import (
    ExecutionSummary,
    PreparedOperation,
    execute_operation,
    execute_undo_operation,
    list_current_files,
    load_mapping_columns,
    prepare_mapping_rename,
    prepare_pdf_conversion,
    prepare_rule_rename,
)
from .config import MAPPING_EXTENSIONS
from .desktop_support import (
    OPERATIONS,
    application_icon_path,
    build_rename_rule,
    ensure_windows,
    ui_asset_path,
)
from .undo import UndoOperation


class Bridge:
    """Thread-safe API exposed to the local HTML front end."""

    def __init__(self) -> None:
        self._window: Any | None = None
        self._prepared: PreparedOperation | None = None
        self._undo: UndoOperation | None = None
        self._state_lock = Lock()
        self._busy = False
        self._maximized = False
        self._last_progress_time = 0.0

    def _attach_window(self, window: Any) -> None:
        self._window = window

    def initialize(self) -> dict[str, object]:
        return {
            "version": __version__,
            "root": str(Path.cwd()),
            "operations": [
                {"value": value, "label": label}
                for value, label in OPERATIONS.items()
            ],
        }

    def choose_root(self, initial_directory: str = "") -> dict[str, object]:
        self._require_idle()
        window = self._require_window()
        selected = window.create_file_dialog(
            webview.FileDialog.FOLDER,
            directory=_dialog_directory(initial_directory),
        )
        return {"cancelled": not selected, "path": selected[0] if selected else ""}

    def list_files(self, root: str) -> dict[str, object]:
        """Return the current files for immediate display after selecting a directory."""
        self._require_idle()
        resolved = Path(root).expanduser().resolve()
        files = list_current_files(resolved)
        return _serialize_current_files(resolved, files)

    def choose_mapping(self, initial_directory: str = "") -> dict[str, object]:
        self._require_idle()
        window = self._require_window()
        patterns = ";".join(f"*{suffix}" for suffix in sorted(MAPPING_EXTENSIONS))
        selected = window.create_file_dialog(
            webview.FileDialog.OPEN,
            directory=_dialog_directory(initial_directory),
            file_types=(f"映射文件 ({patterns})", "所有文件 (*.*)"),
        )
        if not selected:
            return {"cancelled": True, "path": "", "columns": []}
        path = Path(selected[0])
        columns = load_mapping_columns(path)
        return {"cancelled": False, "path": str(path), "columns": list(columns)}

    def resolve_drop(self, dropped_path: str) -> dict[str, object]:
        """Resolve a dropped file or directory to a usable working directory."""
        self._require_idle()
        path = Path(dropped_path).expanduser().resolve()
        if not path.exists():
            raise ValueError("拖入的文件或目录不存在")
        from_file = path.is_file()
        root = path.parent if from_file else path
        if not root.is_dir():
            raise ValueError("无法识别拖入项目所在的目录")
        return {"path": str(root), "fromFile": from_file}

    def _on_drop(self, event: dict[str, object]) -> None:
        with self._state_lock:
            if self._busy:
                return
        try:
            transfer = event.get("dataTransfer", {})
            files = transfer.get("files", []) if isinstance(transfer, dict) else []
            dropped_path = files[0].get("pywebviewFullPath", "") if files else ""
            if not dropped_path:
                raise ValueError("无法读取拖入项目的完整路径")
            result = self.resolve_drop(str(dropped_path))
        except Exception as error:  # noqa: BLE001 - forwarded to the desktop UI
            self._push_event("drop-error", {"message": str(error)})
            return
        self._push_event("directory-dropped", result)

    def minimize_window(self) -> dict[str, bool]:
        self._require_window().minimize()
        return {"minimized": True}

    def toggle_maximize_window(self) -> dict[str, bool]:
        window = self._require_window()
        with self._state_lock:
            maximized = self._maximized
            self._maximized = not maximized
        if maximized:
            window.restore()
        else:
            window.maximize()
        return {"maximized": not maximized}

    def close_window(self) -> dict[str, bool]:
        self._require_window().destroy()
        return {"closed": True}

    def preview(self, args: dict[str, object]) -> dict[str, object]:
        self._claim_task()
        try:
            with self._state_lock:
                self._prepared = None
            prepared = self._prepare(args)
            with self._state_lock:
                self._prepared = prepared
            return _serialize_preview(prepared)
        finally:
            self._release_task()

    def execute(self) -> dict[str, object]:
        with self._state_lock:
            if self._busy:
                raise RuntimeError("已有任务正在处理中")
            prepared = self._prepared
            if prepared is None:
                raise ValueError("请先生成预览")
            if not any(row.status == "ready" for row in prepared.preview_entries):
                raise ValueError("当前预览没有可执行的文件")
            self._busy = True
            self._prepared = None
        self._start_worker(
            lambda: execute_operation(prepared, on_progress=self._push_progress),
            prepared.root,
            "执行完成",
        )
        return {"started": True}

    def undo(self, confirmed: bool = False) -> dict[str, object]:
        if not confirmed:
            raise ValueError("请再次点击撤销按钮确认操作")
        with self._state_lock:
            if self._busy:
                raise RuntimeError("已有任务正在处理中")
            operation = self._undo
            if operation is None:
                raise ValueError("没有可撤销的操作")
            self._busy = True
        with self._state_lock:
            self._prepared = None
        self._start_worker(
            lambda: execute_undo_operation(operation, on_progress=self._push_progress),
            operation.root,
            "撤销完成",
        )
        return {"started": True, "root": str(operation.root)}

    def _prepare(self, args: dict[str, object]) -> PreparedOperation:
        root_text = _required_text(args, "root", "请选择工作目录")
        operation = _required_text(args, "operation", "请选择操作")
        root = Path(root_text)
        if operation in {"prefix", "suffix", "remove", "replace"}:
            rule = build_rename_rule(
                operation,
                str(args.get("primary", "")),
                str(args.get("secondary", "")),
            )
            return prepare_rule_rename(root, rule)
        if operation == "mapping":
            mapping_file = _required_text(args, "mappingFile", "请选择映射文件")
            source_column = _required_text(args, "sourceColumn", "请选择原名称列")
            destination_column = _required_text(args, "destinationColumn", "请选择新名称列")
            return prepare_mapping_rename(
                root,
                Path(mapping_file),
                source_column,
                destination_column,
            )
        if operation == "pdf":
            return prepare_pdf_conversion(root)
        raise ValueError(f"未知操作类型：{operation}")

    def _start_worker(
        self,
        task: Callable[[], ExecutionSummary],
        root: Path,
        action: str,
    ) -> None:
        def worker() -> None:
            try:
                summary = task()
                files = list_current_files(root)
                with self._state_lock:
                    self._undo = summary.undo
                payload = _serialize_completion(summary, root, files, action)
            except Exception as error:  # noqa: BLE001 - forwarded to the desktop UI
                self._release_task()
                self._push_event("error", {"message": str(error)})
                return
            self._release_task()
            self._push_event("completed", payload)

        Thread(target=worker, daemon=True).start()

    def _push_progress(self, index: int, total: int, detail: str) -> None:
        # Progress uses 1-based positions in the executable (ready) entries;
        # blocked preview rows are deliberately excluded from this count.
        now = monotonic()
        if index not in {1, total} and now - self._last_progress_time < 0.05:
            return
        self._last_progress_time = now
        self._push_event(
            "progress",
            {"index": index, "total": total, "detail": Path(detail).name},
        )

    def _push_event(self, event: str, payload: dict[str, object]) -> None:
        window = self._window
        if window is None:
            return
        message = json.dumps(
            {"event": event, "payload": payload},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        window.run_js(f"window.pathcraftHostEvent({message});")

    def _claim_task(self) -> None:
        with self._state_lock:
            if self._busy:
                raise RuntimeError("已有任务正在处理中")
            self._busy = True

    def _release_task(self) -> None:
        with self._state_lock:
            self._busy = False

    def _require_idle(self) -> None:
        with self._state_lock:
            if self._busy:
                raise RuntimeError("已有任务正在处理中")

    def _require_window(self) -> Any:
        if self._window is None:
            raise RuntimeError("桌面窗口尚未初始化")
        return self._window

    def _on_closing(self) -> bool:
        with self._state_lock:
            busy = self._busy
        if not busy:
            return True
        self._require_window().create_confirmation_dialog(
            "PathCraft",
            "任务正在处理中，请等待完成后再关闭应用。",
        )
        return False

    def _on_maximized(self) -> None:
        with self._state_lock:
            self._maximized = True
        self._push_event("window-state", {"maximized": True})

    def _on_restored(self) -> None:
        with self._state_lock:
            self._maximized = False
        self._push_event("window-state", {"maximized": False})


def _required_text(args: dict[str, object], key: str, message: str) -> str:
    value = str(args.get(key, "")).strip()
    if not value:
        raise ValueError(message)
    return value


def _dialog_directory(value: str) -> str:
    candidate = Path(value).expanduser() if value else Path.cwd()
    if candidate.is_file():
        candidate = candidate.parent
    if not candidate.is_dir():
        candidate = Path.cwd()
    return str(candidate.resolve())


def _relative_text(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _serialize_preview(prepared: PreparedOperation) -> dict[str, object]:
    rows: list[dict[str, str]] = []
    for entry in prepared.preview_entries:
        destination = entry.destination
        if isinstance(destination, tuple):
            destination_text = "，".join(path.name for path in destination)
        elif destination is None:
            destination_text = ""
        else:
            destination_text = destination.name
        rows.append(
            {
                "source": _relative_text(entry.source, prepared.root),
                "destination": destination_text,
                "status": entry.status,
                "detail": entry.detail,
            }
        )
    ready = sum(row["status"] == "ready" for row in rows)
    return {
        "root": str(prepared.root),
        "directory": prepared.root.name,
        "rows": rows,
        "readyCount": ready,
        "blockedCount": len(rows) - ready,
        "total": len(rows),
    }


def _serialize_completion(
    summary: ExecutionSummary,
    root: Path,
    files: tuple[Path, ...],
    action: str,
) -> dict[str, object]:
    rows = [
        {"source": "", "destination": "", "status": "issue", "detail": detail}
        for detail in summary.details
    ]
    rows.extend(
        {
            "source": _relative_text(path, root),
            "destination": "",
            "status": "current",
            "detail": "",
        }
        for path in files
    )
    return {
        "action": action,
        "root": str(root),
        "directory": root.name,
        "succeeded": summary.succeeded,
        "skipped": summary.skipped,
        "failed": summary.failed,
        "detailsCount": len(summary.details),
        "fileCount": len(files),
        "canUndo": summary.undo is not None,
        "rows": rows,
    }


def _serialize_current_files(
    root: Path,
    files: tuple[Path, ...],
) -> dict[str, object]:
    return {
        "root": str(root),
        "directory": root.name,
        "fileCount": len(files),
        "rows": [
            {
                "source": _relative_text(path, root),
                "destination": "",
                "status": "current",
                "detail": "",
            }
            for path in files
        ],
    }


def _bind_drop_events(window: Any, bridge: Bridge) -> None:
    window.dom.document.events.drop += DOMEventHandler(
        bridge._on_drop,
        prevent_default=True,
        stop_propagation=True,
    )


def main() -> int:
    ensure_windows()
    bridge = Bridge()
    window = webview.create_window(
        "PathCraft",
        str(ui_asset_path("index.html")),
        js_api=bridge,
        width=1160,
        height=800,
        min_size=(900, 620),
        background_color="#F6F5F1",
        text_select=False,
        frameless=True,
        easy_drag=False,
        transparent=True,
    )
    bridge._attach_window(window)
    window.events.closing += bridge._on_closing
    window.events.maximized += bridge._on_maximized
    window.events.restored += bridge._on_restored
    webview.start(
        _bind_drop_events,
        (window, bridge),
        private_mode=True,
        icon=str(application_icon_path()),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
