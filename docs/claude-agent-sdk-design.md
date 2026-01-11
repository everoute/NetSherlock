# 基于 Claude Agent SDK 的设计方案分析

> 状态: 技术选型对比
> 创建时间: 2026-01-12

---

## 一、方案概述

本文档分析使用 **纯 Claude Agent SDK** 实现网络故障排查 Agent 的架构设计，并与混合架构 (LangGraph + Claude Agent SDK) 进行对比。

### 核心理念差异

| 维度 | 混合架构 (LangGraph) | 纯 Claude Agent SDK |
|------|---------------------|---------------------|
| 控制模式 | **显式编排** - 图结构定义流程 | **隐式引导** - Prompt 驱动决策 |
| 状态管理 | LangGraph State 强类型 | Agent 上下文 + 工具返回值 |
| 流程确定性 | 代码级保证 | Prompt 约束 + 工具设计 |
| 灵活性 | 需预定义节点和边 | 完全动态，AI 自主决策 |

---

## 二、纯 Claude Agent SDK 架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    Network Troubleshooting Agent                 │
│                      (Single Claude Agent)                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                   System Prompt                           │  │
│   │  - 分层诊断方法论 (L1→L2→L3→L4)                          │  │
│   │  - 问题类型识别规则                                       │  │
│   │  - 工具使用指南                                           │  │
│   │  - 约束条件 (如 receiver-first)                          │  │
│   └──────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│   ┌──────────────────────────────────────────────────────────┐  │
│   │                    Tool Layer (MCP)                       │  │
│   │                                                           │  │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │  │
│   │  │  L1 Tools   │ │  L2 Tools   │ │  L3 Tools   │        │  │
│   │  │ - grafana   │ │ - env_coll  │ │ - bcc_tools │        │  │
│   │  │ - loki      │ │ - topology  │ │ - ssh_exec  │        │  │
│   │  │ - pingmesh  │ │             │ │             │        │  │
│   │  └─────────────┘ └─────────────┘ └─────────────┘        │  │
│   │                                                           │  │
│   │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐        │  │
│   │  │  L4 Tools   │ │  Workflow   │ │   Utility   │        │  │
│   │  │ - analyze   │ │  Controls   │ │ - report    │        │  │
│   │  │ - attribute │ │ - checkpoint│ │ - notify    │        │  │
│   │  │             │ │ - rollback  │ │             │        │  │
│   │  └─────────────┘ └─────────────┘ └─────────────┘        │  │
│   └──────────────────────────────────────────────────────────┘  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 通过工具设计实现流程控制

在纯 SDK 方案中，**流程控制转移到工具层**：

```python
# 工具设计示例：内置流程约束的 L3 测量工具

@tool
def execute_coordinated_measurement(
    measurement_plan: MeasurementPlan,
    ssh_credentials: SSHCredentials
) -> MeasurementResult:
    """
    执行多点协同测量。

    内部实现保证：
    1. Receiver 端工具先启动
    2. 等待 receiver ready 信号
    3. 再启动 sender 端工具
    4. 收集两端数据

    这个约束在工具内部实现，而非依赖 AI 决策。
    """
    # 工具内部实现 receiver-first 逻辑
    receiver_proc = start_receiver(measurement_plan.receiver, ...)
    wait_for_ready(receiver_proc)
    sender_proc = start_sender(measurement_plan.sender, ...)

    return collect_results(receiver_proc, sender_proc)
```

### 2.3 状态管理方案

#### 方案 A: 工具返回结构化状态

```python
@tool
def collect_vm_network_env(vm_uuid: str, host_ip: str) -> EnvCollectionResult:
    """收集 VM 网络环境信息"""
    # ... 执行收集 ...
    return EnvCollectionResult(
        vm_info=vm_info,
        network_path=network_path,
        suggested_tools=["vm_latency_breakdown", "tun_to_kvm_irq"],
        next_step="L3_MEASUREMENT",  # 隐式引导下一步
        checkpoint_id="env_collected_12345"  # 用于回溯
    )
```

#### 方案 B: 显式 Checkpoint 工具

```python
@tool
def save_diagnosis_checkpoint(
    layer: str,
    state: dict,
    metadata: dict
) -> CheckpointResult:
    """保存诊断进度检查点，支持中断恢复"""
    checkpoint_id = persist_state(layer, state, metadata)
    return CheckpointResult(
        checkpoint_id=checkpoint_id,
        resumable=True,
        current_layer=layer
    )

@tool
def restore_diagnosis_checkpoint(checkpoint_id: str) -> DiagnosisState:
    """从检查点恢复诊断状态"""
    return load_state(checkpoint_id)
```

### 2.4 System Prompt 设计

```markdown
# Network Troubleshooting Agent

你是一个专业的网络故障排查 Agent，遵循分层诊断方法论。

## 诊断流程（必须按顺序执行）

### Layer 1: 监控告警
- 使用 `grafana_query_metrics` 或 `loki_query_logs` 获取告警上下文
- 使用 `read_pingmesh_logs` 获取系统网络基线数据
- **输出**: 问题类型分类（延迟/丢包/连通性）+ 涉及范围（VM/系统网络）

### Layer 2: 环境感知
- 使用 `collect_vm_network_env` 或 `collect_system_network_env`
- **必须**在开始测量前完成环境收集
- **输出**: 测量计划（工具列表、部署位置、参数）

### Layer 3: 精确测量
- 使用 `execute_coordinated_measurement` 执行测量
- ⚠️ **关键约束**: 不要单独调用底层测量工具，必须通过协调器
- **输出**: 原始测量数据

### Layer 4: 分析诊断
- 使用 `analyze_latency_segments` 或 `analyze_drop_location`
- 使用 `generate_diagnosis_report` 生成报告
- **输出**: 诊断报告

## 约束规则

1. **顺序约束**: L1 → L2 → L3 → L4，不可跳跃（除非用户明确指定起始层）
2. **测量约束**: 多点测量必须 receiver 先于 sender（已封装在工具内）
3. **安全约束**: 不执行任何修改系统状态的操作，仅诊断
4. **确认约束**: 执行 L3 测量前，向用户确认测量计划
```

---

## 三、关键流程控制对比

### 3.1 L3 多点协同测量

| 方面 | 混合架构 | 纯 SDK |
|------|---------|--------|
| **实现位置** | LangGraph 节点 (Python 代码) | MCP 工具内部 |
| **控制方式** | 图边确定执行顺序 | 工具封装原子操作 |
| **AI 参与度** | 仅提供参数 | 仅提供参数 |
| **可靠性** | ✅ 代码保证 | ✅ 工具保证 |

**纯 SDK 实现**:
```python
# 将复杂流程封装为单一工具，AI 只需决定是否调用
@tool
def execute_coordinated_measurement(plan: MeasurementPlan) -> Result:
    """
    原子化的协同测量工具。
    AI 不需要理解内部时序，只需要提供正确的 plan。
    """
    # 内部保证 receiver-first
    with SSHExecutor(plan.receiver.host) as receiver_ssh:
        with SSHExecutor(plan.sender.host) as sender_ssh:
            # 1. 启动 receiver
            recv_handle = receiver_ssh.start_async(plan.receiver.command)
            recv_handle.wait_for_ready()

            # 2. 启动 sender
            send_handle = sender_ssh.start_async(plan.sender.command)
            send_handle.wait_for_completion()

            # 3. 收集结果
            return MeasurementResult(
                receiver_data=recv_handle.get_output(),
                sender_data=send_handle.get_output()
            )
```

### 3.2 条件分支处理

| 场景 | 混合架构 | 纯 SDK |
|------|---------|--------|
| **跳过 L2（环境已知）** | Conditional Edge | Prompt 指令 + AI 判断 |
| **问题类型路由** | 分类节点 → 不同子图 | AI 选择不同工具集 |

**纯 SDK 实现**:
```python
# System Prompt 中的条件逻辑
"""
## 可选优化

如果用户提供了完整的环境信息（包含 vnet 映射、vhost PID），
可以跳过 Layer 2 直接进入 Layer 3 测量。

判断条件：
- 已知源/目的 VM 的 vnet 设备名
- 已知对应的 vhost-net worker PID
- 已知 OVS bridge 和 port
"""

# 或者通过工具返回值引导
@tool
def check_environment_completeness(context: dict) -> EnvironmentCheck:
    """检查当前上下文是否包含足够的环境信息"""
    required = ["src_vnet", "dst_vnet", "vhost_pids", "ovs_bridge"]
    missing = [k for k in required if k not in context]
    return EnvironmentCheck(
        complete=len(missing) == 0,
        missing_fields=missing,
        recommendation="skip_l2" if len(missing) == 0 else "run_l2"
    )
```

---

## 四、优劣势分析

### 4.1 纯 Claude Agent SDK 优势

| 优势 | 说明 |
|------|------|
| **简化架构** | 无需学习/维护 LangGraph，技术栈更简单 |
| **极致灵活** | AI 可根据实际情况动态调整策略 |
| **自然交互** | 用户可随时插入问题，AI 自然理解上下文 |
| **快速迭代** | 修改 Prompt 即可调整行为，无需改代码 |
| **原生 Skill 支持** | 直接复用 latency-analysis 等现有 skill |
| **上下文连续** | 整个诊断过程保持完整对话上下文 |

### 4.2 纯 Claude Agent SDK 劣势

| 劣势 | 说明 | 缓解方案 |
|------|------|----------|
| **流程不确定性** | AI 可能偏离预定流程 | 工具封装 + 强约束 Prompt |
| **状态管理弱** | 无强类型状态 schema | Checkpoint 工具 + Pydantic 返回值 |
| **调试困难** | 决策过程不透明 | 详细日志 + 思考过程输出 |
| **成本较高** | 整个上下文持续消耗 token | 分阶段 Agent 或总结压缩 |
| **多模型支持** | 仅支持 Claude | 如需多模型则必须混合架构 |

### 4.3 决策矩阵

| 需求 | 纯 SDK | 混合架构 | 说明 |
|------|--------|---------|------|
| L3 receiver-first 保证 | ✅ 工具封装 | ✅ 代码保证 | 两者都可实现 |
| 固定流程 + 灵活决策 | ⚠️ 需精心设计 | ✅ 天然支持 | SDK 需要更多工具设计 |
| 上下文管理 | ✅ 自动 | ⚠️ 需手动传递 | SDK 优势 |
| 复用现有 skill | ✅ 原生支持 | ⚠️ 需适配 | SDK 优势 |
| 多模型支持 | ❌ 仅 Claude | ✅ 全支持 | 混合架构优势 |
| 状态持久化 | ⚠️ 需 Checkpoint | ✅ 原生支持 | 混合架构优势 |
| 可观测性 | ⚠️ 需额外开发 | ✅ 图可视化 | 混合架构优势 |
| 开发速度 | ✅ 快 | ⚠️ 需学习成本 | SDK 优势 |

---

## 五、工具层设计（纯 SDK 方案）

### 5.1 工具分类与封装策略

```
┌─────────────────────────────────────────────────────────────────┐
│                      MCP Tool Layer                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           高层工具 (AI 直接调用)                         │    │
│  │                                                          │    │
│  │  diagnose_vm_latency()      # 一键 VM 延迟诊断          │    │
│  │  diagnose_system_latency()  # 一键系统网络延迟诊断       │    │
│  │  diagnose_packet_drop()     # 一键丢包诊断              │    │
│  │                                                          │    │
│  │  # 这些工具内部编排 L1→L4 完整流程                       │    │
│  │  # 适合简单场景，牺牲灵活性换取可靠性                    │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           中层工具 (分层诊断)                            │    │
│  │                                                          │    │
│  │  L1: query_monitoring_data()    # 统一监控数据查询       │    │
│  │  L2: collect_network_env()      # 统一环境收集           │    │
│  │  L3: execute_measurement()      # 统一测量执行           │    │
│  │  L4: analyze_results()          # 统一结果分析           │    │
│  │                                                          │    │
│  │  # AI 按层调用，每层内部处理复杂逻辑                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│                              │                                   │
│                              ▼                                   │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │           底层工具 (细粒度控制)                          │    │
│  │                                                          │    │
│  │  grafana_query_metrics()        # Grafana 查询          │    │
│  │  loki_query_logs()              # Loki 查询             │    │
│  │  ssh_execute_command()          # SSH 命令执行          │    │
│  │  collect_vm_network_info()      # VM 网络信息           │    │
│  │  run_bcc_tool()                 # 执行 BCC 工具         │    │
│  │                                                          │    │
│  │  # 最大灵活性，但需要 AI 正确编排                        │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 推荐: 中层工具为主

对于网络诊断场景，**推荐以中层工具为主**：

```python
# L3 中层工具示例
@tool
def execute_measurement(
    problem_type: Literal["latency", "packet_drop", "connectivity"],
    network_type: Literal["vm", "system"],
    env_info: NetworkEnvironment,
    options: Optional[MeasurementOptions] = None
) -> MeasurementResult:
    """
    执行网络测量。

    根据问题类型和网络类型自动选择合适的 BCC 工具组合，
    并协调多点测量的时序。

    Args:
        problem_type: 问题类型
        network_type: 网络类型
        env_info: L2 阶段收集的环境信息
        options: 可选的测量参数覆盖

    Returns:
        MeasurementResult: 包含原始数据和初步解析结果
    """
    # 内部逻辑:
    # 1. 根据 problem_type + network_type 选择工具组合
    # 2. 根据 env_info 填充工具参数
    # 3. 协调多点测量时序
    # 4. 收集和整合结果
    ...
```

---

## 六、Subagent 设计方案

### 6.1 方案 A: 单一 Agent (推荐)

```python
client = ClaudeSDKClient(
    system_prompt=NETWORK_TROUBLESHOOTING_PROMPT,
    mcp_servers=[
        MCPServer("network-tools", path="./mcp/network_tools.py"),
    ],
    # 无 subagent，所有能力通过工具提供
)
```

**优点**: 简单、上下文连续、调试方便
**缺点**: Prompt 可能很长，需要精心组织

### 6.2 方案 B: 分层 Subagent

```python
client = ClaudeSDKClient(
    system_prompt=ORCHESTRATOR_PROMPT,
    agents={
        "env_collector": Agent(
            name="env_collector",
            description="收集和分析网络环境信息",
            prompt=ENV_COLLECTOR_PROMPT,
            tools=["collect_vm_network_env", "collect_system_network_env"]
        ),
        "measurement_executor": Agent(
            name="measurement_executor",
            description="执行网络测量任务",
            prompt=MEASUREMENT_PROMPT,
            tools=["execute_coordinated_measurement", "ssh_execute"]
        ),
        "analyzer": Agent(
            name="analyzer",
            description="分析测量结果并生成诊断报告",
            prompt=ANALYZER_PROMPT,
            tools=["analyze_latency_segments", "generate_report"]
        )
    }
)
```

**优点**: 职责分离、Prompt 更聚焦
**缺点**: Subagent 间上下文传递需要设计

### 6.3 方案对比

| 方面 | 单一 Agent | 分层 Subagent |
|------|-----------|---------------|
| 复杂度 | 低 | 中 |
| 上下文连续性 | ✅ 自动 | ⚠️ 需设计 |
| Prompt 管理 | 单个长 Prompt | 多个短 Prompt |
| 调试 | 简单 | 需跟踪多个 Agent |
| Token 消耗 | 高（全程携带） | 可优化（按需加载） |

**建议**: MVP 阶段使用单一 Agent，后期如有性能问题再拆分

---

## 七、与混合架构的选择建议

### 7.1 选择纯 Claude Agent SDK 的场景

1. **团队熟悉度**: 团队对 LangGraph 不熟悉，学习成本高
2. **快速验证**: 需要快速出 MVP，迭代验证
3. **灵活性优先**: 诊断场景变化多，需要 AI 灵活应对
4. **Skill 复用**: 大量现有 Claude skill 需要复用

### 7.2 选择混合架构的场景

1. **流程确定性**: 流程必须严格按序执行，不容偏差
2. **多模型需求**: 未来需要接入其他 LLM
3. **可观测性**: 需要清晰的流程可视化和状态追踪
4. **团队协作**: 多人协作，代码比 Prompt 更易维护

### 7.3 折中方案

如果难以抉择，可以考虑**轻量混合**：

```
┌─────────────────────────────────────────────────────────────┐
│                    Python 主控逻辑                           │
│                                                              │
│   def diagnose(problem_info):                               │
│       # L1: 简单 Python 逻辑                                 │
│       monitoring_data = query_monitoring(problem_info)       │
│       problem_type = classify_problem(monitoring_data)       │
│                                                              │
│       # L2-L4: Claude Agent 处理                             │
│       agent = ClaudeSDKClient(...)                          │
│       result = agent.query(f"""                             │
│           问题类型: {problem_type}                          │
│           监控数据: {monitoring_data}                       │
│           请执行 L2→L3→L4 诊断流程...                       │
│       """)                                                   │
│       return result                                          │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

这种方案：
- 外层用 Python 控制关键分支
- 内层用 Claude Agent 处理复杂决策
- 不引入 LangGraph 复杂度

---

## 八、实现建议

### 8.1 如果选择纯 SDK 方案

1. **投资工具设计**: 将关键约束封装在工具内部，不依赖 Prompt
2. **分层 Prompt**: 按问题类型准备不同的 System Prompt
3. **Checkpoint 机制**: 实现状态持久化，支持中断恢复
4. **详细日志**: 记录每次工具调用和 AI 决策
5. **测试覆盖**: 单元测试工具，端到端测试流程

### 8.2 MVP 实现路径

```
Week 1: 基础设施
├── MCP 工具服务框架
├── L2 环境收集工具（复用 network_env_collector）
├── L3 协同测量工具（封装 receiver-first）
└── 基础 CLI 入口

Week 2: Agent 集成
├── System Prompt 设计与调优
├── L1-L4 工具完整集成
├── Checkpoint 机制
└── 端到端测试

Week 3: 完善与优化
├── 多问题类型支持
├── 错误处理与重试
├── 日志与监控
└── 文档
```

---

## 九、总结

| 维度 | 纯 SDK | 混合架构 |
|------|--------|---------|
| **推荐场景** | 快速验证、灵活诊断 | 生产级、严格流程 |
| **开发速度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| **流程可控** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **维护成本** | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| **扩展性** | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

**建议**:

如果当前目标是 MVP 验证，且团队对 LangGraph 不熟悉，可以先用**纯 Claude Agent SDK** 快速实现，通过**精心设计的工具层**来保证关键流程约束。后期如需更强的可控性和可观测性，再迁移到混合架构。

关键是：**无论选择哪种方案，核心的工具封装（如 receiver-first 协同测量）都是复用的**，迁移成本主要在编排层。
