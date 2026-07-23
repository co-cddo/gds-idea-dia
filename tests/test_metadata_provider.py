"""Tests for dia.metadata.provider — MetadataProvider lookup container."""

from dia.metadata.models import DocumentMetadata
from dia.metadata.provider import MetadataProvider


def test_get_metadata_returns_matching_entry():
    lookup = {"files/a.pdf": DocumentMetadata(department="Home Office")}
    provider = MetadataProvider(lookup)

    result = provider.get_metadata("files/a.pdf")

    assert result == DocumentMetadata(department="Home Office")


def test_get_metadata_returns_none_for_missing_key():
    provider = MetadataProvider({})

    result = provider.get_metadata("files/missing.pdf")

    assert result is None


def test_files_for_returns_matching_keys():
    lookup = {
        "files/a.pdf": DocumentMetadata(department="Home Office"),
        "files/b.pdf": DocumentMetadata(department="HMRC"),
        "files/c.pdf": DocumentMetadata(department="Home Office"),
    }
    provider = MetadataProvider(lookup)

    result = provider.files_for(["Home Office"])

    assert result == {"files/a.pdf", "files/c.pdf"}


def test_files_for_multiple_departments():
    lookup = {
        "a.pdf": DocumentMetadata(department="Home Office"),
        "b.pdf": DocumentMetadata(department="HMRC"),
        "c.pdf": DocumentMetadata(department="DWP"),
    }
    provider = MetadataProvider(lookup)

    result = provider.files_for(["Home Office", "HMRC"])

    assert result == {"a.pdf", "b.pdf"}


def test_files_for_no_match_returns_empty_set():
    lookup = {"a.pdf": DocumentMetadata(department="Home Office")}
    provider = MetadataProvider(lookup)

    result = provider.files_for(["Nonexistent Department"])

    assert result == set()


def test_files_for_ignores_entries_without_department():
    lookup = {
        "a.pdf": DocumentMetadata(department=None, spend_id="CS-100"),
        "b.pdf": DocumentMetadata(department="Home Office"),
    }
    provider = MetadataProvider(lookup)

    result = provider.files_for(["Home Office"])

    assert result == {"b.pdf"}


def test_departments_returns_unique_department_names():
    lookup = {
        "a.pdf": DocumentMetadata(department="Home Office"),
        "b.pdf": DocumentMetadata(department="HMRC"),
        "c.pdf": DocumentMetadata(department="Home Office"),
    }
    provider = MetadataProvider(lookup)

    result = provider.departments()

    assert result == {"Home Office", "HMRC"}


def test_departments_excludes_none():
    lookup = {
        "a.pdf": DocumentMetadata(department="Home Office"),
        "b.pdf": DocumentMetadata(department=None),
    }
    provider = MetadataProvider(lookup)

    result = provider.departments()

    assert result == {"Home Office"}


def test_empty_provider_has_no_departments():
    provider = MetadataProvider({})

    assert provider.departments() == set()


def test_len_returns_lookup_size():
    lookup = {
        "a.pdf": DocumentMetadata(department="Home Office"),
        "b.pdf": DocumentMetadata(department="HMRC"),
    }
    provider = MetadataProvider(lookup)

    assert len(provider) == 2
