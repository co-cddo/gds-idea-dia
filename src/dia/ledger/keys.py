"""Shared key-building logic for ledger implementations.

All ProcessingLedger implementations use the same composite key format:
stage#source_name#key#version. This is the single source of truth for
that format — implementations import from here rather than redefining it.
"""

from dia.types import DocumentReference


def composite_key(stage: str, source_name: str, ref: DocumentReference) -> str:
    """Build the composite ledger key: stage#source_name#key#version."""
    return f"{stage}#{source_name}#{ref.key}#{ref.version}"
