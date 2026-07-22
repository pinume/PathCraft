from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
import os
from pathlib import Path
import uuid

from .filesystem import (
    FileSignature,
    file_matches_signature,
    file_signature,
    move_without_overwrite,
    path_exists,
)
from .rules import RenameRule
from .utils import filename_validation_error


@dataclass(frozen=True)
class RenameEntry:
    source: Path
    destination: Path
    problem: str | None = None
    source_signature: FileSignature | None = None


@dataclass
class RenameResult:
    completed: list[tuple[Path, Path]]
    failed: list[tuple[RenameEntry, str]]


def _path_key(path: Path) -> str:
    return os.path.normcase(str(path.absolute()))


def build_plan(files: list[Path], rule: RenameRule) -> list[RenameEntry]:
    destinations = [rule.destination(source, index) for index, source in enumerate(files)]
    counts: dict[str, int] = {}
    for destination in destinations:
        key = _path_key(destination)
        counts[key] = counts.get(key, 0) + 1

    plan = []
    for source, destination in zip(files, destinations):
        problem = None
        signature = None
        if rule.remove is not None and not source.stem.replace(rule.remove, ""):
            problem = "删除后文件名为空"
        elif source == destination:
            problem = "名称未变化"
        elif counts[_path_key(destination)] > 1:
            problem = "目标名称重复"
        else:
            problem = filename_validation_error(destination.name)
        try:
            signature = file_signature(source)
        except OSError as error:
            if problem is None:
                problem = f"无法读取源文件：{error}"
        plan.append(RenameEntry(source, destination, problem, signature))

    return mark_existing_destination_conflicts(plan)


def mark_existing_destination_conflicts(
    plan: list[RenameEntry],
    problem: str = "目标文件已存在",
) -> list[RenameEntry]:
    moving_sources = {
        _path_key(entry.source): index
        for index, entry in enumerate(plan)
        if entry.problem is None
    }
    dependents: dict[int, list[int]] = defaultdict(list)
    blocked = set()

    for index, entry in enumerate(plan):
        if entry.problem is not None or not path_exists(entry.destination):
            continue
        owner = moving_sources.get(_path_key(entry.destination))
        if owner is None:
            blocked.add(index)
        else:
            dependents[owner].append(index)

    queue = deque(blocked)
    while queue:
        owner = queue.popleft()
        for dependent in dependents[owner]:
            if dependent not in blocked:
                blocked.add(dependent)
                queue.append(dependent)

    return [
        RenameEntry(entry.source, entry.destination, problem, entry.source_signature)
        if index in blocked
        else entry
        for index, entry in enumerate(plan)
    ]


def execute_plan(
    plan: list[RenameEntry],
    on_progress: Callable[[int, int, Path], None] | None = None,
) -> RenameResult:
    executable = [entry for entry in plan if entry.problem is None]
    staged: list[tuple[RenameEntry, Path]] = []
    failed: list[tuple[RenameEntry, str]] = []
    total_steps = len(executable)
    progress = 0

    for entry in executable:
        if (
            entry.source_signature is not None
            and not file_matches_signature(entry.source, entry.source_signature)
        ):
            failed.append((entry, "源文件在预览后发生变化，请重新生成预览"))
            rollback_failed, _ = _rollback(staged, set())
            return RenameResult([], failed + rollback_failed)
        temporary = _temporary_path(entry.source.parent)
        try:
            move_without_overwrite(entry.source, temporary)
        except OSError as error:
            failed.append((entry, f"暂存失败：{error}"))
            rollback_failed, _ = _rollback(staged, set())
            return RenameResult([], failed + rollback_failed)
        staged.append((entry, temporary))

    committed: set[int] = set()
    for entry, temporary in staged:
        try:
            if path_exists(entry.destination):
                raise FileExistsError("目标文件在执行前已存在")
            move_without_overwrite(temporary, entry.destination)
        except OSError as error:
            failed.append((entry, f"写入目标失败：{error}"))
            rollback_failed, remaining = _rollback(staged, committed)
            return RenameResult(remaining, failed + rollback_failed)
        committed.add(id(entry))
        progress += 1
        _notify_progress(on_progress, progress, total_steps, entry.destination)

    completed = [(entry.source, entry.destination) for entry in executable]

    return RenameResult(completed, failed)


def _notify_progress(
    callback: Callable[[int, int, Path], None] | None,
    index: int,
    total: int,
    path: Path,
) -> None:
    if callback is None:
        return
    try:
        callback(index, total, path)
    except Exception:
        # 进度显示不能破坏正在执行的文件事务。
        pass


def _temporary_path(parent: Path) -> Path:
    while True:
        candidate = parent / f".pathcraft-{uuid.uuid4().hex}.tmp"
        if not path_exists(candidate):
            return candidate


def _rollback(
    staged: list[tuple[RenameEntry, Path]],
    committed: set[int],
) -> tuple[list[tuple[RenameEntry, str]], list[tuple[Path, Path]]]:
    failed: list[tuple[RenameEntry, str]] = []
    remaining: list[tuple[Path, Path]] = []

    for entry, temporary in reversed(staged):
        was_committed = id(entry) in committed
        current = entry.destination if was_committed else temporary
        try:
            if path_exists(entry.source):
                raise FileExistsError("原文件名在回滚前已被占用")
            move_without_overwrite(current, entry.source)
        except OSError as error:
            failed.append((entry, f"回滚失败（文件保留在 {current}）：{error}"))
            if was_committed:
                remaining.append((entry.source, entry.destination))

    remaining.reverse()
    return failed, remaining
