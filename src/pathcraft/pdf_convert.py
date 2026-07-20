"""旧版 PDF 转换模块的兼容导入。"""

from .pdf import (
    BuyerNameRecognitionError,
    EmptyPdfError,
    EncryptedPdfError,
    PdfContentError,
    PdfConversionPlan,
    PdfConversionResult,
    PdfDependencyError,
    PdfError,
    PdfPageCountChangedError,
    PdfRenderError,
    build_conversion_plans,
    convert_pdf_plan,
    execute_conversion_plans,
    find_pdf_files,
    load_pymupdf,
    recognize_buyer_name,
)

__all__ = [
    "BuyerNameRecognitionError",
    "EmptyPdfError",
    "EncryptedPdfError",
    "PdfContentError",
    "PdfConversionPlan",
    "PdfConversionResult",
    "PdfDependencyError",
    "PdfError",
    "PdfPageCountChangedError",
    "PdfRenderError",
    "build_conversion_plans",
    "convert_pdf_plan",
    "execute_conversion_plans",
    "find_pdf_files",
    "load_pymupdf",
    "recognize_buyer_name",
]
