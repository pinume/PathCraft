import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import DEFAULT_PDF_DPI
from .exceptions import (
    ExitProgram,
    PreviousStep,
    ReturnToMainMenu,
    UserCancelled,
)
from .rename import RenameEntry, build_plan, execute_plan
from .rules import RenameRule
from .prompts import (
    _ask,
    _ask_menu_choice,
    _ask_valid_text,
    _choose_directory,
    _choose_mapping_file,
    _existing_directory,
    _menu_frame,
)
from .scanner import find_files
from .utils import configure_console_encoding


@dataclass(frozen=True)
class InteractiveConfig:
    root: Path
    action: str
    rule: RenameRule | None = None
    menu_index: int = 0


MAIN_MENU_OPTIONS = [
    ("1", "PDF 转 PNG", "识别购买方并生成 PNG"),
    ("2", "添加前缀或后缀", "批量添加固定文字"),
    ("3", "删除指定内容", "批量清理文件名文字"),
    ("4", "替换指定内容", "批量替换文件名文字"),
    ("5", "映射表批量重命名", "使用 Excel、CSV 或 TXT"),
]
_LAST_OPERATION_WORKSPACE: list[str] = []


def _set_operation_workspace(lines: list[str]) -> None:
    _LAST_OPERATION_WORKSPACE.clear()
    _LAST_OPERATION_WORKSPACE.extend(lines)


class _TerminalProgressPanel:
    def __init__(self, selected: int) -> None:
        self._enabled = sys.stdout.isatty()
        self._selected = selected
        self._messages: list[str] = []
        self._drawn = False
        if self._enabled:
            self._render()

    def _render(self) -> None:
        terminal_size = shutil.get_terminal_size(fallback=(80, 24))
        width = max(1, terminal_size.columns - 1)
        height = max(2, terminal_size.lines)
        lines, selected_row = _menu_frame(
            MAIN_MENU_OPTIONS,
            selected=self._selected,
            width=width,
            height=height,
            content_lines=self._messages,
        )
        prefix = "\033[H" if self._drawn else "\033[?25l\033[2J\033[H"
        sys.stdout.write(prefix)
        for index, line in enumerate(lines):
            if index == selected_row:
                line = f"\033[1;36m{line}\033[0m"
            ending = "\n" if index < len(lines) - 1 else ""
            sys.stdout.write(f"\033[2K{line}{ending}")
        sys.stdout.flush()
        self._drawn = True

    def reporter(
        self,
        prefix: str,
        root: Path | None = None,
    ) -> Callable[[int, int, Path], None]:
        if not self._enabled:
            return _progress_printer(prefix, root)

        def report(index: int, total: int, detail: Path) -> None:
            width = len(str(total))
            line = f"{prefix} {index:>{width}}/{total}"
            if root is not None:
                line += f"：{_display_path(detail, root)}"
            self._messages.append(line)
            self._render()

        return report

    def show_result(self, lines: list[str]) -> None:
        self._messages = list(lines)
        if self._enabled:
            self._render()

    @property
    def enabled(self) -> bool:
        return self._enabled

    def finish(self) -> None:
        if self._enabled:
            sys.stdout.write("\033[?25h")
            sys.stdout.flush()


def _interactive_configuration(
    workspace_lines: list[str] | None = None,
) -> InteractiveConfig:
    mode = _ask_menu_choice(
        MAIN_MENU_OPTIONS,
        is_main_menu=True,
        content_lines=workspace_lines,
    )
    while True:
        try:
            root = _choose_directory()

            if mode == "1":
                return InteractiveConfig(
                    root=root,
                    action="pdf2png",
                    menu_index=0,
                )

            if mode == "2":
                position = _ask_menu_choice(
                    [
                        ("1", "添加到文件名称前面"),
                        ("2", "添加到文件名称后面"),
                    ]
                )
                text = _ask_valid_text("请输入要添加的内容：")
                rule = RenameRule(prefix=text) if position == "1" else RenameRule(suffix=text)
                action = "rename"
            elif mode == "3":
                text = _ask("请输入要删除的文字或字符：")
                rule = RenameRule(remove=text)
                action = "rename"
            elif mode == "4":
                old_text = _ask("请输入要替换的文字或字符：")
                new_text = _ask_valid_text("请输入替换后的内容：")
                rule = RenameRule(replace=old_text, replacement=new_text)
                action = "rename"
            else:
                rule = None
                action = "mapping"

            return InteractiveConfig(
                root=root,
                action=action,
                rule=rule,
                menu_index=int(mode) - 1,
            )
        except PreviousStep:
            continue
        except UserCancelled as error:
            raise ReturnToMainMenu from error


def _display_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _print_status_message(message: str, has_failures: bool = False) -> None:
    if sys.stdout.isatty():
        color = "\033[1;33m" if has_failures else "\033[1;32m"
        print(f"\n{color}{message}\033[0m")
    else:
        print(f"\n{message}")


def _find_scoped_files(config: InteractiveConfig) -> list[Path]:
    return find_files(config.root, recursive=True, all_files=True)


def _progress_printer(
    prefix: str,
    root: Path | None = None,
) -> Callable[[int, int, Path], None]:
    is_tty = sys.stdout.isatty()

    def report(index: int, total: int, detail: Path) -> None:
        width = len(str(total))
        line = f"{prefix} {index:>{width}}/{total}"
        if root is not None:
            line += f"：{_display_path(detail, root)}"
        if is_tty:
            sys.stdout.write(f"\r\033[2K{line}")
            sys.stdout.flush()
        else:
            print(line)

    return report


def _run_rename_plan(
    config: InteractiveConfig,
    plan: list[RenameEntry],
) -> int:
    root = config.root
    skipped_count = sum(entry.problem is not None for entry in plan)
    progress_panel = _TerminalProgressPanel(selected=config.menu_index)
    try:
        result = execute_plan(
            plan,
            on_progress=progress_panel.reporter("处理文件", root),
        )
    except Exception:
        progress_panel.finish()
        raise

    result_lines = [
        "处理结果",
        f"成功：{len(result.completed)} 个",
        f"跳过：{skipped_count} 个",
        f"失败：{len(result.failed)} 个",
    ]
    result_lines.extend(
        f"失败详情：{_display_path(entry.source, root)}：{error}"
        for entry, error in result.failed
    )
    _set_operation_workspace(result_lines)
    progress_panel.show_result(result_lines)
    progress_panel.finish()
    if not progress_panel.enabled:
        for entry, error in result.failed:
            print(
                f"失败：{entry.source.name} -> {entry.destination.name}：{error}",
                file=sys.stderr,
            )
        print(
            f"处理完成：成功 {len(result.completed)} 个，跳过 {skipped_count} 个，"
            f"失败 {len(result.failed)} 个。"
        )
    return 1 if result.failed else 0


def _run_pdf2png(config: InteractiveConfig) -> int:
    from .pdf import (
        PdfDependencyError,
        build_conversion_plans,
        execute_conversion_plans,
    )

    root = _existing_directory(config.root)

    try:
        pdf_files = [
            path
            for path in _find_scoped_files(config)
            if path.suffix.lower() == ".pdf"
        ]
        plans, planning_failures = build_conversion_plans(
            root,
            pymupdf_module=None,
            pdf_files=pdf_files,
        )
    except PdfDependencyError as error:
        _set_operation_workspace(["处理结果", f"PDF 转换失败：{error}"])
        print(error, file=sys.stderr)
        return 2

    if not plans and not planning_failures:
        _set_operation_workspace(["处理结果", f"没有在 {root} 中找到 PDF。"])
        print(f"没有在 {root} 中找到 PDF。")
        return 0
    for source, error in planning_failures:
        print(f"识别失败：{_display_path(source, root)}：{error}", file=sys.stderr)
    if not plans:
        result_lines = [
            "处理结果",
            "成功 PDF：0 个",
            "生成 PNG：0 张",
            f"失败：{len(planning_failures)} 个",
        ]
        _set_operation_workspace(result_lines)
        _print_status_message(
            f"处理完成：成功 0 个 PDF，生成 0 张 PNG，失败 {len(planning_failures)} 个。",
            has_failures=bool(planning_failures),
        )
        return 1 if planning_failures else 0

    progress_panel = _TerminalProgressPanel(selected=config.menu_index)
    try:
        result = execute_conversion_plans(
            plans,
            dpi=DEFAULT_PDF_DPI,
            on_progress=progress_panel.reporter("处理 PDF", root),
            on_page_progress=progress_panel.reporter("渲染页面", root),
        )
    except Exception:
        progress_panel.finish()
        raise
    failure_count = len(planning_failures) + len(result.failed)
    image_count = sum(len(plan.outputs) for plan in result.completed)
    result_lines = [
        "处理结果",
        f"成功 PDF：{len(result.completed)} 个",
        f"生成 PNG：{image_count} 张",
        f"失败：{failure_count} 个",
    ]
    result_lines.extend(
        f"失败详情：{_display_path(source, root)}：{error}"
        for source, error in [*planning_failures, *result.failed]
    )
    _set_operation_workspace(result_lines)
    progress_panel.show_result(result_lines)
    progress_panel.finish()
    if not progress_panel.enabled:
        for source, error in result.failed:
            print(
                f"转换失败：{_display_path(source, root)}：{error}",
                file=sys.stderr,
            )
        _print_status_message(
            f"处理完成：成功 {len(result.completed)} 个 PDF，"
            f"生成 {image_count} 张 PNG，失败 {failure_count} 个。",
            has_failures=bool(failure_count),
        )
    return 1 if failure_count else 0


def _run_rename(config: InteractiveConfig) -> int:
    root = config.root
    files = _find_scoped_files(config)
    if not files:
        result_lines = ["处理结果", f"没有在 {root} 中找到可处理的文件。"]
        _set_operation_workspace(result_lines)
        panel = _TerminalProgressPanel(selected=config.menu_index)
        panel.show_result(result_lines)
        panel.finish()
        if not panel.enabled:
            print(result_lines[-1])
        return 0

    assert config.rule is not None
    plan = build_plan(files, config.rule)
    return _run_rename_plan(config, plan)


def _choose_mapping_column(prompt: str, columns: tuple[str, ...]) -> str:
    print(prompt)
    options = [(str(index), column) for index, column in enumerate(columns, start=1)]
    selected = _ask_menu_choice(options)
    return columns[int(selected) - 1]


def _run_mapping_rename(config: InteractiveConfig) -> int:
    from .mapping_rename import build_mapping_plan, load_mapping_table

    root = config.root
    while True:
        mapping_file = _choose_mapping_file(root)
        table = load_mapping_table(mapping_file)
        print(f"检测到列标题：{'、'.join(table.columns)}")
        try:
            while True:
                source_column = _choose_mapping_column(
                    "请选择原名称所在列：",
                    table.columns,
                )
                destination_columns = tuple(
                    column for column in table.columns if column != source_column
                )
                try:
                    destination_column = _choose_mapping_column(
                        "请选择新名称所在列：",
                        destination_columns,
                    )
                    break
                except PreviousStep:
                    continue
            break
        except PreviousStep:
            continue

    mappings = table.mappings(source_column, destination_column)
    plan = build_mapping_plan(
        root,
        mappings,
        files=_find_scoped_files(config),
    )
    return _run_rename_plan(config, plan)


def _dispatch(config: InteractiveConfig) -> int:
    if config.action == "pdf2png":
        return _run_pdf2png(config)
    if config.action == "mapping":
        return _run_mapping_rename(config)

    assert config.rule is not None
    return _run_rename(config)


def _run_interactive() -> int:
    had_failure = False
    workspace_lines: list[str] = []
    while True:
        try:
            config = _interactive_configuration(workspace_lines)
        except ReturnToMainMenu:
            continue
        except PreviousStep:
            continue
        except ExitProgram:
            return 1 if had_failure else 0
        except UserCancelled:
            return 1 if had_failure else 0

        try:
            _set_operation_workspace([])
            exit_code = _dispatch(config)
        except (PreviousStep, ReturnToMainMenu, UserCancelled):
            continue
        except ExitProgram:
            return 1 if had_failure else 0
        workspace_lines = list(_LAST_OPERATION_WORKSPACE)
        had_failure = had_failure or exit_code != 0


def main(argv: list[str] | None = None) -> int:
    configure_console_encoding()
    arguments = list(sys.argv[1:] if argv is None else argv)
    try:
        if arguments:
            print("不再支持命令行参数，请直接运行：uv run main.py", file=sys.stderr)
            return 2
        return _run_interactive()
    except (UserCancelled, EOFError, KeyboardInterrupt):
        print("\n操作已取消。")
        return 130
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
