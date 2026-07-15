# DIA - Department Intelligence Agent

![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/co-cddo/gds-idea-dia/badges/coverage.json)

Knowledge graph extraction pipeline for UK government documents. Extracts structured knowledge graphs from government document types (business cases, spending review bids, contracts) and loads them into Amazon Neptune and OpenSearch.

## Setup

```bash
uv sync --all-extras
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

For local CDK operations:

```bash
cdk diff
cdk synth
```
