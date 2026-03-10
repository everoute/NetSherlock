# NetSherlock Implementation Guide

> 版本: 2.1
> 日期: 2026-01-26
> 状态: MVP 完成 (Skill-Driven Architecture)

NetSherlock is an AI-driven network troubleshooting agent built with Claude Agent SDK, integrating with internal Grafana monitoring data sources. The system uses a **Skill-driven architecture** where diagnostic phases are executed through Claude Code Skills.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Skill-Driven Diagnostic Architecture](#skill-driven-diagnostic-architecture)
3. [Core Components](#core-components)
4. [Configuration System](#configuration-system)
5. [Dual-Mode Control System](#dual-mode-control-system)
6. [API & Webhook Integration](#api--webhook-integration)
7. [Testing](#testing)

---

## Architecture Overview

### Skill-Driven Architecture

NetSherlock's core innovation is the **Skill-driven diagnostic architecture**. Instead of directly calling tool functions, the DiagnosisController orchestrates diagnosis through Claude Code Skills via SkillExecutor.

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
│  - MinimalInputConfig loading                                    │
│  - Phase orchestration (L1→L2→L3→L4)                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Skill Executor                              │
│                   (core/skill_executor.py)                        │
│  - Claude Code Skill invocation                                  │
│  - Parameter mapping from MinimalInputConfig                     │
│  - Result aggregation                                            │
└──────────────────────────────┬───────────────────────────────────┘
                               │
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
┌────────────────────┐ ┌────────────────────┐ ┌────────────────────┐
│ network-env-       │ │ vm-latency-        │ │ vm-latency-        │
│ collector          │ │ measurement        │ │ analysis           │
│ (L2 Skill)         │ │ (L3 Skill)         │ │ (L4 Skill)         │
│                    │ │                    │ │                    │
│ SSH环境收集         │ │ BPF工具部署/执行     │ │ 日志解析/归因分析    │
└────────────────────┘ └────────────────────┘ └────────────────────┘
           │                   │                   │
           ▼                   ▼                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Target Infrastructure                        │
│  - Host nodes (via SSH)                                          │
│  - VMs (via SSH)                                                 │
│  - OVS bridges, vhost processes, BPF tools                       │
└──────────────────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **Skill-based Execution**: L2/L3/L4 phases are implemented as Claude Code Skills, not direct tool calls
2. **MinimalInputConfig Required**: All diagnosis operations require SSH and test configuration
3. **Coordinated Measurement**: 8-point measurement executed via `vm-latency-measurement` Skill
4. **Dual Configuration Modes**: Manual (YAML file) or Auto (GlobalInventory-based)

### Directory Structure

```
src/netsherlock/
├── __init__.py                    # Package exports
├── main.py                        # CLI entry point (Click)
├── api/
│   ├── __init__.py
│   └── webhook.py                 # FastAPI webhook server
├── config/
│   ├── __init__.py
│   ├── settings.py                # Pydantic settings
│   └── global_inventory.py        # GlobalInventory (auto mode)
├── controller/
│   ├── __init__.py
│   ├── diagnosis_controller.py    # Core orchestrator
│   └── checkpoints.py             # Interactive mode checkpoints
├── core/
│   ├── __init__.py
│   ├── skill_executor.py          # ★ Skill invocation core
│   ├── ssh_manager.py             # SSH connection pool
│   ├── grafana_client.py          # Grafana API client
│   └── bpf_executor.py            # BPF tool remote execution
├── schemas/
│   ├── __init__.py
│   ├── alert.py                   # Alert/DiagnosisRequest models
│   ├── analysis.py                # LatencyBreakdown, AnalysisResult
│   ├── config.py                  # DiagnosisConfig, modes
│   ├── environment.py             # Network environment models
│   ├── measurement.py             # Measurement result models
│   ├── minimal_input.py           # ★ MinimalInputConfig
│   └── report.py                  # Diagnosis report models
├── agents/
│   ├── __init__.py
│   ├── base.py                    # Data types
│   ├── orchestrator.py            # Agent orchestrator (future)
│   └── prompts/                   # Agent prompts
└── tools/
    ├── __init__.py
    ├── l1_monitoring.py           # L1: Grafana/Loki queries
    ├── l2_environment.py          # L2: Environment collection helpers
    ├── l3_measurement.py          # L3: Measurement helpers
    └── l4_analysis.py             # L4: Analysis helpers

.claude/skills/                    # ★ Claude Code Skills (核心)
├── network-env-collector/         # L2 Skill: 网络环境收集
├── vm-latency-measurement/        # L3 Skill: 延迟测量
├── vm-latency-analysis/           # L4 Skill: 延迟分析
└── kernel-stack-analyzer/         # L4-Extended: 内核调用栈分析

config/                            # 配置模板
├── minimal-input-template.yaml    # 手动模式配置模板
└── global-inventory-template.yaml # 自动模式资产清单模板
```

---

## Skill-Driven Diagnostic Architecture

### Four-Layer Overview

| Layer | Component | Implementation | Purpose |
|-------|-----------|----------------|---------|
| **L1** | Base Monitoring | Direct tool calls | Grafana/Loki 查询、节点日志读取 |
| **L2** | Environment Awareness | `network-env-collector` Skill | SSH 环境收集 (OVS, vhost, NIC mapping) |
| **L3** | Precise Measurement | `vm-latency-measurement` Skill | BPF 工具部署、8 点协调测量 |
| **L4** | Diagnostic Analysis | `vm-latency-analysis` Skill | 日志解析、延迟归因、报告生成 |
| **L4-Ext** | Kernel Stack Analysis | `kernel-stack-analyzer` Skill | kfree_skb 堆栈追踪、丢包原因分析 |

### L1: Base Monitoring (Direct Tools)

L1 层通过直接工具调用获取监控数据，不使用 Skill。

**工具实现**: `tools/l1_monitoring.py`

```python
# Grafana PromQL 查询
result = grafana_query_metrics(
    query='host_network_ping_time_ns{hostname="node1"}',
    start="-1h",
    end="now",
    step="30s"
)

# Loki LogQL 查询
logs = loki_query_logs(
    query='{app="pingmesh"} |= "high_latency"',
    start="-30m",
    end="now",
    limit=100
)

# 节点本地日志读取 (via SSH)
local_logs = read_node_logs(
    host="192.168.1.10",
    log_type="pingmesh",
    lines=500
)
```

### L2: Environment Awareness (`network-env-collector` Skill)

L2 层通过 `network-env-collector` Skill 收集网络环境信息。

**Skill 定义**: `.claude/skills/network-env-collector.md`

**DiagnosisController 调用方式**:

```python
async def _collect_environment(self, request, l1_context) -> dict:
    """L2: 通过 Skill 收集环境信息"""
    executor = self._get_skill_executor()

    # 从 MinimalInputConfig 获取 SSH 连接信息
    src_vm_node = self._minimal_input.get_node("vm-sender")
    src_host_node = self._minimal_input.get_node("host-sender")
    dst_vm_node = self._minimal_input.get_node("vm-receiver")
    dst_host_node = self._minimal_input.get_node("host-receiver")

    # 收集发送端 VM 环境
    src_vm_result = await executor.invoke(
        skill_name="network-env-collector",
        parameters={
            "mode": "vm",
            "uuid": request.src_vm,
            "host_ip": src_host_node.ssh.host,
            "host_user": src_host_node.ssh.user,
            "vm_host": src_vm_node.ssh.host,
            "vm_user": src_vm_node.ssh.user,
        },
    )

    # 收集接收端 VM 环境
    dst_vm_result = await executor.invoke(
        skill_name="network-env-collector",
        parameters={
            "mode": "vm",
            "uuid": request.dst_vm,
            "host_ip": dst_host_node.ssh.host,
            "host_user": dst_host_node.ssh.user,
            "vm_host": dst_vm_node.ssh.host,
            "vm_user": dst_vm_node.ssh.user,
        },
    )

    return {
        "src_vm_env": src_vm_result.data,
        "dst_vm_env": dst_vm_result.data,
    }
```

**Skill 收集的信息**:
- OVS internal ports, bridges
- Physical NICs, bonds
- VM virtio NIC → vnet mapping
- qemu-kvm PID, vhost process PIDs
- OVS bridge topology

### L3: Precise Measurement (`vm-latency-measurement` Skill)

L3 层通过 `vm-latency-measurement` Skill 执行协调测量。

**Skill 定义**: `.claude/skills/vm-latency-measurement.md`

**关键特性**:
- **8 个测量点**: 发送端/接收端 VM 和 Host 各 4 个
- **BPF 工具部署**: 自动部署到目标节点

**DiagnosisController 调用方式**:

```python
async def _execute_measurement(self, request, l2_context) -> dict:
    """L3: 通过 Skill 执行测量"""
    executor = self._get_skill_executor()

    # 从 MinimalInputConfig 获取测试 IP
    src_vm_node = self._minimal_input.get_node("vm-sender")
    dst_vm_node = self._minimal_input.get_node("vm-receiver")

    result = await executor.invoke(
        skill_name="vm-latency-measurement",
        parameters={
            "sender_vm_ip": src_vm_node.test_ip,      # 测试流量 IP
            "sender_vm_ssh": src_vm_node.ssh.host,    # SSH 管理 IP
            "sender_host_ssh": self._minimal_input.get_node("host-sender").ssh.host,
            "receiver_vm_ip": dst_vm_node.test_ip,    # 测试流量 IP
            "receiver_vm_ssh": dst_vm_node.ssh.host,  # SSH 管理 IP
            "receiver_host_ssh": self._minimal_input.get_node("host-receiver").ssh.host,
            "duration": 30,
        },
    )

    return result.data
```

**重要**: `test_ip` 和 SSH IP 可能不同！
- `test_ip`: BPF 工具过滤数据包的 IP（测试流量网络）
- `ssh.host`: SSH 连接管理的 IP（管理网络）

### L4: Diagnostic Analysis (`vm-latency-analysis` Skill)

L4 层通过 `vm-latency-analysis` Skill 分析测量日志。

**Skill 定义**: `.claude/skills/vm-latency-analysis.md`

**DiagnosisController 调用方式**:

```python
async def _analyze_and_report(self, request, l3_context) -> DiagnosisReport:
    """L4: 通过 Skill 分析并生成报告"""
    executor = self._get_skill_executor()

    result = await executor.invoke(
        skill_name="vm-latency-analysis",
        parameters={
            "measurement_logs": l3_context["measurement_logs"],
            "environment": l3_context.get("environment", {}),
        },
    )

    return DiagnosisReport(
        latency_breakdown=result.data.get("latency_breakdown"),
        root_cause=result.data.get("root_cause"),
        recommendations=result.data.get("recommendations"),
    )
```

**分析输出**:
- 延迟分段数据 (LatencyBreakdown)
- 归因表格 (AttributionTable)
- 根因分析 (RootCause)
- 改进建议 (Recommendations)

### L4-Extended: Kernel Stack Analysis (`kernel-stack-analyzer` Skill)

L4 扩展层通过 `kernel-stack-analyzer` Skill 分析内核调用栈，用于丢包原因分析。

**Skill 定义**: `.claude/skills/kernel-stack-analyzer/SKILL.md`

**功能**:
- 分析 `kfree_skb` 追踪工具的输出
- 解析内核调用栈地址到源码行号（使用 GDB 或 addr2line）
- 区分真正的丢包和正常的数据包处理完成
- 分类调用栈：真正丢包 vs 正常完成

**使用场景**:
- 诊断 TCP/UDP 丢包问题
- 分析 OVS/虚拟化层的数据包丢弃
- 追踪网络栈中的异常路径

**调用示例**:

```python
result = await executor.invoke(
    skill_name="kernel-stack-analyzer",
    parameters={
        "stack_trace_file": "/path/to/kfree_skb_output.txt",
        "vmlinux_path": "/usr/lib/debug/boot/vmlinux-$(uname -r)",
        "kernel_src_path": "/usr/src/linux",
    },
)

# 输出包含:
# - classified_stacks: 分类后的调用栈列表
# - true_drops: 真正丢包的栈追踪
# - normal_completions: 正常处理完成的栈追踪
# - summary: 分析摘要
```

---

## Core Components

### SkillExecutor (`core/skill_executor.py`)

**核心组件**: 负责调用 Claude Code Skills。

```python
@dataclass
class SkillResult:
    """Skill 执行结果"""
    status: Literal["success", "error", "timeout"]
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    raw_outputs: list[Any] = field(default_factory=list)


class SkillExecutor:
    """Claude Code Skill 执行器"""

    def __init__(
        self,
        project_path: str | Path,
        allowed_tools: list[str] | None = None,
        default_timeout: float = 300.0,
    ):
        self.project_path = Path(project_path)
        self.allowed_tools = allowed_tools or ["Skill", "Read", "Write", "Bash"]
        self.default_timeout = default_timeout

    async def invoke(
        self,
        skill_name: str,
        parameters: dict[str, Any],
        timeout: float | None = None,
    ) -> SkillResult:
        """
        调用指定的 Claude Code Skill。

        Args:
            skill_name: Skill 名称 (如 "network-env-collector")
            parameters: 传递给 Skill 的参数
            timeout: 超时时间 (秒)

        Returns:
            SkillResult with status, data, and optional error
        """
        # Implementation details...
```

**使用示例**:

```python
from netsherlock.core.skill_executor import SkillExecutor

executor = SkillExecutor(
    project_path="/path/to/netsherlock",
    allowed_tools=["Skill", "Read", "Write", "Bash"],
    default_timeout=300.0
)

# 调用 L2 Skill
result = await executor.invoke(
    skill_name="network-env-collector",
    parameters={
        "mode": "vm",
        "uuid": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
        "host_ip": "192.168.75.101",
        "host_user": "smartx",
        "vm_host": "192.168.2.100",
        "vm_user": "root",
    }
)

if result.status == "success":
    vm_env = result.data
    print(f"OVS Bridge: {vm_env['ovs_bridge']}")
    print(f"vhost PIDs: {vm_env['vhost_pids']}")
```

### DiagnosisController (`controller/diagnosis_controller.py`)

**诊断流程编排器**: 管理配置加载和四层诊断流程。

```python
class DiagnosisController:
    """诊断流程控制器"""

    def __init__(
        self,
        config: DiagnosisConfig,
        minimal_input_path: str | None = None,      # 手动模式
        global_inventory_path: str | None = None,   # 自动模式
    ):
        self._config = config
        self._minimal_input_path = minimal_input_path
        self._global_inventory_path = global_inventory_path
        self._minimal_input: MinimalInputConfig | None = None

    def _load_minimal_input(self, request: DiagnosisRequest) -> MinimalInputConfig:
        """
        加载 MinimalInputConfig。

        优先级:
        1. minimal_input_path (手动模式 YAML 文件)
        2. global_inventory_path + request 参数 (自动模式)
        3. 从 request 创建简化配置 (回退，功能有限)
        """
        if self._minimal_input_path:
            return MinimalInputConfig.load(self._minimal_input_path)

        if self._global_inventory_path:
            inventory = GlobalInventory.load(self._global_inventory_path)
            return inventory.build_minimal_input(
                src_host_ip=request.src_host,
                src_vm_uuid=request.src_vm,
                dst_host_ip=request.dst_host,
                dst_vm_uuid=request.dst_vm,
            )

        # 回退: 从 request 创建简化配置
        return self._create_minimal_from_request(request)

    async def run(self, request: DiagnosisRequest) -> DiagnosisResult:
        """执行完整诊断流程"""
        # 1. 加载配置
        self._minimal_input = self._load_minimal_input(request)

        # 2. 根据模式执行
        if self._config.default_mode == DiagnosisMode.AUTONOMOUS:
            return await self._run_autonomous(request)
        else:
            return await self._run_interactive(request)

    async def _run_autonomous(self, request: DiagnosisRequest) -> DiagnosisResult:
        """自动模式: 无人工干预"""
        l1_context = await self._query_monitoring(request)
        l2_context = await self._collect_environment(request, l1_context)
        l3_context = await self._execute_measurement(request, l2_context)
        report = await self._analyze_and_report(request, l3_context)
        return DiagnosisResult.from_report(report)

    async def _run_interactive(self, request: DiagnosisRequest) -> DiagnosisResult:
        """交互模式: 检查点确认"""
        # 包含检查点逻辑...
```

### MinimalInputConfig (`schemas/minimal_input.py`)

**诊断配置**: 定义节点 SSH 信息、测试 IP、测试对。

```python
@dataclass
class SSHConfig:
    """SSH 连接配置"""
    host: str           # SSH 连接地址
    user: str = "root"
    port: int = 22
    key_file: str | None = None

@dataclass
class NodeConfig:
    """节点配置"""
    ssh: SSHConfig
    role: Literal["host", "vm"]
    workdir: str = "/tmp/netsherlock"
    # VM 特有字段
    host_ref: str | None = None   # 所属宿主机节点名
    uuid: str | None = None       # VM UUID
    test_ip: str | None = None    # 测试流量 IP (可能与 SSH IP 不同!)

@dataclass
class NodePair:
    """节点对配置"""
    server: str  # 接收端节点名
    client: str  # 发送端节点名

@dataclass
class MinimalInputConfig:
    """诊断最小输入配置"""
    nodes: dict[str, NodeConfig]
    test_pairs: dict[str, NodePair] | None = None
    discovery_hints: dict | None = None

    @classmethod
    def load(cls, path: str | Path) -> "MinimalInputConfig":
        """从 YAML 文件加载"""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    def get_node(self, name: str) -> NodeConfig:
        """获取指定节点配置"""
        return self.nodes[name]

    def get_sender_receiver_config(self, test_type: str = "vm"):
        """获取发送/接收端配置"""
        if not self.test_pairs or test_type not in self.test_pairs:
            return None
        pair = self.test_pairs[test_type]
        sender = self.nodes[pair.client]
        receiver = self.nodes[pair.server]
        sender_host = self.nodes.get(sender.host_ref) if sender.host_ref else None
        receiver_host = self.nodes.get(receiver.host_ref) if receiver.host_ref else None
        return sender, sender_host, receiver, receiver_host
```

### GlobalInventory (`config/global_inventory.py`)

**资产清单**: 自动模式下从告警参数构建 MinimalInputConfig。

```python
@dataclass
class HostConfig:
    """宿主机配置"""
    mgmt_ip: str
    ssh: SSHConfig
    network_types: list[str] | None = None

@dataclass
class VMConfig:
    """虚拟机配置"""
    uuid: str
    host_ref: str       # 所属宿主机名
    ssh: SSHConfig
    test_ip: str | None = None

@dataclass
class GlobalInventory:
    """全局资产清单"""
    hosts: dict[str, HostConfig]
    vms: dict[str, VMConfig]

    @classmethod
    def load(cls, path: str | Path) -> "GlobalInventory":
        """从 YAML 文件加载"""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls._from_dict(data)

    def find_host_by_ip(self, ip: str) -> tuple[str, HostConfig] | None:
        """根据管理 IP 查找宿主机"""
        for name, host in self.hosts.items():
            if host.mgmt_ip == ip:
                return name, host
        return None

    def find_vm_by_uuid(self, uuid: str) -> tuple[str, VMConfig] | None:
        """根据 UUID 查找 VM"""
        for name, vm in self.vms.items():
            if vm.uuid == uuid:
                return name, vm
        return None

    def build_minimal_input(
        self,
        src_host_ip: str,
        src_vm_uuid: str,
        dst_host_ip: str | None = None,
        dst_vm_uuid: str | None = None,
    ) -> MinimalInputConfig:
        """
        从资产清单构建 MinimalInputConfig。

        根据告警参数 (IP, UUID) 查找节点，构建诊断所需配置。
        """
        nodes = {}

        # 构建发送端配置
        src_host_name, src_host = self.find_host_by_ip(src_host_ip)
        nodes["host-sender"] = NodeConfig(
            ssh=src_host.ssh,
            role="host",
        )

        src_vm_name, src_vm = self.find_vm_by_uuid(src_vm_uuid)
        nodes["vm-sender"] = NodeConfig(
            ssh=src_vm.ssh,
            role="vm",
            host_ref="host-sender",
            uuid=src_vm.uuid,
            test_ip=src_vm.test_ip,
        )

        # 构建接收端配置 (如果提供)
        if dst_host_ip and dst_vm_uuid:
            dst_host_name, dst_host = self.find_host_by_ip(dst_host_ip)
            nodes["host-receiver"] = NodeConfig(
                ssh=dst_host.ssh,
                role="host",
            )

            dst_vm_name, dst_vm = self.find_vm_by_uuid(dst_vm_uuid)
            nodes["vm-receiver"] = NodeConfig(
                ssh=dst_vm.ssh,
                role="vm",
                host_ref="host-receiver",
                uuid=dst_vm.uuid,
                test_ip=dst_vm.test_ip,
            )

        return MinimalInputConfig(
            nodes=nodes,
            test_pairs={"vm": NodePair(server="vm-receiver", client="vm-sender")},
        )
```

### Other Core Components

#### SSH Manager (`core/ssh_manager.py`)

SSH 连接池管理。

```python
with SSHManager(settings.ssh) as ssh:
    result = ssh.execute("192.168.1.10", "cat /proc/version")
    if result.success:
        print(result.stdout)
```

#### Grafana Client (`core/grafana_client.py`)

Grafana datasource proxy API 客户端。

```python
with GrafanaClient(base_url, username, password) as client:
    metrics = client.query_metrics(promql, start, end, step)
    logs = client.query_logs(logql, start, end, limit)
```

#### BPF Executor (`core/bpf_executor.py`)

BPF 工具远程执行 (由 Skills 内部使用)。

```python
executor = BPFExecutor(ssh, host, remote_tools_path)
result = executor.execute(command, duration=30)
```

---

## Configuration System

### 配置模式对比

| 模式 | 配置文件 | CLI 参数 | 使用场景 |
|------|----------|----------|----------|
| **手动模式** | `minimal-input.yaml` | `--config` | 开发调试、单次诊断 |
| **自动模式** | `global-inventory.yaml` | `--inventory` | 告警触发、批量诊断 |

### 手动模式配置 (`minimal-input.yaml`)

```yaml
# config/minimal-input.yaml
nodes:
  host-sender:
    ssh: smartx@192.168.75.101     # SSH 连接 (管理网络)
    workdir: /tmp/netsherlock
    role: host

  vm-sender:
    ssh: root@192.168.2.100        # SSH 连接 (管理网络)
    workdir: /tmp/netsherlock
    role: vm
    host_ref: host-sender          # 所属宿主机
    uuid: ae6aa164-604c-4cb0-84b8-2dea034307f1
    test_ip: 10.0.0.1              # ★ 测试流量 IP (可能与 SSH IP 不同!)

  host-receiver:
    ssh: smartx@192.168.75.102
    workdir: /tmp/netsherlock
    role: host

  vm-receiver:
    ssh: root@192.168.2.200
    workdir: /tmp/netsherlock
    role: vm
    host_ref: host-receiver
    uuid: bf7bb275-715d-5dc1-95c9-3feb045418g2
    test_ip: 10.0.0.2              # ★ 测试流量 IP

test_pairs:
  vm:
    server: vm-receiver            # 接收端
    client: vm-sender              # 发送端
```

**重要**: `test_ip` vs SSH IP 区别

```
┌─────────────────────────────────────────────────────────────────┐
│                        VM 网络配置                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────┐         ┌─────────────┐                      │
│   │  管理网络    │         │  测试网络    │                      │
│   │ (SSH 访问)   │         │ (数据流量)   │                      │
│   └──────┬──────┘         └──────┬──────┘                      │
│          │                       │                              │
│          ▼                       ▼                              │
│   ssh.host: 192.168.2.100       test_ip: 10.0.0.1              │
│   (SSH 连接)                    (BPF 过滤)                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

- **ssh.host**: SSH 连接管理 VM 的 IP，通常是管理网络
- **test_ip**: BPF 工具过滤数据包的 IP，必须是实际测试流量的 IP

### 自动模式配置 (`global-inventory.yaml`)

```yaml
# config/global-inventory.yaml
hosts:
  node1:
    mgmt_ip: 192.168.75.101
    ssh:
      user: smartx
      key_file: ~/.ssh/id_rsa
    network_types: ["storage", "management"]

  node2:
    mgmt_ip: 192.168.75.102
    ssh:
      user: smartx
      key_file: ~/.ssh/id_rsa
    network_types: ["storage", "management"]

vms:
  test-vm-1:
    uuid: ae6aa164-604c-4cb0-84b8-2dea034307f1
    host_ref: node1
    ssh:
      user: root
      host: 192.168.2.100
    test_ip: 10.0.0.1

  test-vm-2:
    uuid: bf7bb275-715d-5dc1-95c9-3feb045418g2
    host_ref: node2
    ssh:
      user: root
      host: 192.168.2.200
    test_ip: 10.0.0.2
```

### 环境变量配置 (`config/settings.py`)

```bash
# SSH 配置
SSH_DEFAULT_USER=root
SSH_DEFAULT_PORT=22
SSH_PRIVATE_KEY_PATH=/path/to/key
SSH_CONNECT_TIMEOUT=10
SSH_COMMAND_TIMEOUT=60

# Grafana 配置
GRAFANA_BASE_URL=http://192.168.79.79/grafana
GRAFANA_USERNAME=o11y
GRAFANA_PASSWORD=secret

# BPF 工具配置
BPF_LOCAL_TOOLS_PATH=/path/to/tools
BPF_REMOTE_TOOLS_PATH=/tmp/netsherlock-tools
BPF_DEPLOY_MODE=auto

# 诊断模式配置
DIAGNOSIS_DEFAULT_MODE=interactive
DIAGNOSIS_AUTONOMOUS_ENABLED=true
```

---

## Dual-Mode Control System

### 模式概述

| 模式 | 配置来源 | 人工干预 | 典型使用场景 |
|------|----------|----------|--------------|
| **Interactive** | `--config` | 检查点确认 | CLI 手动诊断、调试 |
| **Autonomous** | `--inventory` | 无 | Webhook 告警触发 |

### Interactive Mode (交互模式)

通过 CLI 手动触发，在关键检查点暂停等待确认。

```bash
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency \
  --interactive
```

**检查点类型**:
- `PROBLEM_CLASSIFICATION`: L2 完成后，确认问题分类
- `MEASUREMENT_PLAN`: 测量计划确认
- `FURTHER_DIAGNOSIS`: L4 后决定是否继续

### Autonomous Mode (自动模式)

通过 Webhook 告警触发，自动执行完整流程。

```bash
# 自动模式需要 --inventory 提供资产清单
netsherlock diagnose \
  --inventory config/global-inventory.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency \
  --autonomous
```

### CLI Mode Selection

```python
def _determine_diagnosis_mode(
    mode: str | None,
    mode_autonomous: bool,
    mode_interactive: bool,
) -> DiagnosisMode:
    """
    优先级:
    1. --mode 选项 (显式指定)
    2. --autonomous 标志
    3. --interactive 标志
    4. 默认: interactive (CLI 最安全)
    """
```

### Exit Codes

| Code | Status | Description |
|------|--------|-------------|
| 0 | COMPLETED | 诊断成功完成 |
| 1 | ERROR | 诊断失败 |
| 2 | CANCELLED | 用户取消 |
| 3 | INTERRUPTED | 诊断被中断 |
| 130 | KeyboardInterrupt | Ctrl+C |

---

## API & Webhook Integration

### Webhook Server (`api/webhook.py`)

**Endpoints**:

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| POST | `/webhook/alertmanager` | API Key | 接收 Alertmanager 告警 |
| POST | `/diagnose` | API Key | 手动诊断请求 |
| GET | `/diagnose/{id}` | API Key | 获取诊断状态/结果 |
| GET | `/diagnoses` | API Key | 列出最近诊断 |

### DiagnosticRequest

```python
class DiagnosticRequest(BaseModel):
    network_type: Literal["vm", "system"]
    diagnosis_type: Literal["latency", "packet_drop", "connectivity"] = "latency"
    src_host: str      # IP 地址
    src_vm: str | None = None
    dst_host: str | None = None
    dst_vm: str | None = None
```

### Example Requests

```bash
# Start webhook server
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080

# Manual diagnosis
curl -X POST http://localhost:8080/diagnose \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "vm",
    "diagnosis_type": "latency",
    "src_host": "192.168.75.101",
    "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    "dst_host": "192.168.75.102",
    "dst_vm": "bf7bb275-715d-5dc1-95c9-3feb045418g2"
  }'
```

---

## Testing

### Test Structure

```
tests/
├── unit/
│   ├── test_skill_executor.py     # SkillExecutor 测试
│   ├── test_minimal_input.py      # MinimalInputConfig 测试
│   ├── test_global_inventory.py   # GlobalInventory 测试
│   ├── test_controller.py         # DiagnosisController 测试
│   ├── test_cli.py                # CLI 测试
│   ├── test_webhook.py            # Webhook 测试
│   └── ...
└── integration/
    ├── test_diagnosis_flow.py     # 完整诊断流程测试
    ├── test_skill_integration.py  # Skill 集成测试
    └── ...
```

### Running Tests

```bash
# All tests
pytest

# Specific module
pytest tests/unit/test_skill_executor.py

# With coverage
pytest --cov=netsherlock --cov-report=html

# Integration tests only
pytest tests/integration/
```

### Test Coverage

| Component | Tests | Coverage |
|-----------|-------|----------|
| SkillExecutor | 24 | Skill invocation, timeout, error handling |
| MinimalInputConfig | 18 | Loading, validation, node lookup |
| GlobalInventory | 16 | Loading, build_minimal_input |
| DiagnosisController | 26 | Mode selection, phase orchestration |
| CLI | 24 | Commands, arguments |
| Webhook | 41 | Authentication, validation |
| Integration | 120 | Full flow, L1→L4 |
| **Total** | **316** | |

---

## Version History

- **v2.0** - Skill-Driven Architecture Documentation (Complete Rewrite)
  - Rewrote documentation to reflect Skill-driven architecture
  - Documented SkillExecutor as core component
  - Documented three Skills (network-env-collector, vm-latency-measurement, vm-latency-analysis)
  - Documented MinimalInputConfig and GlobalInventory
  - Updated architecture diagrams
  - Removed incorrect direct tool call descriptions

- **v0.4.0** - Architecture Evolution (Phase 11)
  - Added SkillExecutor pattern
  - Added MinimalInputConfig
  - Added GlobalInventory
  - New schemas: analysis.py

- **v0.3.0** - CLI Parameter Refactoring (Phase 10.1)
  - Refactored CLI parameters with explicit src/dst semantics

- **v0.2.0** - CLI-Controller Integration (Phase 10)
  - Full CLI integration with DiagnosisController

- **v0.1.0** - Initial implementation
  - Four-layer diagnostic architecture
  - Dual-mode control
  - FastAPI webhook server
