"""Global extraction configuration and chunking strategies.

ExtractionConfig holds infrastructure/runtime settings (embedding model,
region, embedding concurrency) that don't vary per source or document type
— they vary per deployment.

ChunkingConfig holds the text splitting strategy. Per-document-type chunking is
derived from DocumentType, not configured globally.
"""

from pydantic import BaseModel, Field


class ChunkingConfig(BaseModel, frozen=True):
    """Chunking strategy for a document type.

    Determines how extracted text is split before graph extraction.
    Derived from DocumentType — long documents (business cases, SR bids)
    use full 2-stage splitting; short documents (contracts) use sentence
    splitting only.

    sentence_chunk_size_tokens is measured in tokens (~4 chars/token), not
    characters. Default 7900 + 100 overlap = 8000, chosen to sit just under
    Titan Text Embeddings V2's 8,192-token input limit.

    With use_semantic_splitting=True, the semantic splitter has no size
    limit of its own (it cuts purely on topic-shift distance) - this
    setting is the only thing bounding how much text it ever sees in one
    go, i.e. a ceiling, not the actual chunk size. Real chunks end up much
    smaller (~800 tokens in practice).

    With use_semantic_splitting=False, there is no second stage, so this
    setting *is* the actual chunk size - see issue #51 for why that may be
    too large for CONTRACT_FINDER. See issue #50 for the broader chunking
    strategy this leaves open (no max chunk size, pre-split vs post-split,
    tiny/empty chunk waste).
    """

    sentence_chunk_size_tokens: int = Field(default=7900, gt=0)
    sentence_chunk_overlap_tokens: int = Field(default=100, ge=0)
    use_semantic_splitting: bool = True
    semantic_buffer_size: int = Field(default=3, gt=0)
    semantic_breakpoint_threshold: int = Field(default=97, gt=0, le=100)

    def to_fingerprint(self, embeddings_model: str) -> str:
        """Short hash of everything that affects chunk boundaries.

        Used as a key/prefix for persisted chunks (see ChunkStore) so a
        chunking config change invalidates cached chunks automatically -
        a different fingerprint means "no chunks found", not "stale chunks
        silently reused".

        Takes embeddings_model explicitly rather than reading it from
        ExtractionConfig: it isn't a field on this class, but it directly
        determines where the semantic splitter cuts, so it must be part of
        the fingerprint - this class's fields alone aren't sufficient to
        identify a chunk set.

        Known limitation: doesn't include the llama_index/toolkit version,
        so a library upgrade that changes splitter behaviour wouldn't
        invalidate existing chunks. Deliberate - including it would force a
        full re-chunk on every dependency bump.
        """
        import hashlib
        import json

        payload = {**self.model_dump(), "embeddings_model": embeddings_model}
        canonical = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(canonical.encode()).hexdigest()[:8]


class ExtractionConfig(BaseModel, frozen=True):
    """Global infrastructure settings for the chunking/extraction pipeline.

    These settings describe the runtime environment - which embedding model
    to use, how concurrent embedding calls are, etc. They don't vary per
    source or document type; they vary per deployment.

    Only chunking-related settings live here for now (embeddings_model,
    region, embed_concurrency). Extraction-stage settings (extraction_model,
    max_tokens, temperature, etc.) will be added alongside to_llm() when the
    extraction stage is built, rather than kept here unwired in the
    meantime - a previous version of this config had exactly that problem:
    fields that looked configurable but were never actually applied anywhere.

    Per-document-type processing decisions (chunking strategy, entity
    classifications) are derived from DocumentType, not from this config.
    """

    embeddings_model: str = "amazon.titan-embed-text-v2:0"
    region: str = "eu-west-2"
    # Bounds the asyncio.Semaphore BedrockEmbedding uses for concurrent
    # embedding calls (llama_index's BaseEmbedding.num_workers). Titan
    # doesn't support batched embedding requests (one text per API call
    # regardless), so embed_batch_size is fixed at 1 in to_embedding_model()
    # - this is the only concurrency dial, and in-flight requests are
    # exactly this number, not a multiple of it.
    #
    # ge=2, not ge=1: llama_index only engages the semaphore when
    # num_workers > 1 - at exactly 1 it falls through to a plain
    # asyncio.gather with NO concurrency limit at all, the opposite of what
    # this field says.
    embed_concurrency: int = Field(default=8, ge=2)

    def to_embedding_model(self):
        """Build the embedding model used for semantic chunking."""
        from llama_index.embeddings.bedrock import BedrockEmbedding

        return BedrockEmbedding(
            model_name=self.embeddings_model,
            region_name=self.region,
            num_workers=self.embed_concurrency,
            embed_batch_size=1,
        )


class TextExtractionConfig(BaseModel, frozen=True):
    """Configuration for Stage 1: text extraction from documents.

    Controls how documents are downloaded and extracted in batches.
    The pipeline checkpoints after each batch (writes to output + updates
    ledger), so if the process dies, at most one batch is lost.
    """

    batch_size: int = Field(default=100, gt=0)
    max_concurrency: int = Field(default=10, gt=0)
