"""Tests for dia.embeddings.pooled_bedrock — client reuse across calls."""

import asyncio
import json

import pytest

from dia.embeddings.pooled_bedrock import PooledBedrockEmbedding


class _FakeStreamingBody:
    """Mimics aiobotocore's StreamingBody - an async-readable response body."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    async def read(self) -> bytes:
        return self._data


class _FakeBedrockRuntimeClient:
    """Records invoke_model calls and returns a canned Titan-shaped response."""

    def __init__(self, embedding: list[float] | None = None) -> None:
        self.invoke_model_calls = 0
        self.last_call_kwargs: dict | None = None
        self._embedding = embedding or [0.1, 0.2, 0.3]

    async def invoke_model(self, **kwargs):
        self.invoke_model_calls += 1
        self.last_call_kwargs = kwargs
        body = json.dumps({"embedding": self._embedding}).encode()
        return {"body": _FakeStreamingBody(body)}


class _FakeClientContextManager:
    """Mimics what aioboto3's `session.client(...)` returns - an async
    context manager whose __aenter__ yields the actual client."""

    def __init__(self, client: _FakeBedrockRuntimeClient) -> None:
        self._client = client
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> _FakeBedrockRuntimeClient:
        self.entered += 1
        return self._client

    async def __aexit__(self, *exc_info) -> None:
        self.exited += 1


class _FakeSession:
    """Records how many times .client(...) is called - the exact thing
    PooledBedrockEmbedding exists to minimise (should be at most once, no
    matter how many embedding calls are made)."""

    def __init__(self) -> None:
        self.client_call_count = 0
        self.fake_client = _FakeBedrockRuntimeClient()
        self.context_managers: list[_FakeClientContextManager] = []

    def client(self, service_name: str, config=None) -> _FakeClientContextManager:
        self.client_call_count += 1
        cm = _FakeClientContextManager(self.fake_client)
        self.context_managers.append(cm)
        return cm


def _embedding_with_fake_session() -> tuple[PooledBedrockEmbedding, _FakeSession]:
    """A real PooledBedrockEmbedding, with its _asession swapped for a fake
    so no real AWS SDK code runs - only the client-reuse logic under test."""
    embed_model = PooledBedrockEmbedding(model_name="amazon.titan-embed-text-v2:0", region_name="eu-west-2")
    fake_session = _FakeSession()
    embed_model._asession = fake_session
    return embed_model, fake_session


@pytest.mark.asyncio
async def test_first_call_creates_one_client():
    embed_model, fake_session = _embedding_with_fake_session()

    await embed_model._aget_text_embedding("hello")

    assert fake_session.client_call_count == 1


@pytest.mark.asyncio
async def test_repeated_calls_reuse_the_same_client():
    embed_model, fake_session = _embedding_with_fake_session()

    await embed_model._aget_text_embedding("first")
    await embed_model._aget_text_embedding("second")
    await embed_model._aget_text_embedding("third")

    assert fake_session.client_call_count == 1
    assert fake_session.fake_client.invoke_model_calls == 3


@pytest.mark.asyncio
async def test_concurrent_calls_still_create_only_one_client():
    """The double-checked lock in _get_client() exists specifically for
    this: many calls racing to create the client for the first time must
    not each create their own."""
    embed_model, fake_session = _embedding_with_fake_session()

    await asyncio.gather(*[embed_model._aget_text_embedding(f"text-{i}") for i in range(20)])

    assert fake_session.client_call_count == 1
    assert fake_session.fake_client.invoke_model_calls == 20


@pytest.mark.asyncio
async def test_returns_parsed_embedding():
    embed_model, fake_session = _embedding_with_fake_session()
    fake_session.fake_client._embedding = [0.5, 0.25, 0.75]

    result = await embed_model._aget_text_embedding("some text")

    assert result == [0.5, 0.25, 0.75]


@pytest.mark.asyncio
async def test_invoke_model_called_with_model_name():
    embed_model, fake_session = _embedding_with_fake_session()

    await embed_model._aget_text_embedding("hello")

    assert fake_session.fake_client.last_call_kwargs["modelId"] == "amazon.titan-embed-text-v2:0"


@pytest.mark.asyncio
async def test_aclose_exits_the_context_manager():
    embed_model, fake_session = _embedding_with_fake_session()
    await embed_model._aget_text_embedding("hello")

    await embed_model.aclose()

    assert fake_session.context_managers[0].exited == 1
    assert embed_model._persistent_client is None
    assert embed_model._client_cm is None


@pytest.mark.asyncio
async def test_aclose_is_safe_if_never_used():
    embed_model, _ = _embedding_with_fake_session()

    await embed_model.aclose()  # must not raise


@pytest.mark.asyncio
async def test_aclose_then_reuse_creates_a_new_client():
    """Closing releases the connection; using the embedding model again
    afterwards should transparently create a fresh client rather than
    fail or reuse the closed one."""
    embed_model, fake_session = _embedding_with_fake_session()
    await embed_model._aget_text_embedding("first")
    await embed_model.aclose()

    await embed_model._aget_text_embedding("second")

    assert fake_session.client_call_count == 2


@pytest.mark.asyncio
async def test_used_as_async_context_manager_closes_on_exit():
    embed_model, fake_session = _embedding_with_fake_session()

    async with embed_model:
        await embed_model._aget_text_embedding("hello")

    assert fake_session.context_managers[0].exited == 1
    assert embed_model._persistent_client is None
