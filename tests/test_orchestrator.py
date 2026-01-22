"""Tests for NetworkTroubleshootingOrchestrator."""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock the claude_code_sdk module before importing orchestrator
mock_sdk = MagicMock()
sys.modules["claude_code_sdk"] = mock_sdk

from netsherlock.agents.base import (
    AlertContext,
    DiagnosisResult,
    Recommendation,
    RootCause,
    RootCauseCategory,
)
from netsherlock.agents.orchestrator import (
    NetworkTroubleshootingOrchestrator,
    create_orchestrator,
)


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create mock settings."""
    settings = MagicMock()

    # LLM settings
    settings.llm.model = "claude-sonnet-4-20250514"
    settings.llm.compact_prompts = False

    # Grafana settings
    settings.grafana.base_url = "http://test-grafana/grafana"
    settings.grafana.username = "test-user"
    settings.grafana.password = MagicMock()
    settings.grafana.password.get_secret_value.return_value = "test-password"

    return settings


class TestNetworkTroubleshootingOrchestratorInit:
    """Tests for orchestrator initialization."""

    def test_init_with_settings(self, mock_settings: MagicMock) -> None:
        """Initialize with provided settings."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        assert orchestrator.model == "claude-sonnet-4-20250514"
        assert orchestrator.compact_prompts is False
        assert orchestrator.grafana_url == "http://test-grafana/grafana"

    def test_init_with_model_override(self, mock_settings: MagicMock) -> None:
        """Model override takes precedence over settings."""
        orchestrator = NetworkTroubleshootingOrchestrator(
            settings=mock_settings,
            model="claude-opus-4-20250514",
        )

        assert orchestrator.model == "claude-opus-4-20250514"

    def test_init_with_compact_prompts_override(self, mock_settings: MagicMock) -> None:
        """compact_prompts override takes precedence over settings."""
        orchestrator = NetworkTroubleshootingOrchestrator(
            settings=mock_settings,
            compact_prompts=True,
        )

        assert orchestrator.compact_prompts is True

    def test_init_creates_subagents(self, mock_settings: MagicMock) -> None:
        """Subagents are created during initialization."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        assert orchestrator._l2_subagent is not None
        assert orchestrator._l3_subagent is not None
        assert orchestrator._l4_subagent is not None

    @patch("netsherlock.config.settings.get_settings")
    def test_init_without_settings_uses_default(
        self, mock_get_settings: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Uses default settings when none provided."""
        mock_get_settings.return_value = mock_settings

        orchestrator = NetworkTroubleshootingOrchestrator()

        mock_get_settings.assert_called()
        assert orchestrator._settings == mock_settings


class TestL1ToolsCreation:
    """Tests for L1 tool creation."""

    def test_create_l1_tools_returns_list(self, mock_settings: MagicMock) -> None:
        """_create_l1_tools returns a list of tool definitions."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        tools = orchestrator._create_l1_tools()

        assert isinstance(tools, list)
        assert len(tools) == 6

    def test_l1_tools_contain_grafana_query_metrics(self, mock_settings: MagicMock) -> None:
        """L1 tools include grafana_query_metrics."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        tools = orchestrator._create_l1_tools()
        tool_names = [t["name"] for t in tools]

        assert "grafana_query_metrics" in tool_names

    def test_l1_tools_contain_loki_query_logs(self, mock_settings: MagicMock) -> None:
        """L1 tools include loki_query_logs."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        tools = orchestrator._create_l1_tools()
        tool_names = [t["name"] for t in tools]

        assert "loki_query_logs" in tool_names

    def test_l1_tools_contain_read_pingmesh_logs(self, mock_settings: MagicMock) -> None:
        """L1 tools include read_pingmesh_logs."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        tools = orchestrator._create_l1_tools()
        tool_names = [t["name"] for t in tools]

        assert "read_pingmesh_logs" in tool_names

    def test_l1_tools_contain_subagent_invocations(self, mock_settings: MagicMock) -> None:
        """L1 tools include subagent invocation tools."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        tools = orchestrator._create_l1_tools()
        tool_names = [t["name"] for t in tools]

        assert "invoke_l2_subagent" in tool_names
        assert "invoke_l3_subagent" in tool_names
        assert "invoke_l4_subagent" in tool_names

    def test_l1_tool_schema_structure(self, mock_settings: MagicMock) -> None:
        """Tool definitions have correct schema structure."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        tools = orchestrator._create_l1_tools()

        for tool in tools:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"
            assert "properties" in tool["input_schema"]

    def test_grafana_query_metrics_schema(self, mock_settings: MagicMock) -> None:
        """grafana_query_metrics has correct required parameters."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        tools = orchestrator._create_l1_tools()
        metrics_tool = next(t for t in tools if t["name"] == "grafana_query_metrics")

        assert "query" in metrics_tool["input_schema"]["required"]
        assert "query" in metrics_tool["input_schema"]["properties"]
        assert "start" in metrics_tool["input_schema"]["properties"]
        assert "end" in metrics_tool["input_schema"]["properties"]
        assert "step" in metrics_tool["input_schema"]["properties"]


class TestParseAlert:
    """Tests for alert parsing."""

    def test_parse_alert_extracts_labels(self, mock_settings: MagicMock) -> None:
        """Labels are correctly extracted from alert."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        alert = {
            "labels": {
                "alertname": "VMNetworkLatency",
                "instance": "192.168.1.10:9100",
                "severity": "critical",
                "vm_uuid": "test-uuid",
            },
            "annotations": {
                "summary": "High latency detected",
                "description": "VM network latency is above threshold",
            },
        }

        context = orchestrator._parse_alert(alert)

        assert context.alertname == "VMNetworkLatency"
        assert context.instance == "192.168.1.10:9100"
        assert context.severity == "critical"
        assert context.labels["vm_uuid"] == "test-uuid"

    def test_parse_alert_extracts_annotations(self, mock_settings: MagicMock) -> None:
        """Annotations are correctly extracted from alert."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        alert = {
            "labels": {"alertname": "TestAlert"},
            "annotations": {
                "summary": "Test summary",
                "runbook_url": "http://example.com",
            },
        }

        context = orchestrator._parse_alert(alert)

        assert context.annotations["summary"] == "Test summary"
        assert context.annotations["runbook_url"] == "http://example.com"

    def test_parse_alert_with_missing_labels(self, mock_settings: MagicMock) -> None:
        """Missing labels are handled with defaults."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        alert = {}

        context = orchestrator._parse_alert(alert)

        assert context.alertname == "unknown"
        assert context.instance == ""
        assert context.severity == "warning"

    def test_parse_alert_returns_alert_context(self, mock_settings: MagicMock) -> None:
        """_parse_alert returns AlertContext instance."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        alert = {"labels": {"alertname": "TestAlert"}}

        context = orchestrator._parse_alert(alert)

        assert isinstance(context, AlertContext)


class TestSynthesizeDiagnosis:
    """Tests for diagnosis synthesis."""

    def test_synthesize_diagnosis_returns_diagnosis_result(
        self, mock_settings: MagicMock
    ) -> None:
        """_synthesize_diagnosis returns DiagnosisResult."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-test123",
            timestamp="2024-01-15T10:00:00Z",
            alert_context=None,
            agent_result=None,
        )

        assert isinstance(result, DiagnosisResult)
        assert result.diagnosis_id == "diag-test123"
        assert result.timestamp == "2024-01-15T10:00:00Z"

    def test_synthesize_diagnosis_with_alert_context(
        self, mock_settings: MagicMock
    ) -> None:
        """Diagnosis includes alert context when provided."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        alert_context = AlertContext(
            alertname="VMNetworkLatency",
            instance="192.168.1.10:9100",
            severity="critical",
        )

        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-test",
            timestamp="2024-01-15T10:00:00Z",
            alert_context=alert_context,
            agent_result=None,
        )

        assert result.alert_source == alert_context

    def test_synthesize_diagnosis_has_root_cause(
        self, mock_settings: MagicMock
    ) -> None:
        """Synthesized diagnosis includes root cause."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-test",
            timestamp="2024-01-15T10:00:00Z",
            alert_context=None,
            agent_result=None,
        )

        assert isinstance(result.root_cause, RootCause)
        assert result.root_cause.category == RootCauseCategory.HOST_INTERNAL

    def test_synthesize_diagnosis_has_recommendations(
        self, mock_settings: MagicMock
    ) -> None:
        """Synthesized diagnosis includes recommendations."""
        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-test",
            timestamp="2024-01-15T10:00:00Z",
            alert_context=None,
            agent_result=None,
        )

        assert len(result.recommendations) >= 1
        assert isinstance(result.recommendations[0], Recommendation)


class TestCreateOrchestrator:
    """Tests for create_orchestrator factory function."""

    def test_create_orchestrator_returns_instance(self, mock_settings: MagicMock) -> None:
        """create_orchestrator returns NetworkTroubleshootingOrchestrator."""
        orchestrator = create_orchestrator(settings=mock_settings)

        assert isinstance(orchestrator, NetworkTroubleshootingOrchestrator)

    def test_create_orchestrator_with_model(self, mock_settings: MagicMock) -> None:
        """create_orchestrator accepts model parameter."""
        orchestrator = create_orchestrator(
            settings=mock_settings,
            model="claude-opus-4-20250514",
        )

        assert orchestrator.model == "claude-opus-4-20250514"

    def test_create_orchestrator_with_compact_prompts(
        self, mock_settings: MagicMock
    ) -> None:
        """create_orchestrator accepts compact_prompts parameter."""
        orchestrator = create_orchestrator(
            settings=mock_settings,
            compact_prompts=True,
        )

        assert orchestrator.compact_prompts is True

    @patch("netsherlock.config.settings.get_settings")
    def test_create_orchestrator_without_settings(
        self, mock_get_settings: MagicMock, mock_settings: MagicMock
    ) -> None:
        """create_orchestrator uses default settings when none provided."""
        mock_get_settings.return_value = mock_settings

        orchestrator = create_orchestrator()

        mock_get_settings.assert_called()
        assert isinstance(orchestrator, NetworkTroubleshootingOrchestrator)


class TestDiagnoseAlertIntegration:
    """Integration tests for diagnose_alert (mocked SDK)."""

    @pytest.mark.asyncio
    @patch("netsherlock.agents.orchestrator.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.orchestrator.Agent")
    async def test_diagnose_alert_generates_diagnosis_id(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """diagnose_alert generates a unique diagnosis ID."""
        # Setup mocks
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        alert = {
            "labels": {
                "alertname": "VMNetworkLatency",
                "instance": "192.168.1.10:9100",
            }
        }

        result = await orchestrator.diagnose_alert(alert)

        assert result.diagnosis_id.startswith("diag-")
        assert len(result.diagnosis_id) == 13  # "diag-" + 8 hex chars

    @pytest.mark.asyncio
    @patch("netsherlock.agents.orchestrator.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.orchestrator.Agent")
    async def test_diagnose_alert_calls_agent(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """diagnose_alert invokes the Claude Agent SDK."""
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        alert = {"labels": {"alertname": "TestAlert"}}

        await orchestrator.diagnose_alert(alert)

        mock_agent.assert_called_once()
        mock_query.assert_called_once()


class TestDiagnoseRequestIntegration:
    """Integration tests for diagnose_request (mocked SDK)."""

    @pytest.mark.asyncio
    @patch("netsherlock.agents.orchestrator.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.orchestrator.Agent")
    async def test_diagnose_request_generates_diagnosis_id(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """diagnose_request generates a unique diagnosis ID."""
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        request = {
            "problem_type": "vm_network_latency",
            "src_node": "192.168.1.10",
            "dst_node": "192.168.1.20",
        }

        result = await orchestrator.diagnose_request(request)

        assert result.diagnosis_id.startswith("diag-")

    @pytest.mark.asyncio
    @patch("netsherlock.agents.orchestrator.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.orchestrator.Agent")
    async def test_diagnose_request_with_vm_name(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """diagnose_request handles vm_name in request."""
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        request = {
            "problem_type": "vm_network_latency",
            "src_node": "192.168.1.10",
            "vm_name": "test-vm",
        }

        result = await orchestrator.diagnose_request(request)

        assert isinstance(result, DiagnosisResult)

    @pytest.mark.asyncio
    @patch("netsherlock.agents.orchestrator.query", new_callable=AsyncMock)
    @patch("netsherlock.agents.orchestrator.Agent")
    async def test_diagnose_request_with_description(
        self,
        mock_agent: MagicMock,
        mock_query: AsyncMock,
        mock_settings: MagicMock,
    ) -> None:
        """diagnose_request handles description in request."""
        mock_agent_instance = MagicMock()
        mock_agent.return_value.__aenter__.return_value = mock_agent_instance
        mock_query.return_value = None

        orchestrator = NetworkTroubleshootingOrchestrator(settings=mock_settings)

        request = {
            "problem_type": "packet_loss",
            "description": "High packet loss observed between VMs",
        }

        result = await orchestrator.diagnose_request(request)

        assert isinstance(result, DiagnosisResult)
