"""Unified diagnosis result model.

Consolidates the two incompatible DiagnosisResult types:
- controller/diagnosis_controller.py DiagnosisResult (status-centric, dict-based)
- agents/base.py DiagnosisResult (data-centric, typed dataclasses)

into a single DiagnosisResult used as output by both engines.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from netsherlock.schemas.analysis import AnalysisResult
from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.report import Recommendation, RootCause


class DiagnosisStatus(str, Enum):
    """Status of diagnosis execution."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"  # Waiting at checkpoint
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"
    INTERRUPTED = "interrupted"


@dataclass
class DiagnosisResult:
    """Unified diagnosis result — both engines output this type.

    Fields are organized by category:
    - Core identification and lifecycle
    - Request context
    - Diagnosis conclusions (typed)
    - Detailed layer data
    - Report artifacts
    - Controller-specific (checkpoint history)
    - Error information
    """

    # === Core identification ===
    diagnosis_id: str
    status: DiagnosisStatus

    # === Time information ===
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # === Request context ===
    source: DiagnosisRequestSource = DiagnosisRequestSource.CLI
    mode: DiagnosisMode = DiagnosisMode.AUTONOMOUS
    network_type: str = ""
    request_type: str = ""  # latency, packet_drop, connectivity
    src_host: str = ""
    src_vm: str | None = None
    dst_host: str | None = None
    dst_vm: str | None = None

    # === Diagnosis conclusions ===
    summary: str = ""
    root_cause: RootCause | None = None
    recommendations: list[Recommendation] = field(default_factory=list)
    confidence: float = 0.0

    # === Detailed data by layer ===
    l1_observations: dict[str, Any] = field(default_factory=dict)
    l2_environment: dict[str, Any] = field(default_factory=dict)
    l3_measurements: dict[str, Any] = field(default_factory=dict)
    l4_analysis: dict[str, Any] = field(default_factory=dict)

    # === Report artifacts ===
    analysis_result: AnalysisResult | None = None
    markdown_report: str = ""
    report_path: str = ""

    # === Controller-specific ===
    checkpoint_history: list[Any] = field(default_factory=list)

    # === Error information ===
    error: str | None = None

    # === Factory methods ===

    @classmethod
    def from_controller_state(
        cls,
        state: Any,
        analysis_result: AnalysisResult | None = None,
        checkpoint_history: list[Any] | None = None,
    ) -> DiagnosisResult:
        """Create result from controller's DiagnosisState.

        Args:
            state: DiagnosisState from DiagnosisController (imported as Any
                   to avoid circular imports with controller module).
            analysis_result: Optional AnalysisResult from L4 analysis.
            checkpoint_history: Optional list of CheckpointResult from
                interactive mode.

        Returns:
            Unified DiagnosisResult.
        """
        # Map controller's dict-based root_cause to typed RootCause
        raw_root_cause = state.analysis.get("root_cause", {})
        root_cause = None
        if raw_root_cause:
            from netsherlock.schemas.report import RootCauseCategory

            raw_category = raw_root_cause.get("category", "unknown")
            try:
                category = RootCauseCategory(raw_category)
            except ValueError:
                category = RootCauseCategory.UNKNOWN

            root_cause = RootCause(
                category=category,
                component=raw_root_cause.get("component", ""),
                confidence=raw_root_cause.get("confidence", 0.0),
                evidence=raw_root_cause.get("evidence", []),
                contributing_factors=raw_root_cause.get(
                    "contributing_factors", []
                ),
            )

        # Map controller's list[dict] recommendations to typed Recommendation
        raw_recs = state.analysis.get("recommendations", [])
        recommendations = []
        _priority_str_to_int = {"high": 1, "medium": 2, "low": 3}
        for raw_rec in raw_recs:
            if isinstance(raw_rec, dict):
                raw_prio = raw_rec.get("priority", 1)
                priority = (
                    _priority_str_to_int.get(raw_prio, 2)
                    if isinstance(raw_prio, str)
                    else raw_prio
                )
                recommendations.append(
                    Recommendation(
                        priority=priority,
                        action=raw_rec.get("action", ""),
                        command=raw_rec.get("command", ""),
                        metric=raw_rec.get("metric", ""),
                        rationale=raw_rec.get("rationale", ""),
                    )
                )
            elif isinstance(raw_rec, Recommendation):
                recommendations.append(raw_rec)

        # Fall back to analysis_result recommendations if state.analysis had none
        if not recommendations and analysis_result and analysis_result.recommendations:
            for rec in analysis_result.recommendations:
                raw_prio = getattr(rec, "priority", "medium")
                priority = (
                    _priority_str_to_int.get(raw_prio, 2)
                    if isinstance(raw_prio, str)
                    else raw_prio
                )
                recommendations.append(
                    Recommendation(
                        priority=priority,
                        action=getattr(rec, "action", ""),
                        rationale=getattr(rec, "rationale", ""),
                    )
                )

        summary = ""
        if analysis_result:
            summary = analysis_result.summary()

        # Get confidence: prefer from root_cause, then analysis_result, then analysis dict
        confidence = 0.0
        if root_cause and root_cause.confidence > 0:
            confidence = root_cause.confidence
        elif analysis_result and analysis_result.confidence > 0:
            confidence = analysis_result.confidence
        else:
            confidence = raw_root_cause.get("confidence", 0.0)

        result = cls(
            diagnosis_id=state.diagnosis_id,
            status=DiagnosisStatus(state.status.value),
            started_at=state.started_at,
            completed_at=state.completed_at,
            source=DiagnosisRequestSource.CLI,
            mode=state.mode,
            summary=summary,
            root_cause=root_cause,
            recommendations=recommendations,
            confidence=confidence,
            l3_measurements=state.measurements,
            l4_analysis=state.analysis,
            analysis_result=analysis_result,
            markdown_report=state.analysis.get("markdown_report", ""),
            report_path=state.analysis.get("report_path", ""),
            checkpoint_history=checkpoint_history or [],
            error=state.error,
        )
        return result

    @classmethod
    def from_orchestrator_output(
        cls,
        diagnosis_id: str,
        agent_result: Any,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        source: DiagnosisRequestSource = DiagnosisRequestSource.CLI,
    ) -> DiagnosisResult:
        """Create result from orchestrator agent output.

        Args:
            diagnosis_id: Unique identifier for this diagnosis.
            agent_result: Raw output from the Claude Agent SDK query.
            started_at: When the diagnosis started.
            completed_at: When the diagnosis completed.
            source: Where the request came from.

        Returns:
            Unified DiagnosisResult.
        """
        # Parse agent result - the orchestrator's _synthesize_diagnosis()
        # will provide structured data; for now handle both dict and raw forms
        if isinstance(agent_result, dict):
            summary = agent_result.get("summary", "")
            raw_root_cause = agent_result.get("root_cause", {})
            raw_recs = agent_result.get("recommendations", [])
            l1_obs = agent_result.get("l1_observations", {})
            l2_env = agent_result.get("l2_environment", {})
            l3_meas = agent_result.get("l3_measurements", {})
        else:
            # Raw text output from agent
            summary = str(agent_result) if agent_result else ""
            raw_root_cause = {}
            raw_recs = []
            l1_obs = {}
            l2_env = {}
            l3_meas = {}

        root_cause = None
        if raw_root_cause:
            from netsherlock.schemas.report import RootCauseCategory

            root_cause = RootCause(
                category=RootCauseCategory(
                    raw_root_cause.get("category", "unknown")
                ),
                component=raw_root_cause.get("component", ""),
                confidence=raw_root_cause.get("confidence", 0.0),
                evidence=raw_root_cause.get("evidence", []),
                contributing_factors=raw_root_cause.get(
                    "contributing_factors", []
                ),
            )

        recommendations = []
        for raw_rec in raw_recs:
            if isinstance(raw_rec, dict):
                recommendations.append(
                    Recommendation(
                        priority=raw_rec.get("priority", 1),
                        action=raw_rec.get("action", ""),
                        rationale=raw_rec.get("rationale", ""),
                    )
                )
            elif isinstance(raw_rec, Recommendation):
                recommendations.append(raw_rec)

        return cls(
            diagnosis_id=diagnosis_id,
            status=DiagnosisStatus.COMPLETED,
            started_at=started_at,
            completed_at=completed_at,
            source=source,
            mode=DiagnosisMode.AUTONOMOUS,
            summary=summary,
            root_cause=root_cause,
            recommendations=recommendations,
            confidence=root_cause.confidence if root_cause else 0.0,
            l1_observations=l1_obs,
            l2_environment=l2_env,
            l3_measurements=l3_meas,
        )

    @classmethod
    def create_error(
        cls,
        diagnosis_id: str,
        error: str,
        mode: DiagnosisMode = DiagnosisMode.AUTONOMOUS,
        source: DiagnosisRequestSource = DiagnosisRequestSource.CLI,
        started_at: datetime | None = None,
    ) -> DiagnosisResult:
        """Create an error result."""
        return cls(
            diagnosis_id=diagnosis_id,
            status=DiagnosisStatus.ERROR,
            mode=mode,
            source=source,
            error=error,
            started_at=started_at,
            completed_at=datetime.now(),
        )

    @classmethod
    def create_cancelled(
        cls,
        diagnosis_id: str,
        mode: DiagnosisMode = DiagnosisMode.INTERACTIVE,
        source: DiagnosisRequestSource = DiagnosisRequestSource.CLI,
    ) -> DiagnosisResult:
        """Create a cancelled result."""
        return cls(
            diagnosis_id=diagnosis_id,
            status=DiagnosisStatus.CANCELLED,
            mode=mode,
            source=source,
            summary="Diagnosis cancelled by user",
            completed_at=datetime.now(),
        )
