"""
Subagent implementations using Claude Agent SDK.

This module implements the L2, L3, and L4 subagents that are invoked
by the main orchestrator agent.
"""

from typing import Any

from claude_code_sdk import Agent, query

from .prompts import get_l2_prompt, get_l3_prompt, get_l4_prompt
from .base import (
    AlertContext,
    NetworkEnvironment,
    MeasurementResult,
    DiagnosisResult,
)


class L2EnvironmentSubagent:
    """
    L2 Environment Awareness Subagent.

    Responsible for collecting network topology and environment information
    needed for precise L3 measurements.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514", compact_prompt: bool = False):
        """Initialize the L2 subagent.

        Args:
            model: Claude model to use
            compact_prompt: Use compact prompt for token efficiency
        """
        self.model = model
        self.system_prompt = get_l2_prompt(compact=compact_prompt)
        self._tools = self._create_tools()

    def _create_tools(self) -> list[dict[str, Any]]:
        """Create MCP tool definitions for L2."""
        return [
            {
                "name": "collect_vm_network_env",
                "description": "Collect VM network environment via SSH",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "node_ip": {"type": "string", "description": "Management IP of the host"},
                        "vm_identifier": {"type": "string", "description": "VM name or UUID"},
                    },
                    "required": ["node_ip", "vm_identifier"],
                },
            },
            {
                "name": "collect_system_network_env",
                "description": "Collect system network environment via SSH",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "node_ip": {"type": "string", "description": "Management IP of the host"},
                        "network_type": {
                            "type": "string",
                            "enum": ["storage", "management", "business"],
                            "description": "Type of network to collect",
                        },
                    },
                    "required": ["node_ip", "network_type"],
                },
            },
            {
                "name": "resolve_network_path",
                "description": "Resolve complete data path between source and destination",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "src_env": {"type": "object", "description": "Source environment"},
                        "dst_env": {"type": "object", "description": "Destination environment"},
                        "flow": {"type": "object", "description": "Flow characteristics"},
                    },
                    "required": ["src_env", "dst_env"],
                },
            },
        ]

    async def invoke(self, context: dict[str, Any]) -> NetworkEnvironment:
        """Invoke the L2 subagent to collect environment.

        Args:
            context: Alert context or problem description

        Returns:
            NetworkEnvironment with collected topology
        """
        prompt = f"""
Collect the network environment for the following context:

{context}

Use the available tools to gather complete network topology information.
Output the structured NetworkEnvironment when done.
"""
        # Use Claude Agent SDK to run the subagent
        async with Agent(
            model=self.model,
            system=self.system_prompt,
            tools=self._tools,
        ) as agent:
            result = await query(agent, prompt)

        return self._parse_environment(result)

    def _parse_environment(self, result: Any) -> NetworkEnvironment:
        """Parse agent result into NetworkEnvironment."""
        # Implementation would parse the agent's structured output
        # For now, return a placeholder
        raise NotImplementedError("Environment parsing to be implemented with MCP tools")


class L3MeasurementSubagent:
    """
    L3 Precise Measurement Subagent.

    Responsible for executing BCC/eBPF measurement tools and collecting
    precise network performance data.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514", compact_prompt: bool = False):
        """Initialize the L3 subagent.

        Args:
            model: Claude model to use
            compact_prompt: Use compact prompt for token efficiency
        """
        self.model = model
        self.system_prompt = get_l3_prompt(compact=compact_prompt)
        self._tools = self._create_tools()

    def _create_tools(self) -> list[dict[str, Any]]:
        """Create MCP tool definitions for L3."""
        return [
            {
                "name": "execute_coordinated_measurement",
                "description": "Execute coordinated measurement on sender and receiver nodes",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "measurement_type": {
                            "type": "string",
                            "enum": ["vm_latency", "system_latency", "packet_drop"],
                        },
                        "receiver": {
                            "type": "object",
                            "properties": {
                                "node_ip": {"type": "string"},
                                "tool": {"type": "string"},
                                "args": {"type": "object"},
                            },
                            "required": ["node_ip", "tool", "args"],
                        },
                        "sender": {
                            "type": "object",
                            "properties": {
                                "node_ip": {"type": "string"},
                                "tool": {"type": "string"},
                                "args": {"type": "object"},
                            },
                            "required": ["node_ip", "tool", "args"],
                        },
                        "duration_seconds": {"type": "integer", "default": 30},
                    },
                    "required": ["measurement_type", "receiver", "sender"],
                },
            },
            {
                "name": "measure_vm_latency_breakdown",
                "description": "Measure VM network latency breakdown by segment",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "src_node_ip": {"type": "string"},
                        "dst_node_ip": {"type": "string"},
                        "src_vm": {"type": "object"},
                        "dst_vm": {"type": "object"},
                        "flow": {"type": "object"},
                        "duration_seconds": {"type": "integer", "default": 30},
                    },
                    "required": ["src_node_ip", "dst_node_ip", "src_vm", "dst_vm"],
                },
            },
            {
                "name": "measure_system_latency_breakdown",
                "description": "Measure system network latency breakdown by segment",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "src_node_ip": {"type": "string"},
                        "dst_node_ip": {"type": "string"},
                        "src_network": {"type": "object"},
                        "dst_network": {"type": "object"},
                        "protocol": {"type": "string", "default": "icmp"},
                        "duration_seconds": {"type": "integer", "default": 30},
                    },
                    "required": ["src_node_ip", "dst_node_ip", "src_network", "dst_network"],
                },
            },
            {
                "name": "detect_packet_drops",
                "description": "Detect and localize packet drops in network path",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "src_node_ip": {"type": "string"},
                        "dst_node_ip": {"type": "string"},
                        "path_type": {"type": "string"},
                        "flow": {"type": "object"},
                        "duration_seconds": {"type": "integer", "default": 60},
                    },
                    "required": ["src_node_ip", "dst_node_ip", "path_type"],
                },
            },
        ]

    async def invoke(self, environment: NetworkEnvironment) -> MeasurementResult:
        """Invoke the L3 subagent to execute measurements.

        Args:
            environment: NetworkEnvironment from L2

        Returns:
            MeasurementResult with segment data
        """
        prompt = f"""
Execute measurements for the following network environment:

Problem Type: {environment.problem_type.value}
Measurement Type: {environment.measurement_type}
Source: {environment.source.node_ip}
Destination: {environment.destination.node_ip if environment.destination else 'N/A'}

Use the appropriate measurement tools and return structured results.
"""
        async with Agent(
            model=self.model,
            system=self.system_prompt,
            tools=self._tools,
        ) as agent:
            result = await query(agent, prompt)

        return self._parse_measurement(result)

    def _parse_measurement(self, result: Any) -> MeasurementResult:
        """Parse agent result into MeasurementResult."""
        raise NotImplementedError("Measurement parsing to be implemented with MCP tools")


class L4AnalysisSubagent:
    """
    L4 Diagnostic Analysis Subagent.

    Responsible for analyzing measurement data, identifying root causes,
    and generating actionable diagnostic reports.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514", compact_prompt: bool = False):
        """Initialize the L4 subagent.

        Args:
            model: Claude model to use
            compact_prompt: Use compact prompt for token efficiency
        """
        self.model = model
        self.system_prompt = get_l4_prompt(compact=compact_prompt)
        self._tools = self._create_tools()

    def _create_tools(self) -> list[dict[str, Any]]:
        """Create MCP tool definitions for L4."""
        return [
            {
                "name": "analyze_latency_segments",
                "description": "Analyze latency segments and detect anomalies",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "segments": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Latency segment data from L3",
                        },
                        "thresholds": {
                            "type": "object",
                            "description": "Optional custom thresholds per layer",
                        },
                    },
                    "required": ["segments"],
                },
            },
            {
                "name": "identify_root_cause",
                "description": "Map anomalies to root cause categories",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "anomalies": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Detected anomalies from analysis",
                        },
                        "environment": {
                            "type": "object",
                            "description": "Network environment context",
                        },
                    },
                    "required": ["anomalies"],
                },
            },
            {
                "name": "generate_diagnosis_report",
                "description": "Generate structured diagnostic report",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "root_cause": {"type": "object", "description": "Root cause analysis"},
                        "measurements": {"type": "object", "description": "Measurement summary"},
                        "context": {"type": "object", "description": "Alert and environment context"},
                    },
                    "required": ["root_cause", "measurements"],
                },
            },
        ]

    async def invoke(
        self,
        measurements: MeasurementResult,
        environment: NetworkEnvironment | None = None,
        l1_context: dict[str, Any] | None = None,
    ) -> DiagnosisResult:
        """Invoke the L4 subagent to analyze measurements.

        Args:
            measurements: MeasurementResult from L3
            environment: NetworkEnvironment from L2 (optional)
            l1_context: L1 monitoring context (optional)

        Returns:
            DiagnosisResult with root cause and recommendations
        """
        prompt = f"""
Analyze the following measurement results and provide a diagnosis:

Measurement Type: {measurements.measurement_type}
Duration: {measurements.duration_seconds}s
Sample Count: {measurements.sample_count}

Segments:
{self._format_segments(measurements.segments)}

Total Latency:
{measurements.total_latency}

Analyze the data, identify the root cause, and generate a diagnosis report.
"""
        async with Agent(
            model=self.model,
            system=self.system_prompt,
            tools=self._tools,
        ) as agent:
            result = await query(agent, prompt)

        return self._parse_diagnosis(result)

    def _format_segments(self, segments: list) -> str:
        """Format segments for prompt."""
        lines = []
        for seg in segments:
            lines.append(f"- {seg.name} ({seg.layer}): {seg.histogram}")
        return "\n".join(lines)

    def _parse_diagnosis(self, result: Any) -> DiagnosisResult:
        """Parse agent result into DiagnosisResult."""
        raise NotImplementedError("Diagnosis parsing to be implemented with MCP tools")


# Factory function for creating subagents
def create_subagent(
    layer: str,
    model: str = "claude-sonnet-4-20250514",
    compact_prompt: bool = False,
) -> L2EnvironmentSubagent | L3MeasurementSubagent | L4AnalysisSubagent:
    """Create a subagent for the specified layer.

    Args:
        layer: "l2", "l3", or "l4"
        model: Claude model to use
        compact_prompt: Use compact prompt for token efficiency

    Returns:
        Subagent instance for the specified layer
    """
    subagents = {
        "l2": L2EnvironmentSubagent,
        "l3": L3MeasurementSubagent,
        "l4": L4AnalysisSubagent,
    }

    if layer.lower() not in subagents:
        raise ValueError(f"Unknown layer: {layer}. Must be one of: l2, l3, l4")

    return subagents[layer.lower()](model=model, compact_prompt=compact_prompt)
