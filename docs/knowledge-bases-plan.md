# Plan: Bedrock Knowledge Bases in dia

Move the Bedrock Knowledge Base (KB) infrastructure from the old
assurance-knowledge-graphs repo into dia, as a reusable KB template plus a
file that declares which KBs to deploy.

## Goals

- One generic, reusable KB template (a CDK construct) with no dia-specific names.
- One declarations file listing the KBs. Adding a KB means adding one entry.
- KB IDs written into the `dia-kb-arns` secret automatically.
- Per-document metadata (`<file>.metadata.json` sidecars) so the agent can filter
  searches.
- Safe to open-source: no account IDs in code. Bucket owner accounts come from
  `DeploymentEnvironment`.

This is a separate track from the pipeline build plan
(`docs/design/pipeline-spec.md` section 7). It doesn't depend on that work.

## Naming

Every deployed name goes through `dia.naming.Names` (via `config.names` in CDK):

- **Buckets this repo creates** are added to the `Bucket` enum in
  `src/dia/naming.py`, then named with `config.names(Bucket.X)`. This plan adds:
  - `Bucket.DBR_REPORTS = "dbr-reports"` → `gds-idea-dia-dbr-reports-{phase}`
    (DBR source documents: `readouts/` and `reports/`)
- **The S3 Vectors bucket** is not in the `Bucket` enum, because preflight
  calls `head_bucket` on every `Bucket` and that only works for S3 buckets. It
  uses the resource pattern: `config.names("kb-vectors")` → `dia-kb-vectors-{phase}`.
- **KB names** use the resource pattern: `config.names("kb-sr25-bids")` →
  `dia-kb-sr25-bids-{phase}`. The template derives index and data source names
  from it.
- **Stack ID:** `config.names("knowledge-bases")`.
- **Source buckets owned by other projects** aren't created here, so they stay
  as literal names in the declarations file.

## Decisions

| Topic | Decision |
|---|---|
| Migration | Greenfield. dia creates new KBs with new names, re-ingests, then the old stacks are destroyed. |
| Template location | In this repo (`stacks/constructs/`). It may move to `gds-idea-cdk-constructs` once it has settled. |
| Stack layout | One KB stack: shared vector bucket plus one template instance per declaration. |
| Source buckets | KBs read the existing buckets directly, wherever they are. Sidecars sit next to each document. Moving the buckets we own into this repo is tracked separately in #64. |
| Cross-account | The KB role reads the bucket directly. The data source sets `bucketOwnerAccountId`, and the source bucket policy must allow the KB role. Bedrock can't assume a role for S3, so the pipeline's `assume_role_for_development_account` route doesn't apply to KBs. |
| Prod | Same source buckets in both phases. Each declaration states which environment owns its bucket (`DeploymentEnvironment.DEVELOPMENT` or `PRODUCTION`). It's cross-account whenever that isn't the deploying environment. The GATS bucket is in the prod account, so it's cross-account in dev and same-account in prod. |
| What deploys | Only the keys in `knowledge_bases.DEPLOYED`. This PR deploys the two DBR KBs. The other six are declared and tested but not deployed. |
| Secret wiring | Deferred. The `dia-kb-arns` secret's keys are fixed in `SecretsStack`, and the agent's KB IDs are set in it by hand. Changing its keys in CDK would overwrite those values. For now the KB stack outputs each KB ID. |
| Agent tools | Out of scope. Tools will come from AgentCore Gateway later. |

## Knowledge bases

| Key | Notes |
|---|---|
| `gats_business_cases` | Bucket in the prod account |
| `sr25_bids` | |
| `sr21_bids` | |
| `nao_reports` | FM parsing (Haiku) |
| `efficiency_reports` | FM parsing (Haiku). Key kept so the agent code doesn't change. |
| `other_reports` | Renamed from `tech_reports`. FM parsing (Haiku). |
| `dbr_readouts_letter` | New. Post-DBR letters, mainly text PDFs (default parsing). DBR bucket, `readouts/` prefix. |
| `dbr_reports` | New. Old DIA-generated DBR reports. DBR bucket, `reports/` prefix. |

## Metadata keys

All custom metadata keys are filterable (the S3 Vectors default). The template
marks only Bedrock's internal keys as non-filterable. Each KB declares its
`metadata_keys` so the future metadata writer can be checked against the same
declaration.

| KB | Keys |
|---|---|
| all | `department_name`, `alb`, `document_type`, `report_type`, `year` |
| `gats_business_cases` | + `spend_id`, `project_name`, `assurance_date`, `file_reference` |
| `sr25_bids` | + `spend_id`, `project_name`, `file_reference` |
| `sr21_bids` | + `project_name` |
| `dbr_readouts_letter` | + `readout_date`, `is_latest` |
| `dbr_reports` | + `report_date`, `is_latest` |

- The keys are what a document *may* carry. Not every file will have every key
  (for example, `alb` only applies when the submitter is an ALB).
- `year`, `readout_date` and `report_date` are numbers (`2026`, `20260901`,
  `202606`), so range filters work.
- `document_type` values match what the agent filters on: SR bids are
  `sr_bids_2025` and `sr_bids_2021`, following
  `src/dia/agent/mcp/retrieval_modes.py`.
- Metadata isn't embedded (simplified sidecar format). It's used for filtering only.
- S3 Vectors limit: 1 KB of custom metadata and 35 keys per vector.

### Existing sidecars

The source buckets already have `.metadata.json` files, generated by
`scripts/generate_kb_metadata.py` in the old repo. Its values will be changed
to match this plan, and the sidecars regenerated:

- `document_type`: `sr25_bid`/`sr21_bid` become `sr_bids_2025`/`sr_bids_2021`.
  `nao_report` and `technology_report` already match `DocumentType`.
- `department` is renamed to `department_name`, matching the graph agent's filters.
- `year` is written as a string. It must be a number.
- `year` and `report_type` are only written where a source's metadata CSV has
  those columns. SR21 and GATS get neither.
- `assurance_date` isn't written.
- No sidecars exist yet for efficiency reports, DBR letters or DBR reports.
- Possible bug: the tech reports source reads `files/metadata/nao_reports_metadata.csv`.

The `document_type` values for every KB are the `DocumentType` values in
`src/dia/document_types.py` (added in #72, which also aligned SR bids with the
agent's `sr_bids_2025`). The declarations use the enum, not string literals.

### DBR filenames

`20260901 Letter to HMRC - Digital Business Review 010926` gives:

- `readout_date` = `20260901` (leading 8 digits)
- `department_name` = text between `Letter to ` and ` - `, normalised via
  `src/dia/department_mapping.py`
- `is_latest` = `true` for the newest letter per department, otherwise `false`
- `document_type` = `dbr_readout`

### DBR report filenames

`llm_dbr_report_hmrc_062026` gives:

- `department_name` = text between `llm_dbr_report_` and the final `_`, with
  underscores turned into spaces (`home_office` → `home office`), then
  normalised via `src/dia/department_mapping.py` (case-insensitive, since
  filenames are lowercase)
- `report_date` = `202606` (the trailing `MMYYYY`, stored as `YYYYMM`)
- `is_latest` = `true` for the newest report per department, otherwise `false`
- `document_type` = `dbr_report`

## Commits

| # | Commit | Contents |
|---|---|---|
| 1 | KB template | `stacks/constructs/knowledge_base.py`: `KnowledgeBaseSpec`, `DataSourceSpec`, chunking options, embedding model, `KnowledgeBase` construct. Standalone tests. |
| 2 | DBR bucket | Add `Bucket.DBR_REPORTS` to `src/dia/naming.py`. Create it in `StorageStack` with `config.names(Bucket.DBR_REPORTS)` (versioned, encrypted, public access blocked, SSL enforced, RETAIN). Add `DocumentType.DBR_REPORT`. |
| 3 | Declarations | `knowledge_bases.py` with `knowledge_bases(config)` returning the 8 specs. Owner accounts come from `DeploymentEnvironment`, never literals. Config tests for dev and prod. |
| 4 | KB stack | `stacks/knowledge_base.py`: vector bucket `dia-kb-vectors-{phase}` (RETAIN) and one template per deployed spec, with the account's permissions boundary on each role. Indexes RETAIN. Outputs KB IDs and role ARNs. Stack tests. Also gives the pipeline task role read access to the DBR bucket, because preflight checks every `Bucket`. |
| 5 | Verify | `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, synth, template inspection. Update `docs/design/handover.md`. |

## Follow-up work (not in this plan)

1. Metadata-writer CLI that validates against `metadata_keys`, replacing the old repo's `scripts/generate_kb_metadata.py`. Start with the DBR filename parser. Align it with the common metadata model (pipeline build plan PR 6).
2. Bucket policies on the source buckets allowing the new KB roles: the GATS bucket for the dev KB role, and the dev-account buckets for the prod KB roles.
3. After deploy: upload the DBR documents and their `.metadata.json` files, then start an ingestion job for each data source.
4. Once all eight are deployed, retire the old `AssuranceKB-*` stacks and delete the old vector bucket by hand (it was set to RETAIN).
5. Move the source buckets we own into this repo (#64).
6. Deploy the other six KBs, by adding their keys to `DEPLOYED`. Check the SR25 and SR21 prefixes first: with none set, the whole bucket is ingested.
7. Secret wiring: write KB IDs into the `dia-kb-arns` secret from CDK (or move the agent to a different lookup) without wiping the values set by hand.
