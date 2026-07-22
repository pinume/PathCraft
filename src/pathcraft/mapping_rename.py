import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import MAPPING_EXTENSIONS
from .rename import RenameEntry, mark_existing_destination_conflicts
from .scanner import find_files, is_hidden_within
from .utils import filename_validation_error


SUPPORTED_MAPPING_EXTENSIONS = MAPPING_EXTENSIONS


@dataclass(frozen=True)
class MappingTable:
    columns: tuple[str, ...]
    rows: tuple[dict[str, str], ...]

    def mappings(self, source_column: str, destination_column: str) -> list[tuple[str, str]]:
        if source_column not in self.columns:
            raise ValueError(f"未找到原名称列：{source_column}")
        if destination_column not in self.columns:
            raise ValueError(f"未找到新名称列：{destination_column}")

        mappings = []
        for row_number, row in enumerate(self.rows, start=2):
            source = row[source_column].strip()
            destination = row[destination_column].strip()
            if not source and not destination:
                continue
            if not source:
                raise ValueError(f"第 {row_number} 行的原名称为空")
            if not destination:
                raise ValueError(f"第 {row_number} 行的新名称为空")
            mappings.append((source, destination))
        if not mappings:
            raise ValueError("映射表中没有可用的名称映射")
        return mappings


def load_mapping_table(path: Path) -> MappingTable:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_MAPPING_EXTENSIONS:
        supported = "、".join(sorted(SUPPORTED_MAPPING_EXTENSIONS))
        raise ValueError(f"不支持的映射文件格式：{suffix}（支持 {supported}）")
    if suffix in {".xlsx", ".xlsm"}:
        return _load_excel_table(path)
    return _load_text_table(path)


def load_mapping_columns(path: Path) -> tuple[str, ...]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_MAPPING_EXTENSIONS:
        supported = "、".join(sorted(SUPPORTED_MAPPING_EXTENSIONS))
        raise ValueError(f"不支持的映射文件格式：{suffix}（支持 {supported}）")
    if suffix in {".xlsx", ".xlsm"}:
        return _load_excel_columns(path)
    return _load_text_columns(path)


def _load_text_columns(path: Path) -> tuple[str, ...]:
    errors = []
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            with path.open("r", encoding=encoding, newline="") as stream:
                sample = stream.read(8192)
                if not sample.strip():
                    raise ValueError("映射文件为空")
                stream.seek(0)
                dialect = _detect_dialect(sample, path.suffix.lower())
                header = next(csv.reader(stream, dialect), None)
        except UnicodeDecodeError as error:
            errors.append(error)
            continue
        if header is None:
            raise ValueError("映射文件为空")
        return _columns_from_values(header)
    raise ValueError(f"无法识别映射文件编码：{errors[-1]}")


def _load_text_table(path: Path) -> MappingTable:
    text = _read_text(path)
    if not text.strip():
        raise ValueError("映射文件为空")
    sample = text[:8192]
    dialect = _detect_dialect(sample, path.suffix.lower())
    reader = csv.reader(text.splitlines(), dialect)
    raw_rows = list(reader)
    if not raw_rows:
        raise ValueError("映射文件为空")
    return _table_from_rows(raw_rows)


def _read_text(path: Path) -> str:
    errors = []
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as error:
            errors.append(error)
    raise ValueError(f"无法识别映射文件编码：{errors[-1]}")


def _detect_dialect(sample: str, suffix: str) -> type[csv.Dialect] | csv.Dialect:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;|")
    except csv.Error:
        return csv.excel_tab if suffix == ".txt" else csv.excel


def _load_excel_columns(path: Path) -> tuple[str, ...]:
    try:
        import openpyxl
    except ImportError as error:
        raise ValueError("读取 Excel 需要 openpyxl，请先运行 uv sync") from error

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        header = next(workbook.active.iter_rows(values_only=True), None)
    finally:
        workbook.close()
    if header is None:
        raise ValueError("Excel 映射表为空")
    return _columns_from_values(header)


def _load_excel_table(path: Path) -> MappingTable:
    try:
        import openpyxl
    except ImportError as error:
        raise ValueError("读取 Excel 需要 openpyxl，请先运行 uv sync") from error

    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        worksheet = workbook.active
        raw_rows = [list(row) for row in worksheet.iter_rows(values_only=True)]
    finally:
        workbook.close()
    if not raw_rows:
        raise ValueError("Excel 映射表为空")
    return _table_from_rows(raw_rows)


def _table_from_rows(raw_rows: list[list[Any]]) -> MappingTable:
    columns = _columns_from_values(raw_rows[0])

    rows = []
    for values in raw_rows[1:]:
        padded = [*values, *([None] * (len(columns) - len(values)))]
        rows.append(
            {
                column: _cell_text(value)
                for column, value in zip(columns, padded[: len(columns)])
            }
        )
    return MappingTable(columns, tuple(rows))


def _columns_from_values(values: list[Any] | tuple[Any, ...]) -> tuple[str, ...]:
    columns = tuple(_cell_text(value) for value in values)
    if len(columns) < 2:
        raise ValueError("映射表至少需要两列")
    if any(not column for column in columns):
        raise ValueError("映射表包含空列标题")
    if len(set(columns)) != len(columns):
        raise ValueError("映射表包含重复的列标题")
    return columns


def _cell_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def build_mapping_plan(
    root: Path,
    mappings: list[tuple[str, str]],
    recursive: bool = True,
    all_files: bool = True,
    files: list[Path] | None = None,
) -> list[RenameEntry]:
    if files is None:
        files = find_files(root, recursive=recursive, all_files=all_files)
    else:
        files = [
            path
            for path in files
            if path.is_file() and not is_hidden_within(path, root)
        ]
    by_relative: dict[str, list[Path]] = {}
    by_name: dict[str, list[Path]] = {}
    by_stem: dict[str, list[Path]] = {}
    for path in files:
        relative = path.relative_to(root).as_posix().casefold()
        by_relative.setdefault(relative, []).append(path)
        by_name.setdefault(path.name.casefold(), []).append(path)
        by_stem.setdefault(path.stem.casefold(), []).append(path)

    preliminary = []
    used_sources: set[Path] = set()
    for source_text, destination_text in mappings:
        normalized_source = source_text.replace("\\", "/").strip().strip("/")
        source_relative = Path(normalized_source)
        if source_relative.is_absolute() or ".." in source_relative.parts:
            preliminary.append(
                RenameEntry(root / source_relative.name, root / destination_text, "原名称路径无效")
            )
            continue

        if "/" in normalized_source:
            candidates = by_relative.get(normalized_source.casefold(), [])
        else:
            candidates = list(by_name.get(normalized_source.casefold(), []))
            if not Path(normalized_source).suffix:
                candidates.extend(by_stem.get(normalized_source.casefold(), []))
            candidates = list(dict.fromkeys(candidates))

        placeholder = root / normalized_source
        if not candidates:
            preliminary.append(RenameEntry(placeholder, placeholder, "未找到原文件"))
            continue
        if len(candidates) > 1:
            preliminary.append(RenameEntry(placeholder, placeholder, "原名称匹配多个文件"))
            continue

        source = candidates[0]
        if source in used_sources:
            preliminary.append(RenameEntry(source, source, "原名称在映射表中重复"))
            continue
        used_sources.add(source)

        destination_name = destination_text.strip()
        if Path(destination_name).name != destination_name or "/" in destination_name or "\\" in destination_name:
            preliminary.append(RenameEntry(source, source, "新名称只能是文件名，不能包含目录"))
            continue
        if not Path(destination_name).suffix:
            destination_name = f"{destination_name}{source.suffix}"
        destination = source.with_name(destination_name)
        problem = filename_validation_error(destination.name)
        if source == destination:
            problem = "名称未变化"
        preliminary.append(RenameEntry(source, destination, problem))

    destination_counts: dict[str, int] = {}
    for entry in preliminary:
        if entry.problem is None:
            key = os.path.normcase(str(entry.destination.absolute()))
            destination_counts[key] = destination_counts.get(key, 0) + 1
    plan = [
        RenameEntry(entry.source, entry.destination, "目标名称重复")
        if entry.problem is None
        and destination_counts[os.path.normcase(str(entry.destination.absolute()))] > 1
        else entry
        for entry in preliminary
    ]
    return mark_existing_destination_conflicts(plan)
