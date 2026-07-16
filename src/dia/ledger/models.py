"""Pydantic models for ledger records."""

from datetime import datetime

from pydantic import BaseModel


class LedgerRecord(BaseModel):
    """A record of a successfully processed document."""

    source_name: str
    processed_at: datetime
    code_version: str
    department: str | None = None
