"""dia - Department Intelligence Agent."""

from importlib.metadata import version

from dia._tls import trust_corporate_proxy_ca

# On corporate-managed devices, HTTPS traffic to public internet endpoints
# (e.g. OpenSearch Serverless) is often intercepted by a TLS-inspecting
# proxy (e.g. Zscaler) whose root CA is trusted by the OS but not by the
# `certifi` bundle that most Python HTTP clients (boto3, opensearch-py,
# requests, ...) verify certificates against by default. This adds that CA
# to certifi's bundle so those connections validate correctly, without
# touching Python's global SSL validation mechanism (which would also
# affect connections that never go through the proxy, e.g. Neptune reached
# via an SSH tunnel — see git history for why `truststore` was tried and
# reverted).
trust_corporate_proxy_ca()

__version__ = version("dia")
