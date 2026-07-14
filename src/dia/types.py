"""Shared type definitions for DIA."""

from enum import StrEnum


class DocumentType(StrEnum):
    """Document types supported by the extraction pipeline."""

    BUSINESS_CASE = "business_case"
    SR_BIDS = "sr_bids"
    CONTRACT_FINDER = "contract_finder"
