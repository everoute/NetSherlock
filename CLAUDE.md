# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This repository is the **design and planning workspace** for an AI-driven network troubleshooting agent that integrates with internal Grafana monitoring data sources. The project uses Claude Agent SDK as the implementation framework.

### Related Repositories

This workspace has access to two companion repositories:
- `~/workspace/troubleshooting-tools` - eBPF-based network monitoring tools (84 tools: BCC Python, bpftrace, shell scripts)
- `~/workspace/network-measurement-analyzer` - Network measurement data analysis tools

## Architecture

### Four-Layer Diagnostic Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: Diagnostic Analysis                                 │
│   - Measurement data analysis, root cause identification    │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: Precise Measurement                                │
│   - BCC/eBPF tool execution, coordinated multi-point        │
│   - Critical constraint: receiver-first timing              │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: Environment Awareness                              │
│   - Problem type identification, environment collection     │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: Base Monitoring (Hybrid Data Sources)              │
│   - Grafana/Loki metrics and logs                          │
│   - Node local logs via SSH (pingmesh, l2ping)             │
└─────────────────────────────────────────────────────────────┘
```

### MCP Tool Layers

| Layer | Tools | Purpose |
|-------|-------|---------|
| L1 | `grafana_query_metrics`, `loki_query_logs`, `read_pingmesh_logs` | Base monitoring data |
| L2 | `collect_vm_network_env`, `collect_system_network_env` | Environment and topology |
| L3 | `execute_coordinated_measurement`, `measure_vm_latency_breakdown` | eBPF measurement execution |
| L4 | `analyze_latency_segments`, `generate_diagnosis_report` | Analysis and reporting |

### Key Design Constraint

**receiver-first timing**: For coordinated measurements, the receiver-side tool must start before the sender. This constraint is enforced in the L3 tool implementation (`execute_coordinated_measurement`), not by AI decision.

## Data Sources

### Grafana (http://192.168.79.79/grafana)

| ID | Source | Type | Metrics |
|----|--------|------|---------|
| 1 | VictoriaMetrics | Prometheus | 5641 metrics |
| 2 | Clickhouse | ClickHouse | Log analysis |
| 3 | Loki | Loki | Log aggregation |
| 8 | traffic-visualization-query-api | JSON API | Traffic visualization |

### Key Network Metrics

- `host_network_*` (29): ping_time_ns, loss_rate, speed
- `node_network_*` (36): interface-level traffic/errors
- `elf_vm_network_*` (12): VM network monitoring
- `openvswitch_*` (9): OVS internal counters

### Node Local Logs (SSH)

Path: `/var/log/zbs/`
- `network-high-latency` - High latency events
- `l2ping` - L2 ping probe results
- `pingmesh` - Mesh ping statistics

## Documentation Structure

```
docs/
├── research-plan.md              # Main research plan (Chinese)
├── findings.md                   # Research findings summary
├── claude-agent-sdk-design.md    # SDK architecture design analysis
├── framework-selection-plan.md   # Framework comparison
├── analysis/                     # Detailed analysis documents
├── design/                       # Design specifications
└── prd-and-srs/                 # Requirements documents
```

## Reusable Components from troubleshooting-tools

| Component | Path | Purpose |
|-----------|------|---------|
| network_env_collector | test/tools/ | L2 environment collection |
| ssh_manager | test/automate-performance-test/src/core/ | Remote execution pool |
| bpf_remote_executor | test/tools/ | L3 remote BPF execution |
| latency-analysis skill | .claude/skills/ | L4 analysis reference |
| grafana_cpu_stats.py | scripts/ | L1 query reference |

## Framework Decision

**Recommended**: Pure Claude Agent SDK with layered MCP tools

Rationale:
1. Fast MVP validation without LangGraph learning curve
2. Native Subagent support for four-layer responsibility separation
3. Tool encapsulation guarantees critical constraints (receiver-first)
4. Prompt modification enables rapid iteration

## Browser Automation

Use `agent-browser` for web automation. Run `agent-browser --help` for all commands.

Core workflow:
1. `agent-browser open <url>` - Navigate to page
2. `agent-browser snapshot -i` - Get interactive elements with refs (@e1, @e2)
3. `agent-browser click @e1` / `fill @e2 "text"` - Interact using refs
4. Re-snapshot after page changes
