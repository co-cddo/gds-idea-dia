# DIA - Department Intelligence Agent

![Coverage](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/co-cddo/gds-idea-dia/badges/coverage.json)

Knowledge graph extraction pipeline for UK government documents. Extracts structured knowledge graphs from government document types (business cases, spending review bids, contracts) and loads them into Amazon Neptune and OpenSearch.

## Setup

```bash
uv sync --all-extras
uv run dia --version
```

## Usage

- [`dia extract-text`](docs/extract-text.md) — Stage 1: extract text from documents in a source

## Running tests

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Live AWS integration tests

`tests/test_lexical_graph_integration.py` exercises real Neptune + OpenSearch
Serverless infrastructure and is skipped by default (no AWS access required
for a normal `uv run pytest`). To run it for real:

```bash
# If on a Zscaler-managed corporate device, install the TLS fix first —
# needed for the OpenSearch Serverless (AOSS) connection, which goes over
# the public internet (Neptune's connection tunnels via SSH and is unaffected):
uv sync --group zscaler

./scripts/neptune-tunnel.sh dev   # in a separate terminal

export RUN_LIVE_AWS_TESTS=1
export NEPTUNE_ENDPOINT=<neptune-cluster-endpoint>
export AOSS_ENDPOINT=<aoss-endpoint>
uv run pytest tests/test_lexical_graph_integration.py -m live_aws -v
```

You may see a `DeprecationWarning: There is no current event loop` — this
comes from `graphrag_toolkit`'s own import-time compatibility shim, not
this codebase, and is safe to ignore.

## CDK

Infrastructure is deployed automatically via CI/CD:
- Merge to `dev` → deploys to development account
- Merge to `prod` → deploys to production account

For local CDK operations:

```bash
cdk diff
cdk synth
```
