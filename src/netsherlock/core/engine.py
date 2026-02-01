"""DiagnosisEngine protocol — unified interface for both engines.

The webhook layer and CLI depend only on this protocol,
making the choice of engine (controller vs orchestrator) transparent.
"""

from __future__ import annotations

from typing import Any, Protocol

from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult


class DiagnosisEngine(Protocol):
    """Unified diagnosis engine interface.

    Both ControllerEngine (deterministic) and OrchestratorEngine (AI-autonomous)
    implement this protocol. The webhook and CLI layers depend only on this
    interface, not on concrete engine implementations.
    """

    @property
    def engine_type(self) -> str:
        """Engine type identifier: 'controller' or 'orchestrator'."""
        ...

    async def execute(
        self,
        request: DiagnosisRequest,
    ) -> DiagnosisResult:
        """Execute a diagnosis workflow.

        The request contains source, mode, and all parameters needed
        for the engine to determine its execution strategy.

        Args:
            request: Unified diagnosis request.

        Returns:
            Unified diagnosis result.
        """
        ...

    async def health_check(self) -> dict[str, Any]:
        """Engine health check for /health endpoint.

        Returns:
            Dict with engine status and configuration summary.
        """
        ...
