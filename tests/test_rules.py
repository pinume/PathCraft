import unittest
from pathlib import Path

from pathcraft.rules import RenameRule


class RuleTests(unittest.TestCase):
    def test_fixed_prefix_and_suffix_keep_original_stem(self) -> None:
        source = Path("photo.jpg")
        rule = RenameRule(prefix="new-", suffix="-2026")
        self.assertEqual(rule.destination(source, 0), Path("new-photo-2026.jpg"))

    def test_remove_text_and_characters_from_stem(self) -> None:
        source = Path("旅行-副本-副本.jpg")
        rule = RenameRule(remove="-副本")
        self.assertEqual(rule.destination(source, 0), Path("旅行.jpg"))

    def test_replace_text_in_stem_and_keep_extension(self) -> None:
        source = Path("旅行-旧名称-旧名称.jpg")
        rule = RenameRule(replace="旧名称", replacement="新名称")
        self.assertEqual(
            rule.destination(source, 0),
            Path("旅行-新名称-新名称.jpg"),
        )

    def test_mutually_exclusive_rules_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RenameRule(prefix="new-", remove="old-")
        with self.assertRaises(ValueError):
            RenameRule(prefix="new-", replace="old", replacement="new")
        with self.assertRaises(ValueError):
            RenameRule(replace="", replacement="new")
        with self.assertRaises(ValueError):
            RenameRule(replace="old", replacement="")


if __name__ == "__main__":
    unittest.main()
