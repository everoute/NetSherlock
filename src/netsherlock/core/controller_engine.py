"""ControllerEngine — deterministic diagnosis engine wrapping DiagnosisController.

Implements the DiagnosisEngine protocol using the existing DiagnosisController
for a structured, phase-by-phase diagnostic workflow.
"""

from __future__ import annotations

import structlog
from collections.abc import Callable
from pathlib import Path
from typing import Any

from netsherlock.controller.diagnosis_controller import DiagnosisController
from netsherlock.schemas.config import (
    DiagnosisConfig,
    DiagnosisMode,
    DiagnosisRequestSource,
)
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult

log = structlog.get_logger(component="ControllerEngine")


class ControllerEngine:
    """Deterministic diagnosis engine backed by DiagnosisController.

    Creates a fresh DiagnosisController per execute() call. The engine
    itself is stateless; all diagnosis state lives in the controller.
    """

    def __init__(
        self,
        config: DiagnosisConfig,
        global_inventory_path: str | Path | None = None,
        minimal_input_path: str | Path | None = None,
        project_path: str | Path | None = None,
        llm_model: str | None = None,
        llm_max_turns: int | None = None,
        llm_max_budget_usd: float | None = None,
        llm_permission_mode: str | None = None,
        bpf_local_tools_path: str | Path | None = None,
        bpf_remote_tools_path: str | Path | None = None,
        checkpoint_callback: Any | None = None,
    ):
        """Initialize ControllerEngine.

        Args:
            config: Diagnosis configuration (mode selection, checkpoints, etc.)
            global_inventory_path: Path to global inventory YAML (auto mode).
            minimal_input_path: Path to minimal input YAML (manual mode).
            project_path: Path to netsherlock project root.
            llm_model: Claude model for L4 analysis skill.
            llm_max_turns: Maximum agent turns.
            llm_max_budget_usd: Maximum budget in USD.
            llm_permission_mode: Claude Agent SDK permission mode.
            bpf_local_tools_path: Local path to BPF measurement tools.
            bpf_remote_tools_path: Remote path for deployed tools on targets.
            checkpoint_callback: Optional callback for interactive checkpoints.
                Only used when mode is INTERACTIVE and source is CLI.
        """
        self._config = config
        self._global_inventory_path = global_inventory_path
        self._minimal_input_path = minimal_input_path
        self._project_path = project_path
        self._llm_model = llm_model
        self._llm_max_turns = llm_max_turns
        self._llm_max_budget_usd = llm_max_budget_usd
        self._llm_permission_mode = llm_permission_mode
        self._bpf_local_tools_path = bpf_local_tools_path
        self._bpf_remote_tools_path = bpf_remote_tools_path
        self._checkpoint_callback = checkpoint_callback

    @property
    def engine_type(self) -> str:
        return "controller"

    async def execute(
        self,
        request: DiagnosisRequest,
        progress_callback: Callable[[Any], None] | None = None,
    ) -> DiagnosisResult:
        """Execute diagnosis via DiagnosisController.

        Creates a fresh controller, determines mode, and runs the
        structured diagnostic workflow.

        Args:
            request: Unified diagnosis request.

        Returns:
            Unified diagnosis result.
        """
        # Determine execution mode
        mode = self._config.determine_mode(
            source=request.source.value,
            alert_type=request.alert_type,
            force_mode=request.mode,
        )

        # Only use checkpoint callback for interactive CLI sessions
        callback = None
        if (
            mode == DiagnosisMode.INTERACTIVE
            and request.source == DiagnosisRequestSource.CLI
            and self._checkpoint_callback is not None
        ):
            callback = self._checkpoint_callback

        log.info(
            "engine_execute",
            diagnosis_id=request.request_id,
            mode=mode.value,
            source=request.source.value,
        )

        controller = DiagnosisController(
            config=self._config,
            checkpoint_callback=callback,
            project_path=self._project_path,
            global_inventory_path=self._global_inventory_path,
            minimal_input_path=self._minimal_input_path,
            llm_model=self._llm_model,
            llm_max_turns=self._llm_max_turns,
            llm_max_budget_usd=self._llm_max_budget_usd,
            llm_permission_mode=self._llm_permission_mode,
            bpf_local_tools_path=self._bpf_local_tools_path,
            bpf_remote_tools_path=self._bpf_remote_tools_path,
            progress_callback=progress_callback,
        )

        return await controller.run(
            request=request,
            source=request.source,
            force_mode=mode,
        )

    async def health_check(self) -> dict[str, Any]:
        """Return engine health status."""
        return {
            "engine": "controller",
            "status": "healthy",
            "config": {
                "inventory": str(self._global_inventory_path) if self._global_inventory_path else None,
                "minimal_input": str(self._minimal_input_path) if self._minimal_input_path else None,
                "model": self._llm_model,
            },
        }
