import unittest
from pathlib import Path
from unittest.mock import patch

from pathcraft.exceptions import UserCancelled
from pathcraft.utils import (
    UserCancelled as LegacyUserCancelled,
    configure_console_encoding,
    filename_validation_error,
    path_from_input,
    validate_filename_text,
)


class PlatformTests(unittest.TestCase):
    def test_console_streams_are_reconfigured_to_utf8(self) -> None:
        class Stream:
            def __init__(self) -> None:
                self.encoding = None

            def reconfigure(self, *, encoding: str) -> None:
                self.encoding = encoding

        stdout = Stream()
        stderr = Stream()
        with (
            patch("pathcraft.utils.sys.stdout", stdout),
            patch("pathcraft.utils.sys.stderr", stderr),
        ):
            configure_console_encoding()

        self.assertEqual(stdout.encoding, "utf-8")
        self.assertEqual(stderr.encoding, "utf-8")

    def test_legacy_user_cancelled_import_is_preserved(self) -> None:
        self.assertIs(LegacyUserCancelled, UserCancelled)

    def test_quoted_and_home_paths(self) -> None:
        self.assertEqual(path_from_input('"/tmp/My Photos"'), Path("/tmp/My Photos"))
        self.assertEqual(path_from_input("", Path("/work")), Path("/work"))

    def test_platform_specific_invalid_characters(self) -> None:
        self.assertEqual(validate_filename_text("a:b?c", "Windows"), [":", "?"])
        self.assertEqual(validate_filename_text("a:b/c", "Linux"), ["/"])

    def test_windows_reserved_and_trailing_names_are_rejected(self) -> None:
        self.assertIsNotNone(filename_validation_error("CON.txt", "Windows"))
        self.assertIsNotNone(filename_validation_error("photo.jpg ", "Windows"))
        self.assertIsNone(filename_validation_error("photo.jpg", "Windows"))


if __name__ == "__main__":
    unittest.main()
