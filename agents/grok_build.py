"""Pier agent adapter for Grok Build CLI with Composer 2.5 routing."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from pier.agents.installed.base import BaseInstalledAgent, CliFlag, with_prompt_template
from pier.agents.network import allowlist_from_urls
from pier.environments.base import BaseEnvironment
from pier.models.agent.context import AgentContext
from pier.models.agent.install import AgentInstallSpec, InstallStep
from pier.models.agent.network import NetworkAllowlist
from pier.models.trajectories import Agent, FinalMetrics, Step, Trajectory
from pier.utils.trajectory_metrics import (
    extra_with_context_metrics,
    peak_context_tokens_from_steps,
    populate_context_from_final_metrics,
)
from pier.utils.trajectory_utils import format_trajectory_json


class GrokBuild(BaseInstalledAgent):
    """Run DeepSWE tasks through Grok Build CLI.

    Use model names like ``grok/grok-composer-2.5-fast`` to route inference
    through Grok's Cursor-backed Composer 2.5 harness, or ``grok/grok-build``
    for the native xAI coding agent.
    """

    SUPPORTS_ATIF: bool = True
    _OUTPUT_FILENAME = "grok-build.txt"

    CLI_FLAGS = [
        CliFlag("max_turns", cli="--max-turns", type="int"),
        CliFlag(
            "effort",
            cli="--effort",
            type="enum",
            choices=["low", "medium", "high", "xhigh", "max"],
        ),
        CliFlag("no_plan", cli="--no-plan", type="bool", default=True),
        CliFlag("no_subagents", cli="--no-subagents", type="bool"),
        CliFlag("disable_web_search", cli="--disable-web-search", type="bool"),
    ]

    @staticmethod
    def name() -> str:
        return "grok-build"

    def get_version_command(self) -> str | None:
        return 'export PATH="$HOME/.local/bin:$PATH"; grok version'

    def network_allowlist(self) -> NetworkAllowlist:
        return allowlist_from_urls(
            [],
            default_domains=[
                "grok.com",
                ".grok.com",
                "x.ai",
                "cli-chat-proxy.grok.com",
                "cursor.com",
                "api.cursor.sh",
                "api2.cursor.sh",
                "api3.cursor.sh",
                ".cursor.sh",
            ],
        )

    def install_spec(self) -> AgentInstallSpec:
        return AgentInstallSpec(
            agent_name=self.name(),
            version=self._version,
            steps=[
                InstallStep(
                    user="root",
                    env={"DEBIAN_FRONTEND": "noninteractive"},
                    run=("apt-get update && apt-get install -y curl ca-certificates"),
                ),
                InstallStep(
                    user="agent",
                    run=(
                        "set -euo pipefail; "
                        "curl -fsSL https://x.ai/cli/install.sh | bash && "
                        'export PATH="$HOME/.local/bin:$PATH" && '
                        "grok version"
                    ),
                ),
            ],
            verification_command=self.get_version_command(),
        )

    def _resolve_model_id(self) -> str:
        if not self.model_name:
            return "grok-composer-2.5-fast"
        return self.model_name.split("/", 1)[-1]

    def _build_config_command(self) -> str:
        model_id = self._resolve_model_id()
        config = (
            "[models]\n"
            f'default = "{model_id}"\n\n'
            "[cli]\n"
            "auto_update = false\n"
        )
        quoted = shlex.quote(config)
        return (
            "mkdir -p ~/.grok && "
            f"printf '%s\\n' {quoted} > ~/.grok/config.toml"
        )

    def _parse_stdout(self) -> list[dict[str, Any]]:
        output_path = self.logs_dir / self._OUTPUT_FILENAME
        if not output_path.exists():
            return []

        events: list[dict[str, Any]] = []
        for line in output_path.read_text().splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        return events

    def _convert_events_to_trajectory(
        self,
        events: list[dict[str, Any]],
    ) -> Trajectory | None:
        session_id: str | None = None
        steps: list[Step] = []
        step_id = 1
        assistant_text: list[str] = []
        reasoning_text: list[str] = []
        final_metrics = FinalMetrics()

        for event in events:
            event_type = event.get("type")
            if event_type == "text":
                data = event.get("data")
                if isinstance(data, str) and data:
                    assistant_text.append(data)
            elif event_type == "thought":
                data = event.get("data")
                if isinstance(data, str) and data:
                    reasoning_text.append(data)
            elif event_type == "end":
                session_id = event.get("sessionId") or session_id
                if assistant_text or reasoning_text:
                    steps.append(
                        Step(
                            step_id=step_id,
                            source="agent",
                            model_name=self.model_name,
                            message="".join(assistant_text).strip(),
                            reasoning_content="".join(reasoning_text).strip() or None,
                            llm_call_count=1,
                        )
                    )
                    step_id += 1
                    assistant_text.clear()
                    reasoning_text.clear()
                extra = dict(final_metrics.extra or {})
                if event.get("requestId"):
                    extra["request_id"] = event["requestId"]
                if event.get("stopReason"):
                    extra["stop_reason"] = event["stopReason"]
                final_metrics.extra = extra
            elif event_type == "error":
                extra = dict(final_metrics.extra or {})
                extra["is_error"] = True
                if event.get("message"):
                    extra["error_message"] = event["message"]
                final_metrics.extra = extra

        if assistant_text or reasoning_text:
            steps.append(
                Step(
                    step_id=step_id,
                    source="agent",
                    model_name=self.model_name,
                    message="".join(assistant_text).strip(),
                    reasoning_content="".join(reasoning_text).strip() or None,
                    llm_call_count=1,
                )
            )

        if not steps:
            return None

        final_metrics.total_steps = len(steps)
        final_metrics.extra = extra_with_context_metrics(
            final_metrics.extra,
            peak_context_tokens=peak_context_tokens_from_steps(steps),
            summarization_count=None,
        )

        return Trajectory(
            schema_version="ATIF-v1.7",
            session_id=session_id or "unknown",
            agent=Agent(
                name=self.name(),
                version=self.version() or "unknown",
                model_name=self.model_name,
            ),
            steps=steps,
            final_metrics=final_metrics,
        )

    def populate_context_post_run(self, context: AgentContext) -> None:
        events = self._parse_stdout()
        if not events:
            return

        try:
            trajectory = self._convert_events_to_trajectory(events)
        except Exception:
            self.logger.exception("Failed to convert Grok Build events to trajectory")
            return

        if not trajectory:
            return

        trajectory_path = self.logs_dir / "trajectory.json"
        try:
            trajectory_path.write_text(
                format_trajectory_json(trajectory.to_json_dict())
            )
        except OSError as exc:
            self.logger.debug("Failed to write trajectory file %s: %s", trajectory_path, exc)

        if trajectory.final_metrics:
            populate_context_from_final_metrics(context, trajectory.final_metrics)

    @with_prompt_template
    async def run(
        self,
        instruction: str,
        environment: BaseEnvironment,
        context: AgentContext,
    ) -> None:
        model_id = self._resolve_model_id()
        env = self.build_process_env(
            {
                "XAI_API_KEY": self._get_env("XAI_API_KEY"),
                "GROK_DISABLE_AUTOUPDATER": "1",
            }
        )
        if "XAI_API_KEY" not in env and not self._get_env("GROK_AUTH_JSON"):
            raise ValueError(
                "Grok Build requires XAI_API_KEY or GROK_AUTH_JSON. "
                "Set one in the process environment or pass --env-file .env."
            )

        await self.exec_as_agent(environment, command=self._build_config_command(), env=env)

        auth_json = self._get_env("GROK_AUTH_JSON")
        if auth_json:
            quoted_auth = shlex.quote(auth_json)
            await self.exec_as_agent(
                environment,
                command=f"mkdir -p ~/.grok && printf '%s' {quoted_auth} > ~/.grok/auth.json",
                env=env,
            )

        cli_flags = self.build_cli_flags()
        extra_flags = f"{cli_flags} " if cli_flags else ""
        escaped_instruction = shlex.quote(instruction)
        escaped_model = shlex.quote(model_id)

        await self.exec_as_agent(
            environment,
            command=(
                'export PATH="$HOME/.local/bin:$PATH"; '
                "grok -p "
                f"{escaped_instruction} "
                f"-m {escaped_model} "
                f"{extra_flags}"
                "--yolo --no-auto-update --output-format streaming-json "
                f"2>&1 | stdbuf -oL tee /logs/agent/{self._OUTPUT_FILENAME}"
            ),
            env=env,
        )