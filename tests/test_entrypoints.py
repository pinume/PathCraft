from importlib.metadata import entry_points
import subprocess
import sys
import unittest

from pathcraft.cli import main


class EntrypointTests(unittest.TestCase):
    def test_installed_console_command_forwards_to_cli(self) -> None:
        scripts = entry_points(group="console_scripts")
        entry = next(script for script in scripts if script.name == "pathcraft")

        self.assertEqual(entry.value, "pathcraft.cli:main")
        self.assertIs(entry.load(), main)

    def test_package_module_forwards_to_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pathcraft", "unexpected"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("不再支持命令行参数", result.stderr)
        self.assertIn("pathcraft", result.stderr)

    def test_legacy_main_module_still_forwards_to_cli(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "pathcraft.main", "unexpected"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("不再支持命令行参数", result.stderr)
        self.assertIn("pathcraft", result.stderr)


if __name__ == "__main__":
    unittest.main()
