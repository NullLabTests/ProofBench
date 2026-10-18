"""Citations and upstream attribution for ProofBench.

Machine-readable provenance for ``proofbench cite``.  Two distinct things
are recorded:

1. **Dependencies** ProofBench installs and executes (pydantic, numpy,
   typer — all MIT/Apache-2.0/BSD respectively, see their own metadata).
2. **Upstream research** whose *design ideas* informed ProofBench.  For
   both upstream works, **no source code was reused**: one carries a
   non-OSI sample-code license (ideas reimplemented independently), the
   other is Apache-2.0 (ideas only; nothing copied).  The detailed
   research notes live in ``docs/upstream/``.

Listing an upstream project here is attribution, not endorsement, and
does not imply affiliation with Apple Inc. or Perplexity AI.
"""

from __future__ import annotations

from typing import Any

from proofbench import __version__

CITATIONS: list[dict[str, Any]] = [
    {
        "key": "proofbench",
        "name": "ProofBench",
        "version": __version__,
        "license": "MIT",
        "url": "https://github.com/proofbench/proofbench",
        "relationship": "this project",
    },
    {
        "key": "ml-rsi-inference-bench",
        "name": "Apple RSI-Inference Bench (apple-aiml-research/ml-rsi-inference-bench)",
        "license": "Apple Sample Code License (not OSI-approved)",
        "url": "https://github.com/apple-aiml-research/ml-rsi-inference-bench",
        "relationship": (
            "ideas only; no code reused. Its long-horizon task structure and "
            "independent-verifier grading inspired ProofBench's loop design; "
            "all ProofBench code is original. See docs/upstream/"
            "apple-rsi-inference-bench.md for the full research note and "
            "license obligations."
        ),
    },
    {
        "key": "space",
        "name": "Perplexity SPACE (perplexityai/SPACE)",
        "license": "Apache-2.0",
        "url": "https://github.com/perplexityai/SPACE",
        "relationship": (
            "ideas only; no code reused. Its management-plane/executable-"
            "plane separation and explicit-refusal fallback design informed "
            "ProofBench's executor model. See docs/upstream/perplexity-space."
            "md for the full research note."
        ),
    },
]


def citations_as_json() -> list[dict[str, Any]]:
    """Return the citation records (stable shape for tooling)."""
    return [dict(c) for c in CITATIONS]


def citations_as_text() -> str:
    """Render human-readable citations."""
    lines: list[str] = []
    for c in CITATIONS:
        lines.append(f"{c['name']} (version {c.get('version', 'n/a')})")
        lines.append(f"    license: {c['license']}")
        lines.append(f"    url:     {c['url']}")
        lines.append(f"    relation: {c['relationship']}")
        lines.append("")
    lines.append(
        "Upstream listings are attribution, not endorsement; no affiliation "
        "with Apple Inc. or Perplexity AI is implied."
    )
    return "\n".join(lines)
