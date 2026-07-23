import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock, Mock, patch

from pathcraft.app_service import ExecutionSummary, PreparedOperation, PreviewEntry
from pathcraft.desktop_bridge import Bridge, _bind_drop_events, _serialize_completion, _serialize_preview, main
from pathcraft.desktop_support import ui_asset_path
from pathcraft.undo import UndoOperation


class ImmediateThread:
    def __init__(self, *, target, daemon: bool) -> None:
        self.target = target
        self.daemon = daemon

    def start(self) -> None:
        self.target()


class DesktopBridgeTests(unittest.TestCase):
    def test_initialize_returns_json_serializable_desktop_state(self) -> None:
        result = Bridge().initialize()

        self.assertTrue(result["version"])
        self.assertEqual(result["root"], str(Path.cwd()))
        self.assertIn(
            {"value": "mapping", "label": "映射表重命名"},
            result["operations"],
        )
        json.dumps(result)

    def test_preview_uses_service_and_serializes_relative_paths(self) -> None:
        bridge = Bridge()
        root = Path.cwd()
        prepared = PreparedOperation(
            kind="rename",
            root=root,
            preview_entries=(
                PreviewEntry(root / "old.txt", root / "new.txt", "ready"),
                PreviewEntry(root / "blocked.txt", None, "blocked", "目标已存在"),
            ),
        )

        with patch("pathcraft.desktop_bridge.prepare_rule_rename", return_value=prepared) as prepare:
            result = bridge.preview(
                {"root": str(root), "operation": "prefix", "primary": "new-"}
            )

        prepare.assert_called_once()
        self.assertEqual(result["readyCount"], 1)
        self.assertEqual(result["blockedCount"], 1)
        self.assertEqual(result["rows"][0]["source"], "old.txt")
        self.assertEqual(result["rows"][0]["destination"], "new.txt")

    def test_failed_preview_discards_the_previous_plan(self) -> None:
        bridge = Bridge()
        bridge._prepared = Mock()

        with patch("pathcraft.desktop_bridge.prepare_rule_rename", side_effect=ValueError("bad")):
            with self.assertRaisesRegex(ValueError, "bad"):
                bridge.preview(
                    {"root": str(Path.cwd()), "operation": "prefix", "primary": "x"}
                )

        self.assertIsNone(bridge._prepared)
        self.assertFalse(bridge._busy)

    def test_mapping_dialog_returns_columns(self) -> None:
        bridge = Bridge()
        window = Mock()
        window.create_file_dialog.return_value = (str(Path.cwd() / "mapping.csv"),)
        bridge._attach_window(window)

        with patch("pathcraft.desktop_bridge.load_mapping_columns", return_value=("旧名", "新名")):
            result = bridge.choose_mapping(str(Path.cwd()))

        self.assertFalse(result["cancelled"])
        self.assertEqual(result["columns"], ["旧名", "新名"])

    def test_list_files_serializes_current_directory_rows(self) -> None:
        bridge = Bridge()
        root = Path.cwd().resolve()

        with patch(
            "pathcraft.desktop_bridge.list_current_files",
            return_value=(root / "one.txt", root / "nested" / "two.txt"),
        ):
            result = bridge.list_files(str(root))

        self.assertEqual(result["fileCount"], 2)
        self.assertEqual(result["rows"][0]["source"], "one.txt")
        self.assertEqual(result["rows"][1]["source"], str(Path("nested") / "two.txt"))
        self.assertTrue(all(row["status"] == "current" for row in result["rows"]))

    def test_drop_resolves_directories_and_file_parents(self) -> None:
        bridge = Bridge()
        root = Path.cwd().resolve()
        file = root / "README.md"

        self.assertEqual(
            bridge.resolve_drop(str(root)),
            {"path": str(root), "fromFile": False},
        )
        self.assertEqual(
            bridge.resolve_drop(str(file)),
            {"path": str(root), "fromFile": True},
        )

    def test_drop_event_uses_pywebview_full_path(self) -> None:
        bridge = Bridge()
        window = Mock()
        bridge._attach_window(window)
        bridge._on_drop({
            "dataTransfer": {
                "files": [{"pywebviewFullPath": str(Path.cwd())}],
            },
        })

        script = window.run_js.call_args.args[0]
        self.assertIn('"event":"directory-dropped"', script)

    def test_drop_is_ignored_while_a_task_is_busy(self) -> None:
        bridge = Bridge()
        window = Mock()
        bridge._attach_window(window)
        bridge._busy = True

        bridge._on_drop({"dataTransfer": {"files": []}})

        window.run_js.assert_not_called()

    def test_execute_runs_in_worker_and_pushes_refreshed_result(self) -> None:
        bridge = Bridge()
        window = Mock()
        bridge._attach_window(window)
        root = Path.cwd()
        bridge._prepared = PreparedOperation(
            kind="rename",
            root=root,
            preview_entries=(PreviewEntry(root / "old.txt", root / "new.txt", "ready"),),
        )
        undo = UndoOperation("rename", root)

        with (
            patch("pathcraft.desktop_bridge.Thread", ImmediateThread),
            patch(
                "pathcraft.desktop_bridge.execute_operation",
                return_value=ExecutionSummary(1, 0, 0, undo=undo),
            ),
            patch("pathcraft.desktop_bridge.list_current_files", return_value=(root / "new.txt",)),
        ):
            result = bridge.execute()

        self.assertEqual(result, {"started": True})
        self.assertIs(bridge._undo, undo)
        self.assertFalse(bridge._busy)
        script = window.run_js.call_args.args[0]
        self.assertIn('"event":"completed"', script)
        self.assertIn('"source":"new.txt"', script)

    def test_undo_requires_explicit_confirmation(self) -> None:
        bridge = Bridge()
        bridge._undo = UndoOperation("rename", Path.cwd())

        with self.assertRaisesRegex(ValueError, "再次点击撤销按钮"):
            bridge.undo()
        self.assertFalse(bridge._busy)

    def test_host_events_are_json_encoded(self) -> None:
        bridge = Bridge()
        window = Mock()
        bridge._attach_window(window)
        message = "quote ' and newline\n</script>"

        bridge._push_event("error", {"message": message})

        script = window.run_js.call_args.args[0]
        prefix = "window.pathcraftHostEvent("
        payload = json.loads(script[len(prefix):-2])
        self.assertEqual(payload["payload"]["message"], message)

    def test_progress_events_are_throttled_without_dropping_endpoints(self) -> None:
        bridge = Bridge()
        with (
            patch("pathcraft.desktop_bridge.monotonic", side_effect=(0.0, 0.01, 0.06, 0.061)),
            patch.object(bridge, "_push_event") as push,
        ):
            for index in range(1, 5):
                bridge._push_progress(index, 4, f"file-{index}.txt")

        self.assertEqual(
            [call.args[1]["index"] for call in push.call_args_list],
            [1, 3, 4],
        )

    def test_busy_task_blocks_window_close(self) -> None:
        bridge = Bridge()
        window = Mock()
        bridge._attach_window(window)
        bridge._busy = True

        self.assertFalse(bridge._on_closing())
        window.create_confirmation_dialog.assert_called_once()

    def test_custom_titlebar_controls_the_native_window(self) -> None:
        bridge = Bridge()
        window = Mock()
        bridge._attach_window(window)

        self.assertEqual(bridge.minimize_window(), {"minimized": True})
        self.assertEqual(bridge.toggle_maximize_window(), {"maximized": True})
        self.assertEqual(bridge.toggle_maximize_window(), {"maximized": False})
        self.assertEqual(bridge.close_window(), {"closed": True})

        window.minimize.assert_called_once_with()
        window.maximize.assert_called_once_with()
        window.restore.assert_called_once_with()
        window.destroy.assert_called_once_with()

    def test_main_creates_a_frameless_transparent_window(self) -> None:
        window = MagicMock()

        with (
            patch("pathcraft.desktop_bridge.ensure_windows"),
            patch("pathcraft.desktop_bridge.webview.create_window", return_value=window) as create,
            patch("pathcraft.desktop_bridge.webview.start") as start,
        ):
            self.assertEqual(main(), 0)

        options = create.call_args.kwargs
        self.assertTrue(options["frameless"])
        self.assertTrue(options["transparent"])
        self.assertFalse(options["easy_drag"])
        start.assert_called_once()
        self.assertIs(start.call_args.args[0], _bind_drop_events)
        self.assertEqual(start.call_args.args[1][0], window)

    def test_serializers_return_json_compatible_rows(self) -> None:
        root = Path.cwd()
        prepared = PreparedOperation(
            kind="pdf",
            root=root,
            preview_entries=(
                PreviewEntry(root / "invoice.pdf", (root / "one.png", root / "two.png"), "ready"),
            ),
        )
        preview = _serialize_preview(prepared)
        completion = _serialize_completion(
            ExecutionSummary(1, 0, 0, ("detail",)),
            root,
            (root / "one.png",),
            "执行完成",
        )

        self.assertEqual(preview["rows"][0]["destination"], "one.png，two.png")
        self.assertEqual(completion["rows"][0]["status"], "issue")
        json.dumps(preview)
        json.dumps(completion)

    def test_ui_assets_resolve_inside_runtime_bundle(self) -> None:
        asset = ui_asset_path("index.html")

        self.assertTrue(asset.is_file())

    def test_missing_ui_asset_has_an_explicit_error(self) -> None:
        with self.assertRaisesRegex(FileNotFoundError, "缺少界面资源 missing.html"):
            ui_asset_path("missing.html", Path.cwd())


if __name__ == "__main__":
    unittest.main()
