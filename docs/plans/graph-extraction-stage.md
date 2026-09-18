# Plan: Stage 2b — Graph Extraction

Not an ADR (no irreversible decision recorded here) and not a user guide
(nothing to run yet) — a working plan for the next PR, written down so the
reasoning from the chunking work (PR #53, ADR 0001) doesn't have to be
re-derived. Update this file as decisions change; it's expected to go
stale once the stage is built and superseded by real code + tests.

## Goal

Take chunks persisted by Stage 2a (`ChunkingRunner`/`ChunkStore`, #53) and
run them through Bedrock batch inference (propositions, then topics),
producing graph output and marking documents as done in the ledger.

## Why this design (see ADR 0001 for full detail)

Driving `graphrag_toolkit`'s batch extractor classes directly, not
`LexicalGraphIndex.extract()`/`ExtractionPipeline` — same principle as
chunking. The toolkit's monolithic path couples chunking parallelism to
batch job sizing, sizes jobs before chunk counts are known, has a broken
sub-100-record fallback (awslabs/graphrag-toolkit#534, fix pending in
#535), and has no fault isolation between stages.

## Decisions already made

1. **Job sizing decided after chunk count is known.** One dial —
   `ExtractionConfig.bedrock_max_batch_size` — with job *count* derived,
   not chosen directly. No benefit to multiple sub-max jobs: measured job
   wall-times (110/151/259 records) were all similar, so per-job queue
   overhead dominates regardless of size. For our real volumes (one
   source, tens-to-low-hundreds of docs) this normally means one job per
   stage (propositions, one; topics, one).

2. **The sub-100-chunk guard is ours, not the toolkit's.** If total
   chunks < `BEDROCK_MIN_BATCH_SIZE` (100), call `LLMPropositionExtractor`/
   `TopicExtractor` directly ourselves, with our LLM passed explicitly.
   This makes the upstream bug structurally unreachable — we never call
   the toolkit's own `_run_non_batch_extractor`. Deliberately **not**
   setting `EXTRACTION_MODEL` as a defensive env-var fallback: prefer a
   loud failure over a silent wrong-model substitution.

3. **Always pass `llm=` explicitly** to `BatchLLMPropositionExtractorSync`/
   `BatchTopicExtractorSync`. Needs `ExtractionConfig.to_llm()` — removed
   in the earlier config cleanup (unwired fields), to be re-added here
   alongside the code that actually consumes it. A reasonable starting
   point exists in the abandoned `graph-extraction-runner` branch (closed
   PR #44, commit `699bd5e`): `LLMCache`-wrapped `BedrockConverse` with
   `read_timeout`/`enable_cache`/`temperature`/`max_tokens` — worth reusing
   the shape, not the branch (it predates #47 and would revert the IAM
   fix if merged as-is).

4. **No `IdRewriter`, no toolkit orchestration** — same as chunking. We
   own: loading chunks, sizing the job, grouping chunks back into
   `SourceDocument`s, writing output, marking the ledger.

5. **Group chunks back into `SourceDocument`s via `metadata['key']`**, not
   by walking the `SOURCE` relationship chain. Both are technically
   correct (verified during the chunking work: the relationship resolves
   properly through multi-stage chunking) but `metadata['key']` is
   simpler and matches what `ChunkingRunner._group_by_document` already
   does. ~15 lines; no need for the toolkit's private
   `_source_documents_from_base_nodes`.

6. **Ledger stage = `"graph"`**, mirroring `STAGE = "text"` in
   `text_extraction.py`. Per-document: `ledger.get_unprocessed(refs,
   source_name, "graph")` to find pending work,
   `ledger.mark_processed_many(...)` on success. This is the check that
   actually answers "is this document in the graph" — the real
   requirement from earlier in this project ("if files get added/modified
   I want to get them into the graph").

7. **Chunks are not deleted after successful extraction.** Reversed from
   an earlier draft (`keep_chunks: bool = False`, delete-on-success) once
   chunks became durable/S3-backed rather than transient scratch.
   Superseded chunks (old fingerprint, old version) are left to
   accumulate for now — explicit call, revisit if storage becomes a
   real concern.

## Open questions — not yet decided

1. **Recover command design.** Deferred earlier pending more context.
   Needs persisted job state (ARNs, S3 input/output locations, which
   documents/chunks each job covers) so a crash after submission doesn't
   strand a paid-for, in-flight or completed job.
2. **Where job state lives.** A new small store shaped like `ChunkStore`,
   or metadata folded into the ledger? Not decided.
3. **CLI wiring** (`dia extract-graph`) — not designed.
4. **A document is ledger-pending for `"graph"` but has no chunks yet**
   (chunking hasn't run). Should the extraction runner trigger chunking
   itself, or assume it already ran and fail/skip? Leaning towards the
   latter — keep the stages independently runnable, let CLI wiring decide
   whether to auto-chain them later.
5. **`graph_output_handler`** — reuse the toolkit's `FileBasedDocs`
   (as the abandoned branch did), or write our own? Probably fine to
   reuse; not yet confirmed against the current design.
6. **Default for `bedrock_max_batch_size`.** The toolkit's own default was
   25000 (used on the abandoned branch) — worth a sanity check, not yet
   revisited under this design.

## Rough shape (not yet written)

- `src/dia/config.py` — add `ExtractionConfig.to_llm()`,
  `bedrock_max_batch_size`
- `src/dia/pipeline/graph_extraction.py` (new — the abandoned branch had a
  file of this name; this is a fresh implementation, not a revival)
- A result dataclass mirroring `TextExtractionResult`/`ChunkingResult`'s
  shape (`total`/`processed`/`skipped`/`duration_seconds`, plus whatever
  failure fields turn out to be needed)
- `tests/test_graph_extraction.py` (new)

## Related

- ADR 0001 (`docs/adr/0001-lower-level-graphrag-toolkit-usage.md`)
- PR #53 (chunking stage — this depends on it existing)
- awslabs/graphrag-toolkit#534 / #535 (upstream bug this design avoids)
- #52 (batched semantic splitter — a chunking concern, not extraction;
  unrelated to this stage)
