"""BedrockEmbedding subclass that reuses one persistent async client.

llama_index's BedrockEmbedding._aget_embedding() creates a brand-new
aiobotocore client (and therefore a fresh TCP+TLS connection) on every
single call - see the class docstring below for the measured cost of
that. This subclass caches one client and reuses it across calls instead.

Deliberately has no dependency on anything in dia.* (no ExtractionConfig,
no pipeline code) - part of dia.embeddings, designed to be extractable to
its own package later if it proves useful beyond this project. Only
depends on llama_index and boto3/aioboto3.
"""

import asyncio
import json

from llama_index.core.bridge.pydantic import PrivateAttr
from llama_index.embeddings.bedrock import BedrockEmbedding
from llama_index.embeddings.bedrock.base import PROVIDER_SPECIFIC_IDENTIFIERS


class PooledBedrockEmbedding(BedrockEmbedding):
    """Reuses a single aiobotocore client (and its connection pool) across
    all async embedding calls, instead of creating and tearing down a
    fresh client per call.

    Why this matters: a direct A/B benchmark against real Bedrock measured
    213ms mean latency for "new client per call" (stock BedrockEmbedding)
    vs 99.5ms for "one client reused" - client *construction* itself is
    cheap (~0.7ms measured separately); the cost is the fresh TCP+TLS
    connection each new client's connection pool requires. Under real
    concurrent load (not just sequential calls) this measured out to a
    smaller but still real ~1.3-1.4x speedup end-to-end, with byte-identical
    output to stock BedrockEmbedding (verified: same chunk boundaries when
    used to drive SemanticSplitterNodeParser).

    Usage:
        embed_model = PooledBedrockEmbedding(model_name=..., region_name=...)
        try:
            ...  # use embed_model for any number of async embedding calls
        finally:
            await embed_model.aclose()

        # or as an async context manager:
        async with PooledBedrockEmbedding(model_name=..., region_name=...) as embed_model:
            ...
    """

    _persistent_client: object = PrivateAttr(default=None)
    _client_cm: object = PrivateAttr(default=None)
    _client_lock: object = PrivateAttr(default=None)

    def _lock(self) -> asyncio.Lock:
        if self._client_lock is None:
            self._client_lock = asyncio.Lock()
        return self._client_lock

    async def _get_client(self):
        """Lazily create the persistent client on first use, then reuse it.

        Double-checked locking: the lock only matters for the brief window
        where multiple concurrent calls race to create the client for the
        first time. Once created, every subsequent call takes the fast
        path (the `is None` check) without ever touching the lock.
        """
        if self._persistent_client is None:
            async with self._lock():
                if self._persistent_client is None:
                    self._client_cm = self._asession.client("bedrock-runtime", config=self._config)
                    self._persistent_client = await self._client_cm.__aenter__()
        return self._persistent_client

    async def aclose(self) -> None:
        """Release the persistent client's connection(s). Safe to call
        even if no client was ever created (e.g. no embedding calls made)."""
        if self._client_cm is not None:
            await self._client_cm.__aexit__(None, None, None)
            self._persistent_client = None
            self._client_cm = None

    async def __aenter__(self) -> "PooledBedrockEmbedding":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def _aget_embedding(self, payload, type):
        """Same logic as BedrockEmbedding._aget_embedding, except the
        client comes from _get_client() (reused) instead of a fresh
        `async with self._asession.client(...)` per call."""
        provider = self._get_provider()
        request_body = self._get_request_body(provider, payload, type)
        client = await self._get_client()
        response = await client.invoke_model(
            body=request_body,
            modelId=self.application_inference_profile_arn or self.model_name,
            accept="application/json",
            contentType="application/json",
        )
        streaming_body = await response.get("body").read()
        resp = json.loads(streaming_body.decode("utf-8"))
        identifiers = PROVIDER_SPECIFIC_IDENTIFIERS.get(provider)
        return identifiers["get_embeddings_func"](resp, isinstance(payload, list))
