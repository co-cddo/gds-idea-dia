"""Graph extraction runner — Stage 2 of the extraction pipeline.

Reads Stage 1's output, converts it into LlamaIndex Documents, runs it
through graphrag_toolkit's LexicalGraphIndex.extract() using a domain-tuned
prompt, and writes raw chunk-level output. Stops there — no Neptune/AOSS
load, that's a separate, later stage.
"""

import shutil
from pathlib import Path

from llama_index.core.node_parser import NodeParser, SemanticSplitterNodeParser, SentenceSplitter

from dia.config import ChunkingConfig, ExtractionConfig

# Matches graphrag_toolkit.lexical_graph.indexing.build.checkpoint.SAVEPOINT_ROOT_DIR
_CHECKPOINT_SAVEPOINT_DIR = "save_points"


def _checkpoint_name(source_name: str) -> str:
    """Stable checkpoint name for a source.

    Stable (not timestamped) so a retry after a failure only redoes chunks
    the toolkit's own Checkpoint hasn't already marked complete, rather than
    the whole batch.
    """
    return f"dia-graph-extraction-{source_name}"


def clear_checkpoint_dir(source_name: str, output_dir: str | Path = "output") -> None:
    """Delete the checkpoint directory for a source.

    Used when force=True: reusing the same checkpoint name on a forced
    re-run would make the toolkit silently skip chunks it already
    completed, defeating the point of forcing a fresh run.
    """
    path = Path(output_dir) / _CHECKPOINT_SAVEPOINT_DIR / _checkpoint_name(source_name)
    shutil.rmtree(path, ignore_errors=True)


def _build_chunking_pipeline(chunking: ChunkingConfig, extraction_config: ExtractionConfig) -> list[NodeParser]:
    """ChunkingConfig -> the ordered NodeParsers LexicalGraphIndex chunks documents with."""
    parsers: list[NodeParser] = [
        SentenceSplitter(
            chunk_size=chunking.sentence_chunk_size,
            chunk_overlap=chunking.sentence_chunk_overlap,
        )
    ]
    if chunking.use_semantic_splitting:
        parsers.append(
            SemanticSplitterNodeParser(
                buffer_size=chunking.semantic_buffer_size,
                breakpoint_percentile_threshold=chunking.semantic_breakpoint_threshold,
                embed_model=extraction_config.to_embedding_model(),
            )
        )
    return parsers
