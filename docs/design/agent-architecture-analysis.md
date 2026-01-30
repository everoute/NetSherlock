# Agent 架构分析：双路径诊断与 Webhook 桥接方案

> 文档目的：梳理当前 NetSherlock 的 Agent 整体架构，分析手动诊断（已跑通）与 Webhook 自动诊断之间的差距，给出桥接方案建议。

## 1. 整体架构概览

当前代码中存在 **两套独立的诊断执行路径**，各自完整但互不相通：

```
┌───────────────────────────────────────────────────────────────────────┐
│                            入口层                                      │
├────────────────────────┬──────────────────────────────────────────────┤
│   CLI (main.py)        │   Webhook (api/webhook.py)                   │
│   netsherlock diagnose │   POST /webhook/alertmanager                 │
│                        │   POST /diagnose                             │
└──────────┬─────────────┴───────────────────┬─────────────────────────┘
           │                                 │
           ▼                                 ▼
┌────────────────────────┐   ┌──────────────────────────────────────────┐
│  路径 A (已跑通 ✅)      │   │  路径 B (半成品 ❌)                       │
│                        │   │                                          │
│  DiagnosisController   │   │  NetworkTroubleshootingOrchestrator      │
│  controller/           │   │  agents/orchestrator.py                  │
│                        │   │                                          │
│  确定性编排 + AI 执行    │   │  LLM 自主编排 + AI 执行                   │
│  Python 硬编码流程       │   │  Agent prompt 驱动流程                    │
│  L1 → L2 → L3 → L4    │   │  LLM 自行决定调用顺序                      │
└────────────────────────┘   └──────────────────────────────────────────┘
```

## 2. 路径 A：DiagnosisController（确定性编排, 类似 langraph）

**设计理念**：Python 代码控制流程顺序，AI 只负责执行每个 Skill 内部的具体操作。

### 2.1 调用链

```
CLI: netsherlock diagnose --config config.yaml --src-host ... --src-vm ...
  │
  ▼
DiagnosisController.run(request, source=CLI, force_mode=interactive)
  │
  ├── _load_minimal_input()           ← 从 YAML 加载 SSH/IP/UUID 配置
  │
  ├── _run_autonomous(request)        ← 或 _run_interactive(request)
  │     │
  │     ├── Phase L1: _query_monitoring()
  │     │     └── 直接调 Grafana/Loki API
  │     │
  │     ├── Phase L2: _collect_environment()
  │     │     └── SkillExecutor.invoke("network-env-collector", params)
  │     │           └── claude-agent-sdk query() → Claude Code Skill 子进程
  │     │
  │     ├── Phase L3: _execute_measurement()
  │     │     └── SkillExecutor.invoke("vm-latency-measurement", params)
  │     │           └── claude-agent-sdk query() → Claude Code Skill 子进程
  │     │
  │     └── Phase L4: _analyze_and_report()
  │           └── SkillExecutor.invoke("vm-latency-analysis", params)
  │                 └── claude-agent-sdk query() → Claude Code Skill 子进程
  │
  └── DiagnosisResult.from_state(state)
```

### 2.2 关键特征

| 维度               | 说明                                                          |
| ------------------ | ------------------------------------------------------------- |
| **编排逻辑** | Python 硬编码 L1→L2→L3→L4 顺序，不依赖 LLM 决策            |
| **AI 角色**  | 每个 Skill 内部由 Claude 执行具体操作（SSH 命令、解析输出等） |
| **配置来源** | `MinimalInputConfig` YAML 文件，通过 CLI `--config` 传入  |
| **模式支持** | autonomous（全自动）、interactive（checkpoint 人工确认）      |
| **状态**     | ✅ 已跑通，端到端验证通过                                     |

### 2.3 核心组件

- **`DiagnosisController`** (`controller/diagnosis_controller.py`)：流程编排器
- **`SkillExecutor`** (`core/skill_executor.py`)：调用 Claude Code Skill 的执行器
- **`MinimalInputConfig`** (`schemas/config.py`)：节点 SSH/IP/UUID 配置
- **`CheckpointManager`**：interactive 模式的人工确认点

## 3. 路径 B：NetworkTroubleshootingOrchestrator（AI 自主编排）

**设计理念**：主 Agent 根据 prompt 自行决定调用哪些 Tool/Subagent 以及调用顺序。

### 3.1 调用链

```
Webhook: POST /webhook/alertmanager
  │
  ▼
diagnosis_queue.put(("alert", id, alert_data))
  │
  ▼
diagnosis_worker()
  │
  ▼
orchestrator.diagnose_alert(alert_data)
  │
  ├── _parse_alert()                  ← 提取 labels 为 AlertContext
  │
  ├── Agent(system=system_prompt, tools=l1_tools)
  │     └── query(agent, prompt)      ← LLM 自行决定流程
  │           │
  │           ├── L1 tools（直接调用 grafana_query 等）
  │           ├── L2 subagent: L2EnvironmentSubagent.invoke()
  │           │     └── Agent() + query()  ← 又启动一个 Claude Agent
  │           ├── L3 subagent: L3MeasurementSubagent.invoke()
  │           │     └── Agent() + query()
  │           └── L4 subagent: L4AnalysisSubagent.invoke()
  │                 └── Agent() + query()
  │
  └── _synthesize_diagnosis()         ← ⚠️ PLACEHOLDER，返回硬编码文本
```

### 3.2 关键特征

| 维度               | 说明                                                          |
| ------------------ | ------------------------------------------------------------- |
| **编排逻辑** | LLM 根据 prompt 自行决定调用顺序和是否跳过某些层              |
| **AI 角色**  | 主 Agent 做编排决策 + 子 Agent 做具体操作                     |
| **配置来源** | 只有 alert labels，**没有** MinimalInputConfig 加载逻辑 |
| **模式支持** | 仅 autonomous                                                 |
| **状态**     | ❌ 半成品，`_synthesize_diagnosis()` 是 placeholder         |

### 3.3 核心组件

- **`NetworkTroubleshootingOrchestrator`** (`agents/orchestrator.py`)：主 Agent
- **`L2EnvironmentSubagent`** (`agents/subagents.py`)：环境采集子 Agent
- **`L3MeasurementSubagent`** (`agents/subagents.py`)：测量执行子 Agent
- **`L4AnalysisSubagent`** (`agents/subagents.py`)：分析诊断子 Agent
- **`ToolExecutor`** (`agents/tool_executor.py`)：L1 工具执行器

### 3.4 未完成项

1. `_synthesize_diagnosis()` 返回硬编码 `"Diagnosis synthesis to be implemented"`
2. 子 Agent 没有 SSH 凭据和 test_ip 信息（无 MinimalInputConfig）
3. Alert labels → 节点配置的映射逻辑缺失
4. 主 Agent 的 tool binding 只有 L1 工具，子 Agent 调用机制未验证

## 4. 架构范式定位：从确定性编排到自主 Agent

当前两条路径分别对应了 AI Agent 领域中两种主流架构范式。理解这一对应关系有助于明确各自的定位和演进方向。

### 4.1 三种架构范式

```
确定性编排（Orchestration）          自主 Agent（ReAct Loop）
代码控制流程                         LLM 控制流程

┌──────────────┐                   ┌──────────────┐
│   代码定义    │                   │   LLM 决定    │
│   节点 + 边   │                   │   下一步行动   │
│              │                   │              │
│  Node A      │                   │  Thought     │
│    ↓         │                   │    ↓         │
│  Node B      │                   │  Action      │
│    ↓         │                   │    ↓         │
│  Node C      │                   │  Observation  │
│    ↓         │                   │    ↓         │
│  Node D      │                   │  Thought...   │──→ 循环直到完成
└──────────────┘                   └──────────────┘

LangGraph 风格                      ReAct / AutoGPT 风格
路径 A: DiagnosisController          路径 B: Orchestrator
```

### 4.2 路径 A = LangGraph 风格（确定性编排 + AI 节点）

DiagnosisController 的执行模式与 LangGraph 的核心思路一致：**图的节点和边由代码定义，节点内部可以调用 LLM。LLM 不决定"下一步去哪"，代码决定。**

```python
# 等价的 LangGraph 伪代码
graph = StateGraph(DiagnosisState)

graph.add_node("l1_monitoring",    query_monitoring)
graph.add_node("l2_environment",   collect_environment)    # 内部调 LLM Skill
graph.add_node("l3_measurement",   execute_measurement)    # 内部调 LLM Skill
graph.add_node("l4_analysis",      analyze_and_report)     # 内部调 LLM Skill

graph.add_edge("l1_monitoring",  "l2_environment")
graph.add_edge("l2_environment", "l3_measurement")
graph.add_edge("l3_measurement", "l4_analysis")
graph.add_edge("l4_analysis",    END)

# 条件边：interactive 模式在某些节点后插入人工确认
graph.add_conditional_edges("l2_environment", check_interactive, {
    "checkpoint": "human_review",
    "continue":   "l3_measurement",
})
```

实际实现没有引入 LangGraph 框架，而是用原生 Python async 方法调用达到了同样的效果。这也是 CLAUDE.md 中 framework decision 推荐 "Pure Claude Agent SDK" 的原因 — 当前的图结构足够简单（线性 L1→L2→L3→L4），不需要 LangGraph 的图抽象开销。

**与 LangGraph 的具体对应关系**：

| LangGraph 概念 | 当前实现对应 |
|----------------|-------------|
| `StateGraph` + `add_edge()` | Python async 方法顺序调用 |
| Graph Node（节点） | `_query_monitoring()`, `_collect_environment()`, `_execute_measurement()`, `_analyze_and_report()` |
| Node 内部调用 LLM | `SkillExecutor.invoke()` → Claude Agent SDK `query()` |
| `TypedDict` state | `DiagnosisState` 对象，字段在各阶段逐步填充 |
| `add_conditional_edges()` | `if mode == INTERACTIVE` / `if mode == AUTONOMOUS` 分支 |
| `interrupt()` + `Command(resume=...)` | `CheckpointManager` + `checkpoint_callback` |
| Checkpointer（状态持久化） | `DiagnosisState.to_dict()`（当前仅内存） |

### 4.3 路径 B = ReAct Loop 风格（LLM 自主编排）

Orchestrator 的执行模式是经典的 **ReAct（Reason + Act）循环**：

```
主 Agent 收到 prompt
  │
  ▼
┌─────────────────────────────────────────┐
│  Thought: 需要先了解网络环境            │
│  Action:  调用 L2EnvironmentSubagent    │ ←─┐
│  Observation: 收到环境数据              │   │
│                                         │   │ LLM 自行循环
│  Thought: 环境已知，需要执行测量         │   │ 直到认为完成
│  Action:  调用 L3MeasurementSubagent    │   │
│  Observation: 收到测量结果              │   │
│                                         │   │
│  Thought: 有了数据，需要分析            │   │
│  Action:  调用 L4AnalysisSubagent       │ ──┘
│  Observation: 收到诊断结果              │
│                                         │
│  Thought: 诊断完成，返回结果            │
│  Final Answer: ...                      │
└─────────────────────────────────────────┘
```

关键区别：
- **编排决策在 LLM 内部**：流程顺序不是代码写死的，而是 LLM 根据 Observation 决定下一个 Action
- **可能跳步或回退**：LLM 可能判断某些步骤不需要，或发现需要额外信息而回到之前的步骤
- **不可预测性**：同样的输入，不同次运行可能走不同的路径
- **更高的灵活性**：适合诊断逻辑复杂、需要动态判断的场景

### 4.4 两条路径的完整对比

| 维度 | 路径 A: DiagnosisController | 路径 B: Orchestrator |
|------|---------------------------|---------------------|
| **架构范式** | LangGraph 风格（确定性编排） | ReAct Loop 风格（LLM 自主编排） |
| **编排方式** | Python 硬编码 L1→L2→L3→L4 | LLM prompt 驱动，自行决定顺序 |
| **流程可预测性** | 高（固定顺序，每次一致） | 低（LLM 可能跳步、重复或回退） |
| **AI 调用次数** | 每层 1 次 Skill（共 3-4 次） | 主 Agent + 每层 1 个子 Agent（至少 5 次） |
| **编排成本** | 零 LLM 开销（纯代码控制流） | 主 Agent 的 Thought/Action 循环消耗 token |
| **灵活性** | 低（新诊断类型需改代码） | 高（改 prompt 即可调整策略） |
| **可调试性** | 高（断点、日志、阶段状态清晰） | 低（LLM 内部推理不透明） |
| **配置加载** | MinimalInputConfig YAML | ❌ 缺失 |
| **结果合成** | `DiagnosisResult.from_state()` | ❌ placeholder |
| **interactive 模式** | ✅ CheckpointManager | ❌ 不支持 |
| **测试覆盖** | ✅ 316 tests | 部分 |
| **当前状态** | ✅ 已验证 | ❌ 半成品 |
| **适用场景** | MVP，固定流程诊断 | 未来多诊断类型、动态策略选择 |

### 4.5 为什么 MVP 选择确定性编排

网络诊断场景有几个特点决定了确定性编排更适合 MVP：

1. **流程确定性要求高**：L3 测量涉及在远程节点部署 BPF 工具、协调多点采集，顺序错误会导致无效数据。LLM 跳步或乱序的风险不可接受。
2. **成本敏感**：每次诊断如果走 ReAct 循环，主 Agent 的 Thought/Action 开销可能超过实际 Skill 执行的 token 消耗。
3. **可调试性**：生产环境中诊断失败时，确定性流程可以精确定位到哪个阶段出错，ReAct 循环的调试困难得多。
4. **当前诊断类型单一**：只有 latency 一种类型，线性流程足以覆盖。

## 5. Webhook 自动诊断：双引擎架构

### 5.1 问题：当前 Webhook 硬绑定了路径 B

```
webhook 请求 → diagnosis_queue → diagnosis_worker()
                                       │
                                       └→ orchestrator.diagnose_alert()  ← 只能走路径 B（半成品）
```

如果只是把 Webhook 从 Orchestrator 切换到 DiagnosisController，那后续要上 Orchestrator 时又得改 Webhook 层。两套引擎和 Webhook 之间没有统一抽象，导致每次切换都是硬改。

### 5.2 设计目标：Webhook 兼容两种引擎

Webhook 层不应该知道具体用哪种引擎，而是通过一个统一接口来调度。MVP 使用确定性编排，后续切换到 Agent 编排时 Webhook 层零修改。

### 5.3 统一诊断引擎接口

```python
# core/engine.py

class DiagnosisEngine(Protocol):
    """统一诊断引擎接口 — Webhook 只依赖这个协议。"""

    async def execute(
        self,
        request: DiagnosisRequest,
        source: DiagnosisRequestSource,
        mode: DiagnosisMode,
    ) -> DiagnosisResult:
        ...
```

两种引擎各自实现：

```python
class ControllerEngine(DiagnosisEngine):
    """确定性编排引擎（LangGraph 风格）— 包装 DiagnosisController"""

    def __init__(self, config, inventory_path, ...):
        self._config = config
        self._inventory_path = inventory_path

    async def execute(self, request, source, mode) -> DiagnosisResult:
        controller = DiagnosisController(
            config=self._config,
            global_inventory_path=self._inventory_path,
            ...
        )
        return await controller.run(request=request, source=source, force_mode=mode)


class OrchestratorEngine(DiagnosisEngine):
    """Agent 自主编排引擎（ReAct 风格）— 包装 Orchestrator"""

    def __init__(self, settings):
        self._orchestrator = NetworkTroubleshootingOrchestrator(settings=settings)

    async def execute(self, request, source, mode) -> DiagnosisResult:
        alert_data = request.to_alert_payload()
        return await self._orchestrator.diagnose_alert(alert_data)
```

### 5.4 Webhook Worker 通过接口调度

```python
# api/webhook.py

engine: DiagnosisEngine  # 启动时注入，Webhook 不关心具体实现

async def diagnosis_worker():
    while True:
        request_type, request_id, request_data = await diagnosis_queue.get()
        request = build_request_from_alert(request_data)
        mode = determine_webhook_mode(request_data.get("alert_type"))

        # 统一调用，不区分引擎类型
        result = await engine.execute(
            request=request,
            source=DiagnosisRequestSource.WEBHOOK,
            mode=mode,
        )
        diagnosis_store[request_id] = result
```

### 5.5 启动时选择引擎

```python
# main.py serve 命令
@cli.command()
@click.option("--engine", type=click.Choice(["controller", "orchestrator"]),
              default="controller", help="Diagnosis engine type")
@click.option("--inventory", type=click.Path(exists=True), required=True)
def serve(engine, inventory, ...):
    if engine == "controller":
        app.state.engine = ControllerEngine(config=..., inventory_path=inventory)
    else:
        app.state.engine = OrchestratorEngine(settings=get_settings())

    uvicorn.run(app, ...)
```

也可以通过环境变量 / 配置文件选择：

```bash
# .env
DIAGNOSIS_ENGINE=controller   # MVP
# DIAGNOSIS_ENGINE=orchestrator  # 未来
```

### 5.6 架构全景

```
                          ┌─────────────────────┐
                          │     入口层           │
                          │  CLI / Webhook API   │
                          └──────────┬──────────┘
                                     │
                                     ▼
                          ┌─────────────────────┐
                          │  DiagnosisEngine     │
                          │  (Protocol 接口)     │
                          └──┬───────────────┬──┘
                             │               │
               ┌─────────────▼──┐     ┌──────▼─────────────┐
               │ ControllerEngine│     │ OrchestratorEngine │
               │ (确定性编排)    │     │ (Agent 自主编排)    │
               └───────┬────────┘     └────────┬───────────┘
                       │                       │
                       ▼                       ▼
              DiagnosisController    NetworkTroubleshootingOrchestrator
                       │                       │
                       ▼                       ▼
                 SkillExecutor          L2/L3/L4 Subagents
                       │                       │
                       ▼                       ▼
                Claude Code Skills      Claude Agent SDK
```

### 5.7 两个引擎共享的基础设施

无论哪种引擎，以下组件都需要共享：

| 组件 | 说明 | 当前状态 |
|------|------|----------|
| `DiagnosisRequest` | 统一请求模型 | ⚠️ controller 和 agents 各定义了一套，需统一 |
| `DiagnosisResult` | 统一结果模型 | ⚠️ `controller/` 和 `agents/base.py` 各有一个，需统一 |
| `GlobalInventory` | 资产清单加载 | ✅ 已有，需要 Orchestrator 也能使用 |
| Alert → Request 映射 | alert labels 转换为请求 | ❌ 待实现 |
| 结果存储 | 诊断结果持久化 | ⚠️ 当前仅内存 dict |

**数据模型统一是第一步** — 两个引擎的输入输出必须一致，Webhook 才能真正做到引擎无关。

## 6. 实施清单

### Phase 0：统一数据模型（前置）

| 编号 | 任务 | 说明 |
|------|------|------|
| P0-1 | 统一 `DiagnosisRequest` | `controller/` 和 `agents/base.py` 各有一套，合并到 `schemas/` |
| P0-2 | 统一 `DiagnosisResult` | 同上，确保两个引擎输出同一类型 |
| P0-3 | 定义 `DiagnosisEngine` Protocol | `core/engine.py`，两个引擎的统一接口 |

### Phase 1：ControllerEngine + Webhook（MVP）

| 编号 | 任务 | 说明 |
|------|------|------|
| P1-1 | 实现 `ControllerEngine` | 包装 `DiagnosisController`，实现 `DiagnosisEngine` 接口 |
| P1-2 | 添加 `serve` CLI 命令 | 启动 FastAPI，`--engine` 选择引擎类型 |
| P1-3 | Webhook Worker 改用 `engine.execute()` | 替换直接调用 `orchestrator.diagnose_alert()` |
| P1-4 | Alert → DiagnosisRequest 映射 | 从 alert labels 构建统一请求 |
| P1-5 | GlobalInventory → MinimalInputConfig | 补完自动构建逻辑 |
| P1-6 | 编写 inventory.yaml | 目标环境的真实资产清单 |
| P1-7 | Alertmanager 规则 + receiver | 告警规则 + webhook 指向 NetSherlock |
| P1-8 | 端到端集成测试 | Mock alert → webhook → controller → result |

### Phase 2：OrchestratorEngine（未来）

| 编号 | 任务 | 说明 |
|------|------|------|
| P2-1 | 实现 `OrchestratorEngine` | 包装 `Orchestrator`，实现 `DiagnosisEngine` 接口 |
| P2-2 | 完善 `_synthesize_diagnosis()` | 解析 Agent 输出为统一 `DiagnosisResult` |
| P2-3 | Orchestrator 接入 GlobalInventory | 子 Agent 能获取 SSH 凭据和 test_ip |
| P2-4 | 子 Agent tool 绑定完善 | L2/L3/L4 子 Agent 的 tool 定义和权限 |
| P2-5 | 主 Agent prompt 工程 | 优化编排 prompt |
| P2-6 | 引擎切换测试 | 同一 alert 分别走两个引擎，对比结果 |

### 6.1 Alert Labels → DiagnosisRequest

Alertmanager 告警需包含以下 labels：

```yaml
labels:
  alertname: VMNetworkLatency        # 告警类型 → request_type 映射
  src_host: "192.168.75.101"         # 源宿主机管理 IP
  src_vm: "ae6aa164-..."             # 源 VM UUID
  dst_host: "192.168.75.102"         # 目标宿主机管理 IP（可选）
  dst_vm: "bf7bb275-..."             # 目标 VM UUID（可选）
  network_type: "vm"                 # vm 或 system
```

### 6.2 GlobalInventory 自动构建 MinimalInputConfig

`DiagnosisController._load_minimal_input()` 已有从 inventory 加载的分支逻辑，需验证并补完：

```
GlobalInventory (inventory.yaml)
  │
  ├── hosts:
  │     node1: { mgmt_ip, ssh: {user, key_file} }
  │     node2: { ... }
  │
  └── vms:
        test-vm-1: { uuid, host_ref: node1, test_ip: 10.0.0.1 }
        test-vm-2: { uuid, host_ref: node2, test_ip: 10.0.0.2 }

                    ↓  alert labels: src_vm=uuid1, dst_vm=uuid2

MinimalInputConfig (自动生成)
  ├── nodes:
  │     vm-sender:   { ssh: root@vm_ip, test_ip, uuid, host_ref }
  │     vm-receiver: { ssh: root@vm_ip, test_ip, uuid, host_ref }
  │     host-sender: { ssh: root@host_ip }
  │     host-receiver:{ ssh: root@host_ip }
  └── test_pairs:
        vm: { server: vm-receiver, client: vm-sender }
```

## 7. Orchestrator 的长期价值：从固定图到 ReAct 编排

Orchestrator + Subagents 架构并非废弃设计，而是面向未来的进化方向。随着诊断类型增多，确定性编排的局限性会逐步显现，届时引入 ReAct 风格的自主编排将变得合理。

### 7.1 演进路线

```
Phase 1 (MVP):       确定性编排（LangGraph 风格）
                      所有告警 → 固定流程 L1→L2→L3→L4
                      DiagnosisController 足以胜任

Phase 2 (多类型):     条件编排（LangGraph + conditional edges）
                      代码根据告警类型选择不同子图
                      latency      → L1→L2→L3(BPF)→L4
                      drop         → L1→L2→L3(kfree_skb)→L4
                      connectivity → L1→L2→直接分析

Phase 3 (智能编排):   ReAct 编排（Orchestrator 风格）
                      LLM 根据 L1 数据动态决定后续步骤
                      Orchestrator 主 Agent 自行选择子 Agent
                      支持循环诊断（L4 发现需要更多数据 → 回到 L3）
```

### 7.2 Phase 2 的过渡形态：混合编排

Phase 2 不需要完整的 ReAct，只需在 DiagnosisController 中加入条件分支：

```python
# Phase 2: 代码根据类型选不同的 L3 Skill，仍然是确定性编排
if classification.problem_type == "latency":
    await executor.invoke("vm-latency-measurement", params)
elif classification.problem_type == "packet_drop":
    await executor.invoke("kernel-stack-analyzer", params)
elif classification.problem_type == "connectivity":
    skip L3, go directly to L4
```

这等价于 LangGraph 的 `add_conditional_edges()`，仍在代码可控范围内。

### 7.3 Phase 3 的触发条件

当以下情况出现时，才值得引入 ReAct 风格的 Orchestrator：

- **诊断类型 > 5 种**：条件分支过多，代码维护成本上升
- **需要循环诊断**：L4 分析发现数据不足，需要回到 L3 补充测量
- **需要跨领域关联**：一次诊断涉及网络 + 存储 + 计算多个子系统
- **诊断策略需要频繁调整**：改 prompt 比改代码迭代更快

当前 Orchestrator 的子 Agent 设计（L2/L3/L4 分离）为 Phase 3 提供了良好的基础架构。
