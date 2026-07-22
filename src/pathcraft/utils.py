WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}


def invalid_filename_characters() -> set[str]:
    return set('<>:"/\\|?*\0')


def validate_filename_text(text: str) -> list[str]:
    invalid = invalid_filename_characters()
    return sorted({character for character in text if character in invalid})


def filename_validation_error(name: str) -> str | None:
    invalid = validate_filename_text(name)
    if invalid:
        return "文件名包含当前系统不允许的字符"
    if not name:
        return "文件名不能为空"
    if name.endswith((" ", ".")):
        return "Windows 文件名不能以空格或句点结尾"
    base_name = name.split(".", 1)[0].rstrip(" .").upper()
    if base_name in WINDOWS_RESERVED_NAMES:
        return "Windows 保留文件名"
    if len(name) > 255:
        return "文件名超过 255 个字符"
    return None
