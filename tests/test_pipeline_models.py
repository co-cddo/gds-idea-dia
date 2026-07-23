"""Tests for dia.pipeline.models — TextExtractionOutput."""

from dataclasses import asdict

import pytest

from dia.pipeline.models import TextExtractionOutput


def test_creates_with_all_fields():
    output = TextExtractionOutput(
        key="docs/report.pdf",
        source_name="gats-business-cases",
        content_type="application/pdf",
        version="etag-abc123",
        text="extracted text",
        chars=14,
        metadata={"department": "Home Office"},
        extracted_at="2026-07-23T10:00:00+00:00",
        code_version="0.1.18",
    )

    assert output.key == "docs/report.pdf"
    assert output.chars == 14
    assert output.metadata == {"department": "Home Office"}


def test_is_frozen():
    output = TextExtractionOutput(
        key="a.pdf",
        source_name="source",
        content_type="application/pdf",
        version="v1",
        text="text",
        chars=4,
        metadata={},
        extracted_at="2026-07-23T10:00:00+00:00",
        code_version="0.1.18",
    )

    with pytest.raises(AttributeError):
        output.chars = 100


def test_asdict_produces_plain_dict():
    output = TextExtractionOutput(
        key="a.pdf",
        source_name="source",
        content_type="application/pdf",
        version="v1",
        text="text",
        chars=4,
        metadata={"department": "HMRC"},
        extracted_at="2026-07-23T10:00:00+00:00",
        code_version="0.1.18",
    )

    result = asdict(output)

    assert result == {
        "key": "a.pdf",
        "source_name": "source",
        "content_type": "application/pdf",
        "version": "v1",
        "text": "text",
        "chars": 4,
        "metadata": {"department": "HMRC"},
        "extracted_at": "2026-07-23T10:00:00+00:00",
        "code_version": "0.1.18",
    }


def test_empty_metadata_dict_allowed():
    output = TextExtractionOutput(
        key="a.pdf",
        source_name="source",
        content_type="application/pdf",
        version="v1",
        text="text",
        chars=4,
        metadata={},
        extracted_at="2026-07-23T10:00:00+00:00",
        code_version="0.1.18",
    )

    assert output.metadata == {}
