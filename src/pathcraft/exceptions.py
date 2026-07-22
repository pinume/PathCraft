"""跨模块共享的 PathCraft 异常。"""


class PathCraftError(Exception):
    """PathCraft 可识别的应用错误基类。"""


class PdfError(PathCraftError):
    """PDF 处理错误基类。"""


class PdfDependencyError(PdfError, RuntimeError):
    """缺少 PDF 转换依赖。"""


class PdfContentError(PdfError, ValueError):
    """PDF 内容不满足转换要求。"""


class EncryptedPdfError(PdfContentError):
    """PDF 已加密且当前无法读取。"""


class EmptyPdfError(PdfContentError):
    """PDF 不包含可转换页面。"""


class BuyerNameRecognitionError(PdfContentError):
    """无法从电子发票中识别有效的购买方名称。"""


class PdfPageCountChangedError(PdfContentError):
    """PDF 页数在规划和执行之间发生变化。"""


class PdfRenderError(PdfError, RuntimeError):
    """PDF 页面无法渲染或写入临时图片。"""
