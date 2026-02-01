"""Root-level shared fixtures for all tests.

Provides common DiagnosisRequest, DiagnosisResult, and mock objects
used across multiple test modules.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from netsherlock.schemas.config import (
    DiagnosisMode,
    DiagnosisRequestSource,
)
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus


@pytest.fixture
def sample_vm_diagnosis_request() -> DiagnosisRequest:
    """Standard cross-node VM latency request."""
    return DiagnosisRequest(
        request_id="test-req-001",
        request_type="latency",
        network_type="vm",
        src_host="192.168.75.101",
        src_vm="ae6aa164-604c-4cb0-84b8-2dea034307f1",
        dst_host="192.168.75.102",
        dst_vm="bf7bb275-715d-4cb1-95a9-3efa045308f2",
        source=DiagnosisRequestSource.CLI,
    )


@pytest.fixture
def sample_system_diagnosis_request() -> DiagnosisRequest:
    """Standard system latency request."""
    return DiagnosisRequest(
        request_id="test-req-002",
        request_type="latency",
        network_type="system",
        src_host="192.168.75.101",
        dst_host="192.168.75.102",
        source=DiagnosisRequestSource.CLI,
    )


@pytest.fixture
def sample_completed_result() -> DiagnosisResult:
    """Completed diagnosis result with root cause and recommendations."""
    from netsherlock.schemas.report import (
        Recommendation,
        RootCause,
        RootCauseCategory,
    )

    return DiagnosisResult(
        diagnosis_id="test-diag-001",
        status=DiagnosisStatus.COMPLETED,
        started_at=datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc),
        completed_at=datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc),
        source=DiagnosisRequestSource.CLI,
        mode=DiagnosisMode.AUTONOMOUS,
        summary="High latency in host OVS bridge layer",
        root_cause=RootCause(
            category=RootCauseCategory.HOST_INTERNAL,
            component="ovs_bridge",
            confidence=0.85,
            evidence=["OVS processing delay > 500us"],
        ),
        recommendations=[
            Recommendation(
                priority=1,
                action="Check OVS flow table size",
                rationale="Large flow tables increase lookup time",
            ),
        ],
        confidence=0.85,
    )


@pytest.fixture
def sample_error_result() -> DiagnosisResult:
    """Error diagnosis result."""
    return DiagnosisResult.create_error(
        diagnosis_id="test-diag-err",
        error="Connection timeout to host",
        source=DiagnosisRequestSource.WEBHOOK,
    )


@pytest.fixture
def mock_controller_state():
    """Mock DiagnosisState for from_controller_state() testing."""
    state = MagicMock()
    state.diagnosis_id = "ctrl-diag-001"
    state.status = MagicMock()
    state.status.value = "completed"
    state.started_at = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
    state.completed_at = datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc)
    state.mode = DiagnosisMode.AUTONOMOUS
    state.measurements = {"latency_breakdown": {"A": 15.2, "B": 30.5}}
    state.analysis = {
        "root_cause": {
            "category": "host_internal",
            "component": "ovs_bridge",
            "confidence": 0.85,
            "evidence": ["OVS delay detected"],
        },
        "recommendations": [
            {"priority": 1, "action": "Check OVS flows", "command": "ovs-ofctl dump-flows br0"},
        ],
        "markdown_report": "# Diagnosis Report\n\nOVS bridge delay detected.",
        "report_path": "/tmp/report.md",
    }
    state.error = None
    return state


@pytest.fixture
def mock_orchestrator_agent_output() -> dict:
    """Mock orchestrator agent structured JSON output."""
    return {
        "summary": "High latency in host OVS layer",
        "root_cause": {
            "category": "host_internal",
            "component": "ovs_bridge",
            "confidence": 0.85,
            "evidence": ["OVS processing delay > 500us"],
        },
        "recommendations": [
            {"priority": 1, "action": "Check OVS flow table size"},
        ],
        "l2_environment": {"src_host": {"bridge": "br0"}},
        "l3_measurements": {"total_rtt_us": 450.5},
    }
