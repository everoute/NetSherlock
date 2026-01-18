# NetSherlock Architecture Diagrams

> 版本: 1.0
> 日期: 2026-01-20
> 状态: Phase 10 完成

---

## 1. 系统整体架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Entry Points                                   │
├─────────────────────┬─────────────────────┬─────────────────────────────┤
│     CLI (main.py)   │   Webhook API       │   Programmatic API          │
│                     │   (webhook.py)      │   (agents/__init__.py)      │
│  • diagnose         │   • /webhook/alert  │   • create_orchestrator()   │
│  • env system/vm    │   • /diagnose       │   • diagnose_alert()        │
│  • query metrics    │   • /diagnose/{id}  │   • diagnose_request()      │
│  • config           │   • /diagnoses      │                             │
└──────────┬──────────┴──────────┬──────────┴──────────────┬──────────────┘
           │                     │                         │
           │    ┌────────────────┴───────────────┐         │
           │    │       Mode Selection           │         │
           │    │  • force_mode parameter        │         │
           │    │  • source-based defaults       │         │
           │    │  • config fallback             │         │
           │    └────────────────┬───────────────┘         │
           │                     │                         │
           └─────────────────────┼─────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      DiagnosisController                                 │
│                   (controller/diagnosis_controller.py)                   │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────┐    ┌─────────────────────────┐             │
│  │    Autonomous Mode      │    │    Interactive Mode     │             │
│  │    ─────────────────    │    │    ──────────────────   │             │
│  │  • Auto L1→L2→L3→L4     │    │  • Checkpoint pauses    │             │
│  │  • No user intervention │    │  • User confirmation    │             │
│  │  • Interrupt support    │    │  • Timeout handling     │             │
│  └─────────────────────────┘    └─────────────────────────┘             │
│                                                                          │
│  CheckpointManager:                                                      │
│  • PROBLEM_CLASSIFICATION - After L2, before measurement                │
│  • MEASUREMENT_PLAN - After planning, before L3 execution               │
│  • FURTHER_DIAGNOSIS - After L4, if more investigation needed           │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Network Troubleshooting Agent                         │
│                      (agents/orchestrator.py)                            │
├─────────────────────────────────────────────────────────────────────────┤
│                          System Prompt                                   │
│  • Problem type identification rules                                     │
│  • Layered diagnostic methodology (L1→L2→L3→L4)                         │
│  • Diagnostic flow constraints                                           │
│  • Mode awareness (autonomous/interactive)                               │
├─────────────────────────────────────────────────────────────────────────┤
│                           Subagents                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐          │
│  │  L2 Subagent    │  │  L3 Subagent    │  │  L4 Subagent    │          │
│  │  Environment    │──│  Measurement    │──│  Analysis       │          │
│  │  Awareness      │  │  Execution      │  │  & Reporting    │          │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘          │
│           │                    │                    │                    │
└───────────┼────────────────────┼────────────────────┼────────────────────┘
            │                    │                    │
            ▼                    ▼                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         Tool Executor                                    │
│                    (agents/tool_executor.py)                             │
│  Routes agent tool calls to L1-L4 implementations                        │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        │                        │                        │
        ▼                        ▼                        ▼
┌───────────────┐    ┌───────────────┐    ┌───────────────┐
│   L1 Tools    │    │   L2 Tools    │    │   L3 Tools    │
│   Monitoring  │    │   Environment │    │   Measurement │
├───────────────┤    ├───────────────┤    ├───────────────┤
│ grafana_*     │    │ collect_vm_*  │    │ execute_*     │
│ loki_*        │    │ collect_sys_* │    │ measure_*     │
│ read_logs     │    │ build_path    │    │ (rcvr-first)  │
└───────────────┘    └───────────────┘    └───────────────┘
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│                        L4 Tools - Analysis                             │
├───────────────────────────────────────────────────────────────────────┤
│  analyze_latency_segments  │  identify_root_cause  │  generate_report │
└───────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│                        Infrastructure                                  │
├─────────────────┬─────────────────────┬───────────────────────────────┤
│  GrafanaClient  │    SSHManager       │      BPFExecutor              │
│  (HTTP API)     │    (Connection Pool)│      (Remote Execution)       │
└─────────────────┴─────────────────────┴───────────────────────────────┘
```

---

## 2. 四层诊断数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    L1: Base Monitoring Layer                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Input: Alert/Request                                                   │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │ grafana_query_metrics()  ──→  Prometheus/VictoriaMetrics         │  │
│   │ loki_query_logs()        ──→  Loki log aggregation               │  │
│   │ read_node_logs()         ──→  SSH /var/log/zbs/                  │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│   Output: MetricsResult, LogsResult, AlertContext                        │
│                                                                          │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    L2: Environment Awareness Layer                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Input: L1 Context (node IPs, VM identifiers)                          │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │ collect_vm_network_env()     ──→  VMNetworkEnv                   │  │
│   │   • virsh dominfo/dumpxml                                        │  │
│   │   • /proc/<qemu_pid>/fd                                          │  │
│   │   • ovs-vsctl                                                    │  │
│   │                                                                  │  │
│   │ collect_system_network_env() ──→  SystemNetworkEnv               │  │
│   │   • OVS internal ports                                           │  │
│   │   • /sys/class/net                                               │  │
│   │   • Bond configuration                                           │  │
│   │                                                                  │  │
│   │ build_network_path()         ──→  NetworkPath                    │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│   Output: VMNetworkEnv, SystemNetworkEnv, NetworkPath                    │
│                                                                          │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    L3: Precise Measurement Layer                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Input: L2 Environment (topology, PIDs, interfaces)                    │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │ execute_coordinated_measurement()  [RECEIVER-FIRST GUARANTEE]    │  │
│   │   1. Deploy receiver tool → receiver_host                        │  │
│   │   2. Start receiver, wait for "ready" (min 1 second)             │  │
│   │   3. Deploy sender tool → sender_host                            │  │
│   │   4. Start sender                                                │  │
│   │   5. Wait for duration                                           │  │
│   │   6. Collect results from both                                   │  │
│   │                                                                  │  │
│   │ measure_vm_latency_breakdown()  ──→  LatencyBreakdown            │  │
│   │   Segments: virtio TX/RX, vhost-net, TAP, OVS                    │  │
│   │                                                                  │  │
│   │ measure_packet_drop()           ──→  DropAnalysis                │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│   Output: MeasurementResult, LatencyBreakdown, DropAnalysis              │
│                                                                          │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    L4: Diagnostic Analysis Layer                         │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   Input: L3 Measurements                                                 │
│   ┌──────────────────────────────────────────────────────────────────┐  │
│   │ analyze_latency_segments()   ──→  LatencyAnalysis                │  │
│   │   • Compare against thresholds                                   │  │
│   │   • Identify anomalous segments                                  │  │
│   │                                                                  │  │
│   │ identify_root_cause()        ──→  RootCause                      │  │
│   │   Categories:                                                    │  │
│   │   • HOST_INTERNAL (vhost, OVS, kernel)                           │  │
│   │   • NETWORK_FABRIC (Switch, cable, ToR)                          │  │
│   │   • VM_INTERNAL (Guest OS, virtio driver)                        │  │
│   │   • CONFIGURATION (MTU, flow rules)                              │  │
│   │   • RESOURCE_CONTENTION (CPU, memory)                            │  │
│   │                                                                  │  │
│   │ generate_diagnosis_report()  ──→  DiagnosisReport                │  │
│   └──────────────────────────────────────────────────────────────────┘  │
│   Output: DiagnosisResult                                                │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 3. CLI-Controller 集成

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CLI Entry (main.py)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   netsherlock diagnose --host <IP> --type latency [--autonomous]        │
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ _determine_diagnosis_mode()                                     │   │
│   │   Priority:                                                     │   │
│   │   1. --mode option (explicit)                                   │   │
│   │   2. --autonomous flag                                          │   │
│   │   3. --interactive flag                                         │   │
│   │   4. Default: INTERACTIVE                                       │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
│                                    ▼                                     │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ Create DiagnosisRequest                                         │   │
│   │   • request_id, request_type, source_host, target_host          │   │
│   │   • vm_id, options (duration, mode)                             │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                    │                                     │
└────────────────────────────────────┼─────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     DiagnosisController                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   checkpoint_callback = _cli_checkpoint_callback (if interactive)       │
│                                                                          │
│   asyncio.run(controller.run(request, source=CLI, force_mode=mode))    │
│                                                                          │
└─────────────────────────────────────┬───────────────────────────────────┘
                                      │
             ┌────────────────────────┼────────────────────────┐
             │                        │                        │
             ▼                        ▼                        ▼
    [Interactive Mode]        [Autonomous Mode]        [Checkpoint]
             │                        │                        │
             │                        │                        ▼
             │                        │          ┌─────────────────────────┐
             │                        │          │ _cli_checkpoint_callback│
             │                        │          │ ───────────────────────│
             │                        │          │ Display:               │
             │                        │          │ • Summary              │
             │                        │          │ • Details              │
             │                        │          │ • Options              │
             │                        │          │ • Recommendation       │
             │                        │          │                        │
             │                        │          │ Prompt:                │
             │                        │          │ 1=Confirm 2=Modify     │
             │                        │          │ 3=Cancel               │
             │                        │          │                        │
             │                        │          │ Return:                │
             │                        │          │ CheckpointResult       │
             │                        │          └─────────────────────────┘
             │                        │
             └────────────────────────┼────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      Result Handling                                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   _format_diagnosis_result(result, json_output)                         │
│                                                                          │
│   ┌───────────────────────┐    ┌───────────────────────────────────┐    │
│   │ JSON Output           │    │ Text Output                       │    │
│   │ ────────────          │    │ ───────────                       │    │
│   │ {                     │    │ ============                      │    │
│   │   "diagnosis_id": ... │    │ DIAGNOSIS RESULT                  │    │
│   │   "status": ...       │    │ ============                      │    │
│   │   "mode": ...         │    │ Diagnosis ID: xxx                 │    │
│   │   "summary": ...      │    │ Status: completed                 │    │
│   │   ...                 │    │ Mode: interactive                 │    │
│   │ }                     │    │ Summary: ...                      │    │
│   └───────────────────────┘    └───────────────────────────────────┘    │
│                                                                          │
│   Exit Codes:                                                            │
│   • 0  = COMPLETED (success)                                            │
│   • 1  = ERROR (diagnosis failed)                                       │
│   • 2  = CANCELLED (user cancelled at checkpoint)                       │
│   • 3  = INTERRUPTED (diagnosis interrupted mid-execution)              │
│   • 130 = KeyboardInterrupt (Ctrl+C)                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 4. Checkpoint 交互流程 (Interactive Mode)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Interactive Mode Execution                            │
└───────────────────────────────────┬─────────────────────────────────────┘
                                    │
    ┌───────────────────────────────┼───────────────────────────────┐
    │                               │                               │
    ▼                               ▼                               ▼
┌─────────────┐             ┌─────────────┐             ┌─────────────┐
│   Phase 1   │             │   Phase 2   │             │   Phase 3   │
│   L1 + L2   │             │   L3        │             │   L4        │
│ Environment │             │ Measurement │             │  Analysis   │
└──────┬──────┘             └──────┬──────┘             └──────┬──────┘
       │                           │                           │
       ▼                           ▼                           ▼
╔══════════════════╗       ╔══════════════════╗       ╔══════════════════╗
║  CHECKPOINT 1    ║       ║  CHECKPOINT 2    ║       ║  CHECKPOINT 3    ║
║  PROBLEM_        ║       ║  MEASUREMENT_    ║       ║  FURTHER_        ║
║  CLASSIFICATION  ║       ║  PLAN            ║       ║  DIAGNOSIS       ║
╠══════════════════╣       ╠══════════════════╣       ╠══════════════════╣
║                  ║       ║                  ║       ║                  ║
║ "VM network      ║       ║ "Plan: 3 tools   ║       ║ "Analysis done.  ║
║  latency issue   ║       ║  Duration: 30s   ║       ║  Need further    ║
║  detected"       ║       ║  Impact: <5%"    ║       ║  investigation?" ║
║                  ║       ║                  ║       ║                  ║
║ Options:         ║       ║ Options:         ║       ║ Options:         ║
║ 1. Confirm       ║       ║ 1. Execute       ║       ║ 1. Complete      ║
║ 2. Modify        ║       ║ 2. Adjust        ║       ║ 2. Deep dive     ║
║ 3. Cancel        ║       ║ 3. Cancel        ║       ║                  ║
╚════════╤═════════╝       ╚════════╤═════════╝       ╚════════╤═════════╝
         │                          │                          │
    ┌────┴────┐                ┌────┴────┐                ┌────┴────┐
    │         │                │         │                │         │
    ▼         ▼                ▼         ▼                ▼         ▼
[Confirm] [Cancel]        [Execute] [Cancel]        [Complete] [Continue]
    │         │                │         │                │         │
    │         │                │         │                │         │
    ▼         ▼                ▼         ▼                ▼         ▼
[Continue] [Exit]         [Continue] [Exit]          [Report] [Loop back]
    │         │                │         │                │
    └─────────┼────────────────┼─────────┼────────────────┘
              │                │         │
              ▼                ▼         ▼
        ┌─────────────────────────────────────┐
        │         DiagnosisResult             │
        │  status: completed|cancelled|error  │
        └─────────────────────────────────────┘
```

---

## 5. 目录结构

```
src/netsherlock/
├── __init__.py                      # Package exports, lazy loading
├── main.py                          # CLI entry point (Click)
│   ├── cli()                        # Main CLI group
│   ├── diagnose()                   # Diagnosis command
│   ├── env()                        # Environment collection
│   ├── query()                      # Metrics/logs query
│   ├── config()                     # Show configuration
│   ├── _determine_diagnosis_mode()  # Mode selection logic
│   ├── _cli_checkpoint_callback()   # Terminal checkpoint interaction
│   └── _format_diagnosis_result()   # Result formatting
│
├── api/
│   ├── __init__.py
│   └── webhook.py                   # FastAPI webhook server
│       ├── /health                  # Health check
│       ├── /webhook/alertmanager    # Alert webhook
│       ├── /diagnose                # Manual diagnosis
│       └── /diagnoses               # List diagnoses
│
├── agents/
│   ├── __init__.py                  # Agent exports
│   ├── base.py                      # Data types (ProblemType, RootCause)
│   ├── orchestrator.py              # Main orchestrator agent
│   ├── subagents.py                 # L2/L3/L4 subagent implementations
│   ├── tool_executor.py             # Tool routing dispatcher
│   └── prompts/                     # Agent system prompts
│       ├── main_orchestrator.py
│       ├── l2_environment_awareness.py
│       ├── l3_precise_measurement.py
│       └── l4_diagnostic_analysis.py
│
├── config/
│   ├── __init__.py
│   └── settings.py                  # Pydantic settings configuration
│
├── controller/
│   ├── __init__.py
│   ├── diagnosis_controller.py      # Dual-mode control logic
│   └── checkpoints.py               # Interactive mode checkpoints
│
├── core/
│   ├── __init__.py
│   ├── ssh_manager.py               # SSH connection pool
│   ├── grafana_client.py            # Grafana API client
│   └── bpf_executor.py              # BPF tool remote execution
│
├── schemas/
│   ├── __init__.py
│   ├── alert.py                     # Alert/DiagnosisRequest models
│   ├── config.py                    # DiagnosisConfig, modes, checkpoints
│   ├── environment.py               # Network environment models
│   ├── measurement.py               # Measurement result models
│   └── report.py                    # Diagnosis report models
│
└── tools/
    ├── __init__.py
    ├── l1_monitoring.py             # Grafana, Loki, node log queries
    ├── l2_environment.py            # Network topology collection
    ├── l3_measurement.py            # BPF measurement execution
    └── l4_analysis.py               # Root cause analysis

tests/
├── test_cli.py                      # 24 tests
├── test_controller.py               # 26 tests
├── test_l3_measurement.py           # 18 tests
├── test_schema_migration.py         # 20 tests
├── test_schemas_config.py           # 24 tests
├── test_settings.py                 # 13 tests
├── test_tool_executor.py            # 18 tests
├── test_webhook.py                  # 41 tests
├── fixtures/                        # Test data files
│   ├── alert_payloads.json
│   ├── vm_network_env.json
│   ├── measurement_results.json
│   └── grafana_responses.json
└── integration/                     # 120 tests
    ├── conftest.py
    ├── test_diagnosis_flow.py       # 20 tests
    ├── test_layer_integration.py    # 17 tests
    ├── test_dual_mode.py            # 23 tests
    ├── test_error_handling.py       # 18 tests
    └── test_cli_controller.py       # 42 tests

Total: 304 tests
```
