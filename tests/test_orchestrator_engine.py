"""Tests for OrchestratorEngine and related Phase 2 changes.

Tests the OrchestratorEngine wrapping NetworkTroubleshootingOrchestrator,
_synthesize_diagnosis parsing, and webhook engine creation for orchestrator.
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock claude_code_sdk before importing orchestrator (same pattern as test_orchestrator.py)
if "claude_code_sdk" not in sys.modules:
    sys.modules["claude_code_sdk"] = MagicMock()

from netsherlock.agents.orchestrator import NetworkTroubleshootingOrchestrator
from netsherlock.core.orchestrator_engine import OrchestratorEngine
from netsherlock.schemas.config import (
    DiagnosisMode,
    DiagnosisRequestSource,
)
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus


def _mock_settings():
    """Create mock settings with all required attributes."""
    s = MagicMock()
    s.llm.model = "claude-haiku-4-5-20251001"
    s.llm.compact_prompts = False
    s.grafana.base_url = "http://localhost/grafana"
    s.grafana.username = "admin"
    s.grafana.password = MagicMock()
    s.grafana.password.get_secret_value.return_value = "pass"
    return s


class TestOrchestratorEngineProtocol:
    """Tests for OrchestratorEngine satisfying DiagnosisEngine protocol."""

    def test_engine_type_is_orchestrator(self):
        """OrchestratorEngine.engine_type should be 'orchestrator'."""
        engine = OrchestratorEngine(settings=_mock_settings())
        assert engine.engine_type == "orchestrator"

    def test_has_protocol_methods(self):
        """OrchestratorEngine should have execute and health_check methods."""
        engine = OrchestratorEngine(settings=_mock_settings())
        assert hasattr(engine, "execute")
        assert hasattr(engine, "health_check")
        assert hasattr(engine, "engine_type")


class TestOrchestratorEngineExecute:
    """Tests for OrchestratorEngine.execute()."""

    @pytest.fixture
    def engine_and_orch(self):
        """Create OrchestratorEngine and return (engine, orchestrator)."""
        engine = OrchestratorEngine(settings=_mock_settings())
        orch = engine._orchestrator
        return engine, orch

    @pytest.fixture
    def alert_request(self):
        return DiagnosisRequest(
            request_id="test-orch-001",
            request_type="latency",
            network_type="vm",
            src_host="192.168.1.10",
            src_vm="uuid-1234",
            dst_host="192.168.1.20",
            dst_vm="uuid-5678",
            source=DiagnosisRequestSource.WEBHOOK,
            alert_type="VMNetworkLatency",
            mode=DiagnosisMode.AUTONOMOUS,
        )

    @pytest.fixture
    def manual_request(self):
        return DiagnosisRequest(
            request_id="test-orch-002",
            request_type="latency",
            network_type="system",
            src_host="192.168.1.10",
            source=DiagnosisRequestSource.API,
            description="High latency observed",
        )

    @pytest.mark.asyncio
    async def test_execute_alert_calls_diagnose_alert(self, engine_and_orch, alert_request):
        """Alert requests should route to diagnose_alert()."""
        engine, orch = engine_and_orch
        mock_result = DiagnosisResult(
            diagnosis_id="test-orch-001",
            status=DiagnosisStatus.COMPLETED,
            summary="Root cause found",
        )
        orch.diagnose_alert = AsyncMock(return_value=mock_result)

        result = await engine.execute(request=alert_request)

        orch.diagnose_alert.assert_called_once()
        assert result.diagnosis_id == "test-orch-001"
        assert result.status == DiagnosisStatus.COMPLETED
        assert result.source == DiagnosisRequestSource.WEBHOOK

    @pytest.mark.asyncio
    async def test_execute_manual_calls_diagnose_request(self, engine_and_orch, manual_request):
        """Manual requests should route to diagnose_request()."""
        engine, orch = engine_and_orch
        mock_result = DiagnosisResult(
            diagnosis_id="test-orch-002",
            status=DiagnosisStatus.COMPLETED,
            summary="Analysis complete",
        )
        orch.diagnose_request = AsyncMock(return_value=mock_result)

        result = await engine.execute(request=manual_request)

        orch.diagnose_request.assert_called_once()
        assert result.diagnosis_id == "test-orch-002"
        assert result.source == DiagnosisRequestSource.API

    @pytest.mark.asyncio
    async def test_execute_sets_timestamps(self, engine_and_orch, alert_request):
        """Execute should set started_at and completed_at on result."""
        engine, orch = engine_and_orch
        mock_result = DiagnosisResult(
            diagnosis_id="test-orch-001",
            status=DiagnosisStatus.COMPLETED,
        )
        orch.diagnose_alert = AsyncMock(return_value=mock_result)

        result = await engine.execute(request=alert_request)

        assert result.started_at is not None
        assert result.completed_at is not None

    @pytest.mark.asyncio
    async def test_execute_error_returns_error_result(self, engine_and_orch, alert_request):
        """Exceptions should produce an error DiagnosisResult."""
        engine, orch = engine_and_orch
        orch.diagnose_alert = AsyncMock(
            side_effect=RuntimeError("Connection failed")
        )

        result = await engine.execute(request=alert_request)

        assert result.status == DiagnosisStatus.ERROR
        assert "Connection failed" in result.error

    @pytest.mark.asyncio
    async def test_execute_preserves_mode_from_request(self, engine_and_orch, alert_request):
        """Result mode should be set from request.mode."""
        engine, orch = engine_and_orch
        mock_result = DiagnosisResult(
            diagnosis_id="test-orch-001",
            status=DiagnosisStatus.COMPLETED,
        )
        orch.diagnose_alert = AsyncMock(return_value=mock_result)

        result = await engine.execute(request=alert_request)

        assert result.mode == DiagnosisMode.AUTONOMOUS

    def test_request_to_alert_data(self, engine_and_orch, alert_request):
        """_request_to_alert_data should create proper alert dict."""
        engine, _ = engine_and_orch
        alert_data = engine._request_to_alert_data(alert_request)

        assert alert_data["labels"]["alertname"] == "VMNetworkLatency"
        assert alert_data["labels"]["src_host"] == "192.168.1.10"
        assert alert_data["labels"]["src_vm"] == "uuid-1234"
        assert alert_data["labels"]["network_type"] == "vm"

    def test_request_to_dict(self, engine_and_orch, manual_request):
        """_request_to_dict should create proper request dict."""
        engine, _ = engine_and_orch
        request_dict = engine._request_to_dict(manual_request)

        assert request_dict["problem_type"] == "system_network_latency"
        assert request_dict["src_node"] == "192.168.1.10"
        assert request_dict["description"] == "High latency observed"


class TestOrchestratorEngineHealthCheck:
    """Tests for OrchestratorEngine.health_check()."""

    @pytest.mark.asyncio
    async def test_health_check_returns_engine_info(self):
        """health_check() should return orchestrator engine info."""
        engine = OrchestratorEngine(settings=_mock_settings())
        health = await engine.health_check()

        assert health["engine"] == "orchestrator"
        assert health["status"] == "healthy"
        assert "model" in health["config"]


class TestSynthesizeDiagnosis:
    """Tests for NetworkTroubleshootingOrchestrator._synthesize_diagnosis."""

    @pytest.fixture
    def orchestrator(self):
        """Create orchestrator with mocked SDK dependencies."""
        return NetworkTroubleshootingOrchestrator(settings=_mock_settings())

    def test_synthesize_with_json_block(self, orchestrator):
        """Should parse structured JSON from agent result text."""
        agent_text = '''Based on my analysis:

```json
{
    "summary": "High latency in host OVS layer",
    "root_cause": {
        "category": "host_internal",
        "component": "ovs_bridge",
        "confidence": 0.85,
        "evidence": ["OVS processing delay > 500us"]
    },
    "recommendations": [
        {"priority": 1, "action": "Check OVS flow table size"}
    ]
}
```
'''
        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-test",
            timestamp="2024-01-01T00:00:00Z",
            alert_context=None,
            agent_result=agent_text,
        )

        assert result.diagnosis_id == "diag-test"
        assert result.status == DiagnosisStatus.COMPLETED
        assert result.summary == "High latency in host OVS layer"
        assert result.root_cause is not None
        assert result.root_cause.component == "ovs_bridge"
        assert result.root_cause.confidence == 0.85

    def test_synthesize_with_plain_text(self, orchestrator):
        """Should fall back to using text as summary when no JSON found."""
        agent_text = "The network latency is caused by CPU contention on the host."

        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-test",
            timestamp="2024-01-01T00:00:00Z",
            alert_context=None,
            agent_result=agent_text,
        )

        assert result.diagnosis_id == "diag-test"
        assert result.status == DiagnosisStatus.COMPLETED
        assert "CPU contention" in result.summary

    def test_synthesize_with_none_result(self, orchestrator):
        """Should handle None agent result gracefully."""
        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-test",
            timestamp="2024-01-01T00:00:00Z",
            alert_context=None,
            agent_result=None,
        )

        assert result.status == DiagnosisStatus.COMPLETED
        assert result.summary == "No diagnosis output"

    def test_synthesize_with_message_objects(self, orchestrator):
        """Should extract text from message-like objects."""
        mock_block = MagicMock()
        mock_block.text = '{"summary": "Test diagnosis", "root_cause": {"category": "host_internal", "component": "nic", "confidence": 0.7, "evidence": []}}'

        mock_message = MagicMock()
        mock_message.content = [mock_block]

        result = orchestrator._synthesize_diagnosis(
            diagnosis_id="diag-msg",
            timestamp="2024-01-01T00:00:00Z",
            alert_context=None,
            agent_result=[mock_message],
        )

        assert result.summary == "Test diagnosis"
        assert result.root_cause is not None
        assert result.root_cause.confidence == 0.7


class TestExtractTextFromResult:
    """Tests for _extract_text_from_result static method."""

    def test_string_input(self):
        assert NetworkTroubleshootingOrchestrator._extract_text_from_result("hello") == "hello"

    def test_none_input(self):
        assert NetworkTroubleshootingOrchestrator._extract_text_from_result(None) == ""

    def test_dict_with_text(self):
        result = NetworkTroubleshootingOrchestrator._extract_text_from_result(
            {"text": "some text"}
        )
        assert result == "some text"


class TestTryParseJson:
    """Tests for _try_parse_json static method."""

    def test_fenced_json(self):
        text = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
        result = NetworkTroubleshootingOrchestrator._try_parse_json(text)
        assert result == {"key": "value"}

    def test_raw_json(self):
        text = 'Prefix {"key": "value"} suffix'
        result = NetworkTroubleshootingOrchestrator._try_parse_json(text)
        assert result == {"key": "value"}

    def test_no_json(self):
        result = NetworkTroubleshootingOrchestrator._try_parse_json("just plain text")
        assert result is None

    def test_empty_string(self):
        result = NetworkTroubleshootingOrchestrator._try_parse_json("")
        assert result is None


class TestWebhookOrchestratorEngineCreation:
    """Tests for _create_engine with orchestrator type."""

    def test_create_orchestrator_engine(self):
        """_create_engine with 'orchestrator' should create OrchestratorEngine."""
        from netsherlock.api.webhook import _create_engine

        settings = _mock_settings()
        settings.diagnosis_engine = "orchestrator"

        engine = _create_engine(settings)

        assert isinstance(engine, OrchestratorEngine)
        assert engine.engine_type == "orchestrator"
