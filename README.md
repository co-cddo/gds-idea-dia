# DIA - Department Intelligence Agent

Knowledge graph extraction pipeline for UK government documents. Extracts structured knowledge graphs from government document types (business cases, spending review bids, contracts) and loads them into Amazon Neptune and OpenSearch.

## Setup

```bash
uv sync
uv run dia --version
```

## Running tests

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## CDK

Infrastructure is deployed automatically via CI/CD:
- Merge to `dev` → deploys to development account
- Merge to `prod` → deploys to production account

For local CDK operations (e.g. checking a diff):

```bash
uv sync --all-extras
cdk diff
cdk synth
```
