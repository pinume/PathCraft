"""PDF 单元测试使用的轻量替身。"""

from pathlib import Path
from types import SimpleNamespace


BUYER_WORDS = [
    (20, 10, 60, 30, "名称："),
    (62, 10, 130, 30, "示例"),
    (132, 10, 210, 30, "公司"),
    (320, 10, 360, 30, "名称："),
    (362, 10, 430, 30, "销售方"),
]


class FakePixmap:
    def save(self, path: Path) -> None:
        Path(path).write_bytes(b"png")


class FakePage:
    rect = SimpleNamespace(width=600)

    def __init__(self, words=None, fail_render: bool = False) -> None:
        self.words = BUYER_WORDS if words is None else words
        self.fail_render = fail_render

    def get_text(self, kind: str, sort: bool = False):
        return self.words

    def get_pixmap(self, **kwargs):
        if self.fail_render:
            raise OSError("模拟渲染失败")
        return FakePixmap()


class FakeDocument:
    needs_pass = False

    def __init__(self, pages) -> None:
        self.pages = pages
        self.page_count = len(pages)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def __getitem__(self, index):
        return self.pages[index]

    def __iter__(self):
        return iter(self.pages)


class FakePyMuPDF:
    csRGB = object()

    def __init__(self, pages=None) -> None:
        self.pages = pages or [FakePage()]

    def open(self, path):
        return FakeDocument(self.pages)
