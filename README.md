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

### Composer 2.5 via Cursor CLI

The published [DeepSWE leaderboard](https://deepswe.datacurve.ai/) uses `mini-swe-agent` for cross-model consistency. To benchmark Cursor's own agent stack with Composer 2.5, use Pier's `cursor-cli` agent (available on Pier `main`; not yet in the latest PyPI release):

```bash
git clone https://github.com/ivanfioravanti/deep-swe
cd deep-swe
git checkout composer-2.5-support

uv tool install git+https://github.com/datacurve-ai/pier.git

cp .env.example .env
# Add your key from https://cursor.com/dashboard/api

# Smoke test: one task
pier run -p tasks/cliffy-config-file-parsing \
  --agent cursor-cli \
  --model cursor/composer-2.5 \
  --env docker \
  --env-file .env

# Deterministic 10-task subset
pier run -p tasks \
  --agent cursor-cli \
  --model cursor/composer-2.5 \
  --n-tasks 10 \
  --sample-seed 0 \
  --env docker \
  --env-file .env

# Or use the checked-in job config
pier run -c examples/composer-2.5-job.yaml --env-file .env
```

For a full 113-task run in parallel, switch `--env docker` to `--env modal` and configure Modal credentials. Results land in `jobs/`; inspect them with `pier view jobs/<job-name>`.

## What is Pier

[Pier](https://github.com/datacurve-ai/pier) is a [Harbor](https://www.harborframework.com/docs/tasks)-compatible framework for sandboxed coding-agent evals. It began as a fork of Harbor to support CLI agents in air-gapped tasks: Harbor blocks all outbound traffic in `allow_internet = false` tasks, including dependency installs and LLM API calls. Pier adds per-agent network allowlists, giving agents only the network access they need while keeping the task environment isolated.

Pier also adds more complete trajectory metadata, a better trajectory viewer, and `pier critique run` for analyzing agent trajectories. All leaderboard scores were produced with Pier running `mini-swe-agent` on Modal.

### Agents and models

`mini-swe-agent` is model-agnostic. Pier also drives `claude-code`, `codex`, `cursor-cli`, `gemini-cli`, and `opencode` directly. Pass `--env modal` to run in parallel sandboxes on Modal.

### Subsets and single tasks

Deterministic random subset of the 113-task corpus:

```bash
pier run -p deep-swe/tasks --agent mini-swe-agent --n-tasks 10 --sample-seed 0
```

Single task:

```bash
pier run -p deep-swe/tasks/<task-id> --agent mini-swe-agent
```
