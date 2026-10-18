# Upstream research note: apple-aiml-research/ml-rsi-inference-bench

**Repository:** https://github.com/apple-aiml-research/ml-rsi-inference-bench
**GitHub description:** "A Long-Horizon Benchmark for Self-Improving Inference Systems"
**Access method:** `gh repo view` (succeeded after correcting the JSON field to `licenseInfo`) and a shallow `git clone` into `/tmp/opencode/upstream/ml-rsi/ml-rsi-inference-bench`.
**State at time of research (2026-10-18):** public, non-empty, single squashed commit `a6b10af282014412b4eae14f3105d68555889821` ("Initial commit"), default branch `main`, created 2026-10-16, last pushed 2026-10-16, 69 stars. Clone size ~422 MB (112 MB `.git`, 305 MB `tasks/`). Everything below is read directly from the clone unless stated otherwise.

---

## 1. What the project actually implements

**One-line summary (README.md, lines 12–15):**

> "RSI-Inference Bench is a long-horizon benchmark for coding agents that improve the inference stack of large language models. It follows a model through its life in a production engine, vLLM or SGLang: supported on day 0, optimized after launch, and repaired when a regression lands. An agent works on the real engine, on real GPUs, and is graded by running what it built."

So "self-improving inference" does **not** mean the model improves itself, and does not mean an agent iterating across benchmark attempts. It means: a *coding agent* edits a pinned, real inference-engine source tree (vLLM or SGLang) to (a) add day-0 support for a new model, (b) increase serving throughput, or (c) repair an injected performance regression — and is graded by an independent verifier that builds the edited engine, serves the model, and measures it.

**Main components**

- **37 task directories** under `tasks/`, in three categories (verified by parsing every `task.toml`): 10 `model_support` (`tasks/support_*`), 20 `throughput_optimization` (`tasks/optimize_*`), 7 `regression` (`tasks/regression_*`). Engines: vLLM 20 / SGLang 17. Accelerators: H100 17 / B200 20. GPUs per task: 1→7 tasks, 2→6, 4→14, 8→10 (leaderboard JSON, `release` object).
- **Pier runner**, vendored at `third_party/pier/` (Apache-2.0, a fork of Harbor; per `ACKNOWLEDGEMENTS`: "vendored at commit `3f688a1bd0d15f77f7191609e9f8ecdd3a69db33` on 2026-07-09"). Pier reads Harbor's task format and runs trials (`pier run -p tasks/<task> --env docker --agent <agent> --model <model>`); supports agents `nop, oracle, claude-code, codex, cursor-cli, gemini-cli, opencode, mini-swe-agent`, all emitting the augmented ATIF v1.7 trajectory format (`third_party/pier/README.md` line 22).
- **Task format (Harbor-compatible)**, one directory per task: `task.toml` (schema_version 1.2: resources, timeouts, env vars, target repo/commit, model id, scoring config), `instruction.md` (agent-facing spec), `environment/Dockerfile` + build scripts, `tests/` (verifier: `test.sh`, `_verifier_lib/`, `verify_*.py`), `solution/` (`known_good.patch` + `solve.sh` — a maintainer's reference solution, shipped but withheld from the agent), sometimes `pre_artifacts.sh` (artifact capture).
- **Verifier**: runs in a *separate* container from the agent (`environment_mode = "separate"` in `task.toml`), builds the candidate engine from the state the agent left behind, serves the pinned model, and measures against the untouched baseline. Example: `tasks/optimize_qwen3_6_27b_1xh100_open/tests/verify_throughput_real.py`.
- **Leaderboard** at `docs/leaderboard.html` — a static page with an embedded JS object `window.RSI_LEADERBOARD` (schema `rsi-inference-leaderboard/1`, snapshot `2026-10-12T0539Z`, 444 scored results, 12 agents).

**Benchmark protocol (the agent's loop)** — from `tasks/optimize_qwen3_6_27b_1xh100_open/instruction.md`:

- The agent gets the engine at a pinned commit in `/app/repo`, the model, and 1–8 GPUs, with **no internet** (`allow_internet = false`) and a fixed wall-clock budget (~8.3 h; `[agent] timeout_sec = 30000`). A timer is exposed to the agent as files: "`cat /app/.timer/remaining_secs` shows the seconds left (also `/app/.timer/elapsed_secs`, and `test -f /app/.timer/alert_5min` appears as the deadline nears)" (`environment/scripts/start_agent_timer.sh` writes these).
- What is scored is the final source-tree state: "What is scored is the state of `repo/` you leave behind — your commits AND anything still uncommitted (`git diff inference_base`)." The artifact is a patch: `artifacts = ["/logs/artifacts/model.patch"]`.
- The agent can self-test with the same public harness the verifier uses (`scripts/run_correctness.py`, `scripts/run_benchmark.py`), but the verifier "supplies its own inputs and acceptance" (`tasks/support_minimax_m3_4xb200_vllm/instruction.md`: "The public and grading copies have identical source; grading supplies its own inputs and acceptance").

**How improvement is measured:** baseline-paired, same-session measurement. `instruction.md`: "`PAIRED` runs your candidate and the baseline (`inference_base`) back-to-back in the same session so cross-session GPU drift cancels." The regression tasks are even explicit that no stored numbers are used: "The verifier benches `repo/` and the pinned tree in the same run, on the same machine, every shape against one server per tree, so no stored number can flatter or penalise you" (`tasks/regression_fp8_decode_throughput/instruction.md`).

## 2. Documented assumptions, prerequisites, hardware/API requirements, limitations

- **Python ≥ 3.12**, `uv`-managed (`pyproject.toml`: `requires-python = ">=3.12"`, single dependency `datacurve-pier` via editable path to `third_party/pier`).
- **GPUs are mandatory and specific**: NVIDIA H100 or B200 only (per-task `gpu_types` in `task.toml`), 1–8 GPUs. Typical per-task allocation: 16–64 CPUs, 256 GB–1 TB RAM, 160 GB–2 TB storage, 16–64 GB `/dev/shm` (e.g., `regression_fp8_decode_throughput` asks for `cpus = 64`, `memory_mb = 1048576`, `storage_mb = 2097152`, `gpus = 8`).
- **Offline at runtime**: `allow_internet = false` for both agent and verifier environments. Model weights are *not* in the repo; each model-support task fetches them at image build time from a pinned manifest (`environment/model-manifest.json`: `ACKNOWLEDGEMENTS` says "672 entries carry 540 sha256 digests"; the manifest note says it "verifies the git blob id of every file and the sha256 of every LFS file"). Engines are likewise not vendored — Dockerfiles clone/instal vLLM or SGLang from GitHub/PyPI at build time. `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1` etc. are enforced in `tests/test.sh`.
- **Agent-side API access**: although the *task container* is air-gapped, the agent under test (e.g., Claude Code, Codex, OpenCode) still needs model-API access; Pier handles this with per-agent install scripts + a network allowlist honored even when `allow_internet = false` (`third_party/pier/README.md`, "Installed agents in air-gapped tasks"). The README's run recipe assumes an `ANTHROPIC_API_KEY`-style env file.
- **Time budgets**: agent 30,000 s (~8.3 h; leaderboard `agent_time_limit_hours: 8.3`); verifier budgets are much larger (up to `timeout_sec = 158330` in the MiniMax task); image build `build_timeout_sec` up to 12,400 s.
- **Limitations acknowledged in-repo**: "Pier does not currently resolve or download Harbor registry datasets directly" (`third_party/pier/README.md` line 26). The paper is unpublished: README badge says `Paper-coming%20soon`; `CITATION.cff` cites a 2026 article that is not in the repo.
- Editable-surface policies are task-declared ("edit policy"): e.g., `INFB_EDIT_POLICY_CSRC=1` allows `csrc/**/*.{cu,cpp,h}` edits; support tasks state "Equivalent algorithms, languages, fusion, helper names and cache layouts are allowed" but forbid consulting withheld material.

## 3. Benchmark protocol details: metrics, budgets, baselines, scoring, splits

**Tracks and metrics** (README lines 37–41 and `docs/leaderboard.html`):

- **Day-0 Model Support (10 tasks)** — score **pass@1**: "Full passes over attempts on each task, averaged over the tasks. A partial pass counts as a failure." The leaderboard data shows 3 attempts per task per agent (`"passes": 1, "attempts": 3, "pass_at_1": 0.3333`), tie-breaked by share of hidden tests passed ("ties broken by the share of hidden tests passed"; per-agent `f2p` — fail-to-pass checks — e.g., Sonnet-5.5 aggregate `f2p: 0.9006`).
- **Inference Optimization & Regression Fix (27 tasks)** — score **speed-up**: "Each task's measured ratio against its baseline, as a geometric mean over the tasks. A result that fails its correctness check counts as 1.00×." Per-task speedup = geometric mean over declared workloads (e.g., `decode_heavy`, `prefill_heavy`, `high_load` in `task.toml`) of `baseline_time / candidate_time`.

**Scoring code** (`tasks/optimize_qwen3_6_27b_1xh100_open/tests/_verifier_lib/scoring.py`): `speedup_reward = max(0.0, speedup - 1.0)` with the docstring "The measured gain, floored at 0. No target, no normalisation, no ceiling." Total reward is 0 unless the correctness gate passes; if any workload is non-positive the geomean is 0.

**Gates and anti-gaming (important design content):**
- **Correctness gate**: for the optimize tasks, mode "loose" logits comparison (`atol = 0.05, rtol = 0.05, min_pass_rate = 0.95` on 20 prompts × 100 tokens) — "If the correctness gate fails, your score is zero regardless of measured speed."
- **Category gate**: "CLI flag flips and `vllm/config.py` default-value changes alone are classified `category=config` and contribute 0 regardless of measured speedup" (`instruction.md`); implemented by diff-shape classification over file patterns in `tests/_verifier_lib/category_gate.py` (config/invocation/doc/test/artifact patterns).
- **Guard shapes**: scored workloads have an unscored guard measured identically — "a tree that reads slower than the pinned one there scores zero: a repair that pays for the scored shapes by slowing another is not a repair" (`regression_fp8_decode_throughput/instruction.md`).
- **Output-unchanged requirement**: "the verifier compares the two trees' decoding on fixed prompts, and a tree that fails that check scores zero whatever its speed."
- **Silent reference bar**: "A maintainer's own repair of this deployment exists and has been measured on this rig. You are not told what it changed or what it reached; your result will be read against it."
- **Anti-leak rule**: "Do not consult any source outside this container about this engine's history or development, whatever its date."
- **Infra-void policy**: the optimize `tests/test.sh` states "If the verifier withholds reward.json on an infra void, or this file aborts, the default is NO SCORE rather than a zero."

**Leaderboard scoring / "splits"** (embedded leaderboard JSON): joint ranking by "Category-weighted Bradley-Terry rating on the Elo scale" (`method: weighted-bt-elo-v2`), mean 1500, weights model_support 0.25 / throughput_optimization 0.5 / regression 0.25, optimization draw band 1%, 2,442 pair comparisons. Snapshot 2026-10-12: 12 agents; top is "Sonnet-5.5" (rating 2022.39, support pass@1 0.2667, optimization speedup 1.6772× = throughput 1.5277× + regression 2.1899×); bottom "Gemini-3.7-Flash" (1031.77, 1.0419×). There is no train/test *data* split — the held-out structure is **public vs. hidden tests/inputs** (hidden grading inputs live only in the verifier environment), and the 37 released tasks themselves are the full evaluation set.

## 4. Design principles that transfer to ProofBench

ProofBench tests whether AI systems improve over repeated attempts with feedback and bounded self-modification. The transferable principles from this repo:

1. **Verifier/agent separation with build-and-run grading.** The agent never sees grading inputs; the score comes from executing the artifact the agent produced (`environment_mode = "separate"`, hidden inputs, "graded by running what it built"). Directly transferable: ProofBench should grade by running the agent's modified system against withheld cases, not by self-report.
2. **Paired baseline measurement in the same session.** Candidate and frozen baseline measured back-to-back, same machine, same run, to cancel drift ("cross-session GPU drift cancels"; "no stored number can flatter or penalise you"). For ProofBench's repeated-attempts setting this is the cleanest way to attribute *improvement* to the agent rather than to environment noise.
3. **Correctness gate before improvement credit.** Any behavioral regression ⇒ score zero regardless of speed ("Output must not change, and that is scored too"). Transfer: improvement on the target metric must never be purchasable by breaking the system's contract.
4. **Uncapped, unnormalized, floored-at-zero reward.** `max(0, geomean − 1.0)` — "No target, no normalisation, no ceiling." No reference-solution ceiling; the maintainer's solution is a silent bar, not a cap. Good for measuring open-ended self-improvement.
5. **Trivial-change classification (category gate).** Diff-shape classification (config-only, invocation-only, docs, tests) zeroes out "improvements" that are parameter flips rather than substantive work. ProofBench analogue: classify self-modifications so that hyperparameter tweaks on the harness don't count as system improvement.
6. **Guard conditions.** Uns scored guard shapes catch improvements that mooch on other inputs. Transfer: any improvement metric needs a non-regression guard over adjacent inputs.
7. **Explicit, machine-readable time budget surfaced to the agent.** `/app/.timer/remaining_secs`, `elapsed_secs`, `alert_5min` files, plus a hard external timeout — bounded horizons with agent-visible pacing signals. Exactly matches ProofBench's "bounded" framing.
8. **State-based scoring of self-modification.** Score the *final artifact* (`git diff` against baseline, including uncommitted work) rather than the trajectory; capture it as a patch artifact. Simple, auditable, replayable.
9. **Deterministic infra handling.** "Preparation is deterministic, so a second run fails the same way" — one healthcheck retry, and infra voids yield NO SCORE rather than a misleading 0. Transfer: separate "system failed" from "attempt failed" in ProofBench metrics.
10. **Lifecycle-shaped task families.** Three task types (add capability / improve performance / repair regression) over the same substrate — a compact way to exercise both improvement and robustness-under-change. ProofBench's "repeated attempts with feedback" could reuse the add/improve/repair taxonomy per system.
11. **Reference solutions shipped with tasks** (`solution/known_good.patch`) — useful for calibrating the harness and confirming tasks are solvable, while hidden from the agent.

## 5. Components impractical or inappropriate to reuse

- **The tasks themselves.** Every task hard-requires 1–8 H100/B200 GPUs, CUDA 12.8/12.9 toolchains, 256 GB–1 TB RAM, and multi-hundred-GB image builds; models run up to "1T and up" parameters (README stack figure) with 160 GB–2 TB scratch storage. Not runnable on ordinary hardware or CPU-only CI.
- **Model weights and engines.** Not distributed in the repo (per `ACKNOWLEDGEMENTS`: "NOT distributed. No model weights are included"); fetching requires multi-hundred-GB downloads at build time from Hugging Face plus full vLLM/SGLang builds. The pinned engine commits are specific to each task's era (e.g., vLLM `0.20.1`, commit `1387478…`).
- **The Pier/Harbor runner as-is** is usable in principle (it also runs `docker`/`modal` and CPU tasks), but it is vendored at a specific commit with Apple modifications, drags agent-CLI dependencies (Claude Code, Codex, cursor-agent…), and its trajectory format is oriented at single long agent runs, not at ProofBench's repeated-attempt-with-feedback loop. Adopting the *ideas* (Harbor task format, ATIF discipline) is more practical than adopting the code.
- **The benchmark's measurement loops** assume live GPU servers taking minutes per boot ("Each boot costs several minutes") — the paired-measurement *pattern* transfers; the code (Nsight profiling, NCCL/`/dev/shm` tuning, vLLM bench CLI) does not.
- **The 3-attempt independent-trial structure**: leaderboard attempts are i.i.d. samples for pass@1 — there is *no* cross-attempt memory or cumulative-improvement protocol in this repo. If ProofBench's core question is improvement *over repeated attempts*, this must be designed fresh; this repo supplies the measurement hygiene, not the longitudinal protocol.
- **Apple's reference solution patches** (`solution/*.patch`, up to 3.2 MB) are diffs against vLLM/SGLang containing third-party-derived code (Apache-2.0 obligations) — don't lift them into another project.

## 6. License and attribution obligations

**A LICENSE file exists** at the repo root: the **Apple Sample Code License**, "Copyright (C) 2026 Apple Inc. All Rights Reserved." (GitHub `licenseInfo` reports it as `{"key":"other","name":"Other"}` — i.e., *not* an OSI-approved license.) Full exact contents:

```
Copyright (C) 2026 Apple Inc. All Rights Reserved.

IMPORTANT:  This Apple software is supplied to you by Apple
Inc. ("Apple") in consideration of your agreement to the following
terms, and your use, installation, modification or redistribution of
this Apple software constitutes acceptance of these terms.  If you do
not agree with these terms, please do not use, install, modify or
redistribute this Apple software.

In consideration of your agreement to abide by the following terms and
subject to these terms, Apple grants you a personal, non-exclusive
license, under Apple's copyrights in this original Apple software (the
"Apple Software"), to use, reproduce, modify and redistribute the Apple
Software, with or without modifications, in source and/or binary forms;
provided that if you redistribute the Apple Software in its entirety and
without modifications, you must retain this notice and the following
text and disclaimers in all such redistributions of the Apple Software.
Neither the name, trademarks, service marks or logos of Apple Inc. may
be used to endorse or promote products derived from the Apple Software
without specific prior written permission from Apple.  Except as
expressly stated in this notice, no other rights or licenses, express or
implied, are granted by Apple herein, including but not limited to any
patent rights that may be infringed by your derivative works or by other
works in which the Apple Software may be incorporated.

The Apple Software is provided by Apple on an "AS IS" basis.  APPLE
MAKES NO WARRANTIES, EXPRESS OR IMPLIED, INCLUDING WITHOUT LIMITATION
THE IMPLIED WARRANTIES OF NON-INFRINGEMENT, MERCHANTABILITY AND FITNESS
FOR A PARTICULAR PURPOSE, REGARDING THE APPLE SOFTWARE OR ITS USE AND
OPERATION ALONE OR IN COMBINATION WITH YOUR PRODUCTS.

IN NO EVENT SHALL APPLE BE LIABLE FOR ANY SPECIAL, INDIRECT, INCIDENTAL
OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
INTERRUPTION) ARISING IN ANY WAY OUT OF THE USE, REPRODUCTION,
MODIFICATION AND/OR DISTRIBUTION OF THE APPLE SOFTWARE, HOWEVER CAUSED
AND WHETHER UNDER THEORY OF CONTRACT, TORT (INCLUDING NEGLIGENCE),
STRICT LIABILITY OR OTHERWISE, EVEN IF APPLE HAS BEEN ADVISED OF THE
POSSIBILITY OF SUCH DAMAGE.
```

Obligations if redistributing Apple's material in whole and unmodified: retain the notice; no use of Apple's name/trademarks to endorse derived products; **no patent license granted** (relevant if you build derivative works on top). Note this is sample-code licensing — safest course for ProofBench is to reimplement ideas rather than copy files, and to not present ProofBench as Apple-affiliated.

**Third-party obligations (documented in `ACKNOWLEDGEMENTS`):**
- `third_party/pier/` — Apache License 2.0 (`third_party/pier/LICENSE`, upstream `NOTICE` preserved: "Pier includes code derived from Harbor: https://github.com/harbor-framework/harbor"). Apple-modified files are marked in headers. Attribution + license text retention required if reused.
- vLLM and SGLang — Apache-2.0; *not* distributed as engines, but reference-solution patches contain vLLM/SGLang-derived files carrying their SPDX headers ("Copyright contributors to the vLLM project / SPDX-License-Identifier: Apache-2.0") — retain those headers if those files are ever redistributed.
- Model weights, datasets, CUDA/Python/container base images — not distributed; each carries its own terms.
- `CITATION.cff` requests citation: Liu (Apple; HKUST), Bai, Zheng, Zhang, Zhang — "RSI-Inference: A Long-Horizon Benchmark for Self-Improving Inference Systems", 2026.

## 7. Uncertainties requiring further verification

1. **No paper exists yet.** The README paper badge literally says "coming soon"; `CITATION.cff` describes an article that is not in the repo. All protocol details above come from repo files only; a future paper may contradict or extend them.
2. **Leaderboard agent names are not mapped to model IDs.** Names like "Sonnet-5.5", "Fable-5.1", "GPT-6.1-Sol" appear only in `docs/leaderboard.html`; I found no file in the repo mapping them to specific models/providers. Treat the leaderboard as reported-by-Apple, unaudited.
3. **"3 attempts per task" is inferred** from leaderboard fields (`"attempts": 3`, `pass_at_1 = passes/attempts`) plus README wording ("Full passes over attempts on each task"); the attempt-generation procedure (temperature, agent config) is not documented in the repo.
4. **Execution unverified.** I did not run any task (no H100/B200 in this environment). Claims about the harness behavior come from reading code and instructions, not from execution.
5. **Repo is brand-new and squashed.** Single initial commit dated 2026-10-16; no release tags were checked beyond `git ls-remote` showing only `main`; no issues/PRs were examined. Contents may change quickly.
6. **Whether hidden grading inputs are actually absent from the clone** was spot-checked (public/grading separation stated in instructions; `INFB_OFFICIAL=1` verifier env; `buildcheck/` and `checks/no_reference_impl.py` in support tasks suggest leak checks) but not exhaustively audited across all 37 tasks.
7. **SGLang tasks reference model families** (e.g., `support_sd3_2xh100_sglang`, diffusion models) whose exact verification protocols I did not read; only vLLM support/optimize/regression tasks were sampled in depth.
8. **Pier's `modal` backend and Respan/OpenRouter plumbing** were read from the README but not exercised.

**Evidence locations (local clone):** `/tmp/opencode/upstream/ml-rsi/ml-rsi-inference-bench/` — `README.md`, `LICENSE`, `ACKNOWLEDGEMENTS`, `CITATION.cff`, `pyproject.toml`, `docs/leaderboard.html` (embedded `window.RSI_LEADERBOARD` JSON), `third_party/pier/README.md`, `third_party/pier/NOTICE`, `tasks/*/task.toml`, `tasks/*/instruction.md`, `tasks/optimize_qwen3_6_27b_1xh100_open/tests/_verifier_lib/{scoring,category_gate}.py`, `tasks/optimize_qwen3_6_27b_1xh100_open/environment/scripts/start_agent_timer.sh`, `tasks/regression_fp8_decode_throughput/instruction.md`, `tasks/support_minimax_m3_4xb200_vllm/environment/model-manifest.json`.
