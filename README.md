# NetSherlock

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-316%20passing-brightgreen.svg)](#testing)

> AI-driven network troubleshooting agent with eBPF-based diagnostics

NetSherlock is an intelligent network diagnosis tool that combines Claude AI with eBPF-based measurement tools to automatically diagnose network latency issues in virtualized environments.

## Table of Contents

- [Features](#features)
- [Architecture](#architecture)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Usage](#usage)
- [Testing](#testing)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

## Features

- **Skill-Driven Architecture**: L2/L3/L4 diagnostic phases executed through Claude Code Skills
- **8-Point Coordinated Measurement**: BPF tools deployed across sender/receiver VMs and hosts
- **Receiver-First Timing**: Guaranteed measurement accuracy through proper tool sequencing
- **Dual-Mode Operation**: Interactive (human-in-the-loop) and Autonomous (fully automated) modes
- **Grafana Integration**: Query metrics and logs from existing monitoring infrastructure
- **Webhook API**: Automatic diagnosis triggered by Alertmanager alerts

## Architecture

NetSherlock implements a four-layer diagnostic architecture:

```
┌─────────────────────────────────────────────────────────────┐
│ L4: Diagnostic Analysis    │ vm-latency-analysis Skill      │
│     Root cause identification, latency attribution          │
├─────────────────────────────────────────────────────────────┤
│ L3: Precise Measurement    │ vm-latency-measurement Skill   │
│     BPF tool deployment, 8-point coordinated measurement    │
├─────────────────────────────────────────────────────────────┤
│ L2: Environment Awareness  │ network-env-collector Skill    │
│     OVS topology, vhost mapping, NIC discovery              │
├─────────────────────────────────────────────────────────────┤
│ L1: Base Monitoring        │ Direct tool calls              │
│     Grafana/Loki queries, node log collection               │
└─────────────────────────────────────────────────────────────┘
```

## Installation

### Prerequisites

- Python 3.10+
- SSH access to target hosts
- Grafana instance with VictoriaMetrics/Loki datasources

### Install with uv (Recommended)

```bash
git clone https://github.com/echken/netsherlock.git
cd netsherlock
uv sync
```

### Install with pip

```bash
git clone https://github.com/echken/netsherlock.git
cd netsherlock
pip install -e .
```

## Quick Start

### 1. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```bash
# Required
GRAFANA_BASE_URL=http://192.168.79.79/grafana
GRAFANA_USERNAME=admin
GRAFANA_PASSWORD=your_password
SSH_PRIVATE_KEY_PATH=~/.ssh/id_rsa
```

### 2. Prepare Configuration File

**This is required.** Create a configuration file with SSH and test parameters:

```bash
cp config/minimal-input-template.yaml config/my-diagnosis.yaml
```

Edit `config/my-diagnosis.yaml`:

```yaml
nodes:
  host-sender:
    ssh: smartx@192.168.75.101
    role: host

  vm-sender:
    ssh: root@192.168.2.100
    role: vm
    host_ref: host-sender
    uuid: ae6aa164-604c-4cb0-84b8-2dea034307f1
    test_ip: 10.0.0.1    # BPF packet filter IP (may differ from SSH IP)

  host-receiver:
    ssh: smartx@192.168.75.102
    role: host

  vm-receiver:
    ssh: root@192.168.2.200
    role: vm
    host_ref: host-receiver
    uuid: bf7bb275-715d-5dc1-95c9-3feb045418g2
    test_ip: 10.0.0.2

test_pairs:
  vm:
    server: vm-receiver
    client: vm-sender
```

### 3. Run Diagnosis

```bash
netsherlock diagnose \
  --config config/my-diagnosis.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency
```

## Configuration

### Configuration Modes

| Mode | File | CLI Flag | Use Case |
|------|------|----------|----------|
| **Manual** | `minimal-input.yaml` | `--config` | Development, single diagnosis |
| **Automatic** | `global-inventory.yaml` | `--inventory` | Alert-triggered, batch diagnosis |

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `GRAFANA_BASE_URL` | Grafana server URL | Yes |
| `GRAFANA_USERNAME` | Grafana username | Yes |
| `GRAFANA_PASSWORD` | Grafana password | Yes |
| `SSH_PRIVATE_KEY_PATH` | SSH private key path | Yes |
| `WEBHOOK_API_KEY` | API key for webhook auth | For webhook |
| `DIAGNOSIS_DEFAULT_MODE` | Default mode (`interactive`/`autonomous`) | No |

See [User Guide](docs/user-guide.md) for complete configuration reference.

## Usage

### CLI Commands

```bash
# Single VM diagnosis (interactive mode)
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host <IP> --src-vm <UUID> \
  --type latency

# VM-to-VM diagnosis (autonomous mode)
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host <SRC_IP> --src-vm <SRC_UUID> \
  --dst-host <DST_IP> --dst-vm <DST_UUID> \
  --type latency \
  --autonomous

# Using asset inventory (automatic mode)
netsherlock diagnose \
  --inventory config/global-inventory.yaml \
  --network-type vm \
  --src-host <IP> --src-vm <UUID> \
  --autonomous

# Query Grafana metrics
netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}'

# View configuration
netsherlock config
```

### Webhook API

```bash
# Start webhook server
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080

# Trigger diagnosis via API
curl -X POST http://localhost:8080/diagnose \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "vm",
    "diagnosis_type": "latency",
    "src_host": "192.168.75.101",
    "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1"
  }'
```

### Diagnosis Modes

| Mode | Description | Flag |
|------|-------------|------|
| **Interactive** | Pauses at checkpoints for confirmation | `--interactive` (default) |
| **Autonomous** | Fully automated, no user intervention | `--autonomous` |

## Testing

### Install Dev Dependencies

```bash
uv sync --dev
# or
pip install -e ".[dev]"
```

### Run Tests

```bash
# Run all tests (316 total)
pytest

# Run unit tests only (196 tests)
pytest tests/ --ignore=tests/integration/

# Run integration tests only (120 tests)
pytest tests/integration/

# Run with coverage report
pytest --cov=netsherlock --cov-report=html

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_skill_executor.py
```

### Test Structure

```
tests/
├── test_*.py              # Unit tests
│   ├── test_skill_executor.py
│   ├── test_minimal_input.py
│   ├── test_controller.py
│   └── ...
├── fixtures/              # Test data
└── integration/           # Integration tests
    ├── test_cli_controller.py
    ├── test_diagnosis_flow.py
    ├── test_dual_mode.py
    └── ...
```

### Code Quality

```bash
# Type checking
mypy src/netsherlock/

# Linting
ruff check src/netsherlock/

# Format check
ruff format --check src/netsherlock/
```

## Documentation

| Document | Description |
|----------|-------------|
| [User Guide](docs/user-guide.md) | Complete usage instructions, CLI reference |
| [Implementation Guide](docs/implementation-guide.md) | Architecture, components, APIs |
| [Design Document](docs/design/phase1-mvp-design.md) | System design, data flows |

## Project Structure

```
netsherlock/
├── src/netsherlock/
│   ├── api/               # Webhook API
│   ├── config/            # Settings, GlobalInventory
│   ├── controller/        # DiagnosisController
│   ├── core/              # SkillExecutor, SSH, Grafana clients
│   ├── schemas/           # Data models, MinimalInputConfig
│   └── tools/             # L1-L4 tool implementations
├── .claude/skills/        # Claude Code Skills (L2/L3/L4)
├── config/                # Configuration templates
├── docs/                  # Documentation
└── tests/                 # Test suite
```

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Run linting (`ruff check src/`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## License

[MIT](LICENSE) © echken

---

## Acknowledgments

- [Anthropic Claude](https://www.anthropic.com/) - AI capabilities
- [BCC/eBPF](https://github.com/iovisor/bcc) - Network measurement tools
- [Grafana](https://grafana.com/) - Monitoring integration
