# [DeepSWE](https://deepswe.datacurve.ai/)

DeepSWE is a benchmark for measuring frontier coding agents on original, long-horizon software engineering tasks drawn from active open-source repositories. The benchmark includes 113 tasks across TypeScript, Go, Python, JavaScript, and Rust, with isolated environments and program-based verifiers.

## Task format

DeepSWE tasks use the [Harbor](https://www.harborframework.com/docs/tasks) task format:

```text
task.toml         Metadata: repository, base commit, language, prebuilt image, resource limits
instruction.md    The prompt the agent sees
environment/      Dockerfile that reproduces the prebuilt image (fallback if the image is unavailable)
tests/            Verifier: test.sh (entry point) + test.patch (test additions, applied at grading time)
solution/         Reference solution (held out from the agent; for human and AI reviewers)
```

The verifier exercises the behavior the prompt describes. It accepts any solution whose observable behavior is correct, regardless of internal symbol names or structure.
The reference patch in `solution/` is never used at grading time; it exists so reviewers can spot-check correctness offline.

## Quickstart

Use [Pier](https://github.com/datacurve-ai/pier) to run the benchmark:

```bash
git clone https://github.com/datacurve-ai/deep-swe
uv tool install datacurve-pier

# Claude Opus 4.7 via Claude Code
export ANTHROPIC_API_KEY=...
pier run -p deep-swe/tasks --agent mini-swe-agent --model anthropic/claude-opus-4-7

# GPT-5.5 via Codex
export OPENAI_API_KEY=...
pier run -p deep-swe/tasks --agent mini-swe-agent --model openai/gpt-5.5
```

### Composer 2.5 via Grok Build CLI

The published [DeepSWE leaderboard](https://deepswe.datacurve.ai/) uses `mini-swe-agent` for cross-model consistency. This branch adds a Pier adapter for [Grok Build CLI](https://x.ai/news/grok-build-cli) that routes to Composer 2.5 through Grok's `grok-composer-2.5-fast` model (Cursor agent harness behind the scenes).

```bash
git clone https://github.com/ivanfioravanti/deep-swe
cd deep-swe
git checkout composer-2.5-support

uv tool install datacurve-pier

cp .env.example .env
# Add XAI_API_KEY from https://console.x.ai/
# Or set GROK_AUTH_JSON to the contents of ~/.grok/auth.json

# Smoke test: one task
PYTHONPATH=. pier run -p tasks/cliffy-config-file-parsing \
  --agent-import-path agents.grok_build:GrokBuild \
  --model grok/grok-composer-2.5-fast \
  --env docker \
  --env-file .env

# Deterministic 10-task subset
PYTHONPATH=. pier run -p tasks \
  --agent-import-path agents.grok_build:GrokBuild \
  --model grok/grok-composer-2.5-fast \
  --n-tasks 10 \
  --sample-seed 0 \
  --env docker \
  --env-file .env

# 10-task subset (checked-in job config)
PYTHONPATH=. pier run -c examples/grok-composer-2.5-job.yaml --env-file .env

# Full 113-task run on Docker (same task corpus as the leaderboard)
PYTHONPATH=. pier run -c examples/grok-composer-2.5-full-job.yaml --env-file .env
```

Use `grok/grok-build` instead of `grok/grok-composer-2.5-fast` to benchmark Grok's native coding agent. This uses the Grok Build harness, not `mini-swe-agent`, so scores are not directly comparable to published leaderboard numbers. Results land in `jobs/`; inspect them with `pier view jobs/<job-name>`.

#### Alternative: Cursor CLI

You can also run Composer 2.5 directly through Pier's `cursor-cli` agent (requires Pier `main` from GitHub):

```bash
uv tool install git+https://github.com/datacurve-ai/pier.git
pier run -c examples/composer-2.5-job.yaml --env-file .env
```

## What is Pier

[Pier](https://github.com/datacurve-ai/pier) is a [Harbor](https://www.harborframework.com/docs/tasks)-compatible framework for sandboxed coding-agent evals. It began as a fork of Harbor to support CLI agents in air-gapped tasks: Harbor blocks all outbound traffic in `allow_internet = false` tasks, including dependency installs and LLM API calls. Pier adds per-agent network allowlists, giving agents only the network access they need while keeping the task environment isolated.

Pier also adds more complete trajectory metadata, a better trajectory viewer, and `pier critique run` for analyzing agent trajectories. All leaderboard scores were produced with Pier running `mini-swe-agent` on Modal.

### Agents and models

`mini-swe-agent` is model-agnostic. Pier also drives `claude-code`, `codex`, `cursor-cli`, `gemini-cli`, and `opencode` directly. This fork adds a custom `grok-build` agent (`agents/grok_build.py`) for Grok Build CLI with Composer 2.5 routing. Pass `--env modal` to run in parallel sandboxes on Modal.

### Subsets and single tasks

Deterministic random subset of the 113-task corpus:

```bash
pier run -p deep-swe/tasks --agent mini-swe-agent --n-tasks 10 --sample-seed 0
```

Single task:

```bash
pier run -p deep-swe/tasks/<task-id> --agent mini-swe-agent
```
