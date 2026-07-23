"""Tests for dia.metadata.filter — MetadataDepartmentFilter."""

from dia.metadata.filter import MetadataDepartmentFilter
from dia.metadata.models import DocumentMetadata
from dia.metadata.provider import MetadataProvider
from dia.types import DocumentReference


def _ref(key: str) -> DocumentReference:
    return DocumentReference(key=key, content_type="application/pdf", version="v1")


def test_filters_to_matching_department():
    lookup = {
        "files/a.pdf": DocumentMetadata(department="Home Office"),
        "files/b.pdf": DocumentMetadata(department="HMRC"),
    }
    provider = MetadataProvider(lookup)
    filter_ = MetadataDepartmentFilter(provider, ["Home Office"])

    refs = [_ref("files/a.pdf"), _ref("files/b.pdf")]
    result = filter_.filter(refs)

    assert [r.key for r in result] == ["files/a.pdf"]


def test_multiple_departments():
    lookup = {
        "a.pdf": DocumentMetadata(department="Home Office"),
        "b.pdf": DocumentMetadata(department="HMRC"),
        "c.pdf": DocumentMetadata(department="DWP"),
    }
    provider = MetadataProvider(lookup)
    filter_ = MetadataDepartmentFilter(provider, ["Home Office", "HMRC"])

    refs = [_ref("a.pdf"), _ref("b.pdf"), _ref("c.pdf")]
    result = filter_.filter(refs)

    assert {r.key for r in result} == {"a.pdf", "b.pdf"}


def test_no_metadata_for_key_excludes_it():
    """A document not in the metadata lookup at all is excluded."""
    provider = MetadataProvider({"a.pdf": DocumentMetadata(department="Home Office")})
    filter_ = MetadataDepartmentFilter(provider, ["Home Office"])

    refs = [_ref("a.pdf"), _ref("unknown.pdf")]
    result = filter_.filter(refs)

    assert [r.key for r in result] == ["a.pdf"]


def test_empty_departments_matches_nothing():
    provider = MetadataProvider({"a.pdf": DocumentMetadata(department="Home Office")})
    filter_ = MetadataDepartmentFilter(provider, [])

    result = filter_.filter([_ref("a.pdf")])

    assert result == []


def test_satisfies_document_filter_protocol():
    from dia.filters.protocol import DocumentFilter

    provider = MetadataProvider({})
    filter_: DocumentFilter = MetadataDepartmentFilter(provider, ["Home Office"])

    assert hasattr(filter_, "filter")
