# NetSherlock

AI-driven network troubleshooting agent with eBPF-based diagnostics.

## Overview

NetSherlock is an intelligent network diagnosis tool that combines:
- **Claude AI** for intelligent analysis and decision-making
- **eBPF tools** for precise network measurements
- **Grafana integration** for monitoring data access

### Four-Layer Architecture

| Layer | Function | Tools |
|-------|----------|-------|
| L1 | Base Monitoring | Grafana metrics, Loki logs |
| L2 | Environment Awareness | Network topology collection |
| L3 | Precise Measurement | BPF-based latency breakdown |
| L4 | Diagnostic Analysis | Root cause identification |

## Quick Start

### Installation

```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -e .
```

### Configuration

```bash
# Copy and configure environment
cp .env.example .env

# Required settings:
# - LLM_API_KEY: Anthropic API key
# - GRAFANA_BASE_URL: Grafana server URL
# - SSH_PRIVATE_KEY_PATH: SSH key for remote hosts
```

### Basic Usage

```bash
# VM network latency diagnosis (interactive mode)
netsherlock diagnose \
  --network-type vm \
  --src-host 192.168.1.10 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --type latency

# VM-to-VM diagnosis (autonomous mode)
netsherlock diagnose \
  --network-type vm \
  --src-host 192.168.1.10 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.1.20 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --autonomous

# Collect network environment
netsherlock env system --host 192.168.1.10
netsherlock env vm --host 192.168.1.10 --vm-id <UUID>

# Query Grafana metrics
netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}'
```

## Diagnosis Modes

### Interactive Mode (Default)
- Pauses at checkpoints for user confirmation
- Best for investigating unknown issues
- User can modify diagnosis direction

### Autonomous Mode
- Fully automated execution
- Best for known issue types or alert response
- Use `--autonomous` flag

## Documentation

- [Usage Guide](docs/usage-guide.md) - Complete CLI and API reference
- [Implementation Guide](docs/implementation-guide.md) - Architecture details

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Run tests
uv run pytest

# Type checking
uv run mypy src/netsherlock/

# Linting
uv run ruff check src/netsherlock/
```

## License

MIT
