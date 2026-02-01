"""Tests for unified DiagnosisResult model and factory methods.

Tests creation, all four factory methods (from_controller_state,
from_orchestrator_output, create_error, create_cancelled), and
field mapping for both Controller and Orchestrator data paths.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.report import (
    Recommendation,
    RootCause,
    RootCauseCategory,
)
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus


class TestDiagnosisResultCreation:
    """DiagnosisResult basic creation."""

    def test_minimal_fields(self):
        """Minimal creation requires diagnosis_id and status."""
        result = DiagnosisResult(
            diagnosis_id="test-001",
            status=DiagnosisStatus.COMPLETED,
        )
        assert result.diagnosis_id == "test-001"
        assert result.status == DiagnosisStatus.COMPLETED

    def test_default_values(self):
        """All default values are correctly set."""
        result = DiagnosisResult(
            diagnosis_id="test-002",
            status=DiagnosisStatus.PENDING,
        )
        assert result.started_at is None
        assert result.completed_at is None
        assert result.summary == ""
        assert result.root_cause is None
        assert result.recommendations == []
        assert result.confidence == 0.0
        assert result.l1_observations == {}
        assert result.l2_environment == {}
        assert result.l3_measurements == {}
        assert result.l4_analysis == {}
        assert result.checkpoint_history == []
        assert result.error is None
        assert result.markdown_report == ""
        assert result.report_path == ""

    def test_all_status_enum_values(self):
        """All 7 DiagnosisStatus values can be used."""
        for status in DiagnosisStatus:
            result = DiagnosisResult(
                diagnosis_id=f"test-{status.value}",
                status=status,
            )
            assert result.status == status


class TestFromControllerState:
    """from_controller_state() factory method — Controller data path."""

    def _make_state(self, **overrides):
        """Create a mock DiagnosisState with defaults."""
        state = MagicMock()
        state.diagnosis_id = overrides.get("diagnosis_id", "ctrl-001")
        state.status = MagicMock()
        state.status.value = overrides.get("status_value", "completed")
        state.started_at = overrides.get("started_at", datetime(2024, 1, 1, tzinfo=timezone.utc))
        state.completed_at = overrides.get("completed_at", datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc))
        state.mode = overrides.get("mode", DiagnosisMode.AUTONOMOUS)
        state.measurements = overrides.get("measurements", {})
        state.analysis = overrides.get("analysis", {})
        state.error = overrides.get("error", None)
        return state

    def test_completed_state_maps_all_fields(self):
        """COMPLETED state maps status, id, timestamps correctly."""
        state = self._make_state()
        result = DiagnosisResult.from_controller_state(state)

        assert result.diagnosis_id == "ctrl-001"
        assert result.status == DiagnosisStatus.COMPLETED
        assert result.started_at is not None
        assert result.completed_at is not None

    def test_root_cause_dict_to_typed_rootcause(self):
        """analysis['root_cause'] dict converts to typed RootCause."""
        state = self._make_state(analysis={
            "root_cause": {
                "category": "host_internal",
                "component": "ovs_bridge",
                "confidence": 0.85,
                "evidence": ["OVS delay"],
                "contributing_factors": ["CPU contention"],
            },
        })
        result = DiagnosisResult.from_controller_state(state)

        assert result.root_cause is not None
        assert result.root_cause.category == RootCauseCategory.HOST_INTERNAL
        assert result.root_cause.component == "ovs_bridge"
        assert result.root_cause.confidence == 0.85
        assert "OVS delay" in result.root_cause.evidence

    def test_invalid_root_cause_category_falls_back_to_unknown(self):
        """Invalid category value falls back to UNKNOWN."""
        state = self._make_state(analysis={
            "root_cause": {
                "category": "nonexistent_category",
                "component": "test",
                "confidence": 0.5,
            },
        })
        result = DiagnosisResult.from_controller_state(state)

        assert result.root_cause is not None
        assert result.root_cause.category == RootCauseCategory.UNKNOWN

    def test_empty_root_cause_stays_none(self):
        """Empty root_cause dict results in None."""
        state = self._make_state(analysis={"root_cause": {}})
        result = DiagnosisResult.from_controller_state(state)
        assert result.root_cause is None

    def test_recommendations_dict_to_typed(self):
        """analysis['recommendations'] list[dict] converts to list[Recommendation]."""
        state = self._make_state(analysis={
            "recommendations": [
                {"priority": 1, "action": "Check OVS", "command": "ovs-ofctl dump-flows br0"},
                {"priority": 2, "action": "Check CPU"},
            ],
        })
        result = DiagnosisResult.from_controller_state(state)

        assert len(result.recommendations) == 2
        assert result.recommendations[0].priority == 1
        assert result.recommendations[0].action == "Check OVS"
        assert result.recommendations[0].command == "ovs-ofctl dump-flows br0"

    def test_recommendations_already_typed_preserved(self):
        """Already-typed Recommendation objects are preserved."""
        rec = Recommendation(priority=1, action="Already typed")
        state = self._make_state(analysis={
            "recommendations": [rec],
        })
        result = DiagnosisResult.from_controller_state(state)
        assert result.recommendations[0] is rec

    def test_confidence_from_root_cause(self):
        """Confidence taken from root_cause when available."""
        state = self._make_state(analysis={
            "root_cause": {"category": "host_internal", "component": "x", "confidence": 0.9},
        })
        result = DiagnosisResult.from_controller_state(state)
        assert result.confidence == 0.9

    def test_confidence_from_analysis_result(self):
        """Confidence from analysis_result when root_cause confidence is 0."""
        state = self._make_state(analysis={
            "root_cause": {"category": "host_internal", "component": "x", "confidence": 0.0},
        })
        mock_analysis = MagicMock()
        mock_analysis.confidence = 0.75
        mock_analysis.summary.return_value = "Test summary"
        result = DiagnosisResult.from_controller_state(state, analysis_result=mock_analysis)
        assert result.confidence == 0.75

    def test_confidence_from_analysis_dict(self):
        """Confidence from analysis dict as last fallback."""
        state = self._make_state(analysis={
            "root_cause": {"category": "host_internal", "component": "x", "confidence": 0.6},
        })
        result = DiagnosisResult.from_controller_state(state)
        assert result.confidence == 0.6

    def test_measurements_mapped_to_l3(self):
        """state.measurements maps to result.l3_measurements."""
        state = self._make_state(measurements={"A": 15.2, "B": 30.5})
        result = DiagnosisResult.from_controller_state(state)
        assert result.l3_measurements == {"A": 15.2, "B": 30.5}

    def test_analysis_mapped_to_l4(self):
        """state.analysis maps to result.l4_analysis."""
        analysis = {"summary": "test", "root_cause": {}}
        state = self._make_state(analysis=analysis)
        result = DiagnosisResult.from_controller_state(state)
        assert result.l4_analysis == analysis

    def test_markdown_report_preserved(self):
        """markdown_report and report_path from analysis are preserved."""
        state = self._make_state(analysis={
            "markdown_report": "# Report",
            "report_path": "/tmp/r.md",
        })
        result = DiagnosisResult.from_controller_state(state)
        assert result.markdown_report == "# Report"
        assert result.report_path == "/tmp/r.md"

    def test_checkpoint_history_preserved(self):
        """checkpoint_history parameter is preserved in result."""
        state = self._make_state()
        history = [{"checkpoint": "l2", "status": "confirmed"}]
        result = DiagnosisResult.from_controller_state(state, checkpoint_history=history)
        assert result.checkpoint_history == history

    def test_error_state_maps_error(self):
        """ERROR state maps error field correctly."""
        state = self._make_state(status_value="error", error="Connection failed")
        result = DiagnosisResult.from_controller_state(state)
        assert result.status == DiagnosisStatus.ERROR
        assert result.error == "Connection failed"


class TestFromOrchestratorOutput:
    """from_orchestrator_output() factory method — Orchestrator data path."""

    def test_dict_result_with_all_fields(self):
        """Dict input with summary, root_cause, recommendations, l1/l2/l3 mapped."""
        agent_result = {
            "summary": "OVS bridge delay",
            "root_cause": {
                "category": "host_internal",
                "component": "ovs",
                "confidence": 0.8,
                "evidence": ["high delay"],
            },
            "recommendations": [
                {"priority": 1, "action": "Check flows"},
            ],
            "l1_observations": {"metrics": "collected"},
            "l2_environment": {"bridge": "br0"},
            "l3_measurements": {"rtt": 450},
        }
        result = DiagnosisResult.from_orchestrator_output(
            diagnosis_id="orch-001",
            agent_result=agent_result,
        )
        assert result.summary == "OVS bridge delay"
        assert result.root_cause is not None
        assert result.root_cause.component == "ovs"
        assert len(result.recommendations) == 1
        assert result.l1_observations == {"metrics": "collected"}
        assert result.l2_environment == {"bridge": "br0"}
        assert result.l3_measurements == {"rtt": 450}

    def test_raw_text_result_as_summary(self):
        """Non-dict input used as summary string."""
        result = DiagnosisResult.from_orchestrator_output(
            diagnosis_id="orch-002",
            agent_result="Network issue detected in OVS layer",
        )
        assert result.summary == "Network issue detected in OVS layer"
        assert result.root_cause is None
        assert result.recommendations == []

    def test_none_result_empty_summary(self):
        """None agent_result gives empty summary."""
        result = DiagnosisResult.from_orchestrator_output(
            diagnosis_id="orch-003",
            agent_result=None,
        )
        assert result.summary == ""
        assert result.root_cause is None

    def test_source_and_timing_preserved(self):
        """source, started_at, completed_at are correctly set."""
        started = datetime(2024, 1, 1, tzinfo=timezone.utc)
        completed = datetime(2024, 1, 1, 0, 5, tzinfo=timezone.utc)
        result = DiagnosisResult.from_orchestrator_output(
            diagnosis_id="orch-004",
            agent_result={"summary": "test"},
            started_at=started,
            completed_at=completed,
            source=DiagnosisRequestSource.WEBHOOK,
        )
        assert result.source == DiagnosisRequestSource.WEBHOOK
        assert result.started_at == started
        assert result.completed_at == completed

    def test_root_cause_confidence_propagated(self):
        """root_cause.confidence propagates to result.confidence."""
        agent_result = {
            "summary": "test",
            "root_cause": {
                "category": "host_internal",
                "component": "x",
                "confidence": 0.92,
                "evidence": [],
            },
        }
        result = DiagnosisResult.from_orchestrator_output(
            diagnosis_id="orch-005",
            agent_result=agent_result,
        )
        assert result.confidence == 0.92


class TestCreateErrorAndCancelled:
    """create_error() and create_cancelled() factory methods."""

    def test_create_error_status_and_message(self):
        """create_error sets status=ERROR and preserves error message."""
        result = DiagnosisResult.create_error(
            diagnosis_id="err-001",
            error="Connection timeout",
        )
        assert result.status == DiagnosisStatus.ERROR
        assert result.error == "Connection timeout"

    def test_create_error_sets_completed_at(self):
        """create_error automatically sets completed_at."""
        result = DiagnosisResult.create_error(
            diagnosis_id="err-002",
            error="timeout",
        )
        assert result.completed_at is not None

    def test_create_cancelled_status_and_summary(self):
        """create_cancelled sets status=CANCELLED with standard summary."""
        result = DiagnosisResult.create_cancelled(
            diagnosis_id="cancel-001",
        )
        assert result.status == DiagnosisStatus.CANCELLED
        assert result.summary == "Diagnosis cancelled by user"

    def test_create_cancelled_default_mode_interactive(self):
        """create_cancelled defaults to INTERACTIVE mode."""
        result = DiagnosisResult.create_cancelled(
            diagnosis_id="cancel-002",
        )
        assert result.mode == DiagnosisMode.INTERACTIVE
