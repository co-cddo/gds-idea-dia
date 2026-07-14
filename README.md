# DIA - Department Intelligence Agent

Knowledge graph extraction pipeline for UK government documents. Extracts structured knowledge graphs from government document types (business cases, spending review bids, contracts) and loads them into Amazon Neptune and OpenSearch.

## Setup

```bash
uv sync
uv run dia version
```

## Running tests

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## CDK

```bash
uv sync --group cdk
cdk synth -c phase=dev
cdk deploy -c phase=dev
```
