"""Response model for a completed agent query."""

from datetime import date
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentResponse(BaseModel, frozen=True):
    """The result of a single ask() call — one department query, one answer."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    run_date: date = Field(default_factory=date.today)
    department: str
    query: str
    output: str
