import unittest

from pathcraft import pdf, pdf_convert
from pathcraft.exceptions import (
    EncryptedPdfError,
    PdfDependencyError,
    PdfRenderError,
)


class PdfCompatibilityTests(unittest.TestCase):
    def test_shared_dependency_error_is_reexported(self) -> None:
        self.assertIs(pdf.PdfDependencyError, PdfDependencyError)

    def test_domain_errors_are_reexported(self) -> None:
        self.assertIs(pdf.EncryptedPdfError, EncryptedPdfError)
        self.assertIs(pdf.PdfRenderError, PdfRenderError)

    def test_legacy_module_reexports_pdf_public_api(self) -> None:
        for name in pdf.__all__:
            self.assertIs(getattr(pdf_convert, name), getattr(pdf, name))


if __name__ == "__main__":
    unittest.main()
