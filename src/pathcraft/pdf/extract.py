"""电子发票 PDF 扫描、购买方识别与输出规划。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import ModuleType
from typing import Any
import warnings

from ..exceptions import (
    BuyerNameRecognitionError,
    EmptyPdfError,
    EncryptedPdfError,
    PdfDependencyError,
)
from ..diagnostics import report_exception
from ..filesystem import FileSignature, file_signature
from ..scanner import find_files, is_hidden_within
from ..utils import WINDOWS_RESERVED_NAMES


INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
PYMUPDF_SWIG_DEPRECATION = re.compile(
    r"builtin type (?:SwigPyPacked|SwigPyObject|swigvarlink) "
    r"has no __module__ attribute"
)


@dataclass(frozen=True)
class PdfConversionPlan:
    source: Path
    buyer_name: str
    outputs: tuple[Path, ...]
    archive: Path | None = None
    source_signature: FileSignature | None = None


def load_pymupdf() -> ModuleType:
    try:
        # PyMuPDF 1.28.0 的 SWIG 扩展在部分 Python/系统组合下会在
        # DeprecationWarning 被提升为异常时崩溃。只屏蔽这组上游导入警告，
        # 让应用和测试仍可对其余警告使用 ``-W error``。
        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message=PYMUPDF_SWIG_DEPRECATION.pattern,
                category=DeprecationWarning,
            )
            import pymupdf
    except ImportError as error:
        raise PdfDependencyError(
            "PDF 转换功能需要 PyMuPDF，请运行 uv sync 或 pip install pymupdf"
        ) from error
    return pymupdf


def find_pdf_files(root: Path, recursive: bool = True) -> list[Path]:
    """查找 PDF，扩展名匹配不区分大小写。"""
    candidates = find_files(root, recursive=recursive)
    files = (
        path
        for path in candidates
        if path.suffix.lower() == ".pdf"
    )
    return sorted(files, key=lambda path: str(path.relative_to(root)).casefold())


def _safe_filename_stem(value: str) -> str:
    stem = INVALID_FILENAME_CHARS.sub("_", value).strip().rstrip(". ")
    if not stem:
        raise BuyerNameRecognitionError("购买方名称为空或无法识别")
    if stem.split(".", 1)[0].rstrip(" .").upper() in WINDOWS_RESERVED_NAMES:
        stem = f"_{stem}"
    return stem


def recognize_buyer_name(document: Any) -> str:
    """从电子发票首页左侧的“名称：”字段识别购买方名称。"""
    page = document[0]
    words = page.get_text("words", sort=False)
    labels = [word for word in words if word[4].replace(" ", "") in {"名称：", "名称:"}]
    buyer_labels = [word for word in labels if word[0] < page.rect.width / 2]
    if not buyer_labels:
        raise BuyerNameRecognitionError("未找到购买方‘名称：’字段")

    label = min(buyer_labels, key=lambda word: word[0])
    label_mid_y = (label[1] + label[3]) / 2
    name_words = [
        word
        for word in words
        if word[0] >= label[2] - 3
        and word[2] < page.rect.width / 2
        and word[1] <= label_mid_y <= word[3]
        and word[4].replace(" ", "") not in {"名称：", "名称:"}
    ]
    name = "".join(word[4].strip() for word in sorted(name_words, key=lambda word: word[0]))
    return _safe_filename_stem(name)


def _available_output_paths(
    directory: Path,
    stem: str,
    page_count: int,
    reserved: set[Path],
) -> tuple[Path, ...]:
    outputs = []
    for page_number in range(1, page_count + 1):
        base = stem if page_count == 1 else f"{stem}_第{page_number}页"
        candidate = directory / f"{base}.png"
        index = 2
        while candidate.exists() or candidate in reserved:
            candidate = directory / f"{base}_{index}.png"
            index += 1
        reserved.add(candidate)
        outputs.append(candidate)
    return tuple(outputs)


def _available_archive_path(source: Path, reserved: set[Path]) -> Path:
    directory = source.parent / ".pdf"
    candidate = directory / source.name
    index = 2
    while candidate.exists() or candidate in reserved:
        candidate = directory / f"{source.stem}_{index}{source.suffix}"
        index += 1
    reserved.add(candidate)
    return candidate


def build_conversion_plans(
    root: Path,
    recursive: bool = True,
    pymupdf_module: ModuleType | Any | None = None,
    pdf_files: list[Path] | None = None,
) -> tuple[list[PdfConversionPlan], list[tuple[Path, str]]]:
    """读取 PDF 元数据并生成不会互相覆盖的转换计划。"""
    if pdf_files is None:
        pdf_files = find_pdf_files(root, recursive)
    else:
        pdf_files = [
            path
            for path in pdf_files
            if path.is_file()
            and path.suffix.lower() == ".pdf"
            and not is_hidden_within(path, root)
        ]
    if not pdf_files:
        return [], []
    pymupdf = pymupdf_module or load_pymupdf()
    plans = []
    failed = []
    reserved_outputs: set[Path] = set()
    reserved_archives: set[Path] = set()

    for source in pdf_files:
        output_directory = source.parent
        try:
            signature_before = file_signature(source)
            with pymupdf.open(source) as document:
                if document.needs_pass:
                    raise EncryptedPdfError("PDF 已加密，需要密码")
                if document.page_count == 0:
                    raise EmptyPdfError("PDF 不包含页面")
                buyer_name = recognize_buyer_name(document)
                outputs = _available_output_paths(
                    output_directory,
                    buyer_name,
                    document.page_count,
                    reserved_outputs,
                )
                archive = _available_archive_path(source, reserved_archives)
            signature_after = file_signature(source)
            if signature_before != signature_after:
                raise ValueError("PDF 在生成预览期间发生变化，请重新生成预览")
            plans.append(
                PdfConversionPlan(source, buyer_name, outputs, archive, signature_after)
            )
        except Exception as error:
            report_exception("PDF 规划失败", source, error)
            failed.append((source, str(error)))
    return plans, failed
