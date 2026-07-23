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

    def test_launcher_starts_pywebview_app_directly(self) -> None:
        launcher = (ROOT / "packaging" / "pathcraft_portable.pyw").read_text(encoding="utf-8")

        self.assertIn("from pathcraft.desktop_bridge import main", launcher)
        self.assertNotIn("pathcraft.cli", launcher)

    def test_pyinstaller_is_an_isolated_build_dependency(self) -> None:
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn("[dependency-groups]", project)
        self.assertIn('pyinstaller>=6.21,<7', project.lower())
        self.assertNotIn("wcwidth", project.lower())

    def test_pywebview_assets_and_dependency_are_packaged(self) -> None:
        script = (ROOT / "build.ps1").read_text(encoding="utf-8")
        project = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('"assets\\ui"', script)
        self.assertIn("--add-data $uiData", script)
        self.assertIn("--hidden-import webview", script)
        self.assertIn('"pywebview==6.2.1"', project.lower())

    def test_local_ui_has_no_network_font_dependency(self) -> None:
        ui = ROOT / "assets" / "ui"
        html = (ui / "index.html").read_text(encoding="utf-8")
        style = (ui / "style.css").read_text(encoding="utf-8")
        script = (ui / "app.js").read_text(encoding="utf-8")

        self.assertTrue((ui / "index.html").is_file())
        self.assertTrue((ui / "style.css").is_file())
        self.assertTrue((ui / "app.js").is_file())
        self.assertNotIn("fonts.googleapis.com", style)
        self.assertIn("[hidden] { display: none !important; }", style)
        self.assertIn("pywebview-drag-region", html)
        self.assertIn('id="minimizeWindow"', html)
        self.assertIn('id="maximizeWindow"', html)
        self.assertIn('id="closeWindow"', html)
        self.assertIn('id="progressTrack"', html)
        self.assertIn('id="undoLabel"', html)
        self.assertNotIn('id="emptyPreviewButton"', html)
        self.assertIn('id="resultSearch"', html)
        self.assertIn('id="statusFilter"', html)
        self.assertIn('id="dropOverlay"', html)
        self.assertIn("toggle_maximize_window", script)
        self.assertIn('primary || "final_"', script)
        self.assertIn("console.warn", script)
        self.assertIn('event.key === "Enter"', script)
        self.assertIn("appendDestinationDiff", script)
        self.assertIn("markProcessedThrough", script)
        self.assertIn("undoConfirmationArmed", script)
        self.assertIn("confirm-undo", style)
        self.assertIn('id="tableScroll"', html)
        self.assertIn("renderVirtualRows", script)
        self.assertIn("VIRTUAL_OVERSCAN", script)
        self.assertIn(".virtual-spacer", style)
        self.assertIn(".text-diff-add", style)
        self.assertIn("grid-template-columns: 232px minmax(0, 1fr)", style)
        self.assertIn('data-workflow="setup"', html)
        self.assertIn('id="operationMenu"', html)
        self.assertIn('class="action-bar"', html)
        self.assertIn("tbody tr:not(.virtual-spacer) { height: 37px; }", style)

    def test_installer_is_not_part_of_portable_delivery(self) -> None:
        self.assertFalse((ROOT / "install.ps1").exists())

    def test_windows_icon_contains_an_icon_directory(self) -> None:
        icon = ROOT / "assets" / "pathcraft.ico"

        self.assertTrue(icon.is_file())
        self.assertEqual(icon.read_bytes()[:4], b"\x00\x00\x01\x00")


if __name__ == "__main__":
    unittest.main()
