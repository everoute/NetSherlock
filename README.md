# NetSherlock

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-316%20passing-brightgreen.svg)](#testing)

> AI-driven network troubleshooting agent — encoding expert diagnostic methodology into automated workflows powered by 65+ eBPF tools and Claude AI.

> **[Design Document](docs/design/NetSherlock-design.md)** | **[Requirements & User Stories](docs/network-aiops-requirement-and-user-stories.md)**

---

## The Problem

In large-scale virtualized network environments, troubleshooting network issues is exceptionally difficult:

| Challenge | What it looks like | Impact |
|-----------|-------------------|--------|
| **Path complexity** | VM → virtio → vhost → TUN/TAP → OVS → physical NIC — 6+ network stack layers | Fault isolation requires layer-by-layer investigation |
| **Tool expertise** | 65+ eBPF measurement tools, each with unique parameters, filters, and output formats | Extremely high barrier for operators |
| **Methodology gap** | Requires "boundary-first, then details" layered diagnosis experience | Expert knowledge is hard to transfer and replicate |

We built a comprehensive eBPF toolset ([troubleshooting-tools](https://github.com/everoute/troubleshooting-tools)) covering the full network path — but the more capable the tools, the harder they are to use correctly.

## The Solution

NetSherlock encodes the layered diagnostic methodology into an AI Agent's control logic, achieving **end-to-end automation**: alert/config input → diagnosis report output.

```
Expert manual workflow:                    NetSherlock automated workflow:
┌──────────────────────┐                   ┌──────────────────────┐
│ Phase 1: Boundary    │                   │ Boundary Mode        │
│ "Internal or external│       ══►         │ path_tracer deploy   │
│  problem?"           │                   │ Dual-endpoint coord  │
│ Run path_tracer      │                   │ Auto attribution     │
└──────┬───────────────┘                   └──────┬───────────────┘
       │ internal issue                           │ auto decision
       ▼                                          ▼
┌──────────────────────┐                   ┌──────────────────────┐
│ Phase 2: Segment     │                   │ Segment Mode         │
│ "Which segment is    │       ══►         │ 8-point BPF deploy   │
│  slow?"              │                   │ Full-path latency    │
│ Run detail tools     │                   │ LLM root cause       │
│ Expert interprets    │                   │ analysis             │
└──────────────────────┘                   └──────────────────────┘
```

## Architecture

### Four-Layer Diagnostic Model

NetSherlock implements a four-layer architecture where each layer's output feeds the next:

```
┌─────────────────────────────────────────────────────────────────┐
│ L4: Diagnostic Analysis     │ Latency/drop analysis Skills      │
│     Root cause identification, attribution tables, reports      │
├─────────────────────────────────────────────────────────────────┤
│ L3: Precise Measurement     │ path-tracer / latency-measurement │
│     BPF tool deployment, coordinated multi-point measurement    │
├─────────────────────────────────────────────────────────────────┤
│ L2: Environment Awareness   │ network-env-collector Skill       │
│     OVS topology, vhost mapping, NIC discovery                  │
├─────────────────────────────────────────────────────────────────┤
│ L1: Base Monitoring         │ Direct Grafana/Loki queries       │
│     Metrics, logs, pingmesh data collection                     │
└─────────────────────────────────────────────────────────────────┘
```

### Skill-Driven Execution

L2–L4 phases are executed through **Claude Code Skills** — reusable diagnostic procedures that invoke the LLM for intelligent tool coordination and data interpretation. This is the core innovation: each Skill encapsulates expert knowledge about *when*, *how*, and *in what order* to use specific eBPF tools.

```
10 Claude Code Skills
├── L2: network-env-collector
├── L3: vm-network-path-tracer, vm-latency-measurement,
│       system-network-path-tracer
└── L4: vm-network-latency-analysis, vm-network-drop-analysis,
        system-network-latency-analysis, system-network-drop-analysis,
        kernel-stack-analyzer
```

### Dual-Engine Design

| | ControllerEngine (MVP) | OrchestratorEngine (Future) |
|---|---|---|
| **Paradigm** | Deterministic orchestration (LangGraph-style) | ReAct loop (autonomous agent) |
| **Control flow** | Python-coded L1→L2→L3→L4 sequence | LLM dynamically decides next action |
| **Skill selection** | WORKFLOW_TABLE lookup (deterministic) | LLM chooses which Skill to invoke |
| **Predictability** | High — same path every time | Variable — LLM may skip/repeat steps |
| **LLM calls** | 3–4 (only within Skill execution) | 5+ (orchestration + Skill execution) |
| **Status** | Production-ready, 316 tests | Framework ready, orchestration in progress |

### System Data Flow

```
                    ┌─────────────────────┐
                    │    Trigger Layer     │
                    │  Alertmanager / API  │
                    │      / CLI          │
                    └─────────┬───────────┘
                              │
                    ┌─────────▼───────────┐
                    │  DiagnosisEngine     │
                    │  Protocol            │
                    └──┬──────────────┬────┘
                       │              │
            ┌──────────▼──┐    ┌──────▼──────────┐
            │ Controller  │    │  Orchestrator   │
            │ Engine      │    │  Engine (future) │
            └──────┬──────┘    └─────────────────┘
                   │
        ┌──────────▼──────────┐
        │    Skill Layer      │
        │  SkillExecutor →    │
        │  Claude Agent SDK   │
        │  (L2/L3/L4 Skills)  │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │  Infrastructure     │
        │  SSH Manager        │
        │  65+ BPF Tools      │
        │  Grafana / Loki     │
        └─────────────────────┘
```

## Diagnosis Coverage

### Workflow Matrix

NetSherlock supports multiple network types, problem types, and diagnosis modes:

| Network | Problem | Boundary Mode | Segment Mode | Event Mode |
|---------|---------|:---:|:---:|:---:|
| **VM** | Latency | vm-network-path-tracer | vm-latency-measurement (8-point) | — |
| **VM** | Packet Drop | vm-network-path-tracer | — | kfree_skb tracing |
| **System** | Latency | system-network-path-tracer | kernel full-stack tracing | — |
| **System** | Packet Drop | system-network-path-tracer | — | kfree_skb tracing |

### Diagnosis Modes

| Mode | Scope | Use Case | Dependency |
|------|-------|----------|------------|
| **Boundary** | Edge points only (vnet↔phy) | Quick triage: internal vs external | Minimal |
| **Segment** | Full path, all major modules | Precise: segment-level latency breakdown | Medium |
| **Event** | Per-packet event tracing | Detailed: drop events, latency anomalies | Higher |
| **Specialized** | Specific module/protocol | Deep: OVS datapath, TCP retransmission | Varies |

## Features

- **Skill-Driven Architecture** — L2/L3/L4 diagnostic phases as reusable Claude Code Skills
- **8-Point Coordinated Measurement** — BPF tools deployed across sender/receiver VMs and hosts simultaneously
- **Dual-Mode Operation** — Interactive (human-in-the-loop checkpoints) and Autonomous (fully automated)
- **Multi-Stage Diagnosis** — Iterative L3→L4 loops with escalation between diagnosis modes
- **Grafana Integration** — Query metrics and logs from VictoriaMetrics, Loki, ClickHouse
- **Alertmanager Webhook** — Alert-triggered automatic diagnosis with asset inventory lookup
- **Web Dashboard** — React-based UI for task management, real-time status, and report viewing
- **Workflow Registry** — Extensible mapping of (network_type, problem_type, mode) → Skill combinations

## Installation

### Prerequisites

- Python 3.10+
- [Claude Code CLI](https://docs.anthropic.com/en/docs/claude-code) (for Skill execution)
- SSH access to target hosts
- Grafana instance with VictoriaMetrics/Loki datasources (for L1 monitoring)

### Install

```bash
git clone https://github.com/everoute/netsherlock.git
cd netsherlock

# Option A: uv (recommended)
uv sync

# Option B: pip
pip install -e .
```

### Configure

```bash
cp .env.example .env
```

Key environment variables:

| Variable | Description | Required |
|----------|-------------|:---:|
| `GRAFANA_BASE_URL` | Grafana server URL | Yes |
| `GRAFANA_USERNAME` / `GRAFANA_PASSWORD` | Grafana credentials | Yes |
| `SSH_PRIVATE_KEY_PATH` | SSH private key for remote hosts | Yes |
| `WEBHOOK_API_KEY` | API key for webhook authentication | Webhook only |
| `DIAGNOSIS_DEFAULT_MODE` | `interactive` or `autonomous` | No |

## Usage

### CLI — Manual Diagnosis

```bash
# 1. Prepare config file with SSH and test parameters
cp config/minimal-input-template.yaml config/my-diagnosis.yaml
# Edit with actual SSH IPs, test_ips, VM UUIDs

# 2. Run VM latency diagnosis (interactive mode)
netsherlock diagnose \
  --config config/my-diagnosis.yaml \
  --network-type vm \
  --src-host 192.168.75.101 --src-vm <UUID> \
  --dst-host 192.168.75.102 --dst-vm <UUID> \
  --type latency

# 3. Run in autonomous mode (no checkpoints)
netsherlock diagnose \
  --config config/my-diagnosis.yaml \
  --network-type vm \
  --src-host 192.168.75.101 --src-vm <UUID> \
  --type latency \
  --autonomous

# Query Grafana metrics directly
netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}'
```

### Webhook API — Alert-Driven

```bash
# Start the webhook server
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080

# Or use the CLI shortcut
netsherlock-webhook
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/diagnose` | Create a new diagnosis task |
| `GET` | `/diagnose/{id}` | Get task status and results |
| `GET` | `/diagnoses` | List all diagnosis tasks |
| `POST` | `/diagnose/{id}/checkpoint` | Confirm interactive checkpoint |
| `GET` | `/diagnose/{id}/report` | Get final diagnosis report |
| `DELETE` | `/diagnose/{id}` | Cancel a pending diagnosis |
| `POST` | `/webhook/alertmanager` | Alertmanager webhook receiver |

### Web Dashboard

The React-based frontend provides task management, real-time status tracking, and diagnostic report viewing.

```bash
cd web
npm install
npm run dev    # Development server at http://localhost:5173
```

**Tech stack**: React 19, TypeScript, Vite, Tailwind CSS

## Configuration

### Two Configuration Modes

**Manual Mode** — for development and ad-hoc diagnosis:
```yaml
# config/minimal-input.yaml
nodes:
  host-sender:
    ssh: smartx@192.168.75.101
    role: host
  vm-sender:
    ssh: root@192.168.2.100
    role: vm
    host_ref: host-sender
    uuid: ae6aa164-604c-4cb0-84b8-2dea034307f1
    test_ip: 10.0.0.1    # BPF filter IP (may differ from SSH IP)
test_pairs:
  vm:
    server: vm-receiver
    client: vm-sender
```

**Auto Mode** — for alert-triggered diagnosis with asset inventory:
```yaml
# config/global-inventory.yaml
# Pre-configured asset list; alerts auto-construct MinimalInputConfig
```

See [User Guide](docs/guides/user-guide.md) for complete configuration reference.

## Project Structure

```
netsherlock/
├── src/netsherlock/
│   ├── main.py                  # CLI entry point (Click)
│   ├── api/webhook.py           # FastAPI webhook server
│   ├── controller/              # DiagnosisController (L1→L2→L3→L4)
│   ├── core/                    # SkillExecutor, SSH Manager, Grafana client
│   ├── config/                  # Settings, GlobalInventory
│   ├── schemas/                 # Pydantic models (MinimalInputConfig, alerts, etc.)
│   └── tools/                   # L1–L4 tool implementations
├── .claude/skills/              # 10 Claude Code Skills (L2/L3/L4)
├── config/                      # YAML configuration templates
├── web/                         # React frontend (Vite + Tailwind)
├── docs/                        # Design docs, user guide, architecture
└── tests/                       # 316 tests (unit + integration)
```

## Testing

```bash
# Install dev dependencies
uv sync --dev  # or: pip install -e ".[dev]"

# Run all tests (316 total)
pytest

# Unit tests only
pytest tests/ --ignore=tests/integration/

# Integration tests only
pytest tests/integration/

# With coverage
pytest --cov=netsherlock --cov-report=html

# Code quality
mypy src/netsherlock/         # Type checking
ruff check src/netsherlock/   # Linting
```

## Documentation

| Document | Description |
|----------|-------------|
| [Design Document](docs/design/NetSherlock-design.md) | Complete system design with architecture diagrams |
| [Requirements & User Stories](docs/network-aiops-requirement-and-user-stories.md) | User analysis, functional requirements, and roadmap |
| [Implementation Guide](docs/guides/implementation-guide.md) | Component details, internal APIs |
| [User Guide](docs/guides/user-guide.md) | Usage instructions and configuration reference |
| [E2E Test Guide](docs/guides/e2e-diagnosis-test-guide.md) | End-to-end testing procedures |

## Related Repositories

| Repository | Description |
|------------|-------------|
| [troubleshooting-tools](https://github.com/everoute/troubleshooting-tools) | 65+ eBPF network measurement tools (BCC Python, bpftrace, shell scripts) |
| [network-measurement-analyzer](https://github.com/everoute/network-measurement-analyzer) | Network measurement data analysis tools |

## License

[MIT](LICENSE) © everoute

---

**Acknowledgments**: [Anthropic Claude](https://www.anthropic.com/) for AI capabilities, [BCC/eBPF](https://github.com/iovisor/bcc) for network measurement, [Grafana](https://grafana.com/) for monitoring integration.
