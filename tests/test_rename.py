import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pathcraft.rename as rename_module
from pathcraft.rename import build_plan, execute_plan
from pathcraft.rules import RenameRule


class RenameTests(unittest.TestCase):
    def test_existing_destination_is_skipped(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "photo.jpg"
            source.touch()
            (root / "new-photo.jpg").touch()
            plan = build_plan([source], RenameRule(prefix="new-"))
            self.assertEqual(plan[0].problem, "目标文件已存在")

    def test_destination_occupied_by_moving_source_is_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.jpg"
            second = root / "new-a.jpg"
            first.touch()
            second.touch()

            plan = build_plan([first, second], RenameRule(prefix="new-"))
            self.assertFalse(any(entry.problem for entry in plan))
            result = execute_plan(plan)

            self.assertFalse(result.failed)
            self.assertTrue((root / "new-a.jpg").exists())
            self.assertTrue((root / "new-new-a.jpg").exists())
            self.assertFalse(first.exists())

    def test_blocked_destination_dependency_is_propagated(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.jpg"
            second = root / "new-a.jpg"
            occupied = root / "new-new-a.jpg"
            for path in (first, second, occupied):
                path.touch()

            plan = build_plan([first, second], RenameRule(prefix="new-"))

            self.assertTrue(all(entry.problem == "目标文件已存在" for entry in plan))

    def test_execute_rolls_back_when_commit_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.jpg"
            second = root / "b.jpg"
            first.touch()
            second.touch()
            plan = build_plan([first, second], RenameRule(prefix="new-"))
            original_move = rename_module._move_without_overwrite
            calls = 0

            def fail_second_commit(source: Path, destination: Path) -> None:
                nonlocal calls
                calls += 1
                if calls == 4:
                    raise OSError("simulated failure")
                original_move(source, destination)

            with patch.object(rename_module, "_move_without_overwrite", fail_second_commit):
                result = execute_plan(plan)

            self.assertTrue(result.failed)
            self.assertFalse(result.completed)
            self.assertTrue(first.exists())
            self.assertTrue(second.exists())
            self.assertFalse((root / "new-a.jpg").exists())
            self.assertFalse((root / "new-b.jpg").exists())

    def test_execute_plan_reports_progress_after_each_commit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "a.jpg"
            second = root / "b.jpg"
            first.touch()
            second.touch()
            plan = build_plan([first, second], RenameRule(prefix="new-"))
            progress = []

            result = execute_plan(
                plan,
                on_progress=lambda index, total, path: progress.append(
                    (index, total, path)
                ),
            )

            self.assertFalse(result.failed)
            self.assertEqual(
                progress,
                [(1, 2, root / "new-a.jpg"), (2, 2, root / "new-b.jpg")],
            )

    def test_remove_skips_unchanged_and_empty_names(self) -> None:
        plan = build_plan(
            [Path("photo.jpg"), Path("删除.jpg")],
            RenameRule(remove="删除"),
        )
        self.assertEqual(plan[0].problem, "名称未变化")
        self.assertEqual(plan[1].problem, "删除后文件名为空")

    def test_generated_filename_is_validated_for_current_platform(self) -> None:
        with patch("pathcraft.utils.platform.system", return_value="Windows"):
            plan = build_plan([Path("xCON.txt")], RenameRule(remove="x"))

        self.assertEqual(plan[0].problem, "Windows 保留文件名")


if __name__ == "__main__":
    unittest.main()
