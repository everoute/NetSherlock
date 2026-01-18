# NetSherlock Implementation Guide

NetSherlock is an AI-driven network troubleshooting agent built with Claude Agent SDK, integrating with internal Grafana monitoring data sources.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Four-Layer Diagnostic Architecture](#four-layer-diagnostic-architecture)
3. [Dual-Mode Control System](#dual-mode-control-system)
4. [API & Webhook Integration](#api--webhook-integration)
5. [Configuration System](#configuration-system)
6. [Core Components](#core-components)
7. [Testing](#testing)

---

## Architecture Overview

### System Components

```
┌──────────────────────────────────────────────────────────────────┐
│                         Entry Points                              │
├──────────────────────┬──────────────────┬────────────────────────┤
│     CLI (main.py)    │  Webhook API     │   Programmatic API     │
│                      │  (webhook.py)    │   (agents/__init__.py) │
└──────────┬───────────┴────────┬─────────┴────────────┬───────────┘
           │                    │                      │
           ▼                    ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                    Diagnosis Controller                           │
│                 (controller/diagnosis_controller.py)             │
│  - Mode selection (Autonomous/Interactive)                       │
│  - Checkpoint management                                         │
│  - Phase orchestration                                           │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Agent Orchestrator                          │
│                    (agents/orchestrator.py)                       │
│  - Claude Agent SDK integration                                  │
│  - L2/L3/L4 Subagent coordination                               │
│  - Tool invocation                                               │
└──────────────────────────────┬───────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
┌────────────────┐  ┌────────────────┐  ┌────────────────┐
│ L2 Subagent    │  │ L3 Subagent    │  │ L4 Subagent    │
│ Environment    │  │ Measurement    │  │ Analysis       │
└────────┬───────┘  └────────┬───────┘  └────────┬───────┘
         │                   │                   │
         ▼                   ▼                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Tool Executor                               │
│                   (agents/tool_executor.py)                       │
│  - Routes agent tool calls to L1-L4 implementations              │
└──────────────────────────────┬───────────────────────────────────┘
                               │
┌──────────────────────────────┼───────────────────────────────────┐
│                         MCP Tools                                 │
├─────────────┬─────────────┬─────────────┬────────────────────────┤
│ L1 Tools    │ L2 Tools    │ L3 Tools    │ L4 Tools               │
│ Monitoring  │ Environment │ Measurement │ Analysis               │
└─────────────┴─────────────┴─────────────┴────────────────────────┘
```

### Directory Structure

```
src/netsherlock/
├── __init__.py              # Package exports, lazy loading
├── main.py                  # CLI entry point (Click)
├── api/
│   ├── __init__.py
│   └── webhook.py           # FastAPI webhook server
├── agents/
│   ├── __init__.py          # Agent exports
│   ├── base.py              # Data types (ProblemType, RootCause, etc.)
│   ├── orchestrator.py      # Main orchestrator agent
│   ├── subagents.py         # L2/L3/L4 subagent implementations
│   ├── tool_executor.py     # Tool routing dispatcher
│   └── prompts/             # Agent system prompts
│       ├── main_orchestrator.py
│       ├── l2_environment_awareness.py
│       ├── l3_precise_measurement.py
│       └── l4_diagnostic_analysis.py
├── config/
│   ├── __init__.py
│   └── settings.py          # Pydantic settings configuration
├── controller/
│   ├── __init__.py
│   ├── diagnosis_controller.py  # Dual-mode control logic
│   └── checkpoints.py       # Interactive mode checkpoints
├── core/
│   ├── __init__.py
│   ├── ssh_manager.py       # SSH connection pool
│   ├── grafana_client.py    # Grafana API client
│   └── bpf_executor.py      # BPF tool remote execution
├── schemas/
│   ├── __init__.py
│   ├── alert.py             # Alert/DiagnosisRequest models
│   ├── config.py            # DiagnosisConfig, modes, checkpoints
│   ├── environment.py       # Network environment models
│   ├── measurement.py       # Measurement result models
│   └── report.py            # Diagnosis report models
└── tools/
    ├── __init__.py
    ├── l1_monitoring.py     # Grafana, Loki, node log queries
    ├── l2_environment.py    # Network topology collection
    ├── l3_measurement.py    # BPF measurement execution
    └── l4_analysis.py       # Root cause analysis
```

---

## Four-Layer Diagnostic Architecture

NetSherlock implements a four-layer diagnostic approach where each layer has specific responsibilities and tools.

### Layer Overview

| Layer | Purpose | Tools | Data Flow |
|-------|---------|-------|-----------|
| **L1** | Base Monitoring | `grafana_query_metrics`, `loki_query_logs`, `read_node_logs` | Alert → Context |
| **L2** | Environment Awareness | `collect_vm_network_env`, `collect_system_network_env`, `build_network_path` | Context → Topology |
| **L3** | Precise Measurement | `execute_coordinated_measurement`, `measure_vm_latency_breakdown`, `measure_packet_drop` | Topology → Metrics |
| **L4** | Diagnostic Analysis | `analyze_latency_segments`, `identify_root_cause`, `generate_diagnosis_report` | Metrics → Report |

### L1: Base Monitoring (`tools/l1_monitoring.py`)

Queries existing monitoring infrastructure for baseline data.

**Tools:**
- `grafana_query_metrics(query, start, end, step)` - PromQL queries to VictoriaMetrics
- `loki_query_logs(query, start, end, limit)` - LogQL queries to Loki
- `read_node_logs(host, log_type, lines)` - Read local logs via SSH (pingmesh, l2ping)

**Example:**
```python
from netsherlock.tools.l1_monitoring import grafana_query_metrics

result = grafana_query_metrics(
    query='host_network_ping_time_ns{hostname="node1"}',
    start="-1h",
    end="now",
    step="30s"
)
```

### L2: Environment Awareness (`tools/l2_environment.py`)

Collects network topology and environment information needed for precise measurements.

**Tools:**
- `collect_vm_network_env(vm_id, host)` - VM network topology (vnet, TAP, OVS bridge)
- `collect_system_network_env(host, port_type)` - System network topology (OVS ports, bonds)
- `build_network_path(src_env, dst_env)` - Resolve complete data path

**VMNetworkEnv Structure:**
```python
@dataclass
class VMNetworkEnv:
    vm_uuid: str
    host: str
    qemu_pid: int
    nics: list[VMNicInfo]  # Each has mac, host_vnet, ovs_bridge, vhost_pids
```

### L3: Precise Measurement (`tools/l3_measurement.py`)

Executes BPF-based measurements with **receiver-first timing guarantee**.

**Critical Design Constraint:**
> For coordinated measurements, the receiver-side tool MUST start before the sender.
> This constraint is enforced in the tool implementation, not by AI decision.

**Tools:**
- `execute_coordinated_measurement(receiver_host, sender_host, ...)` - Coordinated dual-host measurement
- `measure_vm_latency_breakdown(vm_id, host, duration)` - VM network stack latency segments
- `measure_packet_drop(host, interface, duration)` - Kernel packet drop monitoring

**Coordinated Measurement Flow:**
```
1. Deploy receiver tool → receiver_host
2. Start receiver, wait for "ready" signal (min 1 second)
3. Deploy sender tool → sender_host
4. Start sender
5. Wait for duration
6. Collect results from both
```

**Latency Breakdown Segments:**
- virtio TX/RX
- vhost-net processing
- TAP device
- OVS flow processing

### L4: Diagnostic Analysis (`tools/l4_analysis.py`)

Analyzes measurement data and generates diagnosis reports.

**Tools:**
- `analyze_latency_segments(segments, thresholds)` - Detect latency anomalies
- `identify_root_cause(anomalies, environment)` - Map to root cause categories
- `generate_diagnosis_report(root_cause, measurements)` - Generate structured report

**Root Cause Categories:**
```python
class RootCauseCategory(str, Enum):
    HOST_INTERNAL = "host_internal"       # vhost, OVS, kernel
    NETWORK_FABRIC = "network_fabric"     # Switch, cable, ToR
    VM_INTERNAL = "vm_internal"           # Guest OS, virtio driver
    CONFIGURATION = "configuration"        # MTU, flow rules
    RESOURCE_CONTENTION = "resource_contention"  # CPU, memory
    UNKNOWN = "unknown"
```

---

## Dual-Mode Control System

NetSherlock supports two diagnosis execution modes to balance automation with human oversight.

### Mode Configuration (`schemas/config.py`)

```python
class DiagnosisMode(str, Enum):
    AUTONOMOUS = "autonomous"    # Full automated loop
    INTERACTIVE = "interactive"  # Human-in-the-loop

class DiagnosisConfig(BaseModel):
    default_mode: DiagnosisMode = DiagnosisMode.INTERACTIVE
    autonomous: AutonomousConfig
    interactive: InteractiveConfig
```

### Autonomous Mode

Runs the full diagnostic workflow without human intervention.

**Configuration:**
```python
class AutonomousConfig(BaseModel):
    enabled: bool = True
    auto_agent_loop: bool = False  # Auto-start on alert
    interrupt_enabled: bool = True  # Allow interrupt
    known_alert_types: list[str] = ["VMNetworkLatency", "HostNetworkLatency"]
```

**When Used:**
- Webhook with `auto_agent_loop=True` AND known alert type
- CLI with `--autonomous` flag
- API with explicit `mode=autonomous`

**Interrupt Support:**
```python
controller.interrupt()  # Request stop at next phase boundary
```

### Interactive Mode

Pauses at defined checkpoints for human confirmation.

**Configuration:**
```python
class InteractiveConfig(BaseModel):
    checkpoints: list[CheckpointType] = [
        CheckpointType.PROBLEM_CLASSIFICATION,
        CheckpointType.MEASUREMENT_PLAN,
    ]
    timeout_seconds: int = 300  # 5 minutes
    auto_confirm_on_timeout: bool = False
```

**Checkpoint Types:**
- `PROBLEM_CLASSIFICATION` - After L2, before measurement planning
- `MEASUREMENT_PLAN` - After planning, before L3 execution
- `FURTHER_DIAGNOSIS` - After L4, if additional investigation needed

**Checkpoint Interaction:**
```python
# System pauses and presents:
CheckpointData(
    checkpoint_type=CheckpointType.MEASUREMENT_PLAN,
    summary="Measurement plan: 3 tools",
    details={"tools": [...], "duration": 30},
    options=["Execute", "Modify", "Cancel"],
    recommendation="Execute"
)

# User can:
controller.confirm_checkpoint()        # Continue
controller.confirm_checkpoint("...")   # Continue with input
controller.cancel_checkpoint()         # Abort
```

### Mode Selection Logic (`controller/diagnosis_controller.py`)

```python
def determine_mode(source, alert_type, force_mode) -> DiagnosisMode:
    # 1. Explicit override always wins
    if force_mode:
        return force_mode

    # 2. CLI defaults to interactive (safe)
    if source == "cli":
        return DiagnosisMode.INTERACTIVE

    # 3. Webhook can trigger autonomous for known alerts
    if source == "webhook" and is_autonomous_allowed(alert_type):
        return DiagnosisMode.AUTONOMOUS

    # 4. Fall back to configured default
    return config.default_mode
```

### CLI Mode Selection (`main.py`)

The CLI provides flexible mode selection through flags:

```python
def _determine_diagnosis_mode(
    mode: str | None,
    mode_autonomous: bool,
    mode_interactive: bool,
) -> DiagnosisMode:
    """
    Priority:
    1. --mode option (explicit mode selection)
    2. --autonomous flag
    3. --interactive flag
    4. Default: interactive (safest for CLI)
    """
    if mode_autonomous and mode_interactive:
        raise click.UsageError(
            "Cannot use both --autonomous and --interactive flags"
        )

    if mode is not None:
        return DiagnosisMode(mode)

    if mode_autonomous:
        return DiagnosisMode.AUTONOMOUS
    if mode_interactive:
        return DiagnosisMode.INTERACTIVE

    return DiagnosisMode.INTERACTIVE  # Default for CLI
```

### CLI Checkpoint Interaction (`main.py`)

Interactive mode uses terminal prompts for checkpoint confirmation:

```python
async def _cli_checkpoint_callback(data: CheckpointData) -> CheckpointResult:
    """CLI callback for checkpoint interactions."""
    # Display checkpoint info
    click.echo("=" * 60)
    click.echo(f"CHECKPOINT: {data.checkpoint_type.value}")
    click.echo("=" * 60)
    click.echo(f"Summary: {data.summary}")

    # Display details and options
    if data.details:
        for key, value in data.details.items():
            click.echo(f"  {key}: {value}")

    if data.recommendation:
        click.echo(f"Recommendation: {data.recommendation}")

    # Get user input
    while True:
        choice = click.prompt(
            "Enter choice (1=Confirm, 2=Modify, 3=Cancel)",
            type=int, default=1
        )
        if choice == 1:
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CONFIRMED,
            )
        elif choice == 2:
            user_input = click.prompt("Enter modifications")
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.MODIFIED,
                user_input=user_input,
            )
        elif choice == 3:
            return CheckpointResult(
                checkpoint_type=data.checkpoint_type,
                status=CheckpointStatus.CANCELLED,
            )
```

### CLI Result Formatting (`main.py`)

Results are formatted based on output mode (JSON or text):

```python
def _format_diagnosis_result(result: DiagnosisResult, json_output: bool) -> None:
    if json_output:
        output = {
            "diagnosis_id": result.diagnosis_id,
            "status": result.status.value,
            "mode": result.mode.value,
            "summary": result.summary,
            "root_cause": result.root_cause,
            "recommendations": result.recommendations,
            "started_at": result.started_at.isoformat() if result.started_at else None,
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "error": result.error,
        }
        click.echo(json.dumps(output, indent=2, default=str))
    else:
        click.echo("=" * 60)
        click.echo("DIAGNOSIS RESULT")
        # ... formatted text output with fields
```

### Exit Codes

The CLI uses standard exit codes to indicate diagnosis result:

| Code | Status | Description |
|------|--------|-------------|
| 0 | COMPLETED | Diagnosis completed successfully |
| 1 | ERROR | Diagnosis failed with error |
| 2 | CANCELLED | User cancelled at checkpoint |
| 3 | INTERRUPTED | Diagnosis interrupted mid-execution |
| 130 | KeyboardInterrupt | User pressed Ctrl+C |

---

## API & Webhook Integration

### FastAPI Webhook Server (`api/webhook.py`)

**Endpoints:**

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| POST | `/webhook/alertmanager` | API Key | Receive Alertmanager alerts |
| POST | `/diagnose` | API Key | Manual diagnosis request |
| GET | `/diagnose/{id}` | API Key | Get diagnosis status/result |
| GET | `/diagnoses` | API Key | List recent diagnoses |

### Authentication

**API Key Authentication:**
```python
async def verify_api_key(x_api_key: str | None = Header()) -> str:
    expected = get_api_key()  # From WEBHOOK_API_KEY env

    if not expected:
        if is_insecure_mode_allowed():  # WEBHOOK_ALLOW_INSECURE=true
            return ""  # Allow unauthenticated
        raise HTTPException(500, "API key not configured")

    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(401/403, "...")
```

**Security Settings:**
```bash
WEBHOOK_API_KEY=your-secret-key        # Required for production
WEBHOOK_ALLOW_INSECURE=true            # Development only
```

### Input Validation

**DiagnosticRequest Validation:**
```python
VALID_PROBLEM_TYPES = {
    "vm_network_latency",
    "vm_network_drop",
    "system_network_latency",
    "host_network_latency"
}

class DiagnosticRequest(BaseModel):
    problem_type: str  # Validated against VALID_PROBLEM_TYPES
    src_node: str      # Validated as IP address
    dst_node: str | None  # Validated as IP if provided

    @field_validator("problem_type")
    def validate_problem_type(cls, v):
        if v not in VALID_PROBLEM_TYPES:
            raise ValueError(f"Invalid: {v}")
        return v

    @field_validator("src_node")
    def validate_src_node(cls, v):
        ipaddress.ip_address(v)  # Raises if invalid
        return v
```

**Pagination Bounds:**
```python
@app.get("/diagnoses")
async def list_diagnoses(
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
```

### Running the Server

```bash
# Development
python -m netsherlock.api.webhook

# Production
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080
```

---

## Configuration System

### Settings Structure (`config/settings.py`)

Uses pydantic-settings for type-safe environment configuration.

```python
class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
    )

    # Nested settings
    ssh: SSHSettings
    grafana: GrafanaSettings
    bpf_tools: BPFToolsSettings
    diagnosis: DiagnosisSettings

    # Webhook security
    webhook_api_key: SecretStr | None = None
    webhook_allow_insecure: bool = False
```

### Environment Variables

**SSH Configuration:**
```bash
SSH_DEFAULT_USER=root
SSH_DEFAULT_PORT=22
SSH_PRIVATE_KEY_PATH=/path/to/key
SSH_CONNECT_TIMEOUT=10
SSH_COMMAND_TIMEOUT=60
SSH_MAX_CONNECTIONS=10
```

**Grafana Configuration:**
```bash
GRAFANA_BASE_URL=http://192.168.79.79/grafana
GRAFANA_USERNAME=o11y
GRAFANA_PASSWORD=secret           # Required, no default
GRAFANA_TIMEOUT=30
GRAFANA_VICTORIAMETRICS_DS_ID=1
GRAFANA_LOKI_DS_ID=3
```

**BPF Tools Configuration:**
```bash
BPF_LOCAL_TOOLS_PATH=/path/to/tools
BPF_REMOTE_TOOLS_PATH=/tmp/netsherlock-tools
BPF_DEPLOY_MODE=auto              # auto|scp|pre-deployed
BPF_REMOTE_PYTHON=/usr/bin/python3
```

**Diagnosis Mode Configuration:**
```bash
DIAGNOSIS_DEFAULT_MODE=interactive
DIAGNOSIS_AUTONOMOUS_ENABLED=true
DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=false
DIAGNOSIS_INTERACTIVE_TIMEOUT_SECONDS=300
```

### Accessing Settings

```python
from netsherlock.config.settings import get_settings, reset_settings

settings = get_settings()  # Singleton
config = settings.get_diagnosis_config()  # DiagnosisConfig instance

# For testing
reset_settings()
```

---

## Core Components

### SSH Manager (`core/ssh_manager.py`)

Manages SSH connection pool for remote command execution.

```python
with SSHManager(settings.ssh) as ssh:
    result = ssh.execute("192.168.1.10", "cat /proc/version")
    if result.success:
        print(result.stdout)
```

### Grafana Client (`core/grafana_client.py`)

HTTP client for Grafana datasource proxy API.

```python
with GrafanaClient(base_url, username, password) as client:
    metrics = client.query_metrics(promql, start, end, step)
    logs = client.query_logs(logql, start, end, limit)
```

### BPF Executor (`core/bpf_executor.py`)

Executes BPF tools on remote hosts with proper deployment.

```python
executor = BPFExecutor(ssh, host, remote_tools_path)
result = executor.execute(command, duration=30)

# Coordinated measurement with receiver-first timing
coord = CoordinatedMeasurement(ssh, timeout, delay)
rx_result, tx_result = coord.execute(
    receiver_host, sender_host,
    receiver_command, sender_command,
    duration=30
)
```

### Tool Executor (`agents/tool_executor.py`)

Routes agent tool calls to actual implementations.

```python
executor = get_tool_executor()

# Available tools by layer
# L1: grafana_query_metrics, loki_query_logs, read_node_logs, ...
# L2: collect_vm_network_env, collect_system_network_env, ...
# L3: execute_coordinated_measurement, measure_vm_latency_breakdown, ...
# L4: analyze_latency_segments, identify_root_cause, ...

result = await executor.execute("grafana_query_metrics", {
    "query": "up",
    "start": "-1h"
})
```

---

## Testing

### Test Structure

```
tests/
├── test_cli.py              # CLI command tests (24 tests)
├── test_controller.py       # DiagnosisController tests (26 tests)
├── test_l3_measurement.py   # L3 tool tests (18 tests)
├── test_schemas_config.py   # Config schema tests (24 tests)
├── test_settings.py         # Settings tests (13 tests)
├── test_tool_executor.py    # Tool routing tests (18 tests)
├── test_webhook.py          # API endpoint tests (41 tests)
├── test_schema_migration.py # Schema compatibility tests (20 tests)
├── fixtures/                # Test data files
│   ├── alert_payloads.json
│   ├── vm_network_env.json
│   ├── measurement_results.json
│   └── grafana_responses.json
└── integration/             # Integration tests (120 tests)
    ├── conftest.py          # Shared fixtures
    ├── test_diagnosis_flow.py    # Diagnosis flow (20 tests)
    ├── test_layer_integration.py # L1→L2→L3→L4 (17 tests)
    ├── test_dual_mode.py         # Mode control (23 tests)
    ├── test_error_handling.py    # Error handling (18 tests)
    └── test_cli_controller.py    # CLI-Controller (42 tests)
```

### Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/test_webhook.py

# With coverage
pytest --cov=netsherlock --cov-report=html

# Verbose
pytest -v
```

### Test Coverage Areas

| Component | Test File | Coverage | Tests |
|-----------|-----------|----------|-------|
| CLI | `test_cli.py` | Commands, argument parsing | 24 |
| Controller | `test_controller.py` | Mode selection, checkpoints, phases | 26 |
| L3 | `test_l3_measurement.py` | Measurement execution, parsing | 18 |
| Schema Migration | `test_schema_migration.py` | Schema compatibility | 20 |
| Schemas | `test_schemas_config.py` | Model validation, serialization | 24 |
| Settings | `test_settings.py` | Env loading, defaults, validation | 13 |
| Tools | `test_tool_executor.py` | Tool routing, layer mapping | 18 |
| Webhook API | `test_webhook.py` | Authentication, validation, endpoints | 41 |
| **Integration** | `integration/*` | **L1→L4 flow, dual-mode, CLI-Controller** | **120** |
| **Total** | | | **304**

### Test Fixtures

```python
@pytest.fixture
def client():
    """Test client with mock authentication."""
    with patch("netsherlock.api.webhook._get_api_key", return_value="test-key"):
        with patch("netsherlock.api.webhook._is_insecure_mode_allowed", return_value=True):
            with TestClient(app) as c:
                yield c

@pytest.fixture
def diagnosis_config():
    """Standard test configuration."""
    return DiagnosisConfig(
        default_mode=DiagnosisMode.INTERACTIVE,
        autonomous=AutonomousConfig(enabled=True),
    )
```

### Integration Test Categories

| Category | File | Description |
|----------|------|-------------|
| Diagnosis Flow | `test_diagnosis_flow.py` | DiagnosisRequest creation, mode selection, checkpoint flow |
| Layer Integration | `test_layer_integration.py` | L1→L2→L3→L4 data transformations |
| Dual Mode | `test_dual_mode.py` | CLI/Webhook sources, known/unknown alerts, checkpoint behavior |
| Error Handling | `test_error_handling.py` | SSH/Grafana failures, graceful degradation |
| CLI-Controller | `test_cli_controller.py` | CLI invocation, checkpoint interaction, result formatting |

---

## Quick Start Examples

### Programmatic Usage

```python
from netsherlock.agents import create_orchestrator

# Create orchestrator
orchestrator = create_orchestrator()

# Diagnose alert
result = await orchestrator.diagnose_alert({
    "labels": {"alertname": "VMNetworkLatency", "instance": "node1"},
    "annotations": {"summary": "High latency detected"}
})

# Manual diagnosis
result = await orchestrator.diagnose_request({
    "problem_type": "vm_network_latency",
    "src_node": "192.168.1.10",
    "dst_node": "192.168.1.20",
    "vm_name": "test-vm",
})

print(result.summary)
print(result.root_cause)
print(result.recommendations)
```

### CLI Usage

```bash
# Diagnose host latency (interactive mode)
netsherlock diagnose --host 192.168.1.10 --type latency

# Diagnose VM network (autonomous mode)
netsherlock diagnose --host 192.168.1.10 --vm-id <uuid> --autonomous

# Collect environment
netsherlock env system --host 192.168.1.10
netsherlock env vm --host 192.168.1.10 --vm-id <uuid>

# Query metrics
netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}' -s "-30m"

# Show configuration
netsherlock config
```

### Webhook Integration

```bash
# Start server
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080

# Send alert
curl -X POST http://localhost:8080/webhook/alertmanager \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {"alertname": "VMNetworkLatency", "instance": "node1"}
    }]
  }'

# Manual diagnosis
curl -X POST http://localhost:8080/diagnose \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "problem_type": "vm_network_latency",
    "src_node": "192.168.1.10",
    "dst_node": "192.168.1.20"
  }'

# Check status
curl http://localhost:8080/diagnose/{diagnosis_id} \
  -H "X-API-Key: your-key"
```

---

## Version History

- **v0.2.0** - CLI-Controller Integration (Phase 10)
  - Full CLI integration with DiagnosisController
  - Terminal-based checkpoint interaction (`_cli_checkpoint_callback`)
  - Result formatting for JSON and text output (`_format_diagnosis_result`)
  - Exit code handling (0=success, 1=error, 2=cancelled, 3=interrupted)
  - Integration test suite (120 tests)
  - Total: 304 passing tests (184 unit + 120 integration)

- **v0.1.0** - Initial implementation
  - Four-layer diagnostic architecture (L1-L4)
  - Dual-mode control (Autonomous/Interactive)
  - FastAPI webhook server with authentication
  - CLI interface with Click
  - Pydantic settings configuration
  - 184 passing tests
