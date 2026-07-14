"""Pipeline configuration for DIA."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class PipelineConfig(BaseModel):
    """Pipeline configuration. Grows as features are added."""

    phase: Literal["dev"] = "dev"
    project: str = "dia"
    team: str = "gds-idea"
    region: str = "eu-west-2"
    aws_profile: str = "default"

    def bucket(self, purpose: str) -> str:
        """Generate a bucket name for this project/phase.

        Pattern: {team}-{project}-{purpose}-{phase}
        Example: gds-idea-dia-graph-raw-dev
        """
        return f"{self.team}-{self.project}-{purpose}-{self.phase}"
