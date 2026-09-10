# ADR 0001: Drive graphrag_toolkit's lower-level components directly, not LexicalGraphIndex.extract()

## Context

`graphrag_toolkit`'s intended entry point, `LexicalGraphIndex.extract(docs, batch_config=...)`, runs chunking (sentence + semantic splitting) and LLM extraction (propositions/topics) as one pipeline, spread across `num_workers` processes, with no persistence between the two.

Live testing surfaced real problems with this:

- **One knob controls two unrelated things.** `num_workers` sets both chunking/embedding parallelism and the number of Bedrock batch jobs. Raising it to speed up embeddings also fragments extraction into more, smaller jobs.
- **Jobs are sized before chunk counts are known.** A real run split 50 documents across 4 workers as 110/151/259/75 chunks. The 75-chunk worker landed under Bedrock's 100-record minimum.
- **The under-minimum fallback is broken.** It silently drops the configured LLM and defaults to a `us.*` model, invalid outside `us-*` regions. Reported and fixed upstream: awslabs/graphrag-toolkit#534, #535.
- **No fault isolation.** A single `asyncio.gather` with no per-document isolation. On 2026-09-09, six Bedrock batch jobs completed successfully and the run still returned `processed=0, failed=50` after 34 minutes, because one unrelated failure aborted everything.
- **No persistence between stages.** Chunking is embedding-heavy (~25 min for 100 docs). Any downstream failure meant redoing it from scratch.

## Decision

Split into two independent stages, joined only by chunks persisted to storage (see `dia.pipeline.chunk_store`):

- **Chunking** (`ChunkingRunner`) — `SentenceSplitter` + `SemanticSplitterNodeParser` via plain `IngestionPipeline.arun()`, not the toolkit's `ExtractionPipeline`/`run_pipeline`. No `IdRewriter`: verified (against real Bedrock-produced chunks, and by tracing llama_index's own `NodeParser._postprocess_parsed_nodes`) that `node.relationships[SOURCE]` resolves correctly to the document key without it, since `to_document()` already sets `doc_id=output.key`. `IdRewriter` exists to give the toolkit's own `IdGenerator` deterministic content-hash IDs for incremental graph updates, which we don't use.
- **Extraction** (not yet built) — Bedrock batch extractors (`BatchLLMPropositionExtractorSync`, `BatchTopicExtractorSync`) driven directly, with `llm=` always passed explicitly so the broken fallback is unreachable, and jobs sized after chunk counts are known.

Chunks are stored durably (S3, per-document, scoped by `ChunkingConfig.to_fingerprint()`) rather than treated as transient — they're expensive to recompute and a config change should mean "chunk again", not "silently reuse stale chunks".

## Consequences

**Gained:** independent dials (chunking concurrency vs. batch job sizing), no under-minimum fallback bug, fault isolation between stages, chunks survive extraction failures, no more repeated-MFA-per-worker-process problem (async instead of multiprocessing).

**Cost:** we own orchestration the toolkit would otherwise provide — document grouping, `ChunkStore`, job sizing — and carry upgrade risk on the toolkit's private methods we still call directly (mitigated by verifying chunk output against real captured data, not just unit tests).

## Related

#47, #48, #49, #50, #51, #52; awslabs/graphrag-toolkit#534, #535; PR #53.
