"""Skill executor for invoking Claude Agent SDK Skills.

This module provides a wrapper around claude-agent-sdk for invoking
Skills in the diagnosis workflow.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SkillResult:
    """Result from a Skill execution.

    Attributes:
        status: Execution status ("success", "error", "timeout")
        data: Parsed output data
        raw_outputs: Raw message outputs from the SDK
        error: Error message if failed
    """

    status: str = "success"
    data: dict[str, Any] = field(default_factory=dict)
    raw_outputs: list[Any] = field(default_factory=list)
    error: str | None = None

    @property
    def is_success(self) -> bool:
        """Check if execution was successful."""
        return self.status == "success"

    def get(self, key: str, default: Any = None) -> Any:
        """Get data value by key."""
        return self.data.get(key, default)


class SkillExecutorProtocol(Protocol):
    """Protocol for Skill executor implementations."""

    async def invoke(
        self,
        skill_name: str,
        parameters: dict[str, Any],
        timeout: float | None = None,
    ) -> SkillResult:
        """Invoke a Skill.

        Args:
            skill_name: Name of the Skill to invoke
            parameters: Skill parameters
            timeout: Optional timeout in seconds

        Returns:
            SkillResult with execution results
        """
        ...


class SkillExecutor:
    """Executor for invoking Skills via claude-agent-sdk.

    This class wraps the claude-agent-sdk query interface to invoke
    Skills as part of the diagnosis workflow. Skills are defined in
    the project's .claude/skills directory.
    """

    def __init__(
        self,
        project_path: str | Path,
        allowed_tools: list[str] | None = None,
        default_timeout: float = 300.0,
        model: str | None = None,
        permission_mode: str | None = None,
        max_turns: int | None = None,
        max_budget_usd: float | None = None,
    ):
        """Initialize the executor.

        Args:
            project_path: Path to the project with Skills defined
            allowed_tools: List of tools the agent can use (default: Skill, Read, Write, Bash)
            default_timeout: Default timeout in seconds for Skill execution
            model: Claude model to use (e.g., "claude-3-5-haiku-latest")
            permission_mode: Permission mode ("default", "acceptEdits", "plan", "bypassPermissions")
            max_turns: Maximum agent turns (None for unlimited)
            max_budget_usd: Maximum budget in USD (None for unlimited)
        """
        self.project_path = Path(project_path)
        self.allowed_tools = allowed_tools or ["Skill", "Read", "Write", "Bash"]
        self.default_timeout = default_timeout
        self.model = model
        self.permission_mode = permission_mode or "bypassPermissions"
        self.max_turns = max_turns
        self.max_budget_usd = max_budget_usd

    async def invoke(
        self,
        skill_name: str,
        parameters: dict[str, Any],
        timeout: float | None = None,
    ) -> SkillResult:
        """Invoke a Skill by name.

        Args:
            skill_name: Name of the Skill (e.g., "vm-latency-measurement")
            parameters: Dictionary of parameters to pass to the Skill
            timeout: Timeout in seconds (uses default if not specified)

        Returns:
            SkillResult containing execution status and results
        """
        try:
            from claude_agent_sdk import ClaudeAgentOptions, query
        except ImportError:
            logger.error("claude_agent_sdk_not_installed")
            return SkillResult(
                status="error",
                error="claude-agent-sdk is not installed. Install with: uv add claude-agent-sdk",
            )

        timeout = timeout or self.default_timeout
        prompt = self._build_skill_prompt(skill_name, parameters)

        options = ClaudeAgentOptions(
            cwd=str(self.project_path),
            allowed_tools=self.allowed_tools,
            model=self.model,
            permission_mode=self.permission_mode,  # type: ignore[arg-type]
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget_usd,
        )

        log = logger.bind(skill=skill_name, project_path=str(self.project_path))
        log.info("invoking_skill", parameters=list(parameters.keys()))

        try:
            outputs: list[Any] = []

            async def collect_all() -> list[Any]:
                result = []
                async for message in query(prompt=prompt, options=options):
                    result.append(message)
                    log.debug("skill_message", message_type=type(message).__name__)
                return result

            outputs = await asyncio.wait_for(collect_all(), timeout=timeout)

            log.info("skill_completed", output_count=len(outputs))
            return self._parse_skill_output(outputs)

        except asyncio.TimeoutError:
            log.error("skill_timeout", timeout=timeout)
            return SkillResult(
                status="timeout",
                error=f"Skill execution timed out after {timeout} seconds",
            )
        except Exception as e:
            log.exception("skill_execution_error")
            return SkillResult(
                status="error",
                error=str(e),
            )

    def _build_skill_prompt(self, skill_name: str, parameters: dict[str, Any]) -> str:
        """Build the prompt to trigger a Skill.

        The prompt instructs the agent to read and follow the SKILL.md file
        directly, since the sub-agent doesn't have access to registered skills.

        Args:
            skill_name: Name of the Skill
            parameters: Skill parameters

        Returns:
            Formatted prompt string
        """
        params_lines = []
        for key, value in parameters.items():
            if isinstance(value, dict):
                params_lines.append(f"  - {key}:")
                for k, v in value.items():
                    params_lines.append(f"      {k}: {v}")
            elif isinstance(value, list):
                params_lines.append(f"  - {key}:")
                for item in value:
                    params_lines.append(f"      - {item}")
            else:
                params_lines.append(f"  - {key}: {value}")

        params_str = "\n".join(params_lines)
        skill_path = self.project_path / ".claude" / "skills" / skill_name / "SKILL.md"

        return f"""You need to execute the "{skill_name}" skill.

IMPORTANT: First read the skill definition file at: {skill_path}

Then follow the instructions in that file to complete the task with these parameters:

{params_str}

After reading the SKILL.md file, execute the appropriate commands using Bash tool.
Return the collected data in JSON format when complete."""

    def _parse_skill_output(self, outputs: list[Any]) -> SkillResult:
        """Parse Skill output into structured result.

        Args:
            outputs: List of message outputs from the SDK

        Returns:
            SkillResult with parsed data
        """
        import json

        result = SkillResult(
            status="success",
            raw_outputs=outputs,
        )

        text_contents: list[str] = []
        tool_outputs: list[str] = []

        for output in outputs:
            # Handle ResultMessage (final result)
            if hasattr(output, "result") and output.result:
                result.data["final_result"] = output.result
                # Try to parse JSON from result
                self._try_parse_json(output.result, result.data)

            # Handle structured_output from ResultMessage
            if hasattr(output, "structured_output") and output.structured_output:
                result.data["structured_output"] = output.structured_output

            # Handle content list (AssistantMessage, UserMessage)
            if hasattr(output, "content") and isinstance(output.content, list):
                for block in output.content:
                    # TextBlock from AssistantMessage
                    if hasattr(block, "text"):
                        text_contents.append(block.text)
                        # Try to extract JSON from text
                        self._try_parse_json(block.text, result.data)

                    # ToolResultBlock from UserMessage (tool execution results)
                    if hasattr(block, "content") and hasattr(block, "tool_use_id"):
                        if block.content:
                            tool_outputs.append(block.content)
                            # Try to extract JSON from tool output
                            self._try_parse_json(block.content, result.data)

        if text_contents:
            result.data["text_content"] = "\n".join(text_contents)
        if tool_outputs:
            result.data["tool_outputs"] = tool_outputs

        return result

    def _try_parse_json(self, text: str, data: dict[str, Any]) -> bool:
        """Try to parse JSON from text and merge into data.

        Args:
            text: Text that might contain JSON
            data: Dictionary to merge parsed JSON into

        Returns:
            True if JSON was found and parsed
        """
        import json
        import re

        if not isinstance(text, str):
            return False

        # Try direct JSON parse
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, dict):
                data.update(parsed)
                return True
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to find JSON in code blocks
        json_patterns = [
            r"```json\s*\n?(.*?)\n?```",  # ```json ... ```
            r"```\s*\n?(\{.*?\})\n?```",  # ``` {...} ```
            r"(\{[^{}]*\"[^\"]+\"[^{}]*\})",  # Simple JSON object
        ]

        for pattern in json_patterns:
            matches = re.findall(pattern, text, re.DOTALL)
            for match in matches:
                try:
                    parsed = json.loads(match.strip())
                    if isinstance(parsed, dict):
                        data.update(parsed)
                        return True
                except (json.JSONDecodeError, ValueError):
                    continue

        return False


class MockSkillExecutor:
    """Mock executor for testing.

    This executor returns predefined responses without actually
    invoking the claude-agent-sdk.
    """

    def __init__(
        self,
        responses: dict[str, SkillResult] | None = None,
        default_response: SkillResult | None = None,
    ):
        """Initialize mock executor.

        Args:
            responses: Dictionary mapping skill names to responses
            default_response: Default response if skill not in responses
        """
        self.responses = responses or {}
        self.default_response = default_response or SkillResult(
            status="success",
            data={"mock": True},
        )
        self.invocations: list[tuple[str, dict[str, Any]]] = []

    async def invoke(
        self,
        skill_name: str,
        parameters: dict[str, Any],
        timeout: float | None = None,
    ) -> SkillResult:
        """Mock invoke that returns predefined responses.

        Args:
            skill_name: Name of the Skill
            parameters: Skill parameters
            timeout: Ignored in mock

        Returns:
            Predefined SkillResult
        """
        self.invocations.append((skill_name, parameters.copy()))

        if skill_name in self.responses:
            return self.responses[skill_name]
        return self.default_response

    def add_response(self, skill_name: str, response: SkillResult) -> None:
        """Add a response for a skill.

        Args:
            skill_name: Name of the Skill
            response: Response to return
        """
        self.responses[skill_name] = response

    def get_invocations(self, skill_name: str | None = None) -> list[tuple[str, dict[str, Any]]]:
        """Get recorded invocations.

        Args:
            skill_name: Filter by skill name (None for all)

        Returns:
            List of (skill_name, parameters) tuples
        """
        if skill_name is None:
            return self.invocations
        return [(name, params) for name, params in self.invocations if name == skill_name]

    def clear_invocations(self) -> None:
        """Clear recorded invocations."""
        self.invocations.clear()


def create_mock_env_collector_response(
    vm_uuid: str = "test-uuid",
    qemu_pid: int = 12345,
    vnet: str = "vnet0",
) -> SkillResult:
    """Create a mock response for network-env-collector skill.

    Args:
        vm_uuid: VM UUID
        qemu_pid: QEMU process ID
        vnet: vnet interface name

    Returns:
        SkillResult with mock environment data
    """
    return SkillResult(
        status="success",
        data={
            "vm_uuid": vm_uuid,
            "qemu_pid": qemu_pid,
            "nics": [
                {
                    "mac": "52:54:00:00:00:01",
                    "vm_nic_name": "ens4",
                    "vm_ip": "10.0.0.1",
                    "host_vnet": vnet,
                    "tap_fds": [47, 48],
                    "vhost_fds": [51, 52],
                    "vhost_pids": [
                        {"pid": qemu_pid + 100, "name": f"vhost-{qemu_pid}"},
                    ],
                    "ovs_bridge": "ovsbr-test",
                    "uplink_bridge": "ovsbr-test",
                    "physical_nics": [
                        {
                            "name": "eth0",
                            "speed": "10000Mb/s",
                            "is_bond": False,
                        }
                    ],
                }
            ],
        },
    )


def create_mock_measurement_response(
    total_rtt_us: float = 2000.0,
    segments: dict[str, float] | None = None,
) -> SkillResult:
    """Create a mock response for vm-latency-measurement skill.

    Args:
        total_rtt_us: Total RTT in microseconds
        segments: Dictionary of segment name to latency value

    Returns:
        SkillResult with mock measurement data
    """
    if segments is None:
        segments = {
            "A": 100.0,
            "B": 200.0,
            "C_J": 300.0,
            "D": 150.0,
            "E": 250.0,
            "F": 120.0,
            "G": 80.0,
            "H": 100.0,
            "I": 180.0,
            "K": 170.0,
            "L": 200.0,
            "M": 150.0,
        }

    return SkillResult(
        status="success",
        data={
            "total_rtt_us": total_rtt_us,
            "segments": segments,
            "log_files": [
                "sender_vm_kernel_icmp_rtt.log",
                "sender_host_icmp_drop_detector.log",
                "sender_host_kvm_vhost_tun_latency.log",
                "sender_host_tun_tx_to_kvm_irq.log",
                "receiver_vm_kernel_icmp_rtt.log",
                "receiver_host_icmp_drop_detector.log",
                "receiver_host_tun_tx_to_kvm_irq.log",
                "receiver_host_kvm_vhost_tun_latency.log",
            ],
        },
    )


def create_mock_analysis_response(
    primary_contributor: str = "host_ovs",
    confidence: float = 0.85,
) -> SkillResult:
    """Create a mock response for vm-latency-analysis skill.

    Args:
        primary_contributor: Primary latency contributor layer
        confidence: Analysis confidence

    Returns:
        SkillResult with mock analysis data
    """
    return SkillResult(
        status="success",
        data={
            "primary_contributor": primary_contributor,
            "confidence": confidence,
            "probable_causes": [
                {
                    "cause": "OVS flow table miss causing upcall",
                    "confidence": 0.8,
                    "evidence": ["High B segment latency", "Elevated upcall count"],
                    "layer": "host_ovs",
                }
            ],
            "recommendations": [
                {
                    "action": "Review OVS flow rules for optimization",
                    "priority": "high",
                    "rationale": "Flow misses increase latency significantly",
                }
            ],
            "reasoning": "Analysis based on segment data shows HOST_OVS layer contributing most latency.",
        },
    )
