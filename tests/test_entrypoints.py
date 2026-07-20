import subprocess
import sys
import unittest


class EntrypointTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
