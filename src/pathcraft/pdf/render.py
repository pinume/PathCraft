"""电子发票 PDF 的事务式 PNG 渲染。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any
import uuid

from ..config import MINIMUM_PDF_DPI
from ..exceptions import EncryptedPdfError, PdfPageCountChangedError, PdfRenderError
from ..rename import _move_without_overwrite
from .extract import PdfConversionPlan, load_pymupdf


@dataclass
class PdfConversionResult:
    completed: list[PdfConversionPlan]
    failed: list[tuple[Path, str]]


def _temporary_output(output: Path) -> Path:
    return output.parent / f".{output.stem}.{uuid.uuid4().hex}.working.png"


def convert_pdf_plan(
    plan: PdfConversionPlan,
    dpi: int,
    pymupdf_module: ModuleType | Any | None = None,
    on_page_progress: Callable[[int, int, Path], None] | None = None,
) -> None:
    """事务式执行单个 PDF 计划，失败时清理由本次操作生成的文件。"""
    if dpi < MINIMUM_PDF_DPI:
        raise ValueError(f"DPI 不能低于 {MINIMUM_PDF_DPI}")
    pymupdf = pymupdf_module or load_pymupdf()
    temporary_outputs: list[Path] = []
    committed_outputs: list[Path] = []
    created_directories: list[Path] = []
    archive = plan.archive or plan.source.parent / ".pdf" / plan.source.name

    try:
        directories = {output.parent for output in plan.outputs}
        directories.add(archive.parent)
        for directory in sorted(directories):
            if directory.exists():
                if not directory.is_dir():
                    raise NotADirectoryError(f"输出路径不是目录：{directory}")
            else:
                directory.mkdir()
                created_directories.append(directory)

        with pymupdf.open(plan.source) as document:
            if document.needs_pass:
                raise EncryptedPdfError("PDF 已加密，需要密码")
            if document.page_count != len(plan.outputs):
                raise PdfPageCountChangedError("PDF 页数在识别后发生变化")
            for page_number, (page, output) in enumerate(
                zip(document, plan.outputs),
                start=1,
            ):
                if output.exists():
                    raise FileExistsError(f"目标文件在执行前已存在：{output}")
                temporary = _temporary_output(output)
                try:
                    pixmap = page.get_pixmap(
                        dpi=dpi,
                        colorspace=pymupdf.csRGB,
                        alpha=False,
                        annots=True,
                    )
                    pixmap.save(temporary)
                except Exception as error:
                    raise PdfRenderError(
                        f"PDF 第 {page_number} 页渲染失败：{error}"
                    ) from error
                temporary_outputs.append(temporary)
                if on_page_progress is not None:
                    on_page_progress(page_number, document.page_count, plan.source)

        for temporary, output in zip(temporary_outputs, plan.outputs):
            _move_without_overwrite(temporary, output)
            committed_outputs.append(output)
        _move_without_overwrite(plan.source, archive)

    except Exception:
        for path in reversed(temporary_outputs):
            path.unlink(missing_ok=True)
        for path in reversed(committed_outputs):
            path.unlink(missing_ok=True)
        for directory in reversed(created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass
        raise


def execute_conversion_plans(
    plans: list[PdfConversionPlan],
    dpi: int,
    pymupdf_module: ModuleType | Any | None = None,
    on_progress: Callable[[int, int, Path], None] | None = None,
    on_page_progress: Callable[[int, int, Path], None] | None = None,
) -> PdfConversionResult:
    completed = []
    failed = []
    for index, plan in enumerate(plans, start=1):
        if on_progress is not None:
            on_progress(index, len(plans), plan.source)
        try:
            convert_pdf_plan(
                plan,
                dpi,
                pymupdf_module,
                on_page_progress,
            )
            completed.append(plan)
        except Exception as error:
            failed.append((plan.source, str(error)))
    return PdfConversionResult(completed, failed)
