from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RenameRule:
    prefix: str = ""
    suffix: str = ""
    remove: str | None = None
    replace: str | None = None
    replacement: str | None = None

    def __post_init__(self) -> None:
        if self.remove == "":
            raise ValueError("要删除的内容不能为空")
        if self.replace == "":
            raise ValueError("要替换的内容不能为空")
        if self.replace is not None and not self.replacement:
            raise ValueError("替换后的内容不能为空")
        if self.replace is None and self.replacement is not None:
            raise ValueError("替换后的内容需要与要替换的内容一起使用")
        if self.remove is not None and (
            self.prefix
            or self.suffix
            or self.replace is not None
        ):
            raise ValueError("删除规则不能与其他重命名规则一起使用")
        if self.replace is not None and (self.prefix or self.suffix):
            raise ValueError("替换规则不能与前缀或后缀规则一起使用")

    def destination(self, source: Path, _index: int) -> Path:
        if self.remove is not None:
            stem = source.stem.replace(self.remove, "")
        elif self.replace is not None:
            stem = source.stem.replace(self.replace, self.replacement or "")
        else:
            stem = f"{self.prefix}{source.stem}{self.suffix}"
        return source.with_name(f"{stem}{source.suffix}")
