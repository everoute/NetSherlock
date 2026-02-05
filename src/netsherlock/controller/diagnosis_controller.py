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
from netsherlock.schemas.analysis import (
    AnalysisResult,
    LatencyBreakdown,
    LayerType,
    ProbableCause,
    Recommendation as AnalysisRecommendation,
    SegmentData,
)
from netsherlock.schemas.config import (
    CheckpointType,
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
)
from netsherlock.schemas.minimal_input import MinimalInputConfig
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus

from .checkpoints import (
    CheckpointCallback,
    CheckpointData,
    CheckpointManager,
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



# DiagnosisResult is now imported from schemas.result.
# The following helper functions create results adapted from controller state.



# =============================================================================
# Workflow Lookup Table
# =============================================================================
#
# Maps (network_type, request_type, mode) → (measurement_skill, analysis_skill, param_builder)
#
# Supported combinations from diagnosis-workflow-architecture.md:
#   - system + latency + boundary → system-network-path-tracer
#   - system + packet_drop + boundary → system-network-path-tracer
#   - vm + latency + boundary → vm-network-path-tracer
#   - vm + packet_drop + boundary → vm-network-path-tracer
#   - vm + latency + segment → vm-latency-measurement
#
# Mode defaults:
#   - VM: boundary (host-only, no VM SSH needed)
#   - System: boundary (host-to-host)
#   - If VM SSH available and segment requested, use segment mode
#

WORKFLOW_TABLE: dict[tuple[str, str, str], tuple[str, str, str]] = {
    # (network_type, request_type, mode) → (measurement_skill, analysis_skill, param_builder)
    #
    # ========== Boundary Mode (边界定界) ==========
    # System Network
    ("system", "latency", "boundary"): (
        "system-network-path-tracer",
        "system-network-latency-analysis",
        "_build_system_skill_params",
    ),
    ("system", "packet_drop", "boundary"): (
        "system-network-path-tracer",
        "system-network-drop-analysis",
        "_build_system_skill_params",
    ),
    # VM Network
    ("vm", "latency", "boundary"): (
        "vm-network-path-tracer",
        "vm-network-latency-analysis",
        "_build_vm_path_tracer_params",
    ),
    ("vm", "packet_drop", "boundary"): (
        "vm-network-path-tracer",
        "vm-network-drop-analysis",
        "_build_vm_path_tracer_params",
    ),
    #
    # ========== Segment Mode (分段定界) ==========
    # VM Network - 8-point measurement (requires VM SSH)
    ("vm", "latency", "segment"): (
        "vm-latency-measurement",
        "vm-latency-analysis",
        "_build_skill_params",
    ),
}

# Default mode for each (network_type, request_type)
DEFAULT_WORKFLOW_MODE: dict[tuple[str, str], str] = {
    ("system", "latency"): "boundary",
    ("system", "packet_drop"): "boundary",
    ("vm", "latency"): "boundary",  # Default to boundary; segment if options["segment"]=True
    ("vm", "packet_drop"): "boundary",
}


def _lookup_workflow(
    network_type: str,
    request_type: str,
    mode: str | None = None,
) -> tuple[str, str, str] | None:
    """Look up workflow from table.

    Args:
        network_type: "vm" or "system"
        request_type: "latency", "packet_drop", etc.
        mode: "boundary", "segment", etc. If None, use default

    Returns:
        Tuple of (measurement_skill, analysis_skill, param_builder) or None
    """
    if mode is None:
        mode = DEFAULT_WORKFLOW_MODE.get((network_type, request_type), "boundary")

    key = (network_type, request_type, mode)
    workflow = WORKFLOW_TABLE.get(key)

    if workflow is None and mode != "boundary":
        # Fallback to boundary mode if requested mode not available
        fallback_key = (network_type, request_type, "boundary")
        workflow = WORKFLOW_TABLE.get(fallback_key)

    return workflow


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
        llm_model: str | None = None,
        llm_max_turns: int | None = None,
        llm_max_budget_usd: float | None = None,
        bpf_local_tools_path: str | Path | None = None,
        bpf_remote_tools_path: str | Path | None = None,
    ):
        """Initialize controller.

        Args:
            config: Diagnosis configuration
            checkpoint_callback: Optional callback for checkpoint interactions
            skill_executor: Optional custom skill executor (for testing)
            project_path: Path to project root for SkillExecutor
            global_inventory_path: Path to global inventory YAML (auto mode)
            minimal_input_path: Path to minimal input YAML (manual mode)
            llm_model: Claude model to use (e.g., "claude-haiku-4-5-20251001")
            llm_max_turns: Maximum agent turns (None for unlimited)
            llm_max_budget_usd: Maximum budget in USD (None for unlimited)
            bpf_local_tools_path: Local path to BPF measurement tools
            bpf_remote_tools_path: Remote path for deployed tools on target hosts
        """
        self.config = config
        self.checkpoint_callback = checkpoint_callback
        self._skill_executor = skill_executor
        self._project_path = Path(project_path) if project_path else Path.cwd()
        self._global_inventory_path = global_inventory_path
        self._minimal_input_path = minimal_input_path
        self._llm_model = llm_model
        self._llm_max_turns = llm_max_turns
        self._llm_max_budget_usd = llm_max_budget_usd
        self._bpf_local_tools_path = Path(bpf_local_tools_path) if bpf_local_tools_path else None
        self._bpf_remote_tools_path = Path(bpf_remote_tools_path) if bpf_remote_tools_path else Path("/tmp/netsherlock-tools")

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
            model=self._llm_model,
            permission_mode="bypassPermissions",
            max_turns=self._llm_max_turns,
            max_budget_usd=self._llm_max_budget_usd,
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
            # Extract test IPs from request options (sent by ping_monitor)
            options = request.options or {}
            return self._global_inventory.build_minimal_input(
                src_host_ip=request.src_host,
                src_vm_uuid=request.src_vm,
                dst_host_ip=request.dst_host,
                dst_vm_uuid=request.dst_vm,
                src_test_ip=options.get("src_test_ip"),
                dst_test_ip=options.get("dst_test_ip"),
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
            return DiagnosisResult.create_error(self._state.diagnosis_id, error=f"Config error: {e}", mode=mode)

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
            return DiagnosisResult.create_cancelled(self._state.diagnosis_id, mode=mode)
        except Exception as e:
            self._log.error(
                "diagnosis_error",
                diagnosis_id=self._state.diagnosis_id,
                error=str(e),
            )
            self._state.status = DiagnosisStatus.ERROR
            self._state.error = str(e)
            return DiagnosisResult.create_error(self._state.diagnosis_id, error=str(e), mode=mode)
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
        state.classification = await self._classify_problem(state.environment, request)

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
            state.measurements, state.environment, state.measurement_plan
        )

        # Complete
        state.phase = DiagnosisPhase.COMPLETED
        state.status = DiagnosisStatus.COMPLETED

        self._log.info(
            "diagnosis_completed",
            diagnosis_id=state.diagnosis_id,
            mode="autonomous",
        )

        return DiagnosisResult.from_controller_state(state, analysis_result=self._analysis_result)

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
        state.classification = await self._classify_problem(state.environment, request)

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
            return DiagnosisResult.create_cancelled(state.diagnosis_id, mode=state.mode)

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
            return DiagnosisResult.create_cancelled(state.diagnosis_id, mode=state.mode)

        state.status = DiagnosisStatus.RUNNING

        # Phase 5: L3 Measurement
        state.phase = DiagnosisPhase.L3_MEASUREMENT
        state.measurements = await self._execute_measurement(state.measurement_plan, state.environment)

        # Phase 6: L4 Analysis
        state.phase = DiagnosisPhase.L4_ANALYSIS
        state.analysis = await self._analyze_and_report(
            state.measurements, state.environment, state.measurement_plan
        )

        # Complete
        state.phase = DiagnosisPhase.COMPLETED
        state.status = DiagnosisStatus.COMPLETED

        self._log.info(
            "diagnosis_completed",
            diagnosis_id=state.diagnosis_id,
            mode="interactive",
        )

        return DiagnosisResult.from_controller_state(
            state,
            analysis_result=self._analysis_result,
            checkpoint_history=self._checkpoint_manager.history,
        )

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

            # Log L2 source environment collection result
            src_nics = result["src_env"].get("nics", [])
            self._log.info(
                "l2_src_env_collected",
                success=src_env_result.is_success,
                test_ip=src_vm_node.test_ip,
                qemu_pid=result["src_env"].get("qemu_pid"),
                vnet=src_nics[0].get("host_vnet") if src_nics else None,
                ovs_bridge=src_nics[0].get("ovs_bridge") if src_nics else None,
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
            # System mode returns a list of ports in parsed_list key
            if src_env_result.is_success:
                result["src_env"] = src_env_result.data.get("parsed_list", src_env_result.data)
            else:
                result["src_env"] = []

            # Log L2 source environment for system network
            src_ports = result["src_env"] if isinstance(result["src_env"], list) else []
            storage_port = next((p for p in src_ports if p.get("port_type") == "storage"), None)
            if storage_port:
                self._log.info(
                    "l2_src_env_collected_system",
                    success=src_env_result.is_success,
                    storage_ip=storage_port.get("ip_address"),
                    phy_nic=storage_port.get("physical_nics", [{}])[0].get("name"),
                )

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

            # Log L2 destination environment collection result
            dst_nics = result["dst_env"].get("nics", [])
            self._log.info(
                "l2_dst_env_collected",
                success=dst_env_result.is_success,
                test_ip=dst_vm_node.test_ip,
                qemu_pid=result["dst_env"].get("qemu_pid"),
                vnet=dst_nics[0].get("host_vnet") if dst_nics else None,
                ovs_bridge=dst_nics[0].get("ovs_bridge") if dst_nics else None,
            )

        elif request.dst_host and request.network_type == "system" and dst_host_node:
            # Collect destination environment for system network
            dst_env_result = await executor.invoke(
                skill_name="network-env-collector",
                parameters={
                    "mode": "system",
                    "host": dst_host_node.ssh.host,
                    "user": dst_host_node.ssh.user,
                },
            )
            # System mode returns a list of ports in parsed_list key
            if dst_env_result.is_success:
                result["dst_env"] = dst_env_result.data.get("parsed_list", dst_env_result.data)
            else:
                result["dst_env"] = []

            # Log L2 destination environment for system network
            dst_ports = result["dst_env"] if isinstance(result["dst_env"], list) else []
            storage_port = next((p for p in dst_ports if p.get("port_type") == "storage"), None)
            if storage_port:
                self._log.info(
                    "l2_dst_env_collected_system",
                    success=dst_env_result.is_success,
                    storage_ip=storage_port.get("ip_address"),
                    phy_nic=storage_port.get("physical_nics", [{}])[0].get("name"),
                )

        return result

    async def _classify_problem(
        self, environment: dict[str, Any], request: DiagnosisRequest
    ) -> dict[str, Any]:
        """Classify the problem type using workflow lookup table.

        Determines the workflow based on:
        - network_type: from environment (vm/system)
        - request_type: from request (latency/packet_drop)
        - mode: from request options or default

        Args:
            environment: L2 environment data
            request: The diagnosis request

        Returns:
            Classification dict with workflow info
        """
        self._log.debug("phase_classification")

        network_type = environment.get("network_type", "vm")
        request_type = request.request_type  # latency, packet_drop, connectivity
        is_cross_node = environment.get("dst_host") is not None

        # Determine workflow mode from request options
        mode = request.options.get("mode")
        if mode is None:
            if request.options.get("segment"):
                mode = "segment"
            else:
                mode = DEFAULT_WORKFLOW_MODE.get((network_type, request_type), "boundary")

        # Look up workflow
        workflow = _lookup_workflow(network_type, request_type, mode)
        if workflow is None:
            return {
                "type": "unsupported",
                "network_type": network_type,
                "request_type": request_type,
                "mode": mode,
                "is_cross_node": is_cross_node,
                "confidence": 0.0,
                "error": f"No workflow for {network_type}/{request_type}/{mode}",
            }

        measurement_skill, analysis_skill, param_builder = workflow

        # Build problem type string for backward compatibility
        if network_type == "vm":
            if is_cross_node:
                problem_type = f"cross_node_vm_{request_type}"
            else:
                problem_type = f"single_node_vm_{request_type}"
        else:
            problem_type = f"system_network_{request_type}"

        return {
            "type": problem_type,
            "network_type": network_type,
            "request_type": request_type,
            "mode": mode,
            "is_cross_node": is_cross_node,
            "confidence": 0.90,
            "evidence": [
                f"Network type: {network_type}",
                f"Request type: {request_type}",
                f"Mode: {mode}",
                f"Cross-node: {is_cross_node}",
            ],
            # Workflow info for downstream phases
            "workflow": {
                "measurement_skill": measurement_skill,
                "analysis_skill": analysis_skill,
                "param_builder": param_builder,
            },
        }

    async def _plan_measurement(
        self,
        classification: dict[str, Any],
        environment: dict[str, Any],
        request: DiagnosisRequest,
    ) -> dict[str, Any]:
        """Plan measurement execution using workflow from classification.

        Uses workflow info from classification phase to determine skill and params.
        """
        self._log.debug("phase_measurement_planning")
        assert self._minimal_input is not None

        # Check for unsupported classification
        if classification.get("type") == "unsupported":
            self._log.warning(
                "unsupported_workflow",
                error=classification.get("error"),
            )
            return {
                "mode": "unsupported",
                "reason": classification.get("error", "Unknown workflow"),
            }

        # Get workflow info from classification
        workflow = classification.get("workflow", {})
        measurement_skill = workflow.get("measurement_skill")
        analysis_skill = workflow.get("analysis_skill")
        param_builder_name = workflow.get("param_builder")

        if not measurement_skill or not param_builder_name:
            # Fallback for backward compatibility with old classification format
            problem_type = classification.get("type", "")
            self._log.warning(
                "missing_workflow_info_using_fallback",
                problem_type=problem_type,
            )
            return await self._plan_measurement_legacy(classification, environment, request)

        # Get param builder method
        param_builder = getattr(self, param_builder_name, None)
        if param_builder is None:
            self._log.error(
                "param_builder_not_found",
                param_builder=param_builder_name,
            )
            return {
                "mode": "unsupported",
                "reason": f"Param builder '{param_builder_name}' not found",
            }

        # Build skill parameters
        skill_params = param_builder(environment, request)

        self._log.info(
            "measurement_planned",
            skill=measurement_skill,
            analysis_skill=analysis_skill,
            mode=classification.get("mode", "boundary"),
        )

        return {
            "mode": "skill",
            "skill": measurement_skill,
            "analysis_skill": analysis_skill,
            "parameters": skill_params,
            "duration": request.options.get("duration", 30),
            "workflow_mode": classification.get("mode", "boundary"),
        }

    async def _plan_measurement_legacy(
        self,
        classification: dict[str, Any],
        environment: dict[str, Any],
        request: DiagnosisRequest,
    ) -> dict[str, Any]:
        """Legacy measurement planning for backward compatibility.

        Used when classification doesn't include workflow info (old format).
        """
        problem_type = classification.get("type", "")

        if problem_type == "cross_node_vm_latency":
            skill_params = self._build_skill_params(environment, request)
            return {
                "mode": "skill",
                "skill": "vm-latency-measurement",
                "analysis_skill": "vm-latency-analysis",
                "parameters": skill_params,
                "duration": request.options.get("duration", 30),
            }
        elif problem_type == "system_network_latency":
            skill_params = self._build_system_skill_params(environment, request)
            return {
                "mode": "skill",
                "skill": "system-network-path-tracer",
                "analysis_skill": "system-network-latency-analysis",
                "parameters": skill_params,
                "duration": request.options.get("duration", 30),
            }
        else:
            self._log.warning("unsupported_problem_type", type=problem_type)
            return {
                "mode": "unsupported",
                "reason": f"Problem type '{problem_type}' not supported",
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
            # Generate ICMP traffic from sender VM (default: False, use background traffic)
            "generate_traffic": request.options.get("generate_traffic", False),
        }

        # BPF tools paths
        if self._bpf_local_tools_path:
            params["local_tools_path"] = str(self._bpf_local_tools_path)
        if self._bpf_remote_tools_path:
            params["remote_tools_path"] = str(self._bpf_remote_tools_path)

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

        # Log L2→L3 data flow
        self._log.info(
            "l2_to_l3_params_built",
            src_vnet=params.get("sender_vnet"),
            src_phy_nic=params.get("sender_phy_nic"),
            dst_vnet=params.get("receiver_vnet"),
            dst_phy_nic=params.get("receiver_phy_nic"),
            local_tools_path=params.get("local_tools_path"),
            remote_tools_path=params.get("remote_tools_path"),
        )

        return params

    def _build_system_skill_params(
        self,
        environment: dict[str, Any],
        request: DiagnosisRequest,
    ) -> dict[str, Any]:
        """Build skill parameters for system network path tracer.

        Maps L2 environment data to system-network-path-tracer skill parameters.
        For host-to-host latency measurement.
        """
        assert self._minimal_input is not None

        src_env = environment.get("src_env", [])
        dst_env = environment.get("dst_env", [])

        # Get host node configurations
        src_host_node = self._minimal_input.get_node("host-sender")
        dst_host_node = self._minimal_input.get_node("host-receiver")

        # Extract storage port info from L2 env (system mode returns list of ports)
        src_ports = src_env if isinstance(src_env, list) else []
        dst_ports = dst_env if isinstance(dst_env, list) else []

        src_storage_port = next((p for p in src_ports if p.get("port_type") == "storage"), None)
        dst_storage_port = next((p for p in dst_ports if p.get("port_type") == "storage"), None)

        params: dict[str, Any] = {
            # Duration and focus
            "duration": request.options.get("duration", 30),
            "focus": request.options.get("focus", "latency"),
            "generate_traffic": request.options.get("generate_traffic", True),
            "protocol": request.options.get("protocol", "icmp"),
        }

        # BPF tools paths
        if self._bpf_local_tools_path:
            params["local_tools_path"] = str(self._bpf_local_tools_path)
        if self._bpf_remote_tools_path:
            params["remote_tools_path"] = str(self._bpf_remote_tools_path)

        # Sender host info
        if src_host_node:
            params["sender_host_ssh"] = src_host_node.ssh_string

        # Sender network info from L2 env
        if src_storage_port:
            params["sender_ip"] = src_storage_port.get("ip_address")
            phy_nics = src_storage_port.get("physical_nics", [])
            if phy_nics:
                params["sender_phy_if"] = phy_nics[0].get("name")

        # Receiver host info
        if dst_host_node:
            params["receiver_host_ssh"] = dst_host_node.ssh_string

        # Receiver network info from L2 env
        if dst_storage_port:
            params["receiver_ip"] = dst_storage_port.get("ip_address")
            phy_nics = dst_storage_port.get("physical_nics", [])
            if phy_nics:
                params["receiver_phy_if"] = phy_nics[0].get("name")

        # Log L2→L3 data flow for system network
        self._log.info(
            "l2_to_l3_system_params_built",
            sender_ip=params.get("sender_ip"),
            sender_phy_if=params.get("sender_phy_if"),
            receiver_ip=params.get("receiver_ip"),
            receiver_phy_if=params.get("receiver_phy_if"),
            focus=params.get("focus"),
            local_tools_path=params.get("local_tools_path"),
        )

        return params

    def _build_vm_path_tracer_params(
        self,
        environment: dict[str, Any],
        request: DiagnosisRequest,
    ) -> dict[str, Any]:
        """Build skill parameters for vm-network-path-tracer (boundary mode).

        Maps L2 environment data to vm-network-path-tracer skill parameters.
        This is for host-only boundary detection (no VM SSH needed).

        Parameter name mapping to skill expectations:
            --sender-host-ssh     = sender_host_ssh
            --sender-vm-ip        = sender_vm_ip
            --receiver-vm-ip      = receiver_vm_ip
            --send-vnet-if        = sender_vnet
            --sender-phy-if       = sender_phy_nic
            --receiver-host-ssh   = receiver_host_ssh
            --recv-vnet-if        = receiver_vnet
            --receiver-phy-if     = receiver_phy_nic
            --local-tools-path    = local_tools_path
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

        # Determine focus from request_type
        request_type = request.request_type
        if request_type == "packet_drop":
            default_focus = "drop"
        else:
            default_focus = "latency"

        params: dict[str, Any] = {
            # Duration and focus
            "duration": request.options.get("duration", 30),
            "focus": request.options.get("focus", default_focus),
            "generate_traffic": request.options.get("generate_traffic", True),
            "protocol": request.options.get("protocol", "icmp"),
        }

        # BPF tools paths
        if self._bpf_local_tools_path:
            params["local_tools_path"] = str(self._bpf_local_tools_path)
        if self._bpf_remote_tools_path:
            params["remote_tools_path"] = str(self._bpf_remote_tools_path)

        # Sender VM info (IP for BPF filter, SSH optional for traffic gen)
        if src_vm_node:
            params["sender_vm_ip"] = src_vm_node.test_ip  # Critical: use test_ip
            # Optionally include VM SSH if available (for traffic generation from VM)
            if src_vm_node.ssh_string:
                params["sender_vm_ssh"] = src_vm_node.ssh_string

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

        # Log L2→L3 data flow
        self._log.info(
            "l2_to_l3_vm_path_tracer_params_built",
            sender_vm_ip=params.get("sender_vm_ip"),
            sender_vnet=params.get("sender_vnet"),
            sender_phy_nic=params.get("sender_phy_nic"),
            receiver_vm_ip=params.get("receiver_vm_ip"),
            receiver_vnet=params.get("receiver_vnet"),
            receiver_phy_nic=params.get("receiver_phy_nic"),
            focus=params.get("focus"),
            local_tools_path=params.get("local_tools_path"),
        )

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
        self._log.info(
            "l3_measurement_starting",
            skill=measurement_plan.get("skill"),
            duration=measurement_plan.get("parameters", {}).get("duration"),
        )

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
                # Log L3 measurement result
                segments = result.data.get("segments", {})
                total_rtt = result.data.get("total_rtt_us", 0)
                self._log.info(
                    "l3_measurement_completed",
                    total_rtt_us=total_rtt,
                    segment_count=len(segments),
                    segments_preview=list(segments.keys())[:5] if segments else [],
                )
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
        measurement_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Analyze results and generate report via analysis skill.

        Uses analysis_skill from measurement_plan if available, otherwise
        falls back to network_type-based selection for backward compatibility.

        Args:
            measurements: Measurement data
            environment: Environment data
            measurement_plan: Measurement plan with analysis_skill info

        Returns:
            Analysis results including detailed report
        """
        self._log.info(
            "l4_analysis_starting",
            measurement_status=measurements.get("status"),
        )

        if measurements.get("status") != "success":
            return {
                "status": "skipped",
                "reason": f"Measurement failed: {measurements.get('error', 'unknown')}",
            }

        # Find measurement directory - try from skill output or find latest
        measurement_dir = measurements.get("data", {}).get("measurement_dir", "")
        if not measurement_dir:
            # Find the most recently modified measurement-* directory
            measurement_dirs = sorted(
                self._project_path.glob("measurement-*"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if measurement_dirs:
                measurement_dir = str(measurement_dirs[0])
                self._log.info(
                    "l4_using_latest_measurement_dir",
                    measurement_dir=measurement_dir,
                )

        if not measurement_dir:
            return {
                "status": "error",
                "reason": "No measurement_dir found",
            }

        # Get analysis skill from measurement plan or fall back to old logic
        analysis_skill = None
        if measurement_plan:
            analysis_skill = measurement_plan.get("analysis_skill")

        if not analysis_skill:
            # Backward compatibility: determine from network_type
            network_type = environment.get("network_type", "vm")
            self._log.info(
                "l4_fallback_to_network_type",
                network_type=network_type,
            )
            if network_type == "system":
                analysis_skill = "system-network-latency-analysis"
            else:
                analysis_skill = "vm-latency-analysis"

        self._log.info(
            "l4_invoking_analysis_skill",
            analysis_skill=analysis_skill,
            measurement_dir=measurement_dir,
        )

        # Invoke the analysis skill
        executor = self._get_skill_executor()
        analysis_result = await executor.invoke(
            skill_name=analysis_skill,
            parameters={
                "measurement_dir": measurement_dir,
            },
        )

        if not analysis_result.is_success:
            self._log.error(
                "l4_analysis_skill_failed",
                skill=analysis_skill,
                error=analysis_result.error,
            )
            return {
                "status": "error",
                "reason": f"Analysis skill '{analysis_skill}' failed: {analysis_result.error}",
            }

        # Extract results from skill output
        data = analysis_result.data
        detailed_report = data.get("detailed_report", {})
        markdown_report = data.get("markdown_report", "")
        report_path = data.get("report_path", "")

        # Get summary info — try nested path first, then flat data
        summary = detailed_report.get("summary", {})
        primary_contributor = (
            summary.get("primary_contributor")
            or data.get("primary_contributor", "unknown")
        )
        confidence = (
            summary.get("confidence")
            or data.get("confidence", 0.0)
        )
        total_rtt_us = summary.get("total_rtt_us", 0.0)

        self._log.info(
            "l4_analysis_completed",
            analysis_skill=analysis_skill,
            total_rtt_us=total_rtt_us,
            primary_contributor=primary_contributor,
            report_path=report_path,
        )

        # Build AnalysisResult for internal use
        breakdown = self._calculate_breakdown(measurements)
        self._analysis_result = AnalysisResult(
            breakdown=breakdown,
            primary_contributor=breakdown.get_primary_contributor(),
            confidence=confidence,
        )

        if primary_contributor and primary_contributor != "unknown":
            try:
                self._analysis_result.primary_contributor = LayerType(primary_contributor)
            except ValueError:
                pass

        # Populate probable causes from skill output
        raw_causes = data.get("probable_causes", [])
        for raw_cause in raw_causes:
            if isinstance(raw_cause, dict):
                layer = None
                if raw_cause.get("layer"):
                    try:
                        layer = LayerType(raw_cause["layer"])
                    except ValueError:
                        pass
                self._analysis_result.probable_causes.append(
                    ProbableCause(
                        cause=raw_cause.get("cause", ""),
                        confidence=raw_cause.get("confidence", 0.0),
                        evidence=raw_cause.get("evidence", []),
                        layer=layer,
                    )
                )

        # Populate recommendations from skill output
        raw_recs = data.get("recommendations", [])
        for raw_rec in raw_recs:
            if isinstance(raw_rec, dict):
                self._analysis_result.recommendations.append(
                    AnalysisRecommendation(
                        action=raw_rec.get("action", ""),
                        priority=raw_rec.get("priority", "medium"),
                        rationale=raw_rec.get("rationale", ""),
                    )
                )

        return {
            "status": "success",
            "analysis_skill": analysis_skill,
            "root_cause": {
                "category": primary_contributor,
                "confidence": confidence,
            },
            "breakdown": breakdown.to_dict(),
            "detailed_report": detailed_report,
            "markdown_report": markdown_report,
            "report_path": report_path,
        }

    async def _analyze_system_network(
        self,
        measurements: dict[str, Any],
        measurement_dir: str,
    ) -> dict[str, Any]:
        """Analyze system network measurement data via analysis skill.

        Invokes system-network-latency-analysis skill to parse dual-host
        measurement logs and compute end-to-end latency breakdown.

        Args:
            measurements: Measurement data from skill (unused, kept for API compat)
            measurement_dir: Path to measurement directory

        Returns:
            Analysis results including detailed report
        """
        self._log.info(
            "l4_system_network_analysis_starting",
            measurement_dir=measurement_dir,
        )

        # Invoke analysis skill
        executor = self._get_skill_executor()
        analysis_result = await executor.invoke(
            skill_name="system-network-latency-analysis",
            parameters={
                "measurement_dir": measurement_dir,
            },
        )

        if not analysis_result.is_success:
            self._log.error(
                "l4_system_network_analysis_failed",
                error=analysis_result.error,
            )
            return {
                "status": "error",
                "reason": f"Analysis skill failed: {analysis_result.error}",
            }

        # Extract results from skill output
        data = analysis_result.data
        detailed_report = data.get("detailed_report", {})
        markdown_report = data.get("markdown_report", "")
        report_path = data.get("report_path", "")

        summary = detailed_report.get("summary", {})
        total_rtt_us = summary.get("total_rtt_us", 0.0)
        primary_contributor = summary.get("primary_contributor", "unknown")

        self._log.info(
            "l4_system_network_analysis_completed",
            total_rtt_us=total_rtt_us,
            primary_contributor=primary_contributor,
            report_path=report_path,
        )

        # Build segments for breakdown from analysis result
        segments = detailed_report.get("segments", {})
        segments_data = {}
        for seg_id, seg_info in segments.items():
            segments_data[seg_id] = {
                "value_us": seg_info.get("avg_us", 0.0),
                "source": seg_info.get("source", ""),
                "description": seg_info.get("description", ""),
            }

        # Build AnalysisResult
        breakdown = LatencyBreakdown(
            total_rtt_us=total_rtt_us,
            segments={
                name: SegmentData(
                    name=name,
                    value_us=val.get("value_us", 0.0),
                    source=val.get("source", ""),
                    description=val.get("description", ""),
                )
                for name, val in segments_data.items()
            },
        )

        self._analysis_result = AnalysisResult(
            breakdown=breakdown,
            primary_contributor=breakdown.get_primary_contributor(),
            confidence=0.85,
        )

        return {
            "status": "success",
            "root_cause": {
                "category": primary_contributor,
                "confidence": 0.85,
            },
            "breakdown": breakdown.to_dict(),
            "detailed_report": detailed_report,
            "markdown_report": markdown_report,
            "report_path": report_path,
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
            completed_at=datetime.now(),
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
