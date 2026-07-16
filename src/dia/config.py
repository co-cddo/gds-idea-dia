"""Global extraction configuration and chunking strategies.

ExtractionConfig holds infrastructure/runtime settings (model, batch size, workers)
that don't vary per source or document type — they vary per deployment.

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

    extraction_model: str = "eu.anthropic.claude-sonnet-4-6"
    embeddings_model: str = "amazon.titan-embed-text-v2:0"
    region: str = "eu-west-2"
    extraction_batch_size: int = Field(default=20000, gt=0)
    extraction_num_workers: int = Field(default=1, gt=0)
    extraction_num_threads_per_worker: int = Field(default=2, gt=0)
    max_tokens: int = Field(default=42768, gt=0)
    temperature: float = Field(default=0.0, ge=0.0, le=1.0)
    read_timeout: int = Field(default=600, gt=0)
    enable_cache: bool = True
