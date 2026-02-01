"""
Main Orchestrator Agent implementation.

This is the primary agent that coordinates the four-layer diagnostic workflow,
invoking subagents in sequence: L1 (direct) → L2 → L3 → L4.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from claude_code_sdk import Agent, query

from netsherlock.schemas.config import DiagnosisRequestSource
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus

from .base import AlertContext
from .prompts import get_main_prompt
from .subagents import (
    L2EnvironmentSubagent,
    L3MeasurementSubagent,
    L4AnalysisSubagent,
)

if TYPE_CHECKING:
    from netsherlock.config.settings import Settings


class NetworkTroubleshootingOrchestrator:
    """
    Main orchestrator agent for network troubleshooting.

    Coordinates the four-layer diagnostic workflow:
    1. L1: Query base monitoring data (Grafana, Loki, node logs)
    2. L2: Collect network environment via subagent
    3. L3: Execute precise measurements via subagent
    4. L4: Analyze and diagnose via subagent
    """

    def __init__(
        self,
        settings: Settings | None = None,
        model: str | None = None,
        compact_prompts: bool | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            settings: Application settings (uses default if None)
            model: Override model from settings
            compact_prompts: Override compact_prompts from settings
        """
        # Load settings if not provided
        if settings is None:
            from netsherlock.config.settings import get_settings
            settings = get_settings()

        self._settings = settings

        # LLM configuration (overrides take precedence)
        self.model = model if model is not None else settings.llm.model
        self.compact_prompts = (
            compact_prompts if compact_prompts is not None else settings.llm.compact_prompts
        )
        self.system_prompt = get_main_prompt(compact=self.compact_prompts)

        # Grafana configuration from settings
        self.grafana_url = settings.grafana.base_url
        self.grafana_auth = (
            settings.grafana.username,
            settings.grafana.password.get_secret_value() if settings.grafana.password else "",
        )

        # Initialize subagents with same settings
        self._l2_subagent = L2EnvironmentSubagent(
            settings=settings, model=self.model, compact_prompt=self.compact_prompts
        )
        self._l3_subagent = L3MeasurementSubagent(
            settings=settings, model=self.model, compact_prompt=self.compact_prompts
        )
        self._l4_subagent = L4AnalysisSubagent(
            settings=settings, model=self.model, compact_prompt=self.compact_prompts
        )

        # L1 tools for direct access
        self._l1_tools = self._create_l1_tools()

    def _create_l1_tools(self) -> list[dict[str, Any]]:
        """Create L1 monitoring tool definitions."""
        return [
            {
                "name": "grafana_query_metrics",
                "description": "Query Prometheus metrics from Grafana/VictoriaMetrics",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "PromQL query"},
                        "start": {"type": "string", "description": "Start time (e.g., 'now-1h')"},
                        "end": {"type": "string", "description": "End time (e.g., 'now')"},
                        "step": {"type": "string", "description": "Query step (e.g., '1m')"},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "loki_query_logs",
                "description": "Query logs from Loki",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "LogQL query"},
                        "start": {"type": "string", "description": "Start time"},
                        "end": {"type": "string", "description": "End time"},
                        "limit": {"type": "integer", "description": "Max results", "default": 100},
                    },
                    "required": ["query"],
                },
            },
            {
                "name": "read_pingmesh_logs",
                "description": "Read pingmesh/l2ping/high-latency logs from node via SSH",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "node_ip": {"type": "string", "description": "Node IP address"},
                        "log_type": {
                            "type": "string",
                            "enum": ["pingmesh", "l2ping", "network-high-latency"],
                            "description": "Type of log to read",
                        },
                        "lines": {"type": "integer", "description": "Number of lines", "default": 100},
                    },
                    "required": ["node_ip", "log_type"],
                },
            },
            {
                "name": "invoke_l2_subagent",
                "description": "Invoke L2 Environment Awareness subagent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "context": {"type": "object", "description": "Alert context or problem description"},
                    },
                    "required": ["context"],
                },
            },
            {
                "name": "invoke_l3_subagent",
                "description": "Invoke L3 Precise Measurement subagent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "environment": {"type": "object", "description": "NetworkEnvironment from L2"},
                    },
                    "required": ["environment"],
                },
            },
            {
                "name": "invoke_l4_subagent",
                "description": "Invoke L4 Diagnostic Analysis subagent",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "measurements": {"type": "object", "description": "MeasurementResult from L3"},
                        "environment": {"type": "object", "description": "NetworkEnvironment from L2"},
                        "l1_context": {"type": "object", "description": "L1 monitoring data"},
                    },
                    "required": ["measurements"],
                },
            },
        ]

    async def diagnose_alert(self, alert: dict[str, Any]) -> DiagnosisResult:
        """Process an incoming alert and generate diagnosis.

        Args:
            alert: Alert payload from Grafana/Alertmanager

        Returns:
            DiagnosisResult with root cause and recommendations
        """
        # Parse alert context
        alert_context = self._parse_alert(alert)

        # Generate diagnosis ID
        diagnosis_id = f"diag-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now(timezone.utc).isoformat() + "Z"

        # Run the orchestrated workflow
        prompt = f"""
Process the following alert and generate a diagnosis:

Alert: {alert_context.alertname}
Instance: {alert_context.instance}
Severity: {alert_context.severity}
Labels: {alert_context.labels}
Annotations: {alert_context.annotations}

Follow the diagnostic workflow:
1. Query L1 metrics to understand the current state
2. Invoke L2 subagent to collect environment
3. Invoke L3 subagent to execute measurements
4. Invoke L4 subagent to analyze and diagnose

Return a complete diagnosis with root cause and recommendations.
"""

        async with Agent(
            model=self.model,
            system=self.system_prompt,
            tools=self._l1_tools,
        ) as agent:
            result = await query(agent, prompt)

        return self._synthesize_diagnosis(
            diagnosis_id=diagnosis_id,
            timestamp=timestamp,
            alert_context=alert_context,
            agent_result=result,
        )

    async def diagnose_request(self, request: dict[str, Any]) -> DiagnosisResult:
        """Process a manual diagnostic request.

        Args:
            request: Manual request with problem description

        Returns:
            DiagnosisResult with root cause and recommendations
        """
        diagnosis_id = f"diag-{uuid.uuid4().hex[:8]}"
        timestamp = datetime.now(timezone.utc).isoformat() + "Z"

        problem_type = request.get("problem_type", "unknown")
        src_node = request.get("src_node", "")
        dst_node = request.get("dst_node", "")
        vm_name = request.get("vm_name", "")

        prompt = f"""
Process the following diagnostic request:

Problem Type: {problem_type}
Source Node: {src_node}
Destination Node: {dst_node}
VM Name: {vm_name if vm_name else 'N/A'}

Additional Info: {request.get('description', 'No additional info')}

Follow the diagnostic workflow:
1. Query L1 metrics to understand the current state
2. Invoke L2 subagent to collect environment
3. Invoke L3 subagent to execute measurements
4. Invoke L4 subagent to analyze and diagnose

Return a complete diagnosis with root cause and recommendations.
"""

        async with Agent(
            model=self.model,
            system=self.system_prompt,
            tools=self._l1_tools,
        ) as agent:
            result = await query(agent, prompt)

        return self._synthesize_diagnosis(
            diagnosis_id=diagnosis_id,
            timestamp=timestamp,
            alert_context=None,
            agent_result=result,
        )

    def _parse_alert(self, alert: dict[str, Any]) -> AlertContext:
        """Parse raw alert into AlertContext."""
        labels = alert.get("labels", {})
        annotations = alert.get("annotations", {})

        return AlertContext(
            alertname=labels.get("alertname", "unknown"),
            instance=labels.get("instance", ""),
            severity=labels.get("severity", "warning"),
            labels=labels,
            annotations=annotations,
        )

    def _synthesize_diagnosis(
        self,
        diagnosis_id: str,
        timestamp: str,
        alert_context: AlertContext | None,
        agent_result: Any,
    ) -> DiagnosisResult:
        """Synthesize final diagnosis from agent result.

        Extracts text from the Claude Agent SDK result, attempts to parse
        structured JSON (if the agent returned a JSON block), and falls back
        to using the raw text as the summary.

        Args:
            diagnosis_id: Unique identifier for this diagnosis.
            timestamp: ISO timestamp string for when diagnosis started.
            alert_context: Parsed alert context (if alert-triggered).
            agent_result: Raw output from claude_code_sdk.query().

        Returns:
            Unified DiagnosisResult.
        """
        started_at = self._parse_timestamp(timestamp)

        # Extract text content from agent result
        text_content = self._extract_text_from_result(agent_result)

        # Try to parse structured JSON from the text
        structured = self._try_parse_json(text_content)

        if structured:
            return DiagnosisResult.from_orchestrator_output(
                diagnosis_id=diagnosis_id,
                agent_result=structured,
                started_at=started_at,
                completed_at=datetime.now(timezone.utc),
                source=DiagnosisRequestSource.WEBHOOK if alert_context else DiagnosisRequestSource.CLI,
            )

        # Fallback: use raw text as summary
        return DiagnosisResult(
            diagnosis_id=diagnosis_id,
            status=DiagnosisStatus.COMPLETED,
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
            summary=text_content[:2000] if text_content else "No diagnosis output",
        )

    @staticmethod
    def _extract_text_from_result(agent_result: Any) -> str:
        """Extract text content from Claude Agent SDK query result.

        The SDK returns message objects; we concatenate all text blocks.
        """
        if agent_result is None:
            return ""
        if isinstance(agent_result, str):
            return agent_result

        # agent_result may be a list of messages or a single message
        texts = []
        items = agent_result if isinstance(agent_result, list) else [agent_result]
        for item in items:
            if isinstance(item, str):
                texts.append(item)
            elif hasattr(item, "content"):
                # Message object with content blocks
                content = item.content
                if isinstance(content, str):
                    texts.append(content)
                elif isinstance(content, list):
                    for block in content:
                        if hasattr(block, "text"):
                            texts.append(block.text)
                        elif isinstance(block, dict) and "text" in block:
                            texts.append(block["text"])
            elif isinstance(item, dict):
                if "text" in item:
                    texts.append(item["text"])
                elif "content" in item:
                    texts.append(str(item["content"]))

        return "\n".join(texts) if texts else str(agent_result)

    @staticmethod
    def _try_parse_json(text: str) -> dict[str, Any] | None:
        """Try to extract a JSON object from text.

        Looks for ```json ... ``` blocks first, then tries the whole text.
        """
        if not text:
            return None

        # Try to find a fenced JSON block
        json_start = text.find("```json")
        if json_start != -1:
            json_body_start = text.index("\n", json_start) + 1
            json_end = text.find("```", json_body_start)
            if json_end != -1:
                try:
                    return json.loads(text[json_body_start:json_end])
                except (json.JSONDecodeError, ValueError):
                    pass

        # Try to find a raw JSON object in the text
        brace_start = text.find("{")
        brace_end = text.rfind("}")
        if brace_start != -1 and brace_end > brace_start:
            try:
                return json.loads(text[brace_start : brace_end + 1])
            except (json.JSONDecodeError, ValueError):
                pass

        return None

    @staticmethod
    def _parse_timestamp(timestamp: str) -> datetime | None:
        """Parse ISO timestamp string to datetime."""
        if not timestamp:
            return None
        try:
            return datetime.fromisoformat(timestamp.rstrip("Z"))
        except (ValueError, AttributeError):
            return None


# Convenience function to create orchestrator
def create_orchestrator(
    settings: Settings | None = None,
    model: str | None = None,
    compact_prompts: bool | None = None,
) -> NetworkTroubleshootingOrchestrator:
    """Create a network troubleshooting orchestrator.

    Args:
        settings: Application settings (uses default if None)
        model: Override model from settings
        compact_prompts: Override compact_prompts from settings

    Returns:
        Configured orchestrator instance
    """
    return NetworkTroubleshootingOrchestrator(
        settings=settings,
        model=model,
        compact_prompts=compact_prompts,
    )
