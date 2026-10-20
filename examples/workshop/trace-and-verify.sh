#!/usr/bin/env bash
set -euo pipefail

# Example: Trace a command and verify the bundle
echo "Tracing command..."
proofbench-workshop tracebundle -- python -c "print('Hello from ProofBench')"

BUNDLE=$(ls -dt tracebundle-* 2>/dev/null | head -1)
echo "Bundle: $BUNDLE"

echo -e "\nVerifying..."
proofbench-workshop verify "$BUNDLE"

echo -e "\nAttesting current directory..."
proofbench-workshop attest . --out example-attestation.json

echo -e "\nVerifying ledger..."
proofbench-workshop ledger verify

echo -e "\nDone!"
