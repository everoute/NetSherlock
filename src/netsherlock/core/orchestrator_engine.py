"""OrchestratorEngine — AI-autonomous diagnosis engine wrapping NetworkTroubleshootingOrchestrator.

Implements the DiagnosisEngine protocol using the existing Orchestrator
for a ReAct-style, agent-driven diagnostic workflow.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import structlog

from netsherlock.schemas.config import DiagnosisRequestSource
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult

if TYPE_CHECKING:
    from netsherlock.config.settings import Settings

log = structlog.get_logger(component="OrchestratorEngine")


class OrchestratorEngine:
    """AI-autonomous diagnosis engine backed by NetworkTroubleshootingOrchestrator.

    The orchestrator uses a ReAct-style loop with Claude Agent SDK to
    autonomously decide which tools to invoke (L1 queries, L2/L3/L4 subagent
    invocations) based on the alert or request context.
    """

    def __init__(self, settings: Settings | None = None):
        """Initialize OrchestratorEngine.

        Args:
            settings: Application settings. If None, loads default settings.
        """
        if settings is None:
            from netsherlock.config.settings import get_settings
            settings = get_settings()

        self._settings = settings

        # Lazy-import to avoid SDK dependency at module level
        from netsherlock.agents.orchestrator import NetworkTroubleshootingOrchestrator

        self._orchestrator = NetworkTroubleshootingOrchestrator(settings=settings)

    @property
    def engine_type(self) -> str:
        return "orchestrator"

    async def execute(self, request: DiagnosisRequest) -> DiagnosisResult:
        """Execute diagnosis via Orchestrator ReAct loop.

        Routes to diagnose_alert() or diagnose_request() based on
        the request's source and alert_type fields.

        Args:
            request: Unified diagnosis request.

        Returns:
            Unified diagnosis result.
        """
        log.info(
            "engine_execute",
            diagnosis_id=request.request_id,
            source=request.source.value,
            alert_type=request.alert_type,
        )

        started_at = datetime.now()

        try:
            if request.alert_type or request.source == DiagnosisRequestSource.WEBHOOK:
                # Alert-triggered diagnosis
                alert_data = self._request_to_alert_data(request)
                result = await self._orchestrator.diagnose_alert(alert_data)
            else:
                # Manual request
                request_data = self._request_to_dict(request)
                result = await self._orchestrator.diagnose_request(request_data)

            # The orchestrator already returns a DiagnosisResult (from _synthesize_diagnosis).
            # Enrich with request context if not already set.
            result.source = request.source
            if request.mode:
                result.mode = request.mode
            if not result.started_at:
                result.started_at = started_at
            if not result.completed_at:
                result.completed_at = datetime.now()

            return result

        except Exception as e:
            log.error("engine_execute_failed", error=str(e))
            return DiagnosisResult.create_error(
                diagnosis_id=request.request_id,
                error=str(e),
                source=request.source,
                started_at=started_at,
            )

    def _request_to_alert_data(self, request: DiagnosisRequest) -> dict[str, Any]:
        """Convert DiagnosisRequest to the dict format expected by diagnose_alert()."""
        return {
            "labels": {
                "alertname": request.alert_type or "VMNetworkLatency",
                "instance": f"{request.src_host}:9100",
                "src_host": request.src_host,
                "src_vm": request.src_vm or "",
                "dst_host": request.dst_host or "",
                "dst_vm": request.dst_vm or "",
                "network_type": request.network_type,
            },
            "annotations": {},
        }

    def _request_to_dict(self, request: DiagnosisRequest) -> dict[str, Any]:
        """Convert DiagnosisRequest to the dict format expected by diagnose_request()."""
        return {
            "problem_type": f"{request.network_type}_network_{request.request_type}",
            "src_node": request.src_host,
            "dst_node": request.dst_host or "",
            "vm_name": request.src_vm or "",
            "description": request.description or "",
        }

    async def health_check(self) -> dict[str, Any]:
        """Return engine health status."""
        return {
            "engine": "orchestrator",
            "status": "healthy",
            "config": {
                "model": self._orchestrator.model,
                "compact_prompts": self._orchestrator.compact_prompts,
            },
        }
