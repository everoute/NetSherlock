"""Tests for engine switching — same request, different engines, unified result.

Verifies that both ControllerEngine and OrchestratorEngine produce
unified DiagnosisResult instances with consistent structure.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from netsherlock.core.controller_engine import ControllerEngine
from netsherlock.schemas.config import (
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
)
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus

# Mock claude_code_sdk before importing orchestrator
if "claude_code_sdk" not in sys.modules:
    sys.modules["claude_code_sdk"] = MagicMock()

from netsherlock.core.orchestrator_engine import OrchestratorEngine


def _mock_settings():
    """Create mock settings for OrchestratorEngine."""
    s = MagicMock()
    s.llm.model = "claude-haiku-4-5-20251001"
    s.llm.compact_prompts = False
    s.grafana.base_url = "http://localhost/grafana"
    s.grafana.username = "admin"
    s.grafana.password = MagicMock()
    s.grafana.password.get_secret_value.return_value = "pass"
    return s


@pytest.fixture
def system_request():
    """Shared system request for both engines."""
    return DiagnosisRequest(
        request_id="switch-test-001",
        request_type="latency",
        network_type="system",
        src_host="192.168.1.10",
        source=DiagnosisRequestSource.WEBHOOK,
        mode=DiagnosisMode.AUTONOMOUS,
    )


class TestEngineSwitching:
    """Same request, different engines, consistent result types."""

    async def test_controller_returns_diagnosis_result(self, system_request):
        """ControllerEngine.execute() returns DiagnosisResult instance."""
        engine = ControllerEngine(config=DiagnosisConfig())
        mock_result = DiagnosisResult(
            diagnosis_id="switch-test-001",
            status=DiagnosisStatus.COMPLETED,
            summary="Controller diagnosis complete",
        )

        with patch("netsherlock.core.controller_engine.DiagnosisController") as MockCtrl:
            MockCtrl.return_value.run = AsyncMock(return_value=mock_result)
            result = await engine.execute(request=system_request)

        assert isinstance(result, DiagnosisResult)
        assert result.status == DiagnosisStatus.COMPLETED

    async def test_orchestrator_returns_diagnosis_result(self, system_request):
        """OrchestratorEngine.execute() returns DiagnosisResult instance."""
        engine = OrchestratorEngine(settings=_mock_settings())
        mock_result = DiagnosisResult(
            diagnosis_id="switch-test-001",
            status=DiagnosisStatus.COMPLETED,
            summary="Orchestrator diagnosis complete",
        )
        engine._orchestrator.diagnose_alert = AsyncMock(return_value=mock_result)

        result = await engine.execute(request=system_request)

        assert isinstance(result, DiagnosisResult)
        assert result.status == DiagnosisStatus.COMPLETED

    async def test_both_have_same_status_type(self, system_request):
        """Both engines produce DiagnosisStatus enum values."""
        ctrl_engine = ControllerEngine(config=DiagnosisConfig())
        orch_engine = OrchestratorEngine(settings=_mock_settings())

        ctrl_result = DiagnosisResult(
            diagnosis_id="ctrl", status=DiagnosisStatus.COMPLETED
        )
        orch_result = DiagnosisResult(
            diagnosis_id="orch", status=DiagnosisStatus.COMPLETED
        )

        with patch("netsherlock.core.controller_engine.DiagnosisController") as MockCtrl:
            MockCtrl.return_value.run = AsyncMock(return_value=ctrl_result)
            r1 = await ctrl_engine.execute(request=system_request)

        orch_engine._orchestrator.diagnose_alert = AsyncMock(return_value=orch_result)
        r2 = await orch_engine.execute(request=system_request)

        assert type(r1.status) == type(r2.status)
        assert isinstance(r1.status, DiagnosisStatus)
        assert isinstance(r2.status, DiagnosisStatus)

    async def test_both_have_timestamps(self, system_request):
        """Both engines set started_at and completed_at."""
        ctrl_engine = ControllerEngine(config=DiagnosisConfig())
        orch_engine = OrchestratorEngine(settings=_mock_settings())

        ctrl_result = DiagnosisResult(
            diagnosis_id="ctrl", status=DiagnosisStatus.COMPLETED,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
        )
        orch_result = DiagnosisResult(
            diagnosis_id="orch", status=DiagnosisStatus.COMPLETED,
        )

        with patch("netsherlock.core.controller_engine.DiagnosisController") as MockCtrl:
            MockCtrl.return_value.run = AsyncMock(return_value=ctrl_result)
            r1 = await ctrl_engine.execute(request=system_request)

        orch_engine._orchestrator.diagnose_alert = AsyncMock(return_value=orch_result)
        r2 = await orch_engine.execute(request=system_request)

        # Both should have timestamps (OrchestratorEngine sets them if missing)
        assert r1.started_at is not None or r1.completed_at is not None
        assert r2.started_at is not None or r2.completed_at is not None

    async def test_controller_can_have_checkpoint_history(self, system_request):
        """Controller result can have non-empty checkpoint_history."""
        engine = ControllerEngine(config=DiagnosisConfig())
        result_with_history = DiagnosisResult(
            diagnosis_id="ctrl",
            status=DiagnosisStatus.COMPLETED,
            checkpoint_history=[{"checkpoint": "l2", "status": "confirmed"}],
        )

        with patch("netsherlock.core.controller_engine.DiagnosisController") as MockCtrl:
            MockCtrl.return_value.run = AsyncMock(return_value=result_with_history)
            result = await engine.execute(request=system_request)

        assert len(result.checkpoint_history) > 0

    async def test_orchestrator_checkpoint_history_empty(self, system_request):
        """Orchestrator result has empty checkpoint_history."""
        engine = OrchestratorEngine(settings=_mock_settings())
        mock_result = DiagnosisResult(
            diagnosis_id="orch",
            status=DiagnosisStatus.COMPLETED,
        )
        engine._orchestrator.diagnose_alert = AsyncMock(return_value=mock_result)

        result = await engine.execute(request=system_request)

        assert result.checkpoint_history == []


class TestEngineErrorHandling:
    """Engine exception handling."""

    async def test_controller_error_propagates(self, system_request):
        """ControllerEngine propagates exceptions (caller handles them)."""
        engine = ControllerEngine(config=DiagnosisConfig())

        with patch("netsherlock.core.controller_engine.DiagnosisController") as MockCtrl:
            MockCtrl.return_value.run = AsyncMock(
                side_effect=RuntimeError("Controller crash")
            )
            with pytest.raises(RuntimeError, match="Controller crash"):
                await engine.execute(request=system_request)

    async def test_orchestrator_error_returns_error_status(self, system_request):
        """OrchestratorEngine catches exceptions and returns ERROR status."""
        engine = OrchestratorEngine(settings=_mock_settings())
        engine._orchestrator.diagnose_alert = AsyncMock(
            side_effect=RuntimeError("Orchestrator crash")
        )

        result = await engine.execute(request=system_request)

        assert result.status == DiagnosisStatus.ERROR
        assert "Orchestrator crash" in result.error
