"""Response model for a completed agent query."""

from datetime import date
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentInput(BaseModel, frozen=True):
    """The input of a single ask() call"""

    query: str
    department: str | None = None


class AgentResponse(BaseModel, frozen=True):
    """The result of a single ask() call"""

    id: str = Field(default_factory=lambda: str(uuid4()))
    run_date: date = Field(default_factory=date.today)
    department: str | None = None
    query: str
    output: str
