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
    ):
        """Initialize the executor.

        Args:
            project_path: Path to the project with Skills defined
            allowed_tools: List of tools the agent can use (default: Skill, Read, Write, Bash)
            default_timeout: Default timeout in seconds for Skill execution
        """
        self.project_path = Path(project_path)
        self.allowed_tools = allowed_tools or ["Skill", "Read", "Write", "Bash"]
        self.default_timeout = default_timeout

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
                error="claude-agent-sdk is not installed. Install with: pip install claude-agent-sdk",
            )

        timeout = timeout or self.default_timeout
        prompt = self._build_skill_prompt(skill_name, parameters)

        options = ClaudeAgentOptions(
            cwd=str(self.project_path),
            setting_sources=["project"],
            allowed_tools=self.allowed_tools,
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

        return f"""Execute the {skill_name} skill with the following parameters:

{params_str}

Please run the complete workflow and return the collected data."""

    def _parse_skill_output(self, outputs: list[Any]) -> SkillResult:
        """Parse Skill output into structured result.

        Args:
            outputs: List of message outputs from the SDK

        Returns:
            SkillResult with parsed data
        """
        result = SkillResult(
            status="success",
            raw_outputs=outputs,
        )

        # Extract structured data from outputs
        for output in outputs:
            # Handle different message types
            if hasattr(output, "content"):
                content = output.content
                # Try to extract JSON data from content
                if isinstance(content, str):
                    result.data["text_content"] = content
                elif isinstance(content, dict):
                    result.data.update(content)

            # Handle tool results
            if hasattr(output, "tool_results"):
                for tool_result in output.tool_results:
                    if hasattr(tool_result, "content"):
                        if "tool_outputs" not in result.data:
                            result.data["tool_outputs"] = []
                        result.data["tool_outputs"].append(tool_result.content)

        return result


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
