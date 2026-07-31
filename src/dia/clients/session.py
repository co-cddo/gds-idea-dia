"""Shared boto3 Session factory for AWS-backed clients.

Provides a single cached Session (region sourced from Settings) so
that MCP tools and other AWS clients don't each construct their own.
"""

from functools import lru_cache

import boto3

from dia.agent.config import settings

@lru_cache(maxsize=1)
def get_session() -> boto3.Session:
    """Return the process-wide boto3 Session used by AWS clients.

    Cached via functools.cache so repeated calls reuse the same
    Session instance instead of re-authenticating each time.
    """
    return boto3.Session(region_name=settings.aws_region)