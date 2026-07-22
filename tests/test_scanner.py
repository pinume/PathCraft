import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pathcraft.scanner import find_files, find_images, is_hidden


class ScannerTests(unittest.TestCase):
    def test_dot_prefixed_paths_are_hidden(self) -> None:
        self.assertTrue(is_hidden(Path(".hidden")))

    def test_scanner_filters_images_and_honors_recursion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "one.JPG").touch()
            (root / "notes.txt").touch()
            nested = root / "nested"
            nested.mkdir()
            (nested / "two.heic").touch()

            self.assertEqual(find_images(root, recursive=False), [root / "one.JPG"])
            self.assertEqual(
                find_images(root, recursive=True),
                [nested / "two.heic", root / "one.JPG"],
            )

    def test_scanner_uses_natural_sorting(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ten = root / "photo10.jpg"
            two = root / "photo2.jpg"
            one = root / "photo1.jpg"
            for path in (ten, two, one):
                path.touch()

            self.assertEqual(find_images(root), [one, two, ten])

    def test_all_files_scanner_honors_recursion(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "one.jpg"
            text = root / "notes.txt"
            image.touch()
            text.touch()
            nested = root / "nested"
            nested.mkdir()
            data = nested / "data.csv"
            data.touch()
            self.assertEqual(
                find_files(root, recursive=False, all_files=True),
                [text, image],
            )
            self.assertEqual(
                find_files(root, recursive=True, all_files=True),
                [data, text, image],
            )

    def test_scanner_ignores_hidden_files_and_directories(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            visible = root / "visible.txt"
            visible.touch()
            (root / ".hidden.txt").touch()
            hidden_directory = root / ".hidden"
            hidden_directory.mkdir()
            (hidden_directory / "nested.txt").touch()

            self.assertEqual(
                find_files(root, recursive=True, all_files=True),
                [visible],
            )
            self.assertEqual(
                find_files(hidden_directory, recursive=True, all_files=True),
                [],
            )

    def test_recursive_walk_does_not_recheck_each_file_ancestor_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir()
            visible = nested / "visible.txt"
            visible.touch()

            with patch(
                "pathcraft.scanner.is_hidden_within",
                side_effect=AssertionError("recursive walk already filtered hidden paths"),
            ):
                files = find_files(root, recursive=True, all_files=True)

            self.assertEqual(files, [visible])


if __name__ == "__main__":
    unittest.main()
