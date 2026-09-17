"""Neptune client for local tunnel-based access.

Wraps boto3's neptunedata client for use with an SSH-tunnelled connection
to Neptune (see scripts/neptune-tunnel.sh). Handles session creation with
an explicit AWS CLI profile and patches DNS resolution so that Neptune's
real hostname resolves to localhost (127.0.0.1) within this process —
required for TLS certificate validation and SigV4 request signing to work
correctly through the SSH tunnel, without needing /etc/hosts modifications
or admin/sudo privileges.
"""

from __future__ import annotations

import socket

import boto3
from botocore.config import Config

_real_getaddrinfo = socket.getaddrinfo
_patched_hosts: set[str] = set()


def _patched_getaddrinfo(host, *args, **kwargs):
    """Redirect specific hostnames to 127.0.0.1 for tunnel-based access."""
    if host in _patched_hosts:
        host = "127.0.0.1"
    return _real_getaddrinfo(host, *args, **kwargs)


# Apply the patch once at module import time
socket.getaddrinfo = _patched_getaddrinfo


def register_tunnel_host(host: str) -> None:
    """Redirect connections to `host` through the local SSH tunnel.
    Requires scripts/neptune-tunnel.sh to already be running.
    Args:
        host: Real hostname to redirect (e.g. a Neptune cluster endpoint).
    """
    _patched_hosts.add(host)


class LocalNeptuneClient:
    """Queries a Neptune cluster through a local SSH tunnel.

    Designed for developer use from notebooks and scripts — connects to
    Neptune via the SSH port-forward established by scripts/neptune-tunnel.sh
    (localhost:8182 → Neptune cluster endpoint:8182, via bastion + EICE).

    Automatically patches Python's DNS resolution so that the Neptune endpoint
    hostname resolves to 127.0.0.1 within this process. This allows boto3 to
    use Neptune's real hostname (required for TLS cert validation and SigV4
    signing) while actually connecting to the local tunnel. No /etc/hosts
    modification or sudo access needed.

    Args:
        endpoint: Neptune cluster endpoint hostname (without port or scheme).
        profile_name: AWS CLI profile to use for SigV4 auth. If None, uses
            the default credential chain (env vars, instance role, etc.).
        region: AWS region for the Neptune cluster.

    Example:
        >>> from dia.clients.neptune import LocalNeptuneClient
        >>> client = LocalNeptuneClient(
        ...     endpoint="dia-neptune-dev.cluster-xxx.eu-west-2.neptune.amazonaws.com",
        ...     profile_name="aws-prototype",
        ... )
        >>> client.query("MATCH (n) RETURN n LIMIT 5")
        []
    """

    def __init__(self, endpoint: str, profile_name: str | None = None, region: str = "eu-west-2") -> None:
        self._endpoint = endpoint

        # Register this endpoint for DNS redirection to localhost
        _patched_hosts.add(endpoint)

        session = boto3.Session(profile_name=profile_name, region_name=region)
        self._client = session.client(
            "neptunedata",
            endpoint_url=f"https://{endpoint}:8182",
            region_name=region,
            config=Config(retries={"total_max_attempts": 1}),
        )

    @property
    def endpoint(self) -> str:
        """The Neptune cluster endpoint hostname this client connects to."""
        return self._endpoint

    def query(self, cypher: str) -> list:
        """Execute an openCypher query and return the results.

        Args:
            cypher: An openCypher query string.

        Returns:
            A list of result records (dicts). Empty list if no results.

        Raises:
            botocore.exceptions.ClientError: If Neptune rejects the request
                (e.g. invalid query syntax, auth failure, connectivity issue).
        """
        response = self._client.execute_open_cypher_query(openCypherQuery=cypher)
        return response["results"]
