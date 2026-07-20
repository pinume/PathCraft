import unittest

from pathcraft.exceptions import (
    BuyerNameRecognitionError,
    EncryptedPdfError,
    PathCraftError,
    PdfContentError,
    PdfError,
    PdfRenderError,
)


class ExceptionHierarchyTests(unittest.TestCase):
    def test_pdf_errors_share_application_base(self) -> None:
        self.assertTrue(issubclass(PdfError, PathCraftError))
        self.assertTrue(issubclass(PdfRenderError, PdfError))

    def test_content_errors_remain_value_errors(self) -> None:
        self.assertTrue(issubclass(PdfContentError, ValueError))
        self.assertTrue(issubclass(EncryptedPdfError, PdfContentError))
        self.assertTrue(issubclass(BuyerNameRecognitionError, PdfContentError))


if __name__ == "__main__":
    unittest.main()
