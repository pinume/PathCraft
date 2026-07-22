"""UI-independent planning and execution services for the Windows App."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_PDF_DPI
from .mapping_rename import (
    build_mapping_plan,
    load_mapping_columns as read_mapping_columns,
    load_mapping_table,
)
from .pdf import (
    PdfConversionPlan,
    build_conversion_plans,
    execute_conversion_plans,
)
from .rename import RenameEntry, build_plan, execute_plan
from .rules import RenameRule
from .scanner import find_files


ProgressCallback = Callable[[int, int, str], None]


@dataclass(frozen=True)
class PreviewEntry:
    source: Path
    destination: Path | tuple[Path, ...] | None
    status: str
    detail: str = ""


@dataclass(frozen=True)
class PreparedOperation:
    kind: str
    root: Path
    preview_entries: tuple[PreviewEntry, ...]
    rename_entries: tuple[RenameEntry, ...] = ()
    pdf_plans: tuple[PdfConversionPlan, ...] = ()
    planning_failures: tuple[tuple[Path, str], ...] = ()


@dataclass(frozen=True)
class ExecutionSummary:
    succeeded: int
    skipped: int
    failed: int
    details: tuple[str, ...] = ()


def validate_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    if not resolved.exists():
        raise ValueError(f"目录不存在：{resolved}")
    if not resolved.is_dir():
        raise ValueError(f"路径不是目录：{resolved}")
    return resolved


def list_current_files(root: Path) -> tuple[Path, ...]:
    resolved = validate_root(root)
    return tuple(find_files(resolved, recursive=True, all_files=True))


def prepare_rule_rename(root: Path, rule: RenameRule) -> PreparedOperation:
    resolved = validate_root(root)
    entries = build_plan(find_files(resolved, recursive=True, all_files=True), rule)
    return _prepared_rename(resolved, entries)


def load_mapping_columns(mapping_file: Path) -> tuple[str, ...]:
    return read_mapping_columns(mapping_file.expanduser().resolve())


def prepare_mapping_rename(
    root: Path,
    mapping_file: Path,
    source_column: str,
    destination_column: str,
) -> PreparedOperation:
    resolved = validate_root(root)
    if source_column == destination_column:
        raise ValueError("原名称列和新名称列不能相同")
    table = load_mapping_table(mapping_file.expanduser().resolve())
    mappings = table.mappings(source_column, destination_column)
    entries = build_mapping_plan(resolved, mappings)
    return _prepared_rename(resolved, entries)


def prepare_pdf_conversion(root: Path) -> PreparedOperation:
    resolved = validate_root(root)
    plans, failures = build_conversion_plans(resolved)
    rows = [
        PreviewEntry(plan.source, plan.outputs, "ready")
        for plan in plans
    ]
    rows.extend(
        PreviewEntry(source, None, "blocked", message)
        for source, message in failures
    )
    return PreparedOperation(
        kind="pdf",
        root=resolved,
        preview_entries=tuple(rows),
        pdf_plans=tuple(plans),
        planning_failures=tuple(failures),
    )


def execute_operation(
    prepared: PreparedOperation,
    *,
    dpi: int = DEFAULT_PDF_DPI,
    on_progress: ProgressCallback | None = None,
) -> ExecutionSummary:
    if prepared.kind == "rename":
        return _execute_rename(prepared, on_progress)
    if prepared.kind == "pdf":
        return _execute_pdf(prepared, dpi, on_progress)
    raise ValueError(f"未知操作类型：{prepared.kind}")


def _prepared_rename(root: Path, entries: list[RenameEntry]) -> PreparedOperation:
    rows = tuple(
        PreviewEntry(
            entry.source,
            entry.destination,
            "blocked" if entry.problem else "ready",
            entry.problem or "",
        )
        for entry in entries
    )
    return PreparedOperation(
        kind="rename",
        root=root,
        preview_entries=rows,
        rename_entries=tuple(entries),
    )


def _execute_rename(
    prepared: PreparedOperation,
    on_progress: ProgressCallback | None,
) -> ExecutionSummary:
    def report(index: int, total: int, path: Path) -> None:
        if on_progress is not None:
            on_progress(index, total, str(path))

    result = execute_plan(list(prepared.rename_entries), on_progress=report)
    blocked = [entry for entry in prepared.rename_entries if entry.problem]
    details = [f"{entry.source.name}：{entry.problem}" for entry in blocked]
    details.extend(
        f"{entry.source.name} -> {entry.destination.name}：{message}"
        for entry, message in result.failed
    )
    return ExecutionSummary(
        succeeded=len(result.completed),
        skipped=len(blocked),
        failed=len(result.failed),
        details=tuple(details),
    )


def _execute_pdf(
    prepared: PreparedOperation,
    dpi: int,
    on_progress: ProgressCallback | None,
) -> ExecutionSummary:
    def report(index: int, total: int, path: Path) -> None:
        if on_progress is not None:
            on_progress(index, total, str(path))

    result = execute_conversion_plans(
        list(prepared.pdf_plans),
        dpi=dpi,
        on_progress=report,
        on_page_progress=report,
    )
    details = [
        f"{source.name}：{message}"
        for source, message in prepared.planning_failures
    ]
    details.extend(f"{source.name}：{message}" for source, message in result.failed)
    return ExecutionSummary(
        succeeded=len(result.completed),
        skipped=len(prepared.planning_failures),
        failed=len(result.failed),
        details=tuple(details),
    )
