"""Bedrock embedding utilities, designed to be extractable to their own
package if they prove useful beyond this project.

Contract for anything added under this module:
  - No imports from dia.config, dia.pipeline.*, dia.document_types,
    dia.ledger, or any other dia-specific module.
  - Only third-party dependencies: llama_index, boto3/aioboto3. Not
    graphrag_toolkit - that pulls in a heavy, project-adjacent dependency
    tree (spacy, tiktoken, anthropic-bedrock, ...) that would undermine
    "generically reusable".
  - Public functions/classes take plain parameters (region, role_arn,
    bucket, model_id, ...), never dia's config objects (ExtractionConfig,
    ChunkingConfig) directly. dia.pipeline.chunking is the adapter layer
    that translates our config into these plain parameters.

See docs/adr/0001-lower-level-graphrag-toolkit-usage.md and issue #52 for
the background on why this module exists.
"""

from dia.embeddings.batch_semantic_splitter import batch_semantic_split
from dia.embeddings.bedrock_batch_client import (
    BatchEmbeddingJobError,
    BatchEmbeddingRequest,
    BatchEmbeddingResult,
    submit_and_await_batch_embeddings,
)
from dia.embeddings.pooled_bedrock import PooledBedrockEmbedding

__all__ = [
    "BatchEmbeddingJobError",
    "BatchEmbeddingRequest",
    "BatchEmbeddingResult",
    "PooledBedrockEmbedding",
    "batch_semantic_split",
    "submit_and_await_batch_embeddings",
]
