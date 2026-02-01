"""Tests for Webhook → OrchestratorEngine end-to-end flow.

Verifies the complete data path from webhook through OrchestratorEngine
to diagnosis_store, ensuring unified DiagnosisResult format.
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.report import RootCause, RootCauseCategory
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus

# Mock claude_code_sdk for OrchestratorEngine import
if "claude_code_sdk" not in sys.modules:
    sys.modules["claude_code_sdk"] = MagicMock()


@pytest.fixture
def mock_orchestrator_result():
    """Standard orchestrator completion result."""
    return DiagnosisResult(
        diagnosis_id="flow-orch-001",
        status=DiagnosisStatus.COMPLETED,
        summary="High latency in host OVS layer",
        source=DiagnosisRequestSource.WEBHOOK,
        mode=DiagnosisMode.AUTONOMOUS,
        root_cause=RootCause(
            category=RootCauseCategory.HOST_INTERNAL,
            component="ovs_bridge",
            confidence=0.85,
            evidence=["OVS delay > 500us"],
        ),
    )


@pytest.fixture
def mock_orch_engine(mock_orchestrator_result):
    """Mock OrchestratorEngine."""
    engine = MagicMock()
    engine.engine_type = "orchestrator"
    engine.execute = AsyncMock(return_value=mock_orchestrator_result)
    engine.health_check = AsyncMock(return_value={
        "engine": "orchestrator", "status": "healthy",
        "config": {"model": "claude-haiku-4-5-20251001"},
    })
    return engine


class TestWebhookOrchestratorFlow:
    """Webhook → OrchestratorEngine end-to-end."""

    async def test_alert_to_orchestrator_execution(self, mock_orch_engine):
        """Alert queued and processed by OrchestratorEngine."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_orch_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "alert", "flow-orch-001",
                {
                    "labels": {
                        "alertname": "VMNetworkLatency",
                        "src_host": "192.168.1.10",
                        "src_vm": "uuid-1234",
                        "network_type": "vm",
                    },
                    "mode": "autonomous",
                }
            ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.15)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            assert "flow-orch-001" in webhook.diagnosis_store
            result = webhook.diagnosis_store["flow-orch-001"]
            assert result.status == DiagnosisStatus.COMPLETED
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_orchestrator_result_has_unified_format(self, mock_orch_engine):
        """Orchestrator result is unified DiagnosisResult with summary/root_cause."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_orch_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "alert", "flow-orch-fmt",
                {
                    "labels": {"alertname": "VMNetworkLatency", "src_host": "1.2.3.4",
                                "src_vm": "uuid-1", "network_type": "vm"},
                    "mode": "autonomous",
                }
            ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.15)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            result = webhook.diagnosis_store["flow-orch-fmt"]
            assert isinstance(result, DiagnosisResult)
            assert result.summary != ""
            assert result.root_cause is not None
            assert result.root_cause.confidence > 0
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_manual_request_to_orchestrator(self, mock_orch_engine):
        """Manual request processed by OrchestratorEngine with source=API."""
        import netsherlock.api.webhook as webhook

        # Override the mock to return API source
        mock_orch_engine.execute = AsyncMock(return_value=DiagnosisResult(
            diagnosis_id="flow-orch-manual",
            status=DiagnosisStatus.COMPLETED,
            source=DiagnosisRequestSource.API,
        ))

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = mock_orch_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "manual", "flow-orch-manual",
                {
                    "diagnosis_type": "latency",
                    "network_type": "system",
                    "src_host": "192.168.1.10",
                }
            ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.15)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            assert "flow-orch-manual" in webhook.diagnosis_store
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_orchestrator_error_stored_correctly(self):
        """OrchestratorEngine exception stores ERROR result."""
        import netsherlock.api.webhook as webhook

        error_engine = MagicMock()
        error_engine.engine_type = "orchestrator"
        error_engine.execute = AsyncMock(side_effect=RuntimeError("Agent SDK timeout"))

        original_engine = webhook.engine
        original_store = webhook.diagnosis_store.copy()
        try:
            webhook.engine = error_engine
            webhook.diagnosis_store.clear()

            await webhook.diagnosis_queue.put((
                "alert", "flow-orch-err",
                {
                    "labels": {"alertname": "VMNetworkLatency", "src_host": "1.2.3.4",
                                "src_vm": "uuid-1", "network_type": "vm"},
                    "mode": "autonomous",
                }
            ))

            worker_task = asyncio.create_task(webhook.diagnosis_worker())
            await asyncio.sleep(0.15)
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

            result = webhook.diagnosis_store["flow-orch-err"]
            assert result.status == DiagnosisStatus.ERROR
            assert "Agent SDK timeout" in result.error
        finally:
            webhook.engine = original_engine
            webhook.diagnosis_store.clear()
            webhook.diagnosis_store.update(original_store)

    async def test_health_shows_orchestrator_engine(self, mock_orch_engine):
        """GET /health returns engine='orchestrator'."""
        import netsherlock.api.webhook as webhook

        original_engine = webhook.engine
        try:
            webhook.engine = mock_orch_engine
            response = await webhook.health_check()
            assert response.engine == "orchestrator"
        finally:
            webhook.engine = original_engine
