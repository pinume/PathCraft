"""终端菜单、工作区和 Unicode 光标布局。"""

from __future__ import annotations

from wcwidth import wcwidth, wcswidth


MENU_LOGO = (
    r" ____       _   _      ____            __ _",
    r"|  _ \ __ _| |_| |__  / ___|_ __ __ _ / _| |_",
    r"| |_) / _` | __| '_ \| |   | '__/ _` | |_| __|",
    r"|  __/ (_| | |_| | | | |___| | | (_| |  _| |_",
    r"|_|   \__,_|\__|_| |_|\____|_|  \__,_|_|  \__|",
)
MenuOption = tuple[str, str] | tuple[str, str, str]


def menu_option_parts(option: MenuOption) -> tuple[str, str, str]:
    if len(option) == 2:
        value, label = option
        return value, label, ""
    return option


def terminal_text_width(text: str) -> int:
    """返回终端显示列宽，正确处理组合字符、零宽字符和 emoji。"""
    return max(0, wcswidth(text))


def character_width(character: str) -> int:
    return max(0, wcwidth(character))


def fit_terminal_text(text: str, width: int) -> str:
    fitted = []
    used = 0
    for character in text:
        current_width = character_width(character)
        if used + current_width > width:
            break
        fitted.append(character)
        used += current_width
    return f"{''.join(fitted)}{' ' * max(0, width - used)}"


def truncate_terminal_text(text: str, width: int) -> str:
    if terminal_text_width(text) <= width:
        return fit_terminal_text(text, width)
    if width <= 1:
        return "…"[:width]
    truncated = fit_terminal_text(text, width - 1).rstrip()
    return fit_terminal_text(f"{truncated}…", width)


def menu_frame(
    options: list[MenuOption],
    selected: int | None,
    width: int,
    height: int | None = None,
    content_lines: list[str] | None = None,
    hint: str | None = None,
) -> tuple[list[str], int]:
    unpacked = [menu_option_parts(option) for option in options]
    branded = any(description for _, _, description in unpacked)
    lines = (
        [
            *(truncate_terminal_text(line, width).rstrip() for line in MENU_LOGO),
            "",
        ]
        if branded
        else []
    )
    selected_row = len(lines) + selected if selected is not None else -1
    label_width = min(
        30,
        max((terminal_text_width(label) for _, label, _ in unpacked), default=0) + 4,
    )
    for index, (value, label, description) in enumerate(unpacked):
        marker = "➤" if index == selected else " "
        item = f"{marker} {value}. "
        if description:
            item += f"{fit_terminal_text(label, label_width)}{description}"
        else:
            item += label
        lines.append(truncate_terminal_text(item, width).rstrip())

    separator = "─" * width
    if hint is None:
        hint = (
            "↑↓ | Enter 确认 | Q/Esc 退出程序"
            if selected is not None
            else "输入编号 | Q 退出程序"
        )
    lines.append(separator)
    content = [truncate_terminal_text(line, width).rstrip() for line in content_lines or []]
    if height is not None:
        available = max(1, height)
        content_height = max(0, available - len(lines) - 2)
        if not content_height:
            lines = lines[: max(0, available - 2)]
            if selected_row >= len(lines):
                selected_row = -1
        else:
            content = content[-content_height:]
            lines.extend(content)
            lines.extend([""] * (content_height - len(content)))
        lines.append(separator)
    else:
        lines.extend(content or [""])
        lines.append(separator)
    lines.append(truncate_terminal_text(hint, width).rstrip())
    return lines, selected_row


def workspace_choice_frame(
    parent_options: list[MenuOption],
    parent_selected: int,
    options: list[MenuOption],
    selected: int,
    width: int,
    height: int,
    completed_lines: list[str] | None = None,
) -> tuple[list[str], int]:
    choice_lines = []
    for index, option in enumerate(options):
        value, label, description = menu_option_parts(option)
        marker = "➤" if index == selected else " "
        item = f"{marker} {value}. {label}"
        if description:
            item += f"  {description}"
        choice_lines.append(item)

    empty_lines, _ = menu_frame(
        parent_options,
        parent_selected,
        width,
        height=height,
        content_lines=[],
    )
    separator = "─" * width
    try:
        first_separator = empty_lines.index(separator)
        second_separator = empty_lines.index(separator, first_separator + 1)
    except ValueError:
        return empty_lines, -1

    content_height = second_separator - first_separator - 1
    if content_height < 1:
        return empty_lines, -1

    context = list(completed_lines or [])
    reserved_context = 1 if context and content_height > 1 else 0
    choice_count = min(len(choice_lines), content_height - reserved_context)
    choice_count = max(1, choice_count)
    choice_start = min(
        max(0, selected - choice_count // 2),
        max(0, len(choice_lines) - choice_count),
    )
    visible_choices = choice_lines[choice_start : choice_start + choice_count]
    context_height = max(0, content_height - len(visible_choices))
    visible_context = context[-context_height:] if context_height else []
    lines, _ = menu_frame(
        parent_options,
        parent_selected,
        width,
        height=height,
        content_lines=[*visible_context, *visible_choices],
    )
    selected_row = (
        first_separator
        + 1
        + len(visible_context)
        + selected
        - choice_start
    )
    return lines, selected_row


def wrapped_input_layout(
    value: str,
    width: int,
) -> tuple[list[str], list[tuple[int, int]]]:
    first_prefix = "➤ "
    continuation_prefix = "  "
    limit = max(terminal_text_width(first_prefix) + 1, width - 1)
    lines = [first_prefix]
    positions: list[tuple[int, int]] = []
    line_index = 0
    column = terminal_text_width(first_prefix)

    for character in value:
        current_width = character_width(character)
        if column + current_width > limit:
            lines.append(continuation_prefix)
            line_index += 1
            column = terminal_text_width(continuation_prefix)
        positions.append((line_index, column))
        lines[line_index] += character
        column += current_width
    positions.append((line_index, column))
    return lines, positions


def move_vertical_cursor(
    positions: list[tuple[int, int]],
    cursor: int,
    direction: int,
    preferred_column: int | None,
) -> tuple[int, int]:
    line, column = positions[cursor]
    target_line = line + direction
    desired_column = column if preferred_column is None else preferred_column
    candidates = [
        (index, position_column)
        for index, (position_line, position_column) in enumerate(positions)
        if position_line == target_line
    ]
    if not candidates:
        return cursor, desired_column
    target, _ = min(
        candidates,
        key=lambda item: (abs(item[1] - desired_column), item[0]),
    )
    return target, desired_column
