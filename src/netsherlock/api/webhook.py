"""
FastAPI webhook entry point for receiving alerts from Grafana/Alertmanager.

This module provides the HTTP API for:
- Receiving Alertmanager webhook notifications
- Accepting manual diagnostic requests
- Querying diagnosis status and results
- Mode-aware diagnosis (autonomous/interactive based on config)
- API key authentication for security

The webhook layer is engine-agnostic: it depends only on the
DiagnosisEngine protocol, not on specific engine implementations.
"""

import asyncio
import hashlib
import hmac
import ipaddress
import logging
import secrets
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from netsherlock.config.settings import get_settings
from netsherlock.schemas.config import DiagnosisMode, DiagnosisRequestSource
from netsherlock.schemas.request import DiagnosisRequest
from netsherlock.schemas.result import DiagnosisResult, DiagnosisStatus

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# In-memory storage for diagnosis results (use Redis/DB in production)
diagnosis_store: dict[str, DiagnosisResult] = {}
diagnosis_queue: asyncio.Queue = asyncio.Queue()

# Global engine instance (DiagnosisEngine protocol)
engine: Any = None  # DiagnosisEngine protocol — Any to avoid circular import


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


# ============================================================
# Engine creation
# ============================================================


def _create_engine(settings: Any) -> Any:
    """Create diagnosis engine based on settings.

    Args:
        settings: Application settings.

    Returns:
        DiagnosisEngine implementation (ControllerEngine or OrchestratorEngine).
    """
    engine_type = settings.diagnosis_engine

    if engine_type == "controller":
        from netsherlock.core.controller_engine import ControllerEngine

        return ControllerEngine(
            config=settings.get_diagnosis_config(),
            global_inventory_path=settings.global_inventory_path,
            project_path=settings.project_path,
            llm_model=settings.llm.model,
            llm_max_turns=settings.llm.max_turns,
            llm_max_budget_usd=settings.llm.max_budget_usd,
            bpf_local_tools_path=settings.bpf_tools.local_tools_path,
            bpf_remote_tools_path=settings.bpf_tools.remote_tools_path,
        )
    elif engine_type == "orchestrator":
        from netsherlock.core.orchestrator_engine import OrchestratorEngine

        return OrchestratorEngine(settings=settings)
    else:
        raise ValueError(f"Unknown engine type: {engine_type}")


# ============================================================
# Request building
# ============================================================


def _build_diagnosis_request(
    request_type: str,
    request_id: str,
    raw_data: dict[str, Any],
) -> DiagnosisRequest:
    """Convert webhook raw data to unified DiagnosisRequest.

    Args:
        request_type: "alert" or "manual".
        request_id: Unique diagnosis ID.
        raw_data: Raw data from queue.

    Returns:
        Unified DiagnosisRequest.
    """
    if request_type == "alert":
        labels = raw_data.get("labels", {})
        src_host_raw = labels.get("src_host") or labels.get("instance", "")
        src_host = src_host_raw.split(":")[0] if src_host_raw else ""

        return DiagnosisRequest(
            request_id=request_id,
            request_type=_map_alert_to_type(labels.get("alertname", "")),
            network_type=labels.get("network_type", "vm"),
            src_host=src_host,
            src_vm=labels.get("src_vm"),
            dst_host=labels.get("dst_host"),
            dst_vm=labels.get("dst_vm"),
            source=DiagnosisRequestSource.WEBHOOK,
            alert_type=labels.get("alertname"),
            mode=DiagnosisMode(raw_data["mode"]) if "mode" in raw_data else None,
        )
    else:
        # Manual request
        mode_str = raw_data.get("mode")
        return DiagnosisRequest(
            request_id=request_id,
            request_type=raw_data.get("diagnosis_type", "latency"),
            network_type=raw_data.get("network_type", "vm"),
            src_host=raw_data["src_host"],
            src_vm=raw_data.get("src_vm"),
            dst_host=raw_data.get("dst_host"),
            dst_vm=raw_data.get("dst_vm"),
            source=DiagnosisRequestSource.API,
            description=raw_data.get("description"),
            alert_type=raw_data.get("alert_type"),
            mode=DiagnosisMode(mode_str) if mode_str else None,
        )


def _map_alert_to_type(alertname: str) -> str:
    """Map alertname to request_type."""
    mapping = {
        "VMNetworkLatency": "latency",
        "HostNetworkLatency": "latency",
        "VMPacketDrop": "packet_drop",
        "HostPacketDrop": "packet_drop",
        "VMConnectivity": "connectivity",
    }
    return mapping.get(alertname, "latency")


# ============================================================
# Application lifecycle
# ============================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global engine

    # Startup
    settings = get_settings()
    logger.info(f"Initializing diagnosis engine: {settings.diagnosis_engine}")
    engine = _create_engine(settings)
    logger.info(f"Engine initialized: {getattr(engine, 'engine_type', 'unknown')}")

    # Start background worker
    worker_task = asyncio.create_task(diagnosis_worker())

    yield

    # Shutdown
    worker_task.cancel()
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    logger.info("Engine shutdown complete")


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


# Valid diagnosis types
VALID_DIAGNOSIS_TYPES = {"latency", "packet_drop", "connectivity"}

# Valid network types
VALID_NETWORK_TYPES = {"vm", "system"}


class DiagnosticRequest(BaseModel):
    """Manual diagnostic request.

    Parameters:
        network_type: Network type (vm or system)
        diagnosis_type: Type of diagnosis (latency, packet_drop, connectivity)
        src_host: Source host management IP (required)
        src_vm: Source VM UUID (required for network_type=vm)
        dst_host: Destination host management IP (optional)
        dst_vm: Destination VM UUID (required when dst_host specified for vm network)
        mode: Diagnosis mode (autonomous or interactive)
        description: Additional problem description
    """

    network_type: Literal["vm", "system"] = Field(
        ..., description="Network type: vm (VM network) or system (host network)"
    )
    diagnosis_type: Literal["latency", "packet_drop", "connectivity"] = Field(
        default="latency", description="Type of diagnosis: latency, packet_drop, connectivity"
    )
    src_host: str = Field(..., description="Source host management IP address")
    src_vm: str | None = Field(None, description="Source VM UUID (required for network_type=vm)")
    dst_host: str | None = Field(None, description="Destination host management IP address")
    dst_vm: str | None = Field(
        None, description="Destination VM UUID (required when dst_host specified for vm network)"
    )
    description: str | None = Field(None, description="Additional problem description")
    mode: Literal["autonomous", "interactive"] | None = Field(
        None,
        description="Diagnosis mode. If not specified, determined by config based on alert type.",
    )
    alert_type: str | None = Field(
        None,
        description="Alert type for mode selection (e.g., VMNetworkLatency)",
    )

    @field_validator("src_host")
    @classmethod
    def validate_src_host(cls, v: str) -> str:
        """Validate src_host is a valid IP address."""
        try:
            ipaddress.ip_address(v)
        except ValueError:
            raise ValueError(f"Invalid src_host IP address: {v}")
        return v

    @field_validator("dst_host")
    @classmethod
    def validate_dst_host(cls, v: str | None) -> str | None:
        """Validate dst_host is a valid IP address if provided."""
        if v is not None:
            try:
                ipaddress.ip_address(v)
            except ValueError:
                raise ValueError(f"Invalid dst_host IP address: {v}")
        return v

    def model_post_init(self, __context) -> None:
        """Validate parameter combinations after model initialization."""
        # VM network validation
        if self.network_type == "vm":
            if not self.src_vm:
                raise ValueError("src_vm is required for network_type=vm")
            if self.dst_host and not self.dst_vm:
                raise ValueError("dst_vm is required when dst_host is specified")
            if self.dst_vm and not self.dst_host:
                raise ValueError("dst_host is required when dst_vm is specified")


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
    engine: str | None = None


# Background worker

async def diagnosis_worker():
    """Background worker that processes diagnosis requests via engine."""
    logger.info("Diagnosis worker started")

    while True:
        request_id = None
        try:
            # Wait for diagnosis request
            request_type, request_id, request_data = await diagnosis_queue.get()

            logger.info(f"Processing diagnosis request: {request_id}")

            if engine is None:
                logger.error("Engine not initialized")
                diagnosis_store[request_id] = DiagnosisResult.create_error(
                    diagnosis_id=request_id,
                    error="Diagnosis engine not initialized",
                )
            else:
                try:
                    # Build unified request from raw data
                    request = _build_diagnosis_request(
                        request_type, request_id, request_data
                    )

                    # Execute via engine protocol
                    result = await engine.execute(request=request)

                    # Store result
                    diagnosis_store[request_id] = result
                    logger.info(f"Diagnosis completed: {request_id}")

                except Exception as e:
                    logger.exception(f"Diagnosis failed for {request_id}: {e}")
                    diagnosis_store[request_id] = DiagnosisResult.create_error(
                        diagnosis_id=request_id,
                        error=str(e),
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
    engine_health = {}
    engine_type = None
    if engine is not None and hasattr(engine, "health_check"):
        try:
            engine_health = await engine.health_check()
            engine_type = engine_health.get("engine")
        except Exception:
            engine_type = getattr(engine, "engine_type", "unknown")

    return HealthResponse(
        status="healthy" if engine else "initializing",
        timestamp=datetime.now(timezone.utc).isoformat(),
        queue_size=diagnosis_queue.qsize(),
        engine=engine_type or getattr(engine, "engine_type", None),
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

    Request body parameters:
    - network_type: vm or system (required)
    - diagnosis_type: latency, packet_drop, or connectivity (default: latency)
    - src_host: Source host management IP (required)
    - src_vm: Source VM UUID (required for network_type=vm)
    - dst_host: Destination host management IP (optional)
    - dst_vm: Destination VM UUID (required when dst_host specified for vm network)
    - mode: autonomous or interactive (optional, determined by config if not specified)

    Mode selection:
    - If mode is specified in request, use it
    - Otherwise, determine based on network_type and config
    """
    diagnosis_id = generate_diagnosis_id("manual")

    # Determine mode
    force_mode = DiagnosisMode(request.mode) if request.mode else None
    # Use alert_type field for mode selection if specified, otherwise derive from network_type
    alert_type_for_mode = request.alert_type or (
        "VMNetworkLatency" if request.network_type == "vm" else "HostNetworkLatency"
    )
    effective_mode = determine_webhook_mode(
        alert_type=alert_type_for_mode,
        force_mode=force_mode,
    )

    # Queue for processing with mode
    request_data = request.model_dump()
    request_data["mode"] = effective_mode.value
    request_data["alert_type"] = alert_type_for_mode  # Include for mode selection
    await diagnosis_queue.put(("manual", diagnosis_id, request_data))

    logger.info(
        f"Manual diagnosis queued: {diagnosis_id} - {request.network_type}/{request.diagnosis_type} (mode={effective_mode.value})"
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

    timestamp = (
        result.completed_at.isoformat() if result.completed_at
        else result.started_at.isoformat() if result.started_at
        else ""
    )
    return DiagnosisResponse(
        diagnosis_id=result.diagnosis_id,
        status=result.status.value,
        timestamp=timestamp,
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
        key=lambda d: d.completed_at or d.started_at or datetime.min,
        reverse=True,
    )

    # Apply pagination
    paginated = sorted_diagnoses[offset : offset + limit]

    return [
        DiagnosisResponse(
            diagnosis_id=d.diagnosis_id,
            status=d.status.value,
            timestamp=(
                d.completed_at.isoformat() if d.completed_at
                else d.started_at.isoformat() if d.started_at
                else ""
            ),
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
