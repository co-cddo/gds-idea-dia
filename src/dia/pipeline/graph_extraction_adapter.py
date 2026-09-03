"""Adapts Stage 1 output into LlamaIndex Documents for Stage 2 (graph extraction).

The GraphRAG Toolkit is built on LlamaIndex and requires
llama_index.core.schema.Document objects as extraction input. Stage 1's
TextExtractionOutput (see pipeline/models.py) is a plain, tool-agnostic JSON
schema with no LlamaIndex dependency — this module is the one place that
boundary gets crossed, so Stage 1 itself never needs to import llama_index.
"""

from llama_index.core.schema import Document

from dia.pipeline.models import TextExtractionOutput

# Pipeline bookkeeping — useful for our own traceability back to the source
# document, but not domain content. Excluded from the LLM prompt and
# embeddings so it doesn't add tokens/noise to extraction.
BOOKKEEPING_METADATA_KEYS = ["key", "source_name", "content_type", "version", "extracted_at", "code_version"]


def to_document(output: TextExtractionOutput) -> Document:
    """Build a Document from a Stage 1 TextExtractionOutput.

    `output.metadata` (department/alb/spend_id/etc, from Stage 1's
    MetadataProvider) is left visible to the LLM and embeddings — it's
    exactly the domain context graph extraction should see. Bookkeeping
    fields are attached to the Document (for traceability) but excluded
    from both via BOOKKEEPING_METADATA_KEYS.
    """
    metadata = {
        **output.metadata,
        "key": output.key,
        "source_name": output.source_name,
        "content_type": output.content_type,
        "version": output.version,
        "extracted_at": output.extracted_at,
        "code_version": output.code_version,
    }

    return Document(
        doc_id=output.key,
        text=output.text,
        metadata=metadata,
        excluded_llm_metadata_keys=list(BOOKKEEPING_METADATA_KEYS),
        excluded_embed_metadata_keys=list(BOOKKEEPING_METADATA_KEYS),
    )
