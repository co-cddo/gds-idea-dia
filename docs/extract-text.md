# dia extract-text

Extract text from documents in a configured source. This is Stage 1 of
the pipeline: download → extract text → enrich with metadata → write
output → record in the ledger.

## Prerequisites

You need active AWS credentials with an `AWS_PROFILE` set — every mode
(including preview) lists documents from a real S3 bucket, and loading
metadata reads CSVs from S3 too.

```bash
export AWS_PROFILE=<your-profile>
aws sts get-caller-identity   # sanity check you're logged in
```

If your credentials expire partway through a run, the command will
fail with an AWS `ExpiredToken` / `AccessDenied` error — just refresh
your credentials and re-run the same command. Local runs resume from
the ledger (see below), so you won't lose progress.

## Quick start

```bash
# Preview: what would happen? Read-only, no writes.
dia extract-text --source gats-business-cases

# Run locally — writes to output/, resumable across runs
dia extract-text --source gats-business-cases --execute

# Run in production — writes to S3 + DynamoDB, asks for confirmation
dia extract-text --source gats-business-cases --live
```

## Local extraction workflow

### 1. (Optional) Seed the local ledger from production

If some documents have already been processed in production, clone
the ledger so a local run doesn't redo that work:

```bash
dia ledger clone
```

Copies every record from DynamoDB into `output/ledger.json`.

### 2. Preview

```bash
dia extract-text --source gats-business-cases
```

```
Source: gats-business-cases
Listing documents... 10714 found
Loading metadata... 10002 entries loaded
Checking ledger (output/ledger.json)... 5420 already done, 5294 to extract

Run with --execute for a local run, or --live for production.
```

Preview checks `output/ledger.json` — the same ledger `--execute`
would use — so it tells you what a local run would actually do next.
If the local ledger is empty, it'll suggest running `dia ledger clone`.

### 3. Execute

```bash
dia extract-text --source gats-business-cases --execute
```

Extracted text is written to `output/<source_name>/<document_key>.json`.
Progress is checkpointed after every batch of 100 documents — safe to
`Ctrl+C` at any point; at most one in-flight batch is lost.

### 4. Resume after stopping

Run the exact same command again:

```bash
dia extract-text --source gats-business-cases --execute
```

The ledger already knows what's done, so only the remaining documents
get processed.

## Production workflow

```bash
dia extract-text --source gats-business-cases --live
```

This checks DynamoDB, shows a summary, and prompts for confirmation
before writing anything to S3 or DynamoDB:

```
Checking ledger... 5294 to extract
About to process 5294 documents against production (dia-ledger-dev -> s3://gds-idea-dia-text-extracted-dev/)
Continue? [y/N]
```

Skip the prompt (e.g. in CI) with `--yes`:

```bash
dia extract-text --source gats-business-cases --live --yes
```

## Department filtering

Use `--departments` to restrict extraction to specific departments.
Values are comma-separated and must match the canonical department
name exactly (case-sensitive, full name — not an abbreviation or ALB
name):

```bash
dia extract-text --source gats-business-cases --departments "Home Office"
dia extract-text --source gats-business-cases --departments "Home Office,Cabinet Office"
```

`--departments` only works for sources with metadata configured. If a
source has none, you'll get an error telling you so.

Common mistake: department names are the canonical Cabinet Office
department list, not everyday abbreviations. For example, use
`"HM Revenue and Customs"`, not `"HMRC"`.

Known canonical department names (from `src/dia/department_mapping.py`):

- Attorney General's Office
- Cabinet Office
- Department for Business, Energy & Industrial Strategy
- Department for Culture, Media & Sport
- Department for Education
- Department for Energy Security and Net Zero
- Department for Environment, Food and Rural Affairs
- Department for Science, Innovation & Technology
- Department for Transport
- Department for Work and Pensions
- Department of Business and Trade
- Department of Health and Social Care
- Foreign, Commonwealth & Development Office
- HM Revenue and Customs
- HM Treasury
- Home Office
- Ministry of Defence
- Ministry of Housing, Communities and Local Government
- Ministry of Justice

Not every department will have documents in every source.

## Reprocessing with --force

Ignore the ledger and reprocess everything, regardless of what's
already been done:

```bash
dia extract-text --source gats-business-cases --execute --force
```

The ledger is still *written* to after each successful extraction —
`--force` only skips the *read* (the "is this already done?" check).

With `--live --force`, the confirmation prompt is more explicit about
what's about to happen:

```
About to REPROCESS 10714 documents (ignoring ledger) against production (dia-ledger-dev -> s3://gds-idea-dia-text-extracted-dev/)
Continue? [y/N]
```

## All flags

| Flag | Description |
|------|-------------|
| `--source` / `-s` | Source name (required) — see `src/dia/sources/known.py` for the list |
| `--departments` / `-d` | Comma-separated department filter |
| `--execute` | Local run: writes to `output/`, ledger at `output/ledger.json` |
| `--live` | Production run: S3 + DynamoDB, with a confirmation prompt |
| `--yes` / `-y` | Skip the `--live` confirmation prompt |
| `--force` / `-f` | Ignore the ledger, reprocess everything |
| `--inmemory-ledger` | Ephemeral ledger, no persistence (only valid with `--execute`) |

`--execute` and `--live` are mutually exclusive. Neither flag set means
preview (read-only).

## Output format

Each extracted document is written as a JSON file at
`output/<source_name>/<document_key>.json` (locally) or
`s3://<bucket>/<source_name>/<document_key>.json` (production):

```json
{
  "key": "files/report.pdf",
  "source_name": "gats-business-cases",
  "content_type": "application/pdf",
  "version": "\"etag-abc123\"",
  "text": "...",
  "chars": 12450,
  "metadata": {
    "department": "Home Office",
    "alb": "National Crime Agency",
    "spend_id": "CS-100",
    "project_name": "Project Alpha",
    "assurance_date": null
  },
  "extracted_at": "2026-07-23T10:00:00+00:00",
  "code_version": "0.1.20"
}
```

`metadata` is `{}` if the source has no metadata configured, or if this
particular document has no matching entry.

## Logs

Full detail — including tracebacks for failed extractions — goes to
`logs/<source_name>-<date>.log` (DEBUG level). The console only shows
batch progress and one-line failure summaries (INFO level), e.g.:

```
INFO     Batch 1/108: processing 100 documents
WARNING  Failed: key='files/broken.docx' error=File is not a zip file
INFO     Batch 1/108 complete: processed=95 failed=5
```

A handful of failures per run is normal — corrupted or mislabeled
files exist in most large document stores. Check the log file for
full tracebacks if you need to investigate a specific failure.
