import unittest

from pathcraft.utils import filename_validation_error, validate_filename_text


class WindowsFilenameTests(unittest.TestCase):
    def test_windows_invalid_characters_are_rejected(self) -> None:
        self.assertEqual(validate_filename_text("a:b?c"), [":", "?"])

    def test_windows_reserved_trailing_and_long_names_are_rejected(self) -> None:
        self.assertIsNotNone(filename_validation_error("CON.txt"))
        self.assertIsNotNone(filename_validation_error("photo.jpg "))
        self.assertIsNotNone(filename_validation_error("a" * 256))
        self.assertIsNone(filename_validation_error("photo.jpg"))


if __name__ == "__main__":
    unittest.main()
