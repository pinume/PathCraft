"""Windows desktop presentation for PathCraft."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from queue import Empty, SimpleQueue
import sys
from pathlib import Path
from threading import Thread
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .app_service import (
    ExecutionSummary,
    PreparedOperation,
    execute_operation,
    load_mapping_columns,
    list_current_files,
    prepare_mapping_rename,
    prepare_pdf_conversion,
    prepare_rule_rename,
)
from .config import MAPPING_EXTENSIONS
from .rules import RenameRule


OPERATIONS = {
    "prefix": "添加前缀",
    "suffix": "添加后缀",
    "remove": "删除内容",
    "replace": "替换内容",
    "mapping": "映射表重命名",
    "pdf": "PDF 转 PNG",
}


@dataclass(frozen=True)
class TaskOutcome:
    value: object | None = None
    error: Exception | None = None


class BackgroundTask:
    def __init__(self, operation: Callable[[], object]) -> None:
        self._operation = operation
        self._outcomes: SimpleQueue[TaskOutcome] = SimpleQueue()
        self._thread = Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def wait(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def poll(self) -> TaskOutcome | None:
        try:
            return self._outcomes.get_nowait()
        except Empty:
            return None

    def _run(self) -> None:
        try:
            self._outcomes.put(TaskOutcome(value=self._operation()))
        except Exception as error:
            self._outcomes.put(TaskOutcome(error=error))


def ensure_windows(platform_name: str | None = None) -> None:
    current = sys.platform if platform_name is None else platform_name
    if current != "win32":
        raise RuntimeError("PathCraft 仅支持 Windows 10 和 Windows 11")


def application_icon_path(bundle_directory: Path | None = None) -> Path:
    if bundle_directory is None:
        frozen_directory = getattr(sys, "_MEIPASS", None)
        bundle_directory = (
            Path(frozen_directory)
            if frozen_directory is not None
            else Path(__file__).resolve().parents[2]
        )
    return bundle_directory / "assets" / "pathcraft.ico"


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


class PathCraftApp:
    def __init__(self, window: tk.Tk) -> None:
        self.window = window
        self.prepared: PreparedOperation | None = None
        self._task: BackgroundTask | None = None
        self._task_callback: Callable[[object], None] | None = None
        self._progress_messages: SimpleQueue[str] = SimpleQueue()
        self._input_version = 0
        self.root_path = tk.StringVar(value=str(Path.cwd()))
        self.operation = tk.StringVar(value="prefix")
        self.primary = tk.StringVar()
        self.secondary = tk.StringVar()
        self.mapping_file = tk.StringVar()
        self.source_column = tk.StringVar()
        self.destination_column = tk.StringVar()
        self.status = tk.StringVar(value="请选择目录和操作，然后生成预览。")

        window.title("PathCraft")
        icon_path = application_icon_path()
        if icon_path.is_file():
            window.iconbitmap(default=str(icon_path))
        window.geometry("1050x720")
        window.minsize(820, 560)
        window.protocol("WM_DELETE_WINDOW", self._close)
        self._build_layout()
        self._render_operation_fields()

    def _build_layout(self) -> None:
        container = ttk.Frame(self.window, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(1, weight=1)
        container.rowconfigure(5, weight=1)

        ttk.Label(container, text="PathCraft", font=("Segoe UI", 20, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
        )
        ttk.Label(container, text="工作目录").grid(row=1, column=0, sticky="w")
        self.root_entry = ttk.Entry(container, textvariable=self.root_path)
        self.root_entry.grid(row=1, column=1, sticky="ew", padx=8)
        self.root_entry.bind("<KeyRelease>", self._invalidate)
        self.root_button = ttk.Button(container, text="选择…", command=self._choose_root)
        self.root_button.grid(row=1, column=2)

        ttk.Label(container, text="操作").grid(row=2, column=0, sticky="w", pady=(10, 0))
        operation_box = ttk.Combobox(
            container,
            state="readonly",
            values=list(OPERATIONS.values()),
        )
        operation_box.current(0)
        operation_box.grid(row=2, column=1, sticky="ew", padx=8, pady=(10, 0))
        operation_box.bind("<<ComboboxSelected>>", self._operation_selected)
        self.operation_box = operation_box

        self.options = ttk.Frame(container)
        self.options.grid(row=3, column=0, columnspan=3, sticky="ew", pady=12)
        self.options.columnconfigure(1, weight=1)

        self.primary_label = ttk.Label(self.options, text="内容")
        self.primary_entry = ttk.Entry(self.options, textvariable=self.primary)
        self.secondary_label = ttk.Label(self.options, text="替换为")
        self.secondary_entry = ttk.Entry(self.options, textvariable=self.secondary)
        self.mapping_label = ttk.Label(self.options, text="映射文件")
        self.mapping_entry = ttk.Entry(self.options, textvariable=self.mapping_file, state="readonly")
        self.mapping_button = ttk.Button(self.options, text="选择…", command=self._choose_mapping)
        self.source_label = ttk.Label(self.options, text="原名称列")
        self.source_box = ttk.Combobox(self.options, textvariable=self.source_column, state="readonly")
        self.destination_label = ttk.Label(self.options, text="新名称列")
        self.destination_box = ttk.Combobox(
            self.options, textvariable=self.destination_column, state="readonly"
        )
        for widget in (self.primary_entry, self.secondary_entry):
            widget.bind("<KeyRelease>", self._invalidate)
        self.source_box.bind("<<ComboboxSelected>>", self._invalidate)
        self.destination_box.bind("<<ComboboxSelected>>", self._invalidate)

        actions = ttk.Frame(container)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.preview_button = ttk.Button(actions, text="生成预览", command=self._preview)
        self.preview_button.pack(side="left")
        self.execute_button = ttk.Button(
            actions, text="执行", command=self._execute, state="disabled"
        )
        self.execute_button.pack(side="left", padx=8)
        ttk.Label(actions, textvariable=self.status).pack(side="left", padx=12)

        columns = ("source", "destination", "status", "detail")
        self.preview_table = ttk.Treeview(container, columns=columns, show="headings")
        headings = {"source": "源文件", "destination": "目标/输出", "status": "状态", "detail": "说明"}
        widths = {"source": 230, "destination": 300, "status": 70, "detail": 300}
        for column in columns:
            self.preview_table.heading(column, text=headings[column])
            self.preview_table.column(column, width=widths[column], anchor="w")
        self.preview_table.tag_configure("blocked", foreground="#a33")
        self.preview_table.grid(row=5, column=0, columnspan=3, sticky="nsew")
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self.preview_table.yview)
        scrollbar.grid(row=5, column=3, sticky="ns")
        self.preview_table.configure(yscrollcommand=scrollbar.set)
        self.input_widgets = (
            self.root_entry,
            self.root_button,
            self.operation_box,
            self.primary_entry,
            self.secondary_entry,
            self.mapping_button,
            self.source_box,
            self.destination_box,
        )

    def _operation_selected(self, _event: object = None) -> None:
        selected = self.operation_box.current()
        self.operation.set(tuple(OPERATIONS)[selected])
        self._render_operation_fields()
        self._invalidate()

    def _render_operation_fields(self) -> None:
        for widget in self.options.winfo_children():
            widget.grid_forget()
        operation = self.operation.get()
        if operation in {"prefix", "suffix", "remove", "replace"}:
            labels = {
                "prefix": "前缀",
                "suffix": "后缀",
                "remove": "删除内容",
                "replace": "查找内容",
            }
            self.primary_label.configure(text=labels[operation])
            self.primary_label.grid(row=0, column=0, sticky="w")
            self.primary_entry.grid(row=0, column=1, sticky="ew", padx=8)
            if operation == "replace":
                self.secondary_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
                self.secondary_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        elif operation == "mapping":
            self.mapping_label.grid(row=0, column=0, sticky="w")
            self.mapping_entry.grid(row=0, column=1, sticky="ew", padx=8)
            self.mapping_button.grid(row=0, column=2)
            self.source_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
            self.source_box.grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
            self.destination_label.grid(row=2, column=0, sticky="w", pady=(8, 0))
            self.destination_box.grid(row=2, column=1, sticky="ew", padx=8, pady=(8, 0))

    def _choose_root(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.root_path.get() or str(Path.cwd()))
        if selected:
            self.root_path.set(selected)
            self._invalidate()

    def _choose_mapping(self) -> None:
        patterns = " ".join(f"*{suffix}" for suffix in sorted(MAPPING_EXTENSIONS))
        selected = filedialog.askopenfilename(
            initialdir=self.root_path.get() or str(Path.cwd()),
            filetypes=[("映射文件", patterns), ("所有文件", "*.*")],
        )
        if not selected:
            return
        try:
            columns = load_mapping_columns(Path(selected))
        except Exception as error:
            self._show_error(error)
            return
        self.mapping_file.set(selected)
        self.source_box.configure(values=columns)
        self.destination_box.configure(values=columns)
        self.source_column.set(columns[0])
        self.destination_column.set(columns[1])
        self._invalidate()

    def _invalidate(self, _event: object = None) -> None:
        self._input_version += 1
        self.prepared = None
        self.execute_button.configure(state="disabled")
        self.status.set("输入已更改，请重新生成预览。")

    def _preview(self) -> None:
        try:
            root = Path(self.root_path.get())
            operation = self.operation.get()
            if operation in {"prefix", "suffix", "remove", "replace"}:
                rule = build_rename_rule(operation, self.primary.get(), self.secondary.get())
                task = lambda: prepare_rule_rename(root, rule)
            elif operation == "mapping":
                if not self.mapping_file.get():
                    raise ValueError("请选择映射文件")
                mapping_file = Path(self.mapping_file.get())
                source_column = self.source_column.get()
                destination_column = self.destination_column.get()
                task = lambda: prepare_mapping_rename(
                    root, mapping_file, source_column, destination_column
                )
            else:
                task = lambda: prepare_pdf_conversion(root)
        except Exception as error:
            self._show_error(error)
            return
        version = self._input_version
        self.prepared = None
        self._start_task(
            task,
            lambda value: self._preview_completed(value, version),
            "正在生成预览…",
        )

    def _preview_completed(self, value: object, version: int) -> None:
        if version != self._input_version:
            self.status.set("输入已更改，请重新生成预览。")
            return
        if not isinstance(value, PreparedOperation):
            raise TypeError("预览任务返回了无效结果")
        prepared = value
        self.prepared = prepared
        self._render_preview(prepared)
        ready = sum(row.status == "ready" for row in prepared.preview_entries)
        blocked = len(prepared.preview_entries) - ready
        self.status.set(f"预览完成：可执行 {ready} 个，阻止 {blocked} 个。")
        self.execute_button.configure(state="normal" if ready else "disabled")

    def _render_preview(self, prepared: PreparedOperation) -> None:
        self.preview_table.delete(*self.preview_table.get_children())
        for row in prepared.preview_entries:
            destination = row.destination
            if isinstance(destination, tuple):
                destination_text = "，".join(path.name for path in destination)
            elif destination is None:
                destination_text = ""
            else:
                destination_text = destination.name
            try:
                source_text = str(row.source.relative_to(prepared.root))
            except ValueError:
                source_text = str(row.source)
            self.preview_table.insert(
                "",
                "end",
                values=(source_text, destination_text, "可执行" if row.status == "ready" else "阻止", row.detail),
                tags=(row.status,),
            )

    def _execute(self) -> None:
        if self.prepared is None:
            return
        prepared = self.prepared
        self.prepared = None
        self._start_task(
            lambda: execute_operation(prepared, on_progress=self._progress),
            lambda value: self._execution_completed(value, prepared.root),
            "正在执行…",
        )

    def _execution_completed(self, value: object, root: Path) -> None:
        if not isinstance(value, ExecutionSummary):
            raise TypeError("执行任务返回了无效结果")
        summary = value
        self._clear_preview()
        self._start_task(
            lambda: list_current_files(root),
            lambda files: self._directory_refreshed(files, root, summary),
            "执行完成，正在刷新当前目录…",
        )

    def _clear_preview(self) -> None:
        self.preview_table.delete(*self.preview_table.get_children())

    def _directory_refreshed(
        self,
        value: object,
        root: Path,
        summary: ExecutionSummary,
    ) -> None:
        if not isinstance(value, tuple) or not all(isinstance(path, Path) for path in value):
            raise TypeError("目录刷新任务返回了无效结果")
        self._clear_preview()
        for path in value:
            self.preview_table.insert(
                "",
                "end",
                values=(str(path.relative_to(root)), "", "当前文件", ""),
            )
        self.status.set(
            f"完成：成功 {summary.succeeded}，跳过 {summary.skipped}，失败 {summary.failed}；"
            f"当前目录共 {len(value)} 个文件。"
        )

    def _progress(self, index: int, total: int, detail: str) -> None:
        self._progress_messages.put(f"处理中 {index}/{total}：{Path(detail).name}")

    def _start_task(
        self,
        operation: Callable[[], object],
        callback: Callable[[object], None],
        status: str,
    ) -> None:
        if self._task is not None:
            return
        self._task = BackgroundTask(operation)
        self._task_callback = callback
        self._set_busy(True)
        self.status.set(status)
        self._task.start()
        self.window.after(50, self._poll_task)

    def _poll_task(self) -> None:
        latest_progress = None
        while True:
            try:
                latest_progress = self._progress_messages.get_nowait()
            except Empty:
                break
        if latest_progress is not None:
            self.status.set(latest_progress)

        task = self._task
        if task is None:
            return
        outcome = task.poll()
        if outcome is None:
            self.window.after(50, self._poll_task)
            return

        callback = self._task_callback
        self._task = None
        self._task_callback = None
        self._set_busy(False)
        if outcome.error is not None:
            self._show_error(outcome.error)
            return
        if callback is not None:
            try:
                callback(outcome.value)
            except Exception as error:
                self._show_error(error)

    def _set_busy(self, busy: bool) -> None:
        state = ["disabled"] if busy else ["!disabled"]
        for widget in self.input_widgets:
            widget.state(state)
        self.preview_button.configure(state="disabled" if busy else "normal")
        self.execute_button.configure(state="disabled")

    def _close(self) -> None:
        if self._task is not None:
            messagebox.showwarning("PathCraft", "任务正在处理中，请等待完成后再关闭应用。")
            return
        self.window.destroy()

    def _show_error(self, error: Exception) -> None:
        self.status.set(str(error))
        messagebox.showerror("PathCraft", str(error))


def main() -> int:
    ensure_windows()
    window = tk.Tk()
    PathCraftApp(window)
    window.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
