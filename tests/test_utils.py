import unittest

from pathcraft.utils import (
    filename_validation_error,
    truncate_windows_filename,
    validate_filename_text,
    windows_filename_length,
)


class WindowsFilenameTests(unittest.TestCase):
    def test_windows_invalid_characters_are_rejected(self) -> None:
        self.assertEqual(validate_filename_text("a:b?c"), [":", "?"])

    def test_windows_control_characters_are_rejected(self) -> None:
        self.assertIn("\n", validate_filename_text("bad\nname.txt"))
        self.assertIsNotNone(filename_validation_error("bad\tname.txt"))

    def test_windows_reserved_trailing_and_long_names_are_rejected(self) -> None:
        self.assertIsNotNone(filename_validation_error("CON.txt"))
        self.assertIsNotNone(filename_validation_error("photo.jpg "))
        self.assertIsNotNone(filename_validation_error("a" * 256))
        self.assertIsNotNone(filename_validation_error("😀" * 128))
        self.assertIsNone(filename_validation_error("photo.jpg"))

    def test_windows_length_helpers_preserve_unicode_characters(self) -> None:
        self.assertEqual(windows_filename_length("A😀中"), 4)
        self.assertEqual(truncate_windows_filename("A😀中", 3), "A😀")


if __name__ == "__main__":
    unittest.main()
