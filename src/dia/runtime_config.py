"""Runtime configuration for pipeline tasks and the CLI.

CDK writes one JSON parameter to SSM Parameter Store for each environment. It
holds what the runtime needs to know about the deployed infrastructure. A task
and a laptop both read it through `RuntimeConfig.load`, which validates it and
fails straight away with a clear message if it is missing or invalid.

The task definition sets one environment variable, `DIA_RUNTIME_CONFIG`, to the
parameter's name, so the dependency is visible on the task. When the variable is
not set (for example on a laptop) the name is built from `Names`.
"""

from __future__ import annotations

import json
import os

import boto3
from botocore.exceptions import ClientError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from dia.naming import REGION, Names

RUNTIME_CONFIG_ENV_VAR = "DIA_RUNTIME_CONFIG"
RUNTIME_CONFIG_RESOURCE = "runtime-config"


class RuntimeConfigError(Exception):
    """The runtime config could not be read or is not valid."""


class RuntimeConfig(BaseModel):
    """What the runtime needs to know about the deployed infrastructure.

    Every field is written by CDK. Unknown fields are rejected, so a field added
    to the stack but not to this model is caught straight away.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    neptune_endpoint: str = Field(description="Neptune cluster endpoint hostname, without scheme or port.")
    neptune_port: int = Field(default=8182, ge=1, le=65535, description="Neptune port.")
    cluster_name: str = Field(min_length=1, description="Name of the shared ECS cluster that tasks run on.")
    task_definition_arn: str = Field(min_length=1, description="ARN of the pipeline task definition.")
    subnet_ids: list[str] = Field(min_length=1, description="Private subnets that tasks run in.")
    security_group_id: str = Field(min_length=1, description="Security group attached to tasks.")
    log_group: str = Field(min_length=1, description="CloudWatch log group that tasks write to.")

    @field_validator("neptune_endpoint")
    @classmethod
    def _hostname_only(cls, value: str) -> str:
        if not value or "://" in value or "/" in value or ":" in value:
            raise ValueError("must be a hostname only: no scheme, port or path")
        return value

    @classmethod
    def parameter_name(cls, names: Names | None = None) -> str:
        """The SSM parameter to read: from `DIA_RUNTIME_CONFIG`, else built from `names`.

        Raises:
            RuntimeConfigError: If the variable is not set and no `names` is given.
        """
        from_env = os.environ.get(RUNTIME_CONFIG_ENV_VAR)
        if from_env:
            return from_env
        if names is None:
            raise RuntimeConfigError(
                f"{RUNTIME_CONFIG_ENV_VAR} is not set, and no environment was given to build the parameter name from"
            )
        return names(RUNTIME_CONFIG_RESOURCE)

    @classmethod
    def load(cls, names: Names | None = None, ssm_client=None) -> RuntimeConfig:
        """Read and validate the runtime config.

        Args:
            names: Used to build the parameter name when `DIA_RUNTIME_CONFIG` is not set.
            ssm_client: Optional injected SSM client (for testing).

        Raises:
            RuntimeConfigError: If the parameter is missing, unreadable, not JSON,
                or has missing or invalid fields.
        """
        name = cls.parameter_name(names)
        ssm = ssm_client or boto3.client("ssm", region_name=REGION)

        try:
            value = ssm.get_parameter(Name=name)["Parameter"]["Value"]
        except ClientError as e:
            raise RuntimeConfigError(f"Could not read the runtime config parameter {name!r}: {e}") from e

        try:
            return cls.model_validate(json.loads(value))
        except json.JSONDecodeError as e:
            raise RuntimeConfigError(f"The runtime config parameter {name!r} is not valid JSON: {e}") from e
        except ValidationError as e:
            problems = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors())
            raise RuntimeConfigError(f"The runtime config parameter {name!r} is not valid: {problems}") from e
