import os
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from pathcraft.diagnostics import report_exception


class DiagnosticsTests(unittest.TestCase):
    def test_exception_details_are_hidden_by_default(self) -> None:
        output = StringIO()

        with patch.dict(os.environ, {}, clear=True), redirect_stderr(output):
            report_exception("PDF 规划失败", Path("invoice.pdf"), ValueError("boom"))

        self.assertEqual(output.getvalue(), "")

    def test_debug_mode_reports_context_and_traceback(self) -> None:
        output = StringIO()

        with (
            patch.dict(os.environ, {"PATHCRAFT_DEBUG": "1"}, clear=True),
            redirect_stderr(output),
        ):
            try:
                raise ValueError("boom")
            except ValueError as error:
                report_exception("PDF 规划失败", Path("invoice.pdf"), error)

        rendered = output.getvalue()
        self.assertIn("[PathCraft DEBUG] PDF 规划失败：invoice.pdf", rendered)
        self.assertIn("Traceback (most recent call last)", rendered)
        self.assertIn("ValueError: boom", rendered)


if __name__ == "__main__":
    unittest.main()
