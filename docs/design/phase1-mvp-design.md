# Phase 1 MVP 详细设计

> 基于 `framework-selection-plan.md` 和 `research-plan.md` 调研结论整理
> 版本: 3.0
> 日期: 2026-01-20
> 变更: Phase 10 CLI-Controller 集成完成，304 测试通过

---

## 一、MVP 范围定义

### 1.1 功能边界

| 维度 | MVP 范围 | 后续扩展 |
|------|----------|----------|
| **入口** | CLI + Alertmanager Webhook | Grafana 面板集成 |
| **问题类型** | VM 网络延迟诊断 | 丢包、吞吐、OVS、vhost 等 9 类 |
| **网络范围** | VM 网络 (virtio → vhost → OVS → 物理) | 系统网络 (OVS internal port) |
| **工具数量** | 3-5 个核心工具 | 全部 57+ BPF 工具 |
| **运行模式** | 全自主模式 + 人机协作模式 | 多步诊断、checkpoint |
| **状态管理** | 单次诊断，内存状态 | 持久化、历史查询 |

### 1.2 双模式控制循环 (核心设计)

MVP 必须支持两种运行模式，可通过配置切换：

#### 模式 1: 全自主模式 (Autonomous Mode)

```
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 告警触发 │ → │ 环境收集 │ → │ 场景初筛 │ → │ 测量部署 │ → │ 数据收集 │ → │ 诊断报告 │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
     ↑                                                                               │
     └───────────────────────── (可选: 深入诊断循环) ─────────────────────────────────┘
```

**前置条件**:
- 配置了基础告警/监控触发规则
- 开启 `auto_agent_loop: true` 选项
- 告警类型在已知问题分类中

**适用场景**:
- 已知问题类型，流程标准化
- 夜间/无人值守运维
- 高频告警快速响应

**行为特征**:
- 收到告警后自动启动诊断流程
- 全流程无需人工干预
- 完成后输出诊断报告
- 支持中途中断/人工介入

#### 模式 2: 人机协作模式 (Interactive Mode) - 默认

```
┌────────────┐    ┌──────────┐    ┌──────────┐    ┌─────────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ 告警/手动  │ → │ 环境收集 │ → │ 问题归类 │ → │ [人工确认]  │ → │ 测量计划 │ → │ 执行测量 │ → │ 分析报告 │
│   触发    │    │          │    │          │    │ 补充信息    │    │          │    │          │    │          │
└────────────┘    └──────────┘    └──────────┘    └─────────────┘    └──────────┘    └──────────┘    └──────────┘
                                                        ↑
                                                   等待用户输入
```

**前置条件**: 无 (默认模式)

**适用场景**:
- 新问题类型，需要人工判断
- 需要补充告警信息中缺失的上下文
- 用户希望确认诊断方向

**人工确认点 (Checkpoints)**:
1. **问题归类确认**: Agent 初筛后，用户确认/修正问题分类
2. **测量计划确认**: Agent 提出测量计划，用户确认执行
3. **结果确认** (可选): 用户可要求进一步诊断

### 1.3 核心用户场景

**场景 A - 全自主模式**:
Grafana 告警 "VMNetworkLatency" 触发 → Agent 自动完成全流程诊断 → 输出报告

**场景 B - 人机协作模式**:
```bash
# CLI 手动触发
netsherlock diagnose --src-node 192.168.1.10 --dst-node 192.168.1.20 --vm vm-123

# Agent 响应
> 已收集环境信息，初步判断为 VM 网络延迟问题
> 检测到以下异常:
>   - vhost worker CPU 使用率 85%
>   - OVS 端口 tx_errors 增加
>
> 建议执行以下测量:
>   1. VM 延迟分段测量 (vm_network_latency_summary.py)
>   2. vhost 调度延迟采样 (vhost_sched_latency.py)
>
> 是否继续? [Y/n]
```

**输出**: 结构化诊断报告，包含：
- 延迟分段数据 (各阶段 P50/P95/P99)
- 异常阶段识别
- 根因定位 (vm_internal / vhost_processing / host_internal / physical_network)
- 处置建议

---

## 二、系统架构

### 2.1 双模式控制器架构

```
                                    ┌─────────────────────────────────┐
                                    │         Entry Points            │
                                    ├────────────────┬────────────────┤
                                    │ Alertmanager   │     CLI        │
                                    │   Webhook      │   (diagnose)   │
                                    └───────┬────────┴───────┬────────┘
                                            │                │
                                            ▼                ▼
                            ┌───────────────────────────────────────────┐
                            │           DiagnosisController             │
                            │  ┌─────────────────────────────────────┐  │
                            │  │         Mode Selection              │  │
                            │  │  ┌─────────────┐  ┌──────────────┐  │  │
                            │  │  │ Autonomous  │  │ Interactive  │  │  │
                            │  │  │   Loop      │  │    Loop      │  │  │
                            │  │  └─────────────┘  └──────────────┘  │  │
                            │  └─────────────────────────────────────┘  │
                            │                    │                      │
                            │         ┌──────────┴──────────┐          │
                            │         ▼                     ▼          │
                            │  ┌─────────────┐     ┌─────────────┐     │
                            │  │ auto_run()  │     │ step_run()  │     │
                            │  │ 全流程执行   │     │ 单步+确认    │     │
                            │  └─────────────┘     └─────────────┘     │
                            └───────────────────────────────────────────┘
                                            │
                                            ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Network Troubleshooting Agent                         │
│                       (Main Orchestrator)                                │
├─────────────────────────────────────────────────────────────────────────┤
│                          System Prompt                                   │
│  - 问题类型识别规则                                                      │
│  - 分层诊断方法论 (L1→L2→L3→L4)                                        │
│  - 诊断流程约束                                                          │
│  - 运行模式感知 (autonomous / interactive)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                         Subagents                                        │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐                   │
│  │ L2 Subagent │   │ L3 Subagent │   │ L4 Subagent │                   │
│  │ (环境收集)  │ → │ (测量执行)  │ → │ (分析报告)  │                   │
│  └─────────────┘   └─────────────┘   └─────────────┘                   │
├─────────────────────────────────────────────────────────────────────────┤
│                         MCP Tool Layer                                   │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐ ┌─────────────┐│
│  │   L1 Tools    │ │   L2 Tools    │ │   L3 Tools    │ │  L4 Tools   ││
│  │ grafana_*     │ │ collect_*     │ │ measure_*     │ │ analyze_*   ││
│  │ loki_*        │ │ resolve_path  │ │ (receiver-    │ │ report_*    ││
│  │ read_logs     │ │               │ │  first内置)   │ │             ││
│  └───────────────┘ └───────────────┘ └───────────────┘ └─────────────┘│
├─────────────────────────────────────────────────────────────────────────┤
│                        Infrastructure                                    │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐        │
│  │   GrafanaClient  │ │   SSHManager     │ │   BPFExecutor    │        │
│  │   (HTTP API)     │ │   (连接池)        │ │   (远程执行)      │        │
│  └──────────────────┘ └──────────────────┘ └──────────────────┘        │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.2 DiagnosisController 详细设计

```python
class DiagnosisController:
    """诊断控制器 - 管理双模式运行"""

    def __init__(self, config: DiagnosisConfig):
        self.config = config
        self.orchestrator = NetworkTroubleshootingOrchestrator()
        self.mode = config.mode  # "autonomous" | "interactive"

    async def run(self, request: DiagnosisRequest) -> DiagnosisResult:
        """根据模式执行诊断"""
        if self.mode == "autonomous":
            return await self._run_autonomous(request)
        else:
            return await self._run_interactive(request)

    async def _run_autonomous(self, request: DiagnosisRequest) -> DiagnosisResult:
        """全自主模式 - 完整流程无中断"""
        # L1: 查询监控数据
        l1_context = await self.orchestrator.query_monitoring(request)
        # L2: 收集环境
        environment = await self.orchestrator.collect_environment(l1_context)
        # L3: 执行测量
        measurements = await self.orchestrator.execute_measurement(environment)
        # L4: 分析报告
        return await self.orchestrator.analyze_and_report(measurements)

    async def _run_interactive(self, request: DiagnosisRequest) -> DiagnosisResult:
        """人机协作模式 - 关键节点等待确认"""
        # Phase 1: 环境收集 + 问题归类
        l1_context = await self.orchestrator.query_monitoring(request)
        environment = await self.orchestrator.collect_environment(l1_context)
        classification = await self.orchestrator.classify_problem(environment)

        # Checkpoint 1: 用户确认问题分类
        if not await self._confirm_classification(classification):
            classification = await self._get_user_input("请提供问题分类或补充信息")

        # Phase 2: 测量计划
        measurement_plan = await self.orchestrator.plan_measurement(classification)

        # Checkpoint 2: 用户确认测量计划
        if not await self._confirm_plan(measurement_plan):
            return DiagnosisResult(status="cancelled")

        # Phase 3: 执行测量 + 分析
        measurements = await self.orchestrator.execute_measurement(measurement_plan)
        return await self.orchestrator.analyze_and_report(measurements)
```

### 2.3 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Agent 框架 | Claude Agent SDK | MVP 最优，MCP 原生支持，快速迭代 |
| 架构模式 | 单 Main Agent + 3 Subagents | 自然实现四层职责分离 |
| 控制循环 | DiagnosisController 双模式 | 满足全自主和人机协作两种需求 |
| receiver-first | 工具层封装 | 在 `execute_coordinated_measurement` 内部保证时序 |
| 数据类型 | Pydantic 模型 | 类型安全，JSON 序列化方便 |
| 默认模式 | Interactive (人机协作) | 保守策略，避免自动执行意外操作 |

---

## 三、层级职责与接口定义

### 3.1 L1: 基础监控层

**职责**: 查询现有监控数据，建立问题上下文

**工具定义**:

| 工具 | 输入 | 输出 | 数据源 |
|------|------|------|--------|
| `grafana_query_metrics` | PromQL query, time range | MetricsResult | VictoriaMetrics |
| `loki_query_logs` | LogQL query, time range | LogsResult | Loki |
| `read_node_logs` | node_ip, log_type | NodeLogsResult | SSH (/var/log/zbs/) |

**关键指标 (MVP)**:
- `host_network_ping_time_ns` - 主机网络延迟
- `elf_vm_network_*` - VM 网络流量/丢包
- `host_service_cpu_usage_percent{_service="ovs_vswitchd_svc"}` - OVS CPU

### 3.2 L2: 环境感知层

**职责**: 收集网络拓扑和环境信息，为 L3 测量提供参数

**工具定义**:

| 工具 | 输入 | 输出 |
|------|------|------|
| `collect_vm_network_env` | node_ip, vm_identifier | VMNetworkEnv |
| `collect_system_network_env` | node_ip, network_type | SystemNetworkEnv |
| `resolve_network_path` | src_env, dst_env | NetworkPath |

**输出数据结构 (VMNetworkEnv)**:
```python
@dataclass
class VMNetworkEnv:
    vm_uuid: str
    vm_name: str
    host: str                    # 宿主机 IP
    qemu_pid: int
    nics: list[VMNicInfo]        # 网络设备列表
        # VMNicInfo:
        #   - mac, host_vnet, ovs_bridge
        #   - vhost_pids, tap_fds
        #   - physical_nics (bond info)
```

**收集步骤**:
1. SSH 连接宿主机
2. `virsh dominfo` / `virsh dumpxml` 获取 VM 信息
3. `/proc/<qemu_pid>/fd` 获取 vhost TID
4. `ovs-vsctl` 获取 OVS 拓扑
5. `/sys/class/net` 获取物理网卡/bond 信息

### 3.3 L3: 精确测量层

**职责**: 执行 BPF 工具，收集分段延迟数据

**核心约束**: **receiver-first 时序** - 接收端必须先于发送端启动

**工具定义**:

| 工具 | 输入 | 输出 | 约束 |
|------|------|------|------|
| `execute_coordinated_measurement` | receiver, sender, duration | MeasurementResult | 内部保证 receiver-first |
| `measure_vm_latency_breakdown` | src_env, dst_env, flow | MeasurementResult | 调用 vm_network_latency_summary.py |
| `measure_system_latency_breakdown` | src_env, dst_env | MeasurementResult | 调用 system_network_latency_summary.py |

**receiver-first 实现**:
```python
async def execute_coordinated_measurement(receiver, sender, duration):
    # 1. 启动 receiver
    recv_proc = await ssh_manager.execute_async(receiver.node_ip, recv_cmd)

    # 2. 等待 receiver ready (解析 stdout 或固定延迟)
    await wait_for_ready(recv_proc, timeout=10)

    # 3. 启动 sender (此时 receiver 已就绪)
    send_proc = await ssh_manager.execute_async(sender.node_ip, send_cmd)

    # 4. 等待测量完成
    await asyncio.sleep(duration)

    # 5. 收集双端数据
    return MeasurementResult(
        receiver_data=parse_output(recv_proc),
        sender_data=parse_output(send_proc),
    )
```

**输出数据结构 (MeasurementResult)**:
```python
@dataclass
class MeasurementResult:
    measurement_id: str
    measurement_type: str        # "vm_latency", "system_latency"
    timestamp: str
    duration_seconds: float
    sample_count: int
    segments: list[LatencySegment]   # 各阶段延迟
    total_latency: LatencyHistogram  # 总延迟直方图

@dataclass
class LatencySegment:
    name: str                    # e.g., "virtio_tx_to_vhost"
    layer: str                   # "vm_internal", "vhost_processing", ...
    histogram: LatencyHistogram  # P50, P95, P99, max
```

### 3.4 L4: 诊断分析层

**职责**: 分析测量数据，识别根因，生成报告

**工具定义**:

| 工具 | 输入 | 输出 |
|------|------|------|
| `analyze_latency_segments` | segments, thresholds | AnomalyReport |
| `identify_root_cause` | anomalies, environment | RootCause |
| `generate_diagnosis_report` | root_cause, measurements | DiagnosisResult |

**根因分类 (RootCauseCategory)**:
```python
class RootCauseCategory(Enum):
    VM_INTERNAL = "vm_internal"           # Guest VM 问题
    VHOST_PROCESSING = "vhost_processing" # vhost-net 处理延迟
    HOST_INTERNAL = "host_internal"       # Host 网络 (OVS, kernel)
    PHYSICAL_NETWORK = "physical_network" # 物理网络
```

**异常阈值 (MVP 默认)**:
| 层级 | 正常 P95 | 异常阈值 |
|------|---------|----------|
| VM Internal | <50μs | >200μs |
| vhost Processing | <100μs | >500μs |
| Host Internal | <100μs | >1ms |
| Physical Network | <500μs | >5ms |

---

## 四、数据流设计

### 4.1 模式 1: 全自主模式数据流

**触发条件**: Alertmanager Webhook + `auto_agent_loop: true`

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Alertmanager Webhook                                                     │
│ ────────────────────                                                    │
│ POST /api/v1/alert                                                      │
│ {                                                                       │
│   "alerts": [{                                                          │
│     "status": "firing",                                                 │
│     "labels": {"alertname": "VMNetworkLatency", "vm_name": "vm-123"},  │
│     "annotations": {"summary": "VM network latency > 5ms"}             │
│   }]                                                                    │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   DiagnosisController         │
                    │   mode = "autonomous"         │
                    │   auto_agent_loop = true      │
                    └───────────────────────────────┘
                                    │
        ┌───────────────────────────┴───────────────────────────┐
        │                    自动执行全流程                        │
        └───────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 1: L1 监控数据查询                                                  │
│ ──────────────────────────                                              │
│ • grafana_query_metrics("host_network_ping_time_ns{vm='vm-123'}")      │
│ • loki_query_logs("{service='elf-vm-monitor'} |= 'vm-123'")            │
│ → L1Context: 指标趋势, 日志事件                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ (自动继续)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 2: L2 环境收集 + 问题分类                                           │
│ ───────────────────────────────                                         │
│ • collect_vm_network_env() → VMNetworkEnv                               │
│ • classify_problem() → ProblemClassification                            │
│ → 自动判断: VM网络延迟问题, 建议测量方案                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ (自动继续)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 3: L3 精确测量 (receiver-first)                                     │
│ ────────────────────────────────────                                    │
│ • measure_vm_latency_breakdown(src_env, dst_env, flow, duration=30s)   │
│ → MeasurementResult: 分段延迟数据                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │ (自动继续)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Step 4: L4 分析报告                                                      │
│ ─────────────────────                                                   │
│ • analyze_latency_segments() → AnomalyReport                           │
│ • identify_root_cause() → RootCause                                    │
│ • generate_diagnosis_report() → DiagnosisResult                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 输出: DiagnosisResult                                                    │
│ ───────────────────                                                     │
│ {                                                                       │
│   "mode": "autonomous",                                                 │
│   "diagnosis_id": "diag-abc12345",                                     │
│   "summary": "VM 网络延迟异常，瓶颈在 vhost 处理阶段",                   │
│   "root_cause": {...},                                                  │
│   "recommendations": [...]                                              │
│ }                                                                       │
│                                                                         │
│ → 通知渠道: Webhook callback / 日志 / 告警系统                           │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 模式 2: 人机协作模式数据流

**触发条件**: CLI 手动触发 或 Webhook + `auto_agent_loop: false` (默认)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 入口 (CLI 或 Webhook)                                                    │
│ ────────────────────                                                    │
│ CLI: netsherlock diagnose --vm vm-123 --src-node 192.168.1.10          │
│  或                                                                     │
│ Webhook: auto_agent_loop=false (需人工确认)                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   DiagnosisController         │
                    │   mode = "interactive"        │
                    └───────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 1: 环境收集 + 问题归类 (自动执行)                                   │
│ ─────────────────────────────────────                                   │
│ • L1 监控数据查询                                                        │
│ • L2 环境信息收集                                                        │
│ • 问题分类和初筛                                                         │
│                                                                         │
│ 输出给用户:                                                              │
│ ┌─────────────────────────────────────────────────────────────────────┐│
│ │ 已收集环境信息，初步判断为 VM 网络延迟问题                            ││
│ │                                                                     ││
│ │ 检测到以下异常:                                                      ││
│ │   • vhost worker CPU 使用率 85%                                     ││
│ │   • OVS 端口 vnet0 tx_errors 近1小时增加 2340                       ││
│ │   • 目标节点 192.168.1.20 延迟 P95=12ms (正常<5ms)                  ││
│ │                                                                     ││
│ │ 问题分类: [VM网络延迟] (置信度: 90%)                                 ││
│ └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ╔═══════════════════════════════╗
                    ║   Checkpoint 1: 问题确认       ║
                    ║   ────────────────────        ║
                    ║   问题分类是否正确?            ║
                    ║   [确认] [修改] [补充信息]     ║
                    ╚═══════════════════════════════╝
                                    │
                        ┌───────────┴───────────┐
                        │                       │
                        ▼                       ▼
                   [用户确认]              [用户修改]
                        │                       │
                        │      ┌────────────────┘
                        │      │ 用户提供新的分类或补充信息
                        │      │ → 重新执行环境收集
                        │      │
                        ▼      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 2: 测量计划 (Agent 提出)                                           │
│ ───────────────────────────────                                         │
│ 根据问题分类，Agent 生成测量计划:                                        │
│                                                                         │
│ ┌─────────────────────────────────────────────────────────────────────┐│
│ │ 建议执行以下测量:                                                    ││
│ │                                                                     ││
│ │ 1. VM 延迟分段测量 (vm_network_latency_summary.py)                  ││
│ │    - 测量时长: 30秒                                                  ││
│ │    - 采样点: virtio_tx, vhost_handle, tap_rx, ovs_process, phy_tx  ││
│ │                                                                     ││
│ │ 2. vhost 调度延迟采样 (vhost_sched_latency.py)                      ││
│ │    - 测量时长: 30秒                                                  ││
│ │    - 目标 PID: 12345 (vhost-12345 worker)                           ││
│ │                                                                     ││
│ │ 预计影响: 测量期间可能增加少量 CPU 开销 (<5%)                        ││
│ └─────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ╔═══════════════════════════════╗
                    ║   Checkpoint 2: 测量确认       ║
                    ║   ────────────────────        ║
                    ║   是否执行测量?                ║
                    ║   [执行] [调整参数] [取消]     ║
                    ╚═══════════════════════════════╝
                                    │
                        ┌───────────┼───────────┐
                        │           │           │
                        ▼           ▼           ▼
                   [执行]      [调整参数]     [取消]
                        │           │           │
                        │           │           └→ DiagnosisResult(status="cancelled")
                        │           │
                        │           └→ 用户调整测量参数 → 返回 Phase 2
                        ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ Phase 3: 执行测量 + 分析 (自动执行)                                      │
│ ─────────────────────────────────                                       │
│ • L3 精确测量 (receiver-first)                                          │
│ • L4 分析报告生成                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 输出: DiagnosisResult                                                    │
│ ───────────────────                                                     │
│ {                                                                       │
│   "mode": "interactive",                                                │
│   "diagnosis_id": "diag-abc12345",                                     │
│   "summary": "VM 网络延迟异常，瓶颈在 vhost 处理阶段",                   │
│   "root_cause": {                                                       │
│     "category": "vhost_processing",                                    │
│     "component": "vhost worker thread",                                │
│     "confidence": 85,                                                   │
│     "evidence": ["vhost_handle P99=2.3ms (阈值 500μs)"]                │
│   },                                                                    │
│   "recommendations": [                                                  │
│     {"priority": 1, "action": "检查 vhost worker CPU 亲和性"},          │
│     {"priority": 2, "action": "检查 VM vCPU 调度延迟"}                  │
│   ]                                                                     │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ╔═══════════════════════════════╗
                    ║   Checkpoint 3 (可选): 继续?   ║
                    ║   ──────────────────────      ║
                    ║   是否需要进一步诊断?          ║
                    ║   [完成] [深入诊断]            ║
                    ╚═══════════════════════════════╝
```

### 4.3 模式切换逻辑

```python
def determine_mode(request: DiagnosisRequest, config: DiagnosisConfig) -> str:
    """确定诊断模式"""

    # 规则 1: CLI 手动触发 → 默认 interactive
    if request.source == "cli" and not request.force_autonomous:
        return "interactive"

    # 规则 2: Webhook 触发 + auto_agent_loop 开启 + 已知问题类型 → autonomous
    if request.source == "webhook":
        if config.auto_agent_loop and is_known_problem_type(request.alert):
            return "autonomous"

    # 规则 3: 其他情况 → interactive (默认)
    return "interactive"


def is_known_problem_type(alert: AlertData) -> bool:
    """判断是否为已知问题类型 (可自动处理)"""
    known_types = {
        "VMNetworkLatency",      # VM 网络延迟
        "HostNetworkLatency",    # 主机网络延迟
        # 后续扩展更多类型
    }
    return alert.labels.get("alertname") in known_types
```

---

## 五、目录结构

```
src/netsherlock/
├── __init__.py                 # 包入口
├── main.py                     # CLI 入口 (Click)
│
├── agents/                     # Agent SDK 架构
│   ├── __init__.py             # 导出 orchestrator, subagents
│   ├── base.py                 # Agent 层数据类型 (dataclass)
│   ├── orchestrator.py         # 主编排器
│   ├── subagents.py            # L2/L3/L4 子代理
│   └── prompts/                # 系统提示词
│       ├── __init__.py
│       ├── main_orchestrator.py
│       ├── l2_environment_awareness.py
│       ├── l3_precise_measurement.py
│       └── l4_diagnostic_analysis.py
│
├── tools/                      # MCP 工具实现
│   ├── __init__.py
│   ├── l1_monitoring.py        # grafana_*, loki_*, read_logs
│   ├── l2_environment.py       # collect_*, resolve_path
│   ├── l3_measurement.py       # measure_*, execute_coordinated
│   └── l4_analysis.py          # analyze_*, report_*
│
├── core/                       # 基础设施
│   ├── __init__.py
│   ├── grafana_client.py       # Grafana/Loki HTTP 客户端
│   ├── ssh_manager.py          # SSH 连接池
│   └── bpf_executor.py         # BPF 工具远程执行
│
├── schemas/                    # Pydantic 数据模型
│   ├── __init__.py
│   ├── alert.py                # AlertContext, DiagnosisRequest
│   ├── environment.py          # VMNetworkEnv, SystemNetworkEnv
│   ├── measurement.py          # MeasurementResult, LatencySegment
│   └── report.py               # DiagnosisResult, RootCause
│
├── config/                     # 配置
│   └── settings.py             # Pydantic Settings
│
└── api/                        # API 层 (P2)
    ├── __init__.py
    └── webhook.py              # FastAPI webhook
```

---

## 六、配置项

### 6.1 环境变量

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `NETSHERLOCK_GRAFANA_URL` | 是 | - | Grafana 地址 |
| `NETSHERLOCK_GRAFANA_USER` | 是 | - | Grafana 用户名 |
| `NETSHERLOCK_GRAFANA_PASSWORD` | 是 | - | Grafana 密码 |
| `NETSHERLOCK_SSH_USER` | 否 | root | SSH 用户名 |
| `NETSHERLOCK_SSH_KEY_PATH` | 否 | ~/.ssh/id_rsa | SSH 私钥路径 |
| `NETSHERLOCK_BPF_TOOLS_PATH` | 是 | - | BPF 工具目录路径 |
| `ANTHROPIC_API_KEY` | 是 | - | Claude API 密钥 |

### 6.2 模式控制配置 (重要)

| 变量 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `NETSHERLOCK_MODE` | 否 | interactive | 默认运行模式 (`autonomous`/`interactive`) |
| `NETSHERLOCK_AUTO_AGENT_LOOP` | 否 | false | 是否开启全自主 Agent 循环 |
| `NETSHERLOCK_KNOWN_ALERT_TYPES` | 否 | VMNetworkLatency | 允许自动处理的告警类型 (逗号分隔) |
| `NETSHERLOCK_INTERRUPT_ENABLED` | 否 | true | autonomous 模式下是否允许中断 |

**模式切换规则**:

```yaml
# 配置示例: config.yaml
diagnosis:
  # 默认模式
  default_mode: interactive  # "autonomous" | "interactive"

  # 全自主模式配置
  autonomous:
    enabled: true              # 是否允许自动模式
    auto_agent_loop: false     # 是否自动启动 agent loop (需手动开启)
    interrupt_enabled: true    # 是否允许中途中断
    known_alert_types:         # 允许自动处理的告警类型
      - VMNetworkLatency
      - HostNetworkLatency

  # 人机协作模式配置
  interactive:
    checkpoints:               # 需要用户确认的检查点
      - problem_classification # 问题分类确认
      - measurement_plan       # 测量计划确认
      - further_diagnosis      # 是否继续诊断 (可选)
    timeout_seconds: 300       # 等待用户输入超时时间
```

### 6.3 配置文件 (.env)

```env
# ===== 基础设施配置 =====
NETSHERLOCK_GRAFANA_URL=http://192.168.79.79/grafana
NETSHERLOCK_GRAFANA_USER=o11y
NETSHERLOCK_GRAFANA_PASSWORD=HC!r0cks
NETSHERLOCK_SSH_USER=root
NETSHERLOCK_SSH_KEY_PATH=/root/.ssh/id_rsa
NETSHERLOCK_BPF_TOOLS_PATH=/opt/troubleshooting-tools/measurement-tools
ANTHROPIC_API_KEY=sk-ant-xxxxx

# ===== 模式控制配置 =====
# 默认使用人机协作模式
NETSHERLOCK_MODE=interactive
# 是否开启全自主 agent loop (开启后 webhook 触发会自动完成全流程)
NETSHERLOCK_AUTO_AGENT_LOOP=false
# 允许自动处理的告警类型
NETSHERLOCK_KNOWN_ALERT_TYPES=VMNetworkLatency,HostNetworkLatency
# 允许在 autonomous 模式下中断
NETSHERLOCK_INTERRUPT_ENABLED=true
```

### 6.4 CLI 参数覆盖

```bash
# 默认使用 interactive 模式
netsherlock diagnose --vm vm-123 --src-node 192.168.1.10

# 强制使用 autonomous 模式 (覆盖配置)
netsherlock diagnose --vm vm-123 --src-node 192.168.1.10 --autonomous

# 强制使用 interactive 模式 (即使配置了 autonomous)
netsherlock diagnose --alert-file alert.json --interactive

# 设置超时时间
netsherlock diagnose --vm vm-123 --timeout 600
```

---

## 七、错误处理

### 7.1 错误分类

| 错误类型 | 处理策略 |
|----------|----------|
| SSH 连接失败 | 重试 3 次，失败后降级（跳过该节点） |
| BPF 工具执行失败 | 记录错误，返回部分结果 |
| Grafana 查询超时 | 重试，使用缓存数据 |
| Agent 解析错误 | 返回原始输出，标记 confidence=0 |

### 7.2 降级策略

- **L2 收集失败**: 使用告警 labels 中的最小信息
- **L3 测量失败**: 仅返回 L1 指标分析
- **L4 分析失败**: 返回原始测量数据

---

## 八、测试策略

### 8.1 单元测试

- tools/ 各工具的输入输出验证
- schemas/ 数据模型序列化测试
- core/ 基础设施 mock 测试

### 8.2 集成测试

- L1→L2→L3→L4 完整流程 (使用真实测试集群)
- receiver-first 时序验证
- 多种告警类型处理

### 8.3 端到端测试

- CLI 命令执行
- 模拟 Grafana 告警
- 诊断结果准确性验证

---

## 九、实现里程碑

| 阶段 | 内容 | 状态 |
|------|------|------|
| **Phase 0** | 基础设施 (core/, schemas/, config/) | ✅ 完成 |
| **Phase 1** | L1 工具 (grafana, loki, logs) | ✅ 完成 |
| **Phase 2** | L2 工具 (环境收集) | ✅ 完成 |
| **Phase 3** | L3 工具 (测量执行, receiver-first) | ✅ 完成 |
| **Phase 4** | L4 工具 (分析报告) | ✅ 完成 |
| **Phase 5** | Agent 架构 (orchestrator, subagents) | ✅ 完成 |
| **Phase 6** | 双模式控制 (DiagnosisController) | ✅ 完成 |
| **Phase 7** | API/Webhook (FastAPI, 认证, 验证) | ✅ 完成 |
| **Phase 8** | 单元测试 (184 tests) | ✅ 完成 |
| **Phase 9** | 集成测试 (78 tests) | ✅ 完成 |
| **Phase 10** | CLI 集成 (42 tests) | ✅ 完成 |
| **Phase 11** | 端到端测试 | ⏳ 待开始 |

### 测试统计

| 测试类别 | 数量 |
|----------|------|
| 单元测试 | 184 |
| 集成测试 | 120 |
| **总计** | **304** |

---

## 十、参考资料

- [框架选型计划](../framework-selection-plan.md)
- [调研计划](../research-plan.md)
- [Claude Agent SDK 文档](https://platform.claude.com/docs/en/agent-sdk/overview)
- [troubleshooting-tools 仓库](~/workspace/troubleshooting-tools)
