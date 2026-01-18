"""
FastAPI webhook entry point for receiving alerts from Grafana/Alertmanager.

This module provides the HTTP API for:
- Receiving Alertmanager webhook notifications
- Accepting manual diagnostic requests
- Querying diagnosis status and results
- Mode-aware diagnosis (autonomous/interactive based on config)
- API key authentication for security
"""

import asyncio
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, Literal
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field, field_validator
import ipaddress

from netsherlock.agents import (
    create_orchestrator,
    DiagnosisResult,
    NetworkTroubleshootingOrchestrator,
)
from netsherlock.config.settings import get_settings
from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for diagnosis results (use Redis/DB in production)
diagnosis_store: dict[str, DiagnosisResult] = {}
diagnosis_queue: asyncio.Queue = asyncio.Queue()

# Global orchestrator instance
orchestrator: NetworkTroubleshootingOrchestrator | None = None


# ============================================================
# Authentication
# ============================================================


def _get_api_key() -> str:
    """Get API key from settings."""
    settings = get_settings()
    api_key = settings.webhook_api_key
    if api_key is None:
        return ""
    # SecretStr needs .get_secret_value() to extract the actual value
    return api_key.get_secret_value()


def _verify_alertmanager_signature(
    payload: bytes,
    signature: str | None,
    secret: str,
) -> bool:
    """Verify Alertmanager webhook signature (HMAC-SHA256).

    Args:
        payload: Raw request body
        signature: Signature from X-Alertmanager-Signature header
        secret: Shared secret for HMAC

    Returns:
        True if signature is valid
    """
    if not signature or not secret:
        return False

    expected = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return secrets.compare_digest(signature, f"sha256={expected}")


def _is_insecure_mode_allowed() -> bool:
    """Check if insecure mode is explicitly allowed."""
    settings = get_settings()
    return settings.webhook_allow_insecure


async def verify_api_key(
    x_api_key: Annotated[str | None, Header()] = None,
) -> str:
    """Verify API key from request header.

    Args:
        x_api_key: API key from X-API-Key header

    Returns:
        The verified API key

    Raises:
        HTTPException: If API key is missing or invalid
    """
    expected_key = _get_api_key()

    # If no API key configured, check for explicit insecure flag
    if not expected_key:
        if _is_insecure_mode_allowed():
            logger.warning("No API key configured - running in insecure mode (WEBHOOK_ALLOW_INSECURE=true)")
            return ""
        else:
            raise HTTPException(
                status_code=500,
                detail="API key not configured. Set WEBHOOK_API_KEY or enable WEBHOOK_ALLOW_INSECURE=true for development.",
            )

    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not secrets.compare_digest(x_api_key, expected_key):
        raise HTTPException(
            status_code=403,
            detail="Invalid API key",
        )

    return x_api_key


def generate_diagnosis_id(prefix: str = "diag") -> str:
    """Generate a secure, unpredictable diagnosis ID.

    Args:
        prefix: Optional prefix for the ID

    Returns:
        UUID-based diagnosis ID
    """
    return f"{prefix}-{uuid.uuid4().hex[:16]}"


def determine_webhook_mode(
    alert_type: str | None = None,
    force_mode: DiagnosisMode | None = None,
) -> DiagnosisMode:
    """Determine the diagnosis mode for a webhook request.

    Mode selection logic:
    1. If force_mode is specified, use it
    2. If auto_agent_loop is enabled and alert_type is known, use autonomous
    3. Otherwise use interactive (safer default for webhook)

    Args:
        alert_type: The alert type/name from Alertmanager
        force_mode: Explicitly requested mode (overrides auto-detection)

    Returns:
        DiagnosisMode to use for this request
    """
    if force_mode is not None:
        return force_mode

    settings = get_settings()
    config = settings.get_diagnosis_config()

    # Use determine_mode from DiagnosisConfig
    return config.determine_mode(
        source=DiagnosisRequestSource.WEBHOOK.value,
        alert_type=alert_type,
        force_mode=force_mode,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global orchestrator

    # Startup
    logger.info("Initializing network troubleshooting orchestrator...")
    orchestrator = create_orchestrator()
    logger.info("Orchestrator initialized successfully")

    # Start background worker
    worker_task = asyncio.create_task(diagnosis_worker())

    yield

    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Orchestrator shutdown complete")


app = FastAPI(
    title="NetSherlock",
    description="AI-driven network troubleshooting agent webhook API",
    version="0.1.0",
    lifespan=lifespan,
)


# Request/Response Models

class AlertmanagerAlert(BaseModel):
    """Single alert from Alertmanager."""

    status: str = "firing"
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)
    startsAt: str | None = None
    endsAt: str | None = None
    generatorURL: str | None = None
    fingerprint: str | None = None


class AlertmanagerWebhook(BaseModel):
    """Alertmanager webhook payload."""

    version: str = "4"
    groupKey: str | None = None
    truncatedAlerts: int = 0
    status: str = "firing"
    receiver: str = ""
    groupLabels: dict[str, str] = Field(default_factory=dict)
    commonLabels: dict[str, str] = Field(default_factory=dict)
    commonAnnotations: dict[str, str] = Field(default_factory=dict)
    externalURL: str | None = None
    alerts: list[AlertmanagerAlert] = Field(default_factory=list)


# Valid problem types
VALID_PROBLEM_TYPES = {"vm_network_latency", "vm_network_drop", "system_network_latency", "host_network_latency"}


class DiagnosticRequest(BaseModel):
    """Manual diagnostic request."""

    problem_type: str = Field(..., description="Type of problem: vm_network_latency, vm_network_drop, system_network_latency, host_network_latency")
    src_node: str = Field(..., description="Source node IP address")
    dst_node: str | None = Field(None, description="Destination node IP address")
    vm_name: str | None = Field(None, description="VM name if applicable")
    description: str | None = Field(None, description="Additional problem description")
    mode: Literal["autonomous", "interactive"] | None = Field(
        None,
        description="Diagnosis mode. If not specified, determined by config based on alert type.",
    )
    alert_type: str | None = Field(
        None,
        description="Alert type for mode selection (e.g., VMNetworkLatency)",
    )

    @field_validator("problem_type")
    @classmethod
    def validate_problem_type(cls, v: str) -> str:
        """Validate problem_type is one of allowed values."""
        if v not in VALID_PROBLEM_TYPES:
            raise ValueError(f"Invalid problem_type: {v}. Must be one of: {', '.join(sorted(VALID_PROBLEM_TYPES))}")
        return v

    @field_validator("src_node")
    @classmethod
    def validate_src_node(cls, v: str) -> str:
        """Validate src_node is a valid IP address."""
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError(f"Invalid src_node IP address: {v}")
        return v

    @field_validator("dst_node")
    @classmethod
    def validate_dst_node(cls, v: str | None) -> str | None:
        """Validate dst_node is a valid IP address if provided."""
        if v is not None:
            try:
                ipaddress.ip_address(v)
            except ValueError:
                raise ValueError(f"Invalid dst_node IP address: {v}")
        return v


class DiagnosisResponse(BaseModel):
    """Diagnosis response."""

    diagnosis_id: str
    status: str  # "queued", "processing", "completed", "error"
    timestamp: str
    mode: str | None = None  # "autonomous" or "interactive"
    summary: str | None = None
    root_cause: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] | None = None
    message: str | None = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    timestamp: str
    queue_size: int


# Background worker

async def diagnosis_worker():
    """Background worker that processes diagnosis requests."""
    logger.info("Diagnosis worker started")

    while True:
        request_id = None
        try:
            # Wait for diagnosis request
            request_type, request_id, request_data = await diagnosis_queue.get()

            logger.info(f"Processing diagnosis request: {request_id}")

            if orchestrator is None:
                logger.error("Orchestrator not initialized")
                # Store error result for uninitialized orchestrator
                diagnosis_store[request_id] = DiagnosisResult(
                    diagnosis_id=request_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    alert_source=None,
                    summary="Diagnosis failed: Orchestrator not initialized",
                    root_cause=None,
                    recommendations=[],
                )
            else:
                try:
                    if request_type == "alert":
                        result = await orchestrator.diagnose_alert(request_data)
                    else:
                        result = await orchestrator.diagnose_request(request_data)

                    # Store result
                    diagnosis_store[request_id] = result
                    logger.info(f"Diagnosis completed: {request_id}")

                except Exception as e:
                    logger.exception(f"Diagnosis failed for {request_id}: {e}")
                    # Store error result
                    diagnosis_store[request_id] = DiagnosisResult(
                        diagnosis_id=request_id,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        alert_source=None,
                        summary=f"Diagnosis failed: {str(e)}",
                        root_cause=None,
                        recommendations=[],
                    )

        except asyncio.CancelledError:
            logger.info("Diagnosis worker cancelled")
            break
        except Exception as e:
            logger.exception(f"Worker error: {e}")
            await asyncio.sleep(1)
        finally:
            # Always mark task as done if we got a request
            if request_id is not None:
                diagnosis_queue.task_done()


# API Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint (no auth required)."""
    return HealthResponse(
        status="healthy" if orchestrator else "initializing",
        timestamp=datetime.now(timezone.utc).isoformat(),
        queue_size=diagnosis_queue.qsize(),
    )


@app.post("/webhook/alertmanager", response_model=list[DiagnosisResponse])
async def receive_alertmanager_webhook(
    payload: AlertmanagerWebhook,
    _api_key: Annotated[str, Depends(verify_api_key)],
):
    """Receive webhook from Alertmanager.

    This endpoint receives alert notifications from Alertmanager and
    queues them for diagnosis processing.

    Requires X-API-Key header for authentication.

    Mode selection:
    - If auto_agent_loop is enabled and alert type is known, uses autonomous mode
    - Otherwise uses interactive mode (requires human confirmation at checkpoints)
    """
    if payload.status != "firing":
        # Only process firing alerts
        return []

    responses = []

    for alert in payload.alerts:
        if alert.status != "firing":
            continue

        # Generate secure, unpredictable diagnosis ID
        diagnosis_id = generate_diagnosis_id("alert")

        # Get alert type for mode determination
        alert_type = alert.labels.get("alertname")

        # Determine mode based on config and alert type
        effective_mode = determine_webhook_mode(alert_type=alert_type)

        # Queue for processing with mode
        alert_data = {
            "labels": alert.labels,
            "annotations": alert.annotations,
            "startsAt": alert.startsAt,
            "mode": effective_mode.value,
            "alert_type": alert_type,  # Include for mode selection in controller
        }

        await diagnosis_queue.put(("alert", diagnosis_id, alert_data))

        responses.append(DiagnosisResponse(
            diagnosis_id=diagnosis_id,
            status="queued",
            timestamp=datetime.now(timezone.utc).isoformat(),
            mode=effective_mode.value,
            message=f"Alert queued for diagnosis in {effective_mode.value} mode",
        ))

        logger.info(
            f"Alert queued: {diagnosis_id} - {alert_type or 'unknown'} (mode={effective_mode.value})"
        )

    return responses


@app.post("/diagnose", response_model=DiagnosisResponse)
async def create_diagnosis(
    request: DiagnosticRequest,
    _api_key: Annotated[str, Depends(verify_api_key)],
):
    """Create a manual diagnostic request.

    This endpoint allows manual triggering of network diagnostics
    without an alert.

    Requires X-API-Key header for authentication.

    Mode selection:
    - If mode is specified in request, use it
    - Otherwise, determine based on problem_type and config
    """
    diagnosis_id = generate_diagnosis_id("manual")

    # Determine mode
    force_mode = DiagnosisMode(request.mode) if request.mode else None
    effective_mode = determine_webhook_mode(
        alert_type=request.problem_type,
        force_mode=force_mode,
    )

    # Queue for processing with mode
    request_data = request.model_dump()
    request_data["mode"] = effective_mode.value
    request_data["alert_type"] = request.problem_type  # Include for mode selection
    await diagnosis_queue.put(("manual", diagnosis_id, request_data))

    logger.info(
        f"Manual diagnosis queued: {diagnosis_id} - {request.problem_type} (mode={effective_mode.value})"
    )

    return DiagnosisResponse(
        diagnosis_id=diagnosis_id,
        status="queued",
        timestamp=datetime.now(timezone.utc).isoformat(),
        mode=effective_mode.value,
        message=f"Diagnosis request queued in {effective_mode.value} mode",
    )


@app.get("/diagnose/{diagnosis_id}", response_model=DiagnosisResponse)
async def get_diagnosis(
    diagnosis_id: str,
    _api_key: Annotated[str, Depends(verify_api_key)],
):
    """Get the status/result of a diagnosis.

    Requires X-API-Key header for authentication.

    Returns the current status and results (if completed) for a
    specific diagnosis ID.
    """
    if diagnosis_id not in diagnosis_store:
        # Check if in queue
        raise HTTPException(
            status_code=404,
            detail=f"Diagnosis {diagnosis_id} not found",
        )

    result = diagnosis_store[diagnosis_id]

    return DiagnosisResponse(
        diagnosis_id=result.diagnosis_id,
        status="completed" if result.root_cause and result.root_cause.confidence > 0 else "error",
        timestamp=result.timestamp,
        summary=result.summary,
        root_cause={
            "category": result.root_cause.category.value if result.root_cause else None,
            "component": result.root_cause.component if result.root_cause else None,
            "confidence": result.root_cause.confidence if result.root_cause else 0,
            "evidence": result.root_cause.evidence if result.root_cause else [],
        } if result.root_cause else None,
        recommendations=[
            {"priority": r.priority, "action": r.action, "command": r.command}
            for r in result.recommendations
        ] if result.recommendations else None,
    )


@app.get("/diagnoses", response_model=list[DiagnosisResponse])
async def list_diagnoses(
    _api_key: Annotated[str, Depends(verify_api_key)],
    limit: int = Query(default=50, ge=1, le=1000, description="Maximum number of results to return"),
    offset: int = Query(default=0, ge=0, description="Number of results to skip"),
):
    """List recent diagnoses.

    Requires X-API-Key header for authentication.

    Returns a list of recent diagnosis results, ordered by timestamp.
    """
    # Ensure bounds are respected (Query validation handles this, but be defensive)
    limit = max(1, min(limit, 1000))
    offset = max(0, offset)

    # Sort by timestamp descending
    sorted_diagnoses = sorted(
        diagnosis_store.values(),
        key=lambda d: d.timestamp,
        reverse=True,
    )

    # Apply pagination
    paginated = sorted_diagnoses[offset : offset + limit]

    return [
        DiagnosisResponse(
            diagnosis_id=d.diagnosis_id,
            status="completed" if d.root_cause and d.root_cause.confidence > 0 else "error",
            timestamp=d.timestamp,
            summary=d.summary,
        )
        for d in paginated
    ]


# CLI entry point for development
def main():
    """Run the webhook server."""
    import uvicorn

    uvicorn.run(
        "netsherlock.api.webhook:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
    )


if __name__ == "__main__":
    main()
