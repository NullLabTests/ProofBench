# Tutorial: implementing an agent adapter

## The agent protocol

An agent acts inside one episode:

```python
from proofbench.agents import Agent

class MyAgent(Agent):
    agent_type = "my_agent"

    def reset(self, observation: dict, rng_seed: int) -> None:
        # Bind to one episode: public observation + a deterministic seed.
        super().reset(observation, rng_seed)

    def act(self) -> Action:
        # Choose the next action from observation + self.history only.
        return {"x": [...]}

    # observe_feedback(action, feedback) is called for you after each step.
```

Register it in `proofbench/agents.py`:

```python
AGENTS: dict[str, type[Agent]] = {
    a.agent_type: a for a in (FixedRandomSearch, AdaptiveSearch, ScriptedAgent, MyAgent)
}
```

Then reference it from a spec: `{"candidate": {"agent": "my_agent", "params": {...}}}`.

## Contract

- **Determinism**: fully determined by (params, observation, feedback
  history, rng_seed). The runner derives `rng_seed` from
  `derive_seed(run_seed, label, instance_id)` so runs replay exactly.
- **No hidden information**: you get `observe()` output and step feedback —
  nothing else. Hidden instance data never reaches you.
- **No self-scoring**: your score is `Episode.finalize()`, computed by the
  evaluator. Never claim one.
- **Budget awareness**: the episode stops at `budget` steps regardless;
  invalid actions consume budget.

## Model-backed adapters (optional, explicit opt-in)

`proofbench/model_adapter.py` provides `OpenAICompatAdapter`:

```python
from proofbench.model_adapter import OpenAICompatAdapter

adapter = OpenAICompatAdapter()          # reads PROOFBENCH_MODEL_* env vars
text = adapter.propose(prompt)           # raises ModelAdapterNotConfigured if unset
usage = adapter.usage_record()           # requests, tokens, failures — never the key
```

Configuration (environment variables only — never commit or log them):

- `PROOFBENCH_MODEL_ID` — model identifier, recorded in evidence.
- `PROOFBENCH_MODEL_API_BASE` — e.g. `https://api.openai.com/v1`.
- `PROOFBENCH_MODEL_API_KEY` — the credential.

Guarantees and non-guarantees:

- Without all three, every call raises `ModelAdapterNotConfigured`
  (CLI exit code 10). There is no implicit network access, at import time or
  otherwise.
- Requests, token usage (when reported), retries/failures are recorded — but
  reproducibility of stochastic remote inference is limited to what the
  recorded configuration and the service permit. Do not claim more.
- The adapter proposes *parameter patches* only. It cannot touch the
  evaluator, the acceptance policy, the baseline, the seeds, or the evidence
  — the same `validate_patch` gate applies to model proposals as to
  deterministic ones.
- Prompts and completions are not written into evidence by default (avoid
  leaking private task content into shared bundles).

## Comparing a model-backed method fairly

Give it the same `budget.evaluations_per_instance` and the same instances as
the baseline, declare any extra inference cost in the run's resource
accounting, and keep the primary outcome preregistered. A model-backed method
that cannot beat `fixed_random_search` under matched budgets is reported as
such — exactly like any other candidate.
