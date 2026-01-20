"""Diagnosis Controller - Core dual-mode control logic.

The DiagnosisController manages the diagnosis workflow in two modes:
- Autonomous: Full automated diagnosis without human intervention
- Interactive: Human-in-the-loop with confirmation checkpoints
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

from netsherlock.schemas.alert import DiagnosisRequest
from netsherlock.schemas.config import (
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
)

from .checkpoints import (
    CheckpointCallback,
    CheckpointData,
    CheckpointManager,
    CheckpointResult,
    CheckpointStatus,
)


logger = structlog.get_logger(__name__)


class DiagnosisPhase(str, Enum):
    """Phases in the diagnosis workflow."""

    INIT = "init"
    L1_MONITORING = "l1_monitoring"
    L2_ENVIRONMENT = "l2_environment"
    CLASSIFICATION = "classification"
    MEASUREMENT_PLANNING = "measurement_planning"
    L3_MEASUREMENT = "l3_measurement"
    L4_ANALYSIS = "l4_analysis"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


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
class DiagnosisState:
    """Current state of a diagnosis session.

    Tracks the progress through the diagnosis workflow.
    """

    diagnosis_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    status: DiagnosisStatus = DiagnosisStatus.PENDING
    phase: DiagnosisPhase = DiagnosisPhase.INIT
    mode: DiagnosisMode = DiagnosisMode.INTERACTIVE
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

    # Phase results
    l1_context: dict[str, Any] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    classification: dict[str, Any] = field(default_factory=dict)
    measurement_plan: dict[str, Any] = field(default_factory=dict)
    measurements: dict[str, Any] = field(default_factory=dict)
    analysis: dict[str, Any] = field(default_factory=dict)
    report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "diagnosis_id": self.diagnosis_id,
            "status": self.status.value,
            "phase": self.phase.value,
            "mode": self.mode.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }


@dataclass
class DiagnosisResult:
    """Result of a diagnosis session."""

    diagnosis_id: str
    status: DiagnosisStatus
    mode: DiagnosisMode
    summary: str = ""
    root_cause: dict[str, Any] = field(default_factory=dict)
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    measurements: dict[str, Any] = field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    checkpoint_history: list[CheckpointResult] = field(default_factory=list)

    @classmethod
    def from_state(cls, state: DiagnosisState) -> DiagnosisResult:
        """Create result from diagnosis state."""
        return cls(
            diagnosis_id=state.diagnosis_id,
            status=state.status,
            mode=state.mode,
            root_cause=state.analysis.get("root_cause", {}),
            recommendations=state.analysis.get("recommendations", []),
            measurements=state.measurements,
            started_at=state.started_at,
            completed_at=state.completed_at,
            error=state.error,
        )

    @classmethod
    def cancelled(cls, diagnosis_id: str, mode: DiagnosisMode) -> DiagnosisResult:
        """Create a cancelled result."""
        return cls(
            diagnosis_id=diagnosis_id,
            status=DiagnosisStatus.CANCELLED,
            mode=mode,
            summary="Diagnosis cancelled by user",
        )

    @classmethod
    def error(cls, diagnosis_id: str, mode: DiagnosisMode, error: str) -> DiagnosisResult:
        """Create an error result."""
        return cls(
            diagnosis_id=diagnosis_id,
            status=DiagnosisStatus.ERROR,
            mode=mode,
            error=error,
        )


class DiagnosisController:
    """Controller for dual-mode diagnosis execution.

    Manages the diagnosis workflow, mode selection, and checkpoint
    interactions for both autonomous and interactive modes.

    Example:
        >>> config = DiagnosisConfig()
        >>> controller = DiagnosisController(config)
        >>> result = await controller.run(request)
    """

    def __init__(
        self,
        config: DiagnosisConfig,
        checkpoint_callback: CheckpointCallback | None = None,
    ):
        """Initialize controller.

        Args:
            config: Diagnosis configuration
            checkpoint_callback: Optional callback for checkpoint interactions
        """
        self.config = config
        self.checkpoint_callback = checkpoint_callback

        self._state: DiagnosisState | None = None
        self._checkpoint_manager: CheckpointManager | None = None
        self._interrupt_event = asyncio.Event()
        self._log = logger.bind(component="DiagnosisController")

    @property
    def state(self) -> DiagnosisState | None:
        """Get current diagnosis state."""
        return self._state

    @property
    def is_running(self) -> bool:
        """Check if diagnosis is currently running."""
        return self._state is not None and self._state.status == DiagnosisStatus.RUNNING

    @property
    def is_waiting(self) -> bool:
        """Check if waiting at a checkpoint."""
        return self._state is not None and self._state.status == DiagnosisStatus.WAITING

    async def run(
        self,
        request: DiagnosisRequest,
        source: DiagnosisRequestSource = DiagnosisRequestSource.CLI,
        force_mode: DiagnosisMode | None = None,
    ) -> DiagnosisResult:
        """Run diagnosis workflow.

        Args:
            request: Diagnosis request
            source: Source of the request
            force_mode: Force specific mode (overrides config)

        Returns:
            Diagnosis result
        """
        # Determine mode based on alert type
        alert_type = request.alert_type
        mode = self.config.determine_mode(
            source=source.value,
            alert_type=alert_type,
            force_mode=force_mode,
        )

        # Initialize state
        self._state = DiagnosisState(
            mode=mode,
            status=DiagnosisStatus.RUNNING,
            started_at=datetime.now(),
        )

        # Initialize checkpoint manager for interactive mode
        if mode == DiagnosisMode.INTERACTIVE:
            self._checkpoint_manager = CheckpointManager(
                enabled_checkpoints=self.config.interactive.checkpoints,
                timeout_seconds=self.config.interactive.timeout_seconds,
                auto_confirm_on_timeout=self.config.interactive.auto_confirm_on_timeout,
                callback=self.checkpoint_callback,
            )

        self._log.info(
            "diagnosis_started",
            diagnosis_id=self._state.diagnosis_id,
            mode=mode.value,
            source=source.value,
        )

        try:
            if mode == DiagnosisMode.AUTONOMOUS:
                return await self._run_autonomous(request)
            else:
                return await self._run_interactive(request)
        except asyncio.CancelledError:
            self._log.info("diagnosis_cancelled", diagnosis_id=self._state.diagnosis_id)
            return DiagnosisResult.cancelled(self._state.diagnosis_id, mode)
        except Exception as e:
            self._log.error(
                "diagnosis_error",
                diagnosis_id=self._state.diagnosis_id,
                error=str(e),
            )
            self._state.status = DiagnosisStatus.ERROR
            self._state.error = str(e)
            return DiagnosisResult.error(self._state.diagnosis_id, mode, str(e))
        finally:
            self._state.completed_at = datetime.now()

    async def _run_autonomous(self, request: DiagnosisRequest) -> DiagnosisResult:
        """Run in autonomous mode - full flow without checkpoints.

        Args:
            request: Diagnosis request

        Returns:
            Diagnosis result
        """
        state = self._state
        assert state is not None

        # Phase 1: L1 Monitoring
        state.phase = DiagnosisPhase.L1_MONITORING
        if self._check_interrupt():
            return self._interrupted_result()
        state.l1_context = await self._query_monitoring(request)

        # Phase 2: L2 Environment
        state.phase = DiagnosisPhase.L2_ENVIRONMENT
        if self._check_interrupt():
            return self._interrupted_result()
        state.environment = await self._collect_environment(request, state.l1_context)

        # Phase 3: Classification
        state.phase = DiagnosisPhase.CLASSIFICATION
        if self._check_interrupt():
            return self._interrupted_result()
        state.classification = await self._classify_problem(state.environment)

        # Phase 4: Measurement Planning
        state.phase = DiagnosisPhase.MEASUREMENT_PLANNING
        if self._check_interrupt():
            return self._interrupted_result()
        state.measurement_plan = await self._plan_measurement(state.classification)

        # Phase 5: L3 Measurement
        state.phase = DiagnosisPhase.L3_MEASUREMENT
        if self._check_interrupt():
            return self._interrupted_result()
        state.measurements = await self._execute_measurement(state.measurement_plan)

        # Phase 6: L4 Analysis
        state.phase = DiagnosisPhase.L4_ANALYSIS
        if self._check_interrupt():
            return self._interrupted_result()
        state.analysis = await self._analyze_and_report(
            state.measurements, state.environment
        )

        # Complete
        state.phase = DiagnosisPhase.COMPLETED
        state.status = DiagnosisStatus.COMPLETED

        self._log.info(
            "diagnosis_completed",
            diagnosis_id=state.diagnosis_id,
            mode="autonomous",
        )

        return DiagnosisResult.from_state(state)

    async def _run_interactive(self, request: DiagnosisRequest) -> DiagnosisResult:
        """Run in interactive mode - with checkpoints.

        Args:
            request: Diagnosis request

        Returns:
            Diagnosis result
        """
        state = self._state
        assert state is not None
        assert self._checkpoint_manager is not None

        # Phase 1: L1 Monitoring
        state.phase = DiagnosisPhase.L1_MONITORING
        state.l1_context = await self._query_monitoring(request)

        # Phase 2: L2 Environment
        state.phase = DiagnosisPhase.L2_ENVIRONMENT
        state.environment = await self._collect_environment(request, state.l1_context)

        # Phase 3: Classification
        state.phase = DiagnosisPhase.CLASSIFICATION
        state.classification = await self._classify_problem(state.environment)

        # Checkpoint 1: Problem Classification
        state.status = DiagnosisStatus.WAITING
        checkpoint_result = await self._checkpoint_manager.wait_at(
            CheckpointData(
                checkpoint_type=CheckpointType.PROBLEM_CLASSIFICATION,
                summary=f"Problem classified as: {state.classification.get('type', 'Unknown')}",
                details=state.classification,
                options=["Confirm", "Modify", "Cancel"],
                recommendation="Confirm",
            )
        )

        if checkpoint_result.is_cancelled:
            state.status = DiagnosisStatus.CANCELLED
            state.phase = DiagnosisPhase.CANCELLED
            return DiagnosisResult.cancelled(state.diagnosis_id, state.mode)

        if checkpoint_result.status == CheckpointStatus.MODIFIED:
            # User modified classification
            state.classification["user_modified"] = True
            state.classification["user_input"] = checkpoint_result.user_input

        state.status = DiagnosisStatus.RUNNING

        # Phase 4: Measurement Planning
        state.phase = DiagnosisPhase.MEASUREMENT_PLANNING
        state.measurement_plan = await self._plan_measurement(state.classification)

        # Checkpoint 2: Measurement Plan
        state.status = DiagnosisStatus.WAITING
        checkpoint_result = await self._checkpoint_manager.wait_at(
            CheckpointData(
                checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
                summary=f"Measurement plan: {len(state.measurement_plan.get('tools', []))} tools",
                details=state.measurement_plan,
                options=["Execute", "Modify", "Cancel"],
                recommendation="Execute",
            )
        )

        if checkpoint_result.is_cancelled:
            state.status = DiagnosisStatus.CANCELLED
            state.phase = DiagnosisPhase.CANCELLED
            return DiagnosisResult.cancelled(state.diagnosis_id, state.mode)

        state.status = DiagnosisStatus.RUNNING

        # Phase 5: L3 Measurement
        state.phase = DiagnosisPhase.L3_MEASUREMENT
        state.measurements = await self._execute_measurement(state.measurement_plan)

        # Phase 6: L4 Analysis
        state.phase = DiagnosisPhase.L4_ANALYSIS
        state.analysis = await self._analyze_and_report(
            state.measurements, state.environment
        )

        # Complete
        state.phase = DiagnosisPhase.COMPLETED
        state.status = DiagnosisStatus.COMPLETED

        self._log.info(
            "diagnosis_completed",
            diagnosis_id=state.diagnosis_id,
            mode="interactive",
        )

        result = DiagnosisResult.from_state(state)
        result.checkpoint_history = self._checkpoint_manager.history
        return result

    # === Phase Implementation Stubs ===
    # These will be connected to actual tools/agents

    async def _query_monitoring(self, request: DiagnosisRequest) -> dict[str, Any]:
        """Query L1 monitoring data."""
        # TODO: Connect to L1 tools via ToolExecutor
        self._log.debug("phase_l1_monitoring", request_id=request.request_id)
        return {
            "metrics": [],
            "logs": [],
            "alerts": [],
        }

    async def _collect_environment(
        self, request: DiagnosisRequest, l1_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Collect L2 environment data."""
        # TODO: Connect to L2 tools via ToolExecutor
        self._log.debug("phase_l2_environment", request_id=request.request_id)
        return {
            "host": request.src_host,
            "src_vm": request.src_vm,
            "dst_host": request.dst_host,
            "dst_vm": request.dst_vm,
            "network_type": request.network_type,
            "network_env": {},
        }

    async def _classify_problem(self, environment: dict[str, Any]) -> dict[str, Any]:
        """Classify the problem type."""
        # TODO: Use Agent to classify
        self._log.debug("phase_classification")
        return {
            "type": "vm_network_latency",
            "confidence": 0.85,
            "evidence": [],
        }

    async def _plan_measurement(self, classification: dict[str, Any]) -> dict[str, Any]:
        """Plan measurement execution."""
        # TODO: Use Agent to plan
        self._log.debug("phase_measurement_planning")
        return {
            "tools": ["vm_network_latency_summary.py"],
            "duration": 30,
            "parameters": {},
        }

    async def _execute_measurement(
        self, measurement_plan: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute L3 measurements."""
        # TODO: Connect to L3 tools via ToolExecutor
        self._log.debug("phase_l3_measurement")
        return {
            "segments": [],
            "total_latency": {},
        }

    async def _analyze_and_report(
        self,
        measurements: dict[str, Any],
        environment: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze results and generate report."""
        # TODO: Connect to L4 tools via ToolExecutor
        self._log.debug("phase_l4_analysis")
        return {
            "root_cause": {
                "category": "unknown",
                "confidence": 0.0,
            },
            "recommendations": [],
        }

    # === Interrupt Handling ===

    def interrupt(self) -> None:
        """Request interruption of autonomous execution."""
        if self.config.autonomous.interrupt_enabled:
            self._interrupt_event.set()
            self._log.info("interrupt_requested")

    def _check_interrupt(self) -> bool:
        """Check if interrupt was requested."""
        return self._interrupt_event.is_set()

    def _interrupted_result(self) -> DiagnosisResult:
        """Create interrupted result."""
        if self._state:
            self._state.status = DiagnosisStatus.INTERRUPTED
        return DiagnosisResult(
            diagnosis_id=self._state.diagnosis_id if self._state else "unknown",
            status=DiagnosisStatus.INTERRUPTED,
            mode=self._state.mode if self._state else DiagnosisMode.AUTONOMOUS,
            summary="Diagnosis interrupted by user",
        )

    # === Checkpoint Interaction ===

    def confirm_checkpoint(self, user_input: str | None = None) -> bool:
        """Confirm current waiting checkpoint.

        Args:
            user_input: Optional user input

        Returns:
            True if checkpoint was confirmed
        """
        if self._checkpoint_manager:
            waiting = self._checkpoint_manager.waiting_checkpoint
            if waiting:
                waiting.confirm(user_input)
                return True
        return False

    def cancel_checkpoint(self) -> bool:
        """Cancel current waiting checkpoint.

        Returns:
            True if checkpoint was cancelled
        """
        if self._checkpoint_manager:
            waiting = self._checkpoint_manager.waiting_checkpoint
            if waiting:
                waiting.cancel()
                return True
        return False

    @property
    def waiting_checkpoint_data(self) -> CheckpointData | None:
        """Get data for currently waiting checkpoint."""
        if self._checkpoint_manager:
            waiting = self._checkpoint_manager.waiting_checkpoint
            if waiting:
                return waiting.current_data
        return None
