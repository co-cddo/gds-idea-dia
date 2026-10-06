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
export AWS_PROFILE=<your-profile>
uv run pytest tests/test_lexical_graph_integration.py -m live_aws -v
```

Only those two exports are required — Neptune/AOSS endpoints are looked up
automatically via CloudFormation (override with `export NEPTUNE_ENDPOINT=...`
/ `export AOSS_ENDPOINT=...` if needed). `AWS_REGION` and model choices can
be set the same way, or persisted locally in a git-ignored `.env` file — see
`src/dia/clients/graph_rag_config.py`.

### Connecting to a different Neptune cluster (temporary)

By default the tunnel and the agent connect to the DIA Neptune cluster for
your phase (`dev` or `prod`). To point them at another Neptune cluster in the
same account and VPC, set `NEPTUNE_ENDPOINT` to that cluster's hostname.

**One-off setup:** let the bastion reach the other cluster. Add an inbound rule
to the other cluster's security group allowing TCP `8182` from the bastion's
security group. You can do this in the console, or:

```bash
BASTION_ID=$(aws cloudformation describe-stacks --stack-name dia-bastion-dev \
  --query "Stacks[0].Outputs[?OutputKey=='BastionInstanceId'].OutputValue" --output text)
BASTION_SG=$(aws ec2 describe-instances --instance-ids "$BASTION_ID" \
  --query "Reservations[0].Instances[0].SecurityGroups[0].GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id <other-cluster-sg-id> \
  --protocol tcp --port 8182 --source-group "$BASTION_SG"
```

Your AWS profile also needs Neptune data access (`neptune-db:*`) on that cluster.

**Each time you use it:**

1. Close any tunnel that's already running (Ctrl+C in its terminal). If one is
   still open, the agent reuses it, and it will still point at the old cluster.
2. Set the endpoint (hostname only, no `https://` and no port):
   ```bash
   export NEPTUNE_ENDPOINT=<other-cluster-hostname>
   ```
3. Use things as normal. Everything below picks the endpoint up:
   ```bash
   uv run dia agent ask --query "..."     # opens its own tunnel to the other cluster
   ```
   ```bash
   ./scripts/neptune-tunnel.sh dev        # manual tunnel, e.g. for notebooks or `dia agent status`
   ```
   The script prints `(NEPTUNE_ENDPOINT override)` next to the endpoint so you
   can confirm which cluster you're on. In a notebook, pass the same hostname
   to `LocalNeptuneClient(endpoint=...)`.

**Going back to the default cluster:** close the tunnel, run
`unset NEPTUNE_ENDPOINT` (and remove it from `.env` if you put it there), then
remove the security group rule you added.

## CDK

Infrastructure is deployed automatically via CI/CD:
- Merge to `dev` → deploys to development account
- Merge to `prod` → deploys to production account

For local CDK operations:

```bash
cdk diff
cdk synth
```
