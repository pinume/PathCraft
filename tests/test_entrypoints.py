from importlib.metadata import entry_points
import unittest

from pathcraft.desktop_bridge import main


class EntrypointTests(unittest.TestCase):
    def test_installed_application_uses_windows_gui_entry(self) -> None:
        gui_scripts = entry_points(group="gui_scripts")
        entry = next(script for script in gui_scripts if script.name == "pathcraft")

        self.assertEqual(entry.value, "pathcraft.desktop_bridge:main")
        self.assertIs(entry.load(), main)

    def test_no_pathcraft_console_entry_is_published(self) -> None:
        console_scripts = entry_points(group="console_scripts")

        self.assertFalse(any(script.name == "pathcraft" for script in console_scripts))


if __name__ == "__main__":
    unittest.main()
