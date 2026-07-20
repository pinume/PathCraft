"""跨模块共享的应用配置。"""

DEFAULT_PDF_DPI = 300
MINIMUM_PDF_DPI = 72

IMAGE_EXTENSIONS = frozenset(
    {
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".bmp",
        ".gif",
        ".tif",
        ".tiff",
        ".heic",
        ".heif",
    }
)
MAPPING_EXTENSIONS = frozenset({".csv", ".txt", ".xlsx", ".xlsm"})
