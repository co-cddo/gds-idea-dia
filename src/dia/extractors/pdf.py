"""PDF text extraction using pdfplumber."""

import logging
from io import BytesIO

import pdfplumber

logger = logging.getLogger(__name__)


class PdfExtractor:
    """Extracts text and tables from PDF documents."""

    def extract(self, content: bytes) -> str:
        """Extract text and tables from PDF bytes.

        Tables are formatted as markdown pipe tables. Text and tables
        are extracted per page and combined into a single string.
        """
        file_stream = BytesIO(content)
        content_parts: list[str] = []

        try:
            with pdfplumber.open(file_stream) as pdf:
                for page in pdf.pages:
                    page_tables = self._process_page_tables(page)
                    if page_tables:
                        content_parts.append(f"\n--- Page {page.page_number} Tables ---\n")
                        for table_text in page_tables:
                            content_parts.append(table_text)
                            content_parts.append("\n")

                    page_text = page.extract_text()
                    if page_text:
                        content_parts.append(page_text)

        except Exception:
            # The runner already logs a WARNING with the error message per
            # failed document — debug here to avoid a duplicate traceback
            # on the console. Full detail still lands in the log file.
            logger.debug("PDF extraction failed", exc_info=True)
            raise

        return "\n".join(content_parts).strip()

    def _process_page_tables(self, page) -> list[str]:
        """Extract and format all tables on a page."""
        tables = page.extract_tables()
        if not tables:
            return []
        return [self._format_table(table) for table in tables]

    def _format_table(self, table: list[list]) -> str:
        """Format a table matrix as a markdown pipe table."""
        rows = []
        for row in table:
            formatted = self._format_row(row)
            if formatted:
                rows.append(formatted)
        return "\n".join(rows)

    def _format_row(self, row: list) -> str:
        """Format a single row as a markdown pipe row."""
        cells = [str(cell).strip() if cell else "" for cell in row]
        if any(cells):
            return "| " + " | ".join(cells) + " |"
        return ""
