"""当前应用会话内最近一次成功操作的安全撤销。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import uuid

from .filesystem import (
    FileContentSignature,
    file_content_signature,
    file_matches_content_signature,
    file_signature,
    move_without_overwrite,
    path_exists,
)
from .pdf import PdfConversionPlan
from .rename import RenameEntry, execute_plan, mark_existing_destination_conflicts


ProgressCallback = Callable[[int, int, Path], None]


@dataclass(frozen=True)
class PdfUndoEntry:
    source: Path
    archive: Path
    archive_signature: FileContentSignature
    outputs: tuple[tuple[Path, FileContentSignature], ...]


@dataclass(frozen=True)
class UndoOperation:
    kind: str
    root: Path
    rename_entries: tuple[RenameEntry, ...] = ()
    pdf_entries: tuple[PdfUndoEntry, ...] = ()


@dataclass(frozen=True)
class UndoResult:
    succeeded: int
    skipped: int
    failed: int
    details: tuple[str, ...]
    remaining: UndoOperation | None = None


def prepare_rename_undo(
    root: Path,
    completed: list[tuple[Path, Path]],
) -> tuple[UndoOperation | None, tuple[str, ...]]:
    entries = []
    details = []
    for original, current in completed:
        try:
            signature = file_signature(current)
        except OSError as error:
            details.append(f"{current.name}：无法记录撤销信息：{error}")
            continue
        entries.append(RenameEntry(current, original, source_signature=signature))
    operation = UndoOperation("rename", root, rename_entries=tuple(entries)) if entries else None
    return operation, tuple(details)


def prepare_pdf_undo(
    root: Path,
    completed: list[PdfConversionPlan],
) -> tuple[UndoOperation | None, tuple[str, ...]]:
    entries = []
    details = []
    for plan in completed:
        archive = plan.archive or plan.source.parent / ".pdf" / plan.source.name
        try:
            archive_signature = file_content_signature(archive)
            outputs = tuple(
                (path, file_content_signature(path)) for path in plan.outputs
            )
        except OSError as error:
            details.append(f"{plan.source.name}：无法记录撤销信息：{error}")
            continue
        entries.append(PdfUndoEntry(plan.source, archive, archive_signature, outputs))
    operation = UndoOperation("pdf", root, pdf_entries=tuple(entries)) if entries else None
    return operation, tuple(details)


def execute_undo(
    operation: UndoOperation,
    on_progress: ProgressCallback | None = None,
) -> UndoResult:
    if operation.kind == "rename":
        return _undo_rename(operation, on_progress)
    if operation.kind == "pdf":
        return _undo_pdf(operation, on_progress)
    raise ValueError(f"未知撤销类型：{operation.kind}")


def _undo_rename(
    operation: UndoOperation,
    on_progress: ProgressCallback | None,
) -> UndoResult:
    original_entries = list(operation.rename_entries)
    plan = mark_existing_destination_conflicts(
        original_entries,
        problem="原文件名已被占用，无法撤销",
    )
    result = execute_plan(plan, on_progress=on_progress)
    blocked = [entry for entry in plan if entry.problem]
    details = [
        f"{entry.source.name} -> {entry.destination.name}：{entry.problem}"
        for entry in blocked
    ]
    details.extend(
        f"{entry.source.name} -> {entry.destination.name}：{message}"
        for entry, message in result.failed
    )
    completed_sources = {_path_key(source) for source, _ in result.completed}
    remaining_entries = tuple(
        entry
        for entry in original_entries
        if _path_key(entry.source) not in completed_sources
    )
    remaining = (
        UndoOperation("rename", operation.root, rename_entries=remaining_entries)
        if remaining_entries
        else None
    )
    return UndoResult(
        len(result.completed),
        len(blocked),
        len(result.failed),
        tuple(details),
        remaining,
    )


def _undo_pdf(
    operation: UndoOperation,
    on_progress: ProgressCallback | None,
) -> UndoResult:
    succeeded = 0
    skipped = 0
    failed = 0
    details = []
    remaining = []
    total = len(operation.pdf_entries)

    for entry in operation.pdf_entries:
        problem, is_conflict = _pdf_undo_problem(entry)
        if problem is not None:
            details.append(f"{entry.source.name}：{problem}")
            remaining.append(entry)
            if is_conflict:
                skipped += 1
            else:
                failed += 1
            continue

        staged: list[tuple[Path, Path]] = []
        archive_moved = False
        try:
            for output, signature in entry.outputs:
                temporary = _temporary_undo_path(output)
                move_without_overwrite(output, temporary)
                staged.append((output, temporary))
                if not file_matches_content_signature(temporary, signature):
                    raise OSError(f"输出图片在撤销期间发生变化：{output.name}")
            if not file_matches_content_signature(
                entry.archive,
                entry.archive_signature,
            ):
                raise OSError("归档 PDF 在撤销期间发生变化")
            move_without_overwrite(entry.archive, entry.source)
            archive_moved = True
            if not file_matches_content_signature(
                entry.source,
                entry.archive_signature,
            ):
                raise OSError("归档 PDF 在恢复期间发生变化")
        except OSError as error:
            archive_details = _restore_archive(entry) if archive_moved else []
            restore_details = _restore_staged_outputs(staged)
            details.append(f"{entry.source.name}：撤销失败：{error}")
            details.extend(archive_details)
            details.extend(restore_details)
            if not archive_details and not restore_details:
                remaining.append(_refresh_pdf_undo_entry(entry))
            failed += 1
            continue

        cleanup_failed = False
        for _, temporary in staged:
            try:
                temporary.unlink()
            except OSError as error:
                cleanup_failed = True
                details.append(f"{entry.source.name}：临时图片清理失败（{temporary}）：{error}")
        if entry.archive.parent.name == ".pdf":
            try:
                entry.archive.parent.rmdir()
            except OSError:
                pass
        succeeded += 1
        _notify_progress(on_progress, succeeded, total, entry.source)
        if cleanup_failed:
            failed += 1

    remaining_operation = (
        UndoOperation("pdf", operation.root, pdf_entries=tuple(remaining))
        if remaining
        else None
    )
    return UndoResult(
        succeeded,
        skipped,
        failed,
        tuple(details),
        remaining_operation,
    )


def _pdf_undo_problem(entry: PdfUndoEntry) -> tuple[str | None, bool]:
    if path_exists(entry.source):
        return "原 PDF 路径已被占用，无法撤销", True
    if not file_matches_content_signature(entry.archive, entry.archive_signature):
        return "归档 PDF 已被移动或修改，无法安全撤销", False
    for output, signature in entry.outputs:
        if not file_matches_content_signature(output, signature):
            return f"输出图片已被移动或修改，无法安全撤销：{output.name}", False
    return None, False


def _temporary_undo_path(output: Path) -> Path:
    while True:
        candidate = output.parent / f".pathcraft-undo-{uuid.uuid4().hex}.tmp"
        if not path_exists(candidate):
            return candidate


def _restore_staged_outputs(staged: list[tuple[Path, Path]]) -> list[str]:
    details = []
    for output, temporary in reversed(staged):
        try:
            move_without_overwrite(temporary, output)
        except OSError as error:
            details.append(f"恢复输出图片失败（文件保留在 {temporary}）：{error}")
    return details


def _restore_archive(entry: PdfUndoEntry) -> list[str]:
    try:
        move_without_overwrite(entry.source, entry.archive)
    except OSError as error:
        return [f"恢复归档 PDF 失败（文件保留在 {entry.source}）：{error}"]
    return []


def _refresh_pdf_undo_entry(entry: PdfUndoEntry) -> PdfUndoEntry:
    try:
        return PdfUndoEntry(
            entry.source,
            entry.archive,
            file_content_signature(entry.archive),
            tuple(
                (path, file_content_signature(path))
                for path, _ in entry.outputs
            ),
        )
    except OSError:
        return entry


def _notify_progress(
    callback: ProgressCallback | None,
    index: int,
    total: int,
    path: Path,
) -> None:
    if callback is None:
        return
    try:
        callback(index, total, path)
    except Exception:
        pass


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.absolute()))
