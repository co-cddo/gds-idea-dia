"""Global extraction configuration and chunking strategies.

ExtractionConfig holds infrastructure/runtime settings (model, batch size, workers)
that don't vary per source or document type — they vary per deployment.

ChunkingConfig holds the text splitting strategy. Per-document-type chunking is
derived from DocumentType, not configured globally.
"""

from typing import Literal

from pydantic import BaseModel, Field

ApprovedModel = Literal[
    "eu.anthropic.claude-sonnet-4-6",
    "anthropic.claude-sonnet-4-5-20250929-v1:0",
]


class ChunkingConfig(BaseModel, frozen=True):
    """Chunking strategy for a document type.

    Determines how extracted text is split before graph extraction.
    Derived from DocumentType — long documents (business cases, SR bids)
    use full 2-stage splitting; short documents (contracts) use sentence
    splitting only.
    """

    sentence_chunk_size: int = Field(default=7900, gt=0)
    sentence_chunk_overlap: int = Field(default=100, ge=0)
    use_semantic_splitting: bool = True
    semantic_buffer_size: int = Field(default=3, gt=0)
    semantic_breakpoint_threshold: int = Field(default=97, gt=0, le=100)


class ExtractionConfig(BaseModel, frozen=True):
    """Global infrastructure settings for the extraction pipeline.

    These settings describe the runtime environment — which model to use,
    how many workers to run, batch sizes, etc. They don't vary per source
    or document type; they vary per deployment (e.g. cheaper model in dev).

    Per-document-type processing decisions (chunking strategy, entity
    classifications) are derived from DocumentType, not from this config.
    """

    extraction_model: ApprovedModel = "eu.anthropic.claude-sonnet-4-6"
    embeddings_model: str = "amazon.titan-embed-text-v2:0"
    region: str = "eu-west-2"
    extraction_batch_size: int = Field(default=20000, gt=0)
    # extraction_num_workers and extraction_num_threads_per_worker are not
    # currently wired to graphrag_toolkit. Both have no per-call override —
    # only global ones (GraphRAGConfig.extraction_num_workers /
    # extraction_num_threads_per_worker, or their EXTRACTION_NUM_WORKERS /
    # EXTRACTION_NUM_THREADS_PER_WORKER env vars), which we deliberately don't
    # mutate. Kept here (rather than removed) so they're easy to find if we
    # decide the global-state tradeoff is worth it later. The toolkit's own
    # defaults (2 and 4 respectively) are used instead.
    extraction_num_workers: int = Field(default=2, gt=0)
    extraction_num_threads_per_worker: int = Field(default=2, gt=0)
    max_tokens: int = Field(default=42768, gt=0)
    temperature: float | None = Field(default=0.0, ge=0.0, le=1.0)
    read_timeout: int = Field(default=600, gt=0)
    enable_cache: bool = True

    def to_llm(self):
        """Build the LLM graphrag_toolkit uses for extraction.

        Passed directly as ExtractionConfig(extraction_llm=...) — the toolkit
        returns an already-constructed LLM instance unchanged, so this is the
        only place our model/max_tokens/temperature settings need to apply.
        """
        from llama_index.llms.bedrock_converse import BedrockConverse

        return BedrockConverse(
            model=self.extraction_model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            region_name=self.region,
        )

    def to_embedding_model(self):
        """Build the embedding model used for semantic chunking."""
        from llama_index.embeddings.bedrock import BedrockEmbedding

        return BedrockEmbedding(
            model_name=self.embeddings_model,
            region_name=self.region,
        )


class TextExtractionConfig(BaseModel, frozen=True):
    """Configuration for Stage 1: text extraction from documents.

    Controls how documents are downloaded and extracted in batches.
    The pipeline checkpoints after each batch (writes to output + updates
    ledger), so if the process dies, at most one batch is lost.
    """

    batch_size: int = Field(default=100, gt=0)
    max_concurrency: int = Field(default=10, gt=0)
