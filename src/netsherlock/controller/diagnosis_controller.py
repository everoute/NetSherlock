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
from pathlib import Path
from typing import Any

import structlog

from netsherlock.config.global_inventory import GlobalInventory
from netsherlock.core.skill_executor import (
    SkillExecutor,
    SkillExecutorProtocol,
)
from netsherlock.schemas.alert import DiagnosisRequest
from netsherlock.schemas.analysis import AnalysisResult, LatencyBreakdown, LayerType, SegmentData
from netsherlock.schemas.config import (
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
)
from netsherlock.schemas.minimal_input import MinimalInputConfig

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
    analysis_result: AnalysisResult | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    checkpoint_history: list[CheckpointResult] = field(default_factory=list)

    @classmethod
    def from_state(cls, state: DiagnosisState, analysis_result: AnalysisResult | None = None) -> DiagnosisResult:
        """Create result from diagnosis state."""
        result = cls(
            diagnosis_id=state.diagnosis_id,
            status=state.status,
            mode=state.mode,
            root_cause=state.analysis.get("root_cause", {}),
            recommendations=state.analysis.get("recommendations", []),
            measurements=state.measurements,
            analysis_result=analysis_result,
            started_at=state.started_at,
            completed_at=state.completed_at,
            error=state.error,
        )
        if analysis_result:
            result.summary = analysis_result.summary()
        return result

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
    def create_error(cls, diagnosis_id: str, mode: DiagnosisMode, error_msg: str) -> DiagnosisResult:
        """Create an error result."""
        return cls(
            diagnosis_id=diagnosis_id,
            status=DiagnosisStatus.ERROR,
            mode=mode,
            error=error_msg,
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
        skill_executor: SkillExecutorProtocol | None = None,
        project_path: str | Path | None = None,
        global_inventory_path: str | Path | None = None,
        minimal_input_path: str | Path | None = None,
    ):
        """Initialize controller.

        Args:
            config: Diagnosis configuration
            checkpoint_callback: Optional callback for checkpoint interactions
            skill_executor: Optional custom skill executor (for testing)
            project_path: Path to project root for SkillExecutor
            global_inventory_path: Path to global inventory YAML (auto mode)
            minimal_input_path: Path to minimal input YAML (manual mode)
        """
        self.config = config
        self.checkpoint_callback = checkpoint_callback
        self._skill_executor = skill_executor
        self._project_path = Path(project_path) if project_path else Path.cwd()
        self._global_inventory_path = global_inventory_path
        self._minimal_input_path = minimal_input_path

        self._state: DiagnosisState | None = None
        self._checkpoint_manager: CheckpointManager | None = None
        self._interrupt_event = asyncio.Event()
        self._log = logger.bind(component="DiagnosisController")

        # Runtime data
        self._minimal_input: MinimalInputConfig | None = None
        self._global_inventory: GlobalInventory | None = None
        self._analysis_result: AnalysisResult | None = None

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

    def _get_skill_executor(self) -> SkillExecutorProtocol:
        """Get or create skill executor."""
        if self._skill_executor:
            return self._skill_executor
        return SkillExecutor(
            project_path=self._project_path,
            allowed_tools=["Skill", "Bash", "Read", "Write"],
        )

    def _load_minimal_input(self, request: DiagnosisRequest) -> MinimalInputConfig:
        """Load or build MinimalInputConfig.

        For manual mode: Load from YAML file
        For auto mode: Build from GlobalInventory + request

        Args:
            request: Diagnosis request

        Returns:
            MinimalInputConfig instance
        """
        # Manual mode: load from file
        if self._minimal_input_path:
            self._log.info("loading_minimal_input", path=str(self._minimal_input_path))
            return MinimalInputConfig.load(self._minimal_input_path)

        # Auto mode: build from global inventory
        if self._global_inventory_path:
            self._log.info("loading_global_inventory", path=str(self._global_inventory_path))
            self._global_inventory = GlobalInventory.load(self._global_inventory_path)
            return self._global_inventory.build_minimal_input(
                src_host_ip=request.src_host,
                src_vm_uuid=request.src_vm,
                dst_host_ip=request.dst_host,
                dst_vm_uuid=request.dst_vm,
            )

        # Fallback: create minimal config from request
        self._log.warning("no_config_file_provided", msg="Creating minimal config from request")
        from netsherlock.schemas.minimal_input import NodeConfig, NodePair, SSHConfig

        nodes = {}
        # Create basic host-sender node
        nodes["host-sender"] = NodeConfig(
            ssh=SSHConfig(user="root", host=request.src_host),
            workdir="/tmp/netsherlock",
            role="host",
        )

        if request.src_vm:
            nodes["vm-sender"] = NodeConfig(
                ssh=SSHConfig(user="root", host=request.src_host),
                workdir="/tmp/netsherlock",
                role="vm",
                host_ref="host-sender",
                uuid=request.src_vm,
            )

        if request.dst_host:
            nodes["host-receiver"] = NodeConfig(
                ssh=SSHConfig(user="root", host=request.dst_host),
                workdir="/tmp/netsherlock",
                role="host",
            )

        if request.dst_vm and request.dst_host:
            nodes["vm-receiver"] = NodeConfig(
                ssh=SSHConfig(user="root", host=request.dst_host),
                workdir="/tmp/netsherlock",
                role="vm",
                host_ref="host-receiver",
                uuid=request.dst_vm,
            )

        test_pairs = None
        if "vm-sender" in nodes and "vm-receiver" in nodes:
            test_pairs = {"vm": NodePair(server="vm-receiver", client="vm-sender")}

        return MinimalInputConfig(nodes=nodes, test_pairs=test_pairs)

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

        # Load minimal input configuration
        try:
            self._minimal_input = self._load_minimal_input(request)
        except Exception as e:
            self._log.error("failed_to_load_config", error=str(e))
            return DiagnosisResult.create_error(self._state.diagnosis_id, mode, f"Config error: {e}")

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
            return DiagnosisResult.create_error(self._state.diagnosis_id, mode, str(e))
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
        assert self._minimal_input is not None

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
        state.measurement_plan = await self._plan_measurement(state.classification, state.environment, request)

        # Phase 5: L3 Measurement
        state.phase = DiagnosisPhase.L3_MEASUREMENT
        if self._check_interrupt():
            return self._interrupted_result()
        state.measurements = await self._execute_measurement(state.measurement_plan, state.environment)

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

        return DiagnosisResult.from_state(state, self._analysis_result)

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
        assert self._minimal_input is not None

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
        state.measurement_plan = await self._plan_measurement(state.classification, state.environment, request)

        # Checkpoint 2: Measurement Plan
        state.status = DiagnosisStatus.WAITING
        checkpoint_result = await self._checkpoint_manager.wait_at(
            CheckpointData(
                checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
                summary=f"Measurement plan: {state.measurement_plan.get('skill', 'Unknown')}",
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
        state.measurements = await self._execute_measurement(state.measurement_plan, state.environment)

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

        result = DiagnosisResult.from_state(state, self._analysis_result)
        result.checkpoint_history = self._checkpoint_manager.history
        return result

    # === Phase Implementation ===

    async def _query_monitoring(self, request: DiagnosisRequest) -> dict[str, Any]:
        """Query L1 monitoring data.

        This phase is currently a pass-through - L1 data comes from
        the original alert or request parameters.
        """
        self._log.debug("phase_l1_monitoring", request_id=request.request_id)
        return {
            "request_type": request.request_type,
            "network_type": request.network_type,
            "src_host": request.src_host,
            "src_vm": request.src_vm,
            "dst_host": request.dst_host,
            "dst_vm": request.dst_vm,
            "alert": request.alert.model_dump() if request.alert else None,
            "options": request.options,
        }

    async def _collect_environment(
        self, request: DiagnosisRequest, l1_context: dict[str, Any]
    ) -> dict[str, Any]:
        """Collect L2 environment data via network-env-collector Skill.

        Args:
            request: Diagnosis request
            l1_context: L1 context data

        Returns:
            Environment data including network topology
        """
        self._log.debug("phase_l2_environment", request_id=request.request_id)
        assert self._minimal_input is not None

        executor = self._get_skill_executor()
        result: dict[str, Any] = {
            "src_host": request.src_host,
            "dst_host": request.dst_host,
            "network_type": request.network_type,
        }

        # Get node configurations
        src_vm_node = self._minimal_input.get_node("vm-sender")
        dst_vm_node = self._minimal_input.get_node("vm-receiver")
        src_host_node = self._minimal_input.get_node("host-sender")
        dst_host_node = self._minimal_input.get_node("host-receiver")

        # Collect source environment
        if request.network_type == "vm" and request.src_vm and src_vm_node and src_host_node:
            src_env_result = await executor.invoke(
                skill_name="network-env-collector",
                parameters={
                    "mode": "vm",
                    "uuid": request.src_vm,
                    "host_ip": src_host_node.ssh.host,
                    "host_user": src_host_node.ssh.user,
                    "vm_host": src_vm_node.ssh.host,
                    "vm_user": src_vm_node.ssh.user,
                },
            )
            result["src_env"] = src_env_result.data if src_env_result.is_success else {}
            result["src_test_ip"] = src_vm_node.test_ip

            self._log.debug(
                "src_env_collected",
                success=src_env_result.is_success,
                test_ip=src_vm_node.test_ip,
            )

        elif request.network_type == "system" and src_host_node:
            src_env_result = await executor.invoke(
                skill_name="network-env-collector",
                parameters={
                    "mode": "system",
                    "host": src_host_node.ssh.host,
                    "user": src_host_node.ssh.user,
                },
            )
            result["src_env"] = src_env_result.data if src_env_result.is_success else {}

        # Collect destination environment (cross-node scenario)
        if request.dst_host and request.network_type == "vm" and request.dst_vm and dst_vm_node and dst_host_node:
            dst_env_result = await executor.invoke(
                skill_name="network-env-collector",
                parameters={
                    "mode": "vm",
                    "uuid": request.dst_vm,
                    "host_ip": dst_host_node.ssh.host,
                    "host_user": dst_host_node.ssh.user,
                    "vm_host": dst_vm_node.ssh.host,
                    "vm_user": dst_vm_node.ssh.user,
                },
            )
            result["dst_env"] = dst_env_result.data if dst_env_result.is_success else {}
            result["dst_test_ip"] = dst_vm_node.test_ip

            self._log.debug(
                "dst_env_collected",
                success=dst_env_result.is_success,
                test_ip=dst_vm_node.test_ip,
            )

        return result

    async def _classify_problem(self, environment: dict[str, Any]) -> dict[str, Any]:
        """Classify the problem type.

        MVP: Simple classification based on network_type.
        Future: Use LLM for intelligent classification.
        """
        self._log.debug("phase_classification")

        network_type = environment.get("network_type", "vm")
        is_cross_node = environment.get("dst_host") is not None

        if network_type == "vm":
            if is_cross_node:
                problem_type = "cross_node_vm_latency"
            else:
                problem_type = "single_node_vm_latency"
        else:
            problem_type = "system_network_latency"

        return {
            "type": problem_type,
            "network_type": network_type,
            "is_cross_node": is_cross_node,
            "confidence": 0.90,
            "evidence": [
                f"Network type: {network_type}",
                f"Cross-node: {is_cross_node}",
            ],
        }

    async def _plan_measurement(
        self,
        classification: dict[str, Any],
        environment: dict[str, Any],
        request: DiagnosisRequest,
    ) -> dict[str, Any]:
        """Plan measurement execution.

        MVP: Only supports cross-node VM latency via skill.
        """
        self._log.debug("phase_measurement_planning")
        assert self._minimal_input is not None

        problem_type = classification.get("type", "")

        if problem_type == "cross_node_vm_latency":
            # Build skill parameters from environment and minimal_input
            skill_params = self._build_skill_params(environment, request)

            return {
                "mode": "skill",
                "skill": "vm-latency-measurement",
                "parameters": skill_params,
                "duration": request.options.get("duration", 30),
            }
        else:
            # Fallback for unsupported scenarios
            self._log.warning("unsupported_problem_type", type=problem_type)
            return {
                "mode": "unsupported",
                "reason": f"Problem type '{problem_type}' not supported in MVP",
            }

    def _build_skill_params(
        self,
        environment: dict[str, Any],
        request: DiagnosisRequest,
    ) -> dict[str, Any]:
        """Build skill parameters from environment and MinimalInput.

        Maps L2 environment data and MinimalInput config to skill parameters.
        """
        assert self._minimal_input is not None

        src_env = environment.get("src_env", {})
        dst_env = environment.get("dst_env", {})

        # Get node configurations
        src_vm_node = self._minimal_input.get_node("vm-sender")
        dst_vm_node = self._minimal_input.get_node("vm-receiver")
        src_host_node = self._minimal_input.get_node("host-sender")
        dst_host_node = self._minimal_input.get_node("host-receiver")

        # Extract network interface info from L2 env
        src_nics = src_env.get("nics", [])
        dst_nics = dst_env.get("nics", [])

        params: dict[str, Any] = {
            # Duration
            "duration": request.options.get("duration", 30),
        }

        # Sender VM info
        if src_vm_node:
            params["sender_vm_ssh"] = src_vm_node.ssh_string
            params["sender_vm_ip"] = src_vm_node.test_ip  # Critical: use test_ip

        # Sender host info
        if src_host_node:
            params["sender_host_ssh"] = src_host_node.ssh_string

        # Sender network interface info from L2 env
        if src_nics:
            nic = src_nics[0]
            params["sender_vnet"] = nic.get("host_vnet")
            phy_nics = nic.get("physical_nics", [])
            if phy_nics:
                params["sender_phy_nic"] = phy_nics[0].get("name")

        # Receiver VM info
        if dst_vm_node:
            params["receiver_vm_ssh"] = dst_vm_node.ssh_string
            params["receiver_vm_ip"] = dst_vm_node.test_ip  # Critical: use test_ip

        # Receiver host info
        if dst_host_node:
            params["receiver_host_ssh"] = dst_host_node.ssh_string

        # Receiver network interface info from L2 env
        if dst_nics:
            nic = dst_nics[0]
            params["receiver_vnet"] = nic.get("host_vnet")
            phy_nics = nic.get("physical_nics", [])
            if phy_nics:
                params["receiver_phy_nic"] = phy_nics[0].get("name")

        return params

    async def _execute_measurement(
        self, measurement_plan: dict[str, Any], environment: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute L3 measurements via skill.

        Args:
            measurement_plan: Measurement plan from planning phase
            environment: Environment data

        Returns:
            Measurement results including raw data and segments
        """
        self._log.debug("phase_l3_measurement")

        mode = measurement_plan.get("mode", "")

        if mode == "skill":
            skill_name = measurement_plan.get("skill", "")
            parameters = measurement_plan.get("parameters", {})

            executor = self._get_skill_executor()
            result = await executor.invoke(
                skill_name=skill_name,
                parameters=parameters,
            )

            if result.is_success:
                return {
                    "status": "success",
                    "skill": skill_name,
                    "data": result.data,
                    "segments": result.data.get("segments", {}),
                    "total_rtt_us": result.data.get("total_rtt_us", 0),
                    "log_files": result.data.get("log_files", []),
                }
            else:
                self._log.error(
                    "measurement_failed",
                    skill=skill_name,
                    error=result.error,
                )
                return {
                    "status": "error",
                    "error": result.error,
                }
        else:
            return {
                "status": "skipped",
                "reason": measurement_plan.get("reason", "Unsupported mode"),
            }

    async def _analyze_and_report(
        self,
        measurements: dict[str, Any],
        environment: dict[str, Any],
    ) -> dict[str, Any]:
        """Analyze results and generate report.

        Two-phase analysis:
        1. Data calculation (deterministic)
        2. LLM reasoning (intelligent)

        Args:
            measurements: Measurement data
            environment: Environment data

        Returns:
            Analysis results
        """
        self._log.debug("phase_l4_analysis")

        if measurements.get("status") != "success":
            return {
                "status": "skipped",
                "reason": f"Measurement failed: {measurements.get('error', 'unknown')}",
            }

        # Phase 1: Data calculation (deterministic)
        breakdown = self._calculate_breakdown(measurements)

        # Phase 2: LLM reasoning via skill
        executor = self._get_skill_executor()
        analysis_result = await executor.invoke(
            skill_name="vm-latency-analysis",
            parameters={
                "breakdown": breakdown.to_dict(),
                "environment": environment,
            },
        )

        # Build AnalysisResult
        self._analysis_result = AnalysisResult(
            breakdown=breakdown,
            primary_contributor=breakdown.get_primary_contributor(),
        )

        if analysis_result.is_success:
            data = analysis_result.data

            # Parse LLM analysis
            if "primary_contributor" in data:
                try:
                    self._analysis_result.primary_contributor = LayerType(data["primary_contributor"])
                except ValueError:
                    pass

            self._analysis_result.confidence = data.get("confidence", 0.0)
            self._analysis_result.reasoning = data.get("reasoning", "")

            # Add probable causes
            for cause_data in data.get("probable_causes", []):
                layer = None
                if cause_data.get("layer"):
                    try:
                        layer = LayerType(cause_data["layer"])
                    except ValueError:
                        pass
                self._analysis_result.add_probable_cause(
                    cause=cause_data.get("cause", ""),
                    confidence=cause_data.get("confidence", 0.0),
                    evidence=cause_data.get("evidence", []),
                    layer=layer,
                )

            # Add recommendations
            for rec_data in data.get("recommendations", []):
                self._analysis_result.add_recommendation(
                    action=rec_data.get("action", ""),
                    priority=rec_data.get("priority", "medium"),
                    rationale=rec_data.get("rationale", ""),
                )

        return {
            "status": "success",
            "root_cause": {
                "category": (
                    self._analysis_result.primary_contributor.value
                    if self._analysis_result.primary_contributor
                    else "unknown"
                ),
                "confidence": self._analysis_result.confidence,
            },
            "recommendations": [
                {"action": r.action, "priority": r.priority}
                for r in self._analysis_result.recommendations
            ],
            "breakdown": breakdown.to_dict(),
        }

    def _calculate_breakdown(self, measurements: dict[str, Any]) -> LatencyBreakdown:
        """Calculate latency breakdown from measurement data.

        Phase 1 of L4 analysis (deterministic).
        """
        segments_data = measurements.get("segments", {})
        total_rtt_us = measurements.get("total_rtt_us", 0.0)

        # Create segment objects
        segments = {}
        for name, value in segments_data.items():
            if isinstance(value, dict):
                segments[name] = SegmentData(
                    name=name,
                    value_us=value.get("value_us", 0.0),
                    source=value.get("source", ""),
                    description=value.get("description", ""),
                )
            else:
                segments[name] = SegmentData(name=name, value_us=float(value))

        breakdown = LatencyBreakdown(
            total_rtt_us=total_rtt_us,
            segments=segments,
        )

        # Calculate layer attribution
        breakdown.calculate_layer_attribution()

        return breakdown

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
