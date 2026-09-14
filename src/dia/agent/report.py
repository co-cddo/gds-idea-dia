"""Convert the agent's markdown response to a .docx and upload it to S3."""

import re
from io import BytesIO

import boto3
import markdown as markdown_lib
from docx import Document
from html4docx import HtmlToDocx

from dia.agent.models import AgentResponse


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

    @staticmethod
    def _to_docx(markdown_text: str) -> bytes:
        """Render markdown into a .docx using built-in Word styles only.

        Converts markdown -> HTML (via the `markdown` library, with the GFM
        `tables` extension and `pymdownx.betterem` for correctly-nested
        emphasis, e.g. `*italic with **bold** inside*`) -> .docx (via
        `html4docx`, which walks the HTML into python-docx calls). Headings,
        bullet/numbered lists, tables, and inline **bold**/*italic*/`code`
        spans all map onto built-in Word styles. No colors, emoji, or custom
        styling — a plain, professional document.
        """
        html = markdown_lib.markdown(markdown_text, extensions=["tables", "pymdownx.betterem"])

        document = Document()
        parser = HtmlToDocx()
        parser.table_style = "Table Grid"
        parser.add_html_to_document(html, document)

        buffer = BytesIO()
        document.save(buffer)
        return buffer.getvalue()
