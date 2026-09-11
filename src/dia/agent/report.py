"""Convert the agent's markdown response to a .docx and upload it to S3."""

import re
from io import BytesIO

import boto3
from docx import Document
from docx.document import Document as DocumentObject
from docx.table import Table
from docx.text.paragraph import Paragraph

from dia.agent.models import AgentResponse

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_NUMBERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_BULLET_LIST_RE = re.compile(r"^\s*[-*]\s+(.*)$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(.+)\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_INLINE_SPLIT_RE = re.compile(r"(\*\*.+?\*\*|\*.+?\*|`.+?`)")


class ReportUploader:
    """Converts an agent's markdown response to .docx and uploads both to S3.

    Args:
        bucket: Target S3 bucket name.
        s3_client: Optional injected S3 client (for testing).
    """

    def __init__(self, bucket: str, s3_client=None) -> None:
        self._bucket = bucket
        self._s3 = s3_client or boto3.client("s3")

    def upload(self, response: AgentResponse, *, url_expiry_seconds: int = 86_400) -> dict[str, str]:
        """Upload markdown and docx renderings of `response` to S3.

        Args:
            response: The agent's completed query response.
            url_expiry_seconds: How long the presigned download URLs stay valid.
                Defaults to 24 hours. May be capped shorter by the caller's own
                AWS session, if using temporary/assumed-role credentials.

        Returns:
            {
                "markdown_uri": "s3://...", "docx_uri": "s3://...",
                "markdown_download_url": "https://...",
                "docx_download_url": "https://...",
            }
        """
        md_key = self._build_key(response, "md")
        self._s3.put_object(
            Bucket=self._bucket,
            Key=md_key,
            Body=response.output.encode(),
            ContentType="text/markdown",
        )

        docx_key = self._build_key(response, "docx")
        self._s3.put_object(
            Bucket=self._bucket,
            Key=docx_key,
            Body=self._to_docx(response.output),
            ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )

        return {
            "markdown_uri": f"s3://{self._bucket}/{md_key}",
            "docx_uri": f"s3://{self._bucket}/{docx_key}",
            "markdown_download_url": self._presign(md_key, url_expiry_seconds),
            "docx_download_url": self._presign(docx_key, url_expiry_seconds),
        }

    def _presign(self, key: str, expiry_seconds: int) -> str:
        return self._s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expiry_seconds,
        )

    @staticmethod
    def _slugify(department: str | None) -> str:
        """e.g. 'Home Office' -> 'home-office'; None/'' -> 'cross-government'."""
        if not department:
            return "cross-government"
        slug = re.sub(r"[^a-z0-9]+", "-", department.lower()).strip("-")
        return slug or "cross-government"

    @classmethod
    def _build_key(cls, response: AgentResponse, extension: str) -> str:
        dept_slug = cls._slugify(response.department)
        short_id = response.id[:8]
        return f"{dept_slug}/{response.run_date.isoformat()}_{short_id}.{extension}"

    @classmethod
    def _to_docx(cls, markdown: str) -> bytes:
        """Render markdown into a .docx using built-in Word styles only.

        Supports headings (#-######), bullet/numbered lists, GFM pipe tables
        (header row + separator row), and inline **bold**/*italic*/`code` spans.
        No colors, emoji, or custom styling — a plain, professional document.
        """
        document = Document()
        lines = markdown.splitlines()

        i = 0
        while i < len(lines):
            line = lines[i]

            if not line.strip():
                i += 1
                continue

            if cls._is_table_start(lines, i):
                table_lines, i = cls._consume_table(lines, i)
                cls._render_table(document, table_lines)
                continue

            heading_match = _HEADING_RE.match(line)
            if heading_match:
                level = min(len(heading_match.group(1)), 9)
                paragraph = document.add_heading(level=level)
                cls._add_inline_runs(paragraph, heading_match.group(2).strip())
                i += 1
                continue

            bullet_match = _BULLET_LIST_RE.match(line)
            if bullet_match:
                paragraph = document.add_paragraph(style="List Bullet")
                cls._add_inline_runs(paragraph, bullet_match.group(1).strip())
                i += 1
                continue

            numbered_match = _NUMBERED_LIST_RE.match(line)
            if numbered_match:
                paragraph = document.add_paragraph(style="List Number")
                cls._add_inline_runs(paragraph, numbered_match.group(1).strip())
                i += 1
                continue

            paragraph = document.add_paragraph()
            cls._add_inline_runs(paragraph, line.strip())
            i += 1

        buffer = BytesIO()
        document.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _is_table_start(lines: list[str], index: int) -> bool:
        """A table starts when a '| ... |' row is immediately followed by a separator row."""
        if index + 1 >= len(lines):
            return False
        return bool(_TABLE_ROW_RE.match(lines[index]) and _TABLE_SEPARATOR_RE.match(lines[index + 1]))

    @staticmethod
    def _consume_table(lines: list[str], index: int) -> tuple[list[str], int]:
        """Collect consecutive '| ... |' rows starting at index (skipping the separator row)."""
        table_lines = [lines[index]]
        i = index + 2  # skip the header row (kept) and the separator row (discarded)
        while i < len(lines) and _TABLE_ROW_RE.match(lines[i]):
            table_lines.append(lines[i])
            i += 1
        return table_lines, i

    @classmethod
    def _render_table(cls, document: DocumentObject, table_lines: list[str]) -> None:
        rows = [[cell.strip() for cell in row.strip().strip("|").split("|")] for row in table_lines]
        num_cols = max(len(row) for row in rows)

        table: Table = document.add_table(rows=0, cols=num_cols)
        table.style = "Table Grid"

        for row_index, row_cells in enumerate(rows):
            row = table.add_row()
            for col_index in range(num_cols):
                cell_text = row_cells[col_index] if col_index < len(row_cells) else ""
                paragraph = row.cells[col_index].paragraphs[0]
                cls._add_inline_runs(paragraph, cell_text, bold=(row_index == 0))

    @staticmethod
    def _add_inline_runs(paragraph: Paragraph, text: str, *, bold: bool = False) -> None:
        """Split text on **bold**/*italic*/`code` markers and add formatted runs."""
        for chunk in _INLINE_SPLIT_RE.split(text):
            if not chunk:
                continue
            if chunk.startswith("**") and chunk.endswith("**"):
                run = paragraph.add_run(chunk[2:-2])
                run.bold = True
            elif chunk.startswith("`") and chunk.endswith("`"):
                run = paragraph.add_run(chunk[1:-1])
                run.font.name = "Consolas"
            elif chunk.startswith("*") and chunk.endswith("*"):
                run = paragraph.add_run(chunk[1:-1])
                run.italic = True
            else:
                run = paragraph.add_run(chunk)

            if bold:
                run.bold = True

        if not paragraph.runs:
            paragraph.add_run("")
            if bold:
                paragraph.runs[0].bold = True
