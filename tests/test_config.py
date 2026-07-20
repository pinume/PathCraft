import unittest

from pathcraft import config
from pathcraft import mapping_rename, scanner


class ConfigTests(unittest.TestCase):
    def test_extension_sets_are_immutable(self) -> None:
        self.assertIsInstance(config.IMAGE_EXTENSIONS, frozenset)
        self.assertIsInstance(config.MAPPING_EXTENSIONS, frozenset)

    def test_modules_share_central_extension_configuration(self) -> None:
        self.assertIs(scanner.IMAGE_EXTENSIONS, config.IMAGE_EXTENSIONS)
        self.assertIs(
            mapping_rename.SUPPORTED_MAPPING_EXTENSIONS,
            config.MAPPING_EXTENSIONS,
        )


if __name__ == "__main__":
    unittest.main()
