#!/usr/bin/env bash
# scripts/neptune-tunnel.sh
#
# Opens an SSH tunnel to Neptune via the bastion host, using EICE for
# the SSH connection (no public IP, no SSH keys needed - makes connecting easier because it just 
# uses our existing IAM auth credentials to connect to Neptune via the bastion).
#
# The bastion resolves Neptune's private DNS hostname server-side (inside
# the VPC). On the client side, LocalNeptuneClient handles DNS redirection
# at the Python process level — no /etc/hosts modification needed.
#
# Usage:
#   ./scripts/neptune-tunnel.sh [phase]
#   NEPTUNE_ENDPOINT=<host> ./scripts/neptune-tunnel.sh [phase]
#
# Args:
#   phase   dev or prod (default: dev). Selects the bastion, and the Neptune
#           cluster too unless NEPTUNE_ENDPOINT is set.
#
# Env:
#   NEPTUNE_ENDPOINT   Optional. Neptune hostname to tunnel to instead of the
#                      one in the dia-neptune-<phase> stack. The cluster's
#                      security group must allow inbound 8182 from the bastion.
#
# Prerequisites:
#   - AWS CLI v2 (ec2-instance-connect ssh requires v2)
#   - Authenticated to the correct AWS account for the given phase

set -euo pipefail

PHASE="${1:-dev}"
REGION="eu-west-2"
BASTION_STACK="dia-bastion-${PHASE}"
NEPTUNE_STACK="dia-neptune-${PHASE}"

echo "Resolving stack outputs for phase: ${PHASE}..."

BASTION_ID=$(aws cloudformation describe-stacks \
    --stack-name "${BASTION_STACK}" \
    --region "${REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='BastionInstanceId'].OutputValue" \
    --output text)

if [ -n "${NEPTUNE_ENDPOINT:-}" ]; then
    ENDPOINT="${NEPTUNE_ENDPOINT}"
    ENDPOINT_SOURCE="NEPTUNE_ENDPOINT override"
else
    ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name "${NEPTUNE_STACK}" \
        --region "${REGION}" \
        --query "Stacks[0].Outputs[?OutputKey=='NeptuneEndpoint'].OutputValue" \
        --output text)
    ENDPOINT_SOURCE="stack ${NEPTUNE_STACK}"
fi

if [ -z "${BASTION_ID}" ] || [ "${BASTION_ID}" = "None" ]; then
    echo "Error: Could not resolve bastion instance ID from stack ${BASTION_STACK}"
    exit 1
fi

if [ -z "${ENDPOINT}" ] || [ "${ENDPOINT}" = "None" ]; then
    echo "Error: Could not resolve Neptune endpoint from ${ENDPOINT_SOURCE}"
    exit 1
fi

echo "Bastion instance: ${BASTION_ID}"
echo "Neptune endpoint: ${ENDPOINT} (${ENDPOINT_SOURCE})"
echo ""
echo "Opening tunnel: localhost:8182 -> ${ENDPOINT}:8182 (via bastion)"
echo "Press Ctrl+C to close the tunnel"
echo ""

aws ec2-instance-connect ssh \
    --instance-id "${BASTION_ID}" \
    --connection-type eice \
    --local-forwarding "8182:${ENDPOINT}:8182" \
    --region "${REGION}"
