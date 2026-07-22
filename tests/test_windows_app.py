import unittest
from pathlib import Path
from threading import get_ident
from unittest.mock import Mock, patch

from pathcraft.app_service import ExecutionSummary, PreparedOperation, PreviewEntry
from pathcraft.rules import RenameRule
from pathcraft.windows_app import (
    BackgroundTask,
    PathCraftApp,
    application_icon_path,
    build_rename_rule,
    ensure_windows,
)


class WindowsAppHelperTests(unittest.TestCase):
    def test_builds_each_supported_rename_rule(self) -> None:
        self.assertEqual(build_rename_rule("prefix", "new-"), RenameRule(prefix="new-"))
        self.assertEqual(build_rename_rule("suffix", "-done"), RenameRule(suffix="-done"))
        self.assertEqual(build_rename_rule("remove", "copy"), RenameRule(remove="copy"))
        self.assertEqual(
            build_rename_rule("replace", "old", "new"),
            RenameRule(replace="old", replacement="new"),
        )

    def test_rule_inputs_are_required(self) -> None:
        with self.assertRaisesRegex(ValueError, "不能为空"):
            build_rename_rule("prefix", "")
        with self.assertRaisesRegex(ValueError, "不能为空"):
            build_rename_rule("replace", "old", "")

    def test_only_windows_is_supported(self) -> None:
        ensure_windows("win32")
        with self.assertRaisesRegex(RuntimeError, "仅支持 Windows"):
            ensure_windows("linux")

    def test_app_module_does_not_import_cli(self) -> None:
        with patch.dict("sys.modules", {"pathcraft.cli": None}):
            __import__("pathcraft.windows_app")

    def test_application_icon_is_resolved_from_the_runtime_bundle(self) -> None:
        bundle = Path("runtime-bundle")

        self.assertEqual(
            application_icon_path(bundle),
            bundle / "assets" / "pathcraft.ico",
        )

    def test_background_task_runs_operation_off_the_calling_thread(self) -> None:
        calling_thread = get_ident()
        task = BackgroundTask(get_ident)

        task.start()
        task.wait(1)
        outcome = task.poll()

        self.assertIsNotNone(outcome)
        self.assertIsNone(outcome.error)
        self.assertNotEqual(outcome.value, calling_thread)

    def test_background_task_returns_worker_error(self) -> None:
        def fail() -> None:
            raise ValueError("boom")

        task = BackgroundTask(fail)

        task.start()
        task.wait(1)
        outcome = task.poll()

        self.assertIsNotNone(outcome)
        self.assertIsInstance(outcome.error, ValueError)

    def test_execute_starts_without_confirmation_dialog(self) -> None:
        app = PathCraftApp.__new__(PathCraftApp)
        source = Path("photo.jpg")
        app.prepared = PreparedOperation(
            kind="rename",
            root=Path.cwd(),
            preview_entries=(PreviewEntry(source, Path("new-photo.jpg"), "ready"),),
        )
        app._start_task = Mock()
        app._progress = Mock()
        app._execution_completed = Mock()

        with patch("pathcraft.windows_app.messagebox.askyesno") as confirmation:
            app._execute()

        confirmation.assert_not_called()
        app._start_task.assert_called_once()

    def test_execution_completion_clears_preview_and_starts_directory_refresh(self) -> None:
        app = PathCraftApp.__new__(PathCraftApp)
        app.preview_table = Mock()
        app.preview_table.get_children.return_value = ("old-row",)
        app.status = Mock()
        app._start_task = Mock()
        root = Path.cwd()

        with patch("pathcraft.windows_app.messagebox.showinfo") as result_dialog:
            app._execution_completed(ExecutionSummary(1, 0, 0), root)

        result_dialog.assert_not_called()
        app.preview_table.delete.assert_called_once_with("old-row")
        app._start_task.assert_called_once()


if __name__ == "__main__":
    unittest.main()
