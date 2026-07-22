import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class PortableBuildTests(unittest.TestCase):
    def test_build_script_creates_one_windowed_executable(self) -> None:
        script = (ROOT / "build.ps1").read_text(encoding="utf-8")

        self.assertIn("--onefile", script)
        self.assertIn("--windowed", script)
        self.assertIn("--name", script)
        self.assertIn("PathCraft", script)
        self.assertIn("packaging/pathcraft_portable.pyw", script.replace("\\", "/"))
        self.assertIn('"assets\\pathcraft.ico"', script)
        self.assertIn("--icon $icon", script)
        self.assertIn("--add-data $iconData", script)
        self.assertNotIn("--collect-all", script)
        for module in ("numpy", "pandas", "PIL", "lxml", "fontTools"):
            self.assertIn(f"--exclude-module {module}", script)

    def test_launcher_starts_windows_app_directly(self) -> None:
        launcher = (ROOT / "packaging" / "pathcraft_portable.pyw").read_text(encoding="utf-8")

        self.assertIn("from pathcraft.windows_app import main", launcher)
        self.assertNotIn("pathcraft.cli", launcher)

    def test_pyinstaller_is_an_isolated_build_dependency(self) -> None:
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[dependency-groups]", project)
        self.assertIn('pyinstaller>=6.21,<7', project.lower())
        self.assertNotIn("wcwidth", project.lower())

    def test_installer_is_not_part_of_portable_delivery(self) -> None:
        self.assertFalse((ROOT / "install.ps1").exists())

    def test_windows_icon_contains_an_icon_directory(self) -> None:
        icon = ROOT / "assets" / "pathcraft.ico"

        self.assertTrue(icon.is_file())
        self.assertEqual(icon.read_bytes()[:4], b"\x00\x00\x01\x00")


if __name__ == "__main__":
    unittest.main()
