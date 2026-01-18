# 网络 Troubleshooting Agent 框架选型与实现计划

> 状态: 待审批 (已更新框架调研)
> 创建时间: 2026-01-11
> 更新时间: 2026-01-15

---

## 一、框架调研概述

### 1.1 调研范围

本次调研覆盖了 9 个主流 AI Agent 框架：

| 框架 | 来源 | 定位 |
|------|------|------|
| Claude Agent SDK | Anthropic | Claude 原生 Agent SDK |
| LangGraph | LangChain | 图工作流编排 |
| OpenAI Agents SDK | OpenAI | 轻量级多 Agent |
| PydanticAI | Pydantic | 类型安全 Agent |
| AutoGen / MS Agent Framework | Microsoft | 企业级多 Agent |
| CrewAI | CrewAI Inc | 角色协作 Agent |
| smolagents | HuggingFace | 轻量级 Code Agent |
| Agno | Agno | 高性能 Agent |

详细调研记录见: [framework-research-notes.md](./framework-research-notes.md)

### 1.2 项目核心约束

| 约束 | 描述 | 重要性 |
|------|------|--------|
| **receiver-first 时序** | L3 测量层必须保证接收端先于发送端启动 | 🔴 关键 |
| **MCP 工具集成** | 需与 Grafana/Loki/SSH 等外部系统集成 | 🔴 关键 |
| **四层职责分离** | L1监控 → L2环境 → L3测量 → L4分析 | 🟡 重要 |
| **多点协同测量** | 跨主机并行执行 BPF 工具 | 🟡 重要 |
| **快速迭代** | MVP 快速验证，后续持续优化 | 🟡 重要 |

---

## 二、MVP 场景对比分析

### 2.1 MVP 场景定义

| 维度 | MVP 范围 |
|------|----------|
| 入口 | CLI 命令行 |
| 问题类型 | VM 网络延迟诊断 |
| 工具数量 | 3-5 个核心工具 |
| 复杂度 | 单次诊断流程，无状态持久化需求 |

### 2.2 MVP 场景框架评估

| 框架 | 上手速度 | 工具集成 | 调试便捷 | 现有资产复用 | MVP 评分 |
|------|---------|---------|---------|-------------|---------|
| **Claude Agent SDK** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **25/25** |
| OpenAI Agents SDK | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 21/25 |
| PydanticAI | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 22/25 |
| Agno | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 21/25 |
| smolagents | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 18/25 |
| CrewAI | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 17/25 |
| LangGraph | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ | 16/25 |
| AutoGen | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | 16/25 |

### 2.3 MVP 场景分析

**Claude Agent SDK 优势 (MVP 场景最佳)**:
1. **零学习成本**: 现有 skill/workflow 可直接复用
2. **MCP 原生支持**: 无需适配即可集成外部工具
3. **Prompt 驱动**: 快速迭代，无需重构代码
4. **Subagent 支持**: 自然实现四层职责分离

**receiver-first 约束解决方案**:
```python
# 在 MCP 工具层封装确定性时序
@tool
def execute_coordinated_measurement(receiver_host, sender_host, ...):
    """L3 协同测量工具 - 内部保证 receiver-first 时序"""
    # 1. 启动 receiver
    receiver_proc = ssh_execute(receiver_host, receiver_cmd)
    await receiver_ready_signal()

    # 2. 启动 sender (receiver 已就绪)
    sender_proc = ssh_execute(sender_host, sender_cmd)

    # 3. 收集结果
    return collect_results(receiver_proc, sender_proc)
```

关键洞察: **receiver-first 时序约束应在工具层(MCP)而非框架层解决**，这使得框架选择更加灵活。

---

## 三、复杂功能场景对比分析

### 3.1 复杂功能场景定义

| 维度 | 复杂场景 |
|------|----------|
| 入口 | CLI + API + Grafana Webhook |
| 问题类型 | 延迟/丢包/吞吐/OVS/vhost 等 9 类 |
| 工具数量 | 57+ BPF 工具 |
| 复杂度 | 多步诊断、状态持久化、人机交互、长运行任务 |

### 3.2 复杂功能场景框架评估

| 框架 | 状态管理 | 工作流编排 | 可观测性 | 错误恢复 | 扩展性 | 复杂评分 |
|------|---------|-----------|---------|---------|--------|---------|
| **LangGraph** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | **23/25** |
| AutoGen/MS Agent | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | **23/25** |
| Agno | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 20/25 |
| OpenAI Agents SDK | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | 19/25 |
| Claude Agent SDK | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | 17/25 |
| CrewAI | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ | 15/25 |
| PydanticAI | ⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ | 16/25 |
| smolagents | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 11/25 |

### 3.3 复杂场景关键需求分析

| 需求 | Claude SDK | LangGraph | AutoGen | Agno |
|------|-----------|-----------|---------|------|
| Checkpoint/恢复 | ❌ 需自建 | ✅ 原生 | ✅ 原生 | ✅ 原生 |
| 条件分支 | ⚠️ Prompt | ✅ 图边 | ✅ Workflow | ✅ Workflow |
| 长运行任务 | ⚠️ 需封装 | ✅ 支持 | ✅ 支持 | ✅ 支持 |
| Human-in-the-loop | ⚠️ 需封装 | ✅ 原生 | ✅ 原生 | ✅ 原生 |
| Time-travel 调试 | ❌ | ✅ LangSmith | ⚠️ 有限 | ⚠️ 有限 |
| 多模型切换 | ❌ Claude only | ✅ | ✅ | ✅ |

---

## 四、综合权衡与最终建议

### 4.1 方案对比

| 方案 | 描述 | MVP 友好度 | 复杂扩展度 | 学习成本 |
|------|------|-----------|-----------|---------|
| **方案 A** | 纯 Claude Agent SDK | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 低 |
| **方案 B** | 纯 LangGraph | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 高 |
| **方案 C** | LangGraph + Claude SDK 混合 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 中高 |
| **方案 D** | PydanticAI | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | 低 |
| **方案 E** | Agno | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 低 |

### 4.2 最终推荐: 渐进式架构

> **Phase 1 (MVP): 纯 Claude Agent SDK**
> **Phase 2+ (复杂功能): 按需引入编排层**

#### Phase 1: 纯 Claude Agent SDK

**选择理由**:
1. ✅ 快速 MVP 验证，无需学习新框架
2. ✅ MCP 原生支持，工具集成零成本
3. ✅ 现有 skill/workflow 直接复用
4. ✅ Subagent 实现四层职责分离
5. ✅ **receiver-first 通过工具封装解决，无需图编排**

**架构**:
```
┌─────────────────────────────────────────────────────────────┐
│                Network Troubleshooting Agent                 │
│                  (Single Claude Agent)                       │
├─────────────────────────────────────────────────────────────┤
│                      System Prompt                           │
│  - 问题类型识别规则 (丢包/延迟/吞吐/...)                    │
│  - 分层诊断方法论 (L1→L2→L3→L4)                            │
│  - 诊断流程约束                                              │
├─────────────────────────────────────────────────────────────┤
│                     Subagents                                │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │L2 Subagent  │ │L3 Subagent  │ │L4 Subagent  │           │
│  │(环境收集)   │ │(测量协调)   │ │(分析报告)   │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
├─────────────────────────────────────────────────────────────┤
│                    MCP Tool Layer                            │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐     │
│  │ L1: grafana_* │ │ L2: collect_* │ │ L3: measure_* │     │
│  │     loki_*    │ │               │ │ (内含时序)    │     │
│  └───────────────┘ └───────────────┘ └───────────────┘     │
│  ┌───────────────┐                                          │
│  │ L4: analyze_* │                                          │
│  └───────────────┘                                          │
└─────────────────────────────────────────────────────────────┘
```

#### Phase 2+: 按需引入编排层

**触发条件** (满足任一即考虑):
- 需要 checkpoint/恢复能力
- 需要复杂的条件分支逻辑
- 需要严格的状态机控制
- 需要 time-travel 调试
- 需要多模型切换

**推荐选项**:
| 选项 | 适用场景 |
|------|----------|
| LangGraph | 需要精细流程控制 + LangSmith 调试 |
| Agno | 需要高性能 + 简单工作流 |
| MS Agent Framework | 需要企业级特性 + Azure 集成 |

### 4.3 对比原方案的变化

| 维度 | 原方案 (混合架构) | 新方案 (渐进式) |
|------|------------------|----------------|
| MVP 复杂度 | 需同时学习 LangGraph + Claude SDK | 仅需 Claude SDK |
| 时序约束 | LangGraph 图控制 | MCP 工具封装 |
| 迭代速度 | 中等 | 快速 |
| 扩展路径 | 固定架构 | 按需引入 |
| 风险 | LangGraph API 变动影响 | 低 |

**变化原因**:
1. 深度调研发现 **receiver-first 可在工具层解决**，不需要图编排
2. LangGraph 学习曲线高，MVP 阶段引入增加复杂度
3. 渐进式架构保留未来灵活性，不锁定技术选型

---

## 五、Phase 1 MVP 实现计划

### 5.1 MVP 范围

| 维度 | MVP 范围 | 后续扩展 |
|------|----------|----------|
| 入口 | CLI 仅 | API/Webhook |
| 问题类型 | 延迟诊断 | 丢包、连通性 |
| 网络范围 | VM 网络 | 系统网络 |
| 工具数量 | 3 个核心 | 全部 57+ |

### 5.2 目录结构

```
netsherlock/
├── src/
│   ├── agent/
│   │   ├── main_agent.py           # 主 Agent 定义
│   │   └── subagents/
│   │       ├── l2_collector.py     # L2 环境收集 subagent
│   │       ├── l3_measurer.py      # L3 测量协调 subagent
│   │       └── l4_analyzer.py      # L4 分析 subagent
│   ├── tools/                      # MCP 工具
│   │   ├── l1/
│   │   │   ├── grafana_tool.py
│   │   │   └── loki_tool.py
│   │   ├── l2/
│   │   │   └── network_env_tool.py
│   │   ├── l3/
│   │   │   └── measurement_tool.py # 封装 receiver-first 时序
│   │   └── l4/
│   │       └── analysis_tool.py
│   └── prompts/
│       ├── system_prompt.md
│       └── subagent_prompts/
├── cli/
│   └── main.py                     # Click CLI 入口
├── tests/
└── pyproject.toml
```

### 5.3 关键实现

#### receiver-first 时序封装

```python
# src/tools/l3/measurement_tool.py
from claude_agent_sdk import tool
from typing import Dict, Any

@tool
def execute_coordinated_measurement(
    receiver_host: str,
    sender_host: str,
    tool_name: str,
    receiver_args: Dict[str, Any],
    sender_args: Dict[str, Any],
    duration_seconds: int = 30
) -> Dict[str, Any]:
    """
    执行协同网络测量，自动保证 receiver-first 时序。

    Args:
        receiver_host: 接收端主机 IP
        sender_host: 发送端主机 IP
        tool_name: BPF 工具名称
        receiver_args: 接收端工具参数
        sender_args: 发送端工具参数
        duration_seconds: 测量持续时间

    Returns:
        包含双端测量数据的结构化结果
    """
    # 1. 启动 receiver
    receiver_proc = ssh_manager.execute_async(
        host=receiver_host,
        command=build_tool_command(tool_name, receiver_args)
    )

    # 2. 等待 receiver 就绪
    await_ready_signal(receiver_proc, timeout=10)

    # 3. 启动 sender (确保 receiver 已就绪)
    sender_proc = ssh_manager.execute_async(
        host=sender_host,
        command=build_tool_command(tool_name, sender_args)
    )

    # 4. 等待测量完成
    await asyncio.sleep(duration_seconds)

    # 5. 收集双端结果
    return {
        "receiver": collect_output(receiver_proc),
        "sender": collect_output(sender_proc),
        "metadata": {
            "tool": tool_name,
            "duration": duration_seconds,
            "timestamp": datetime.now().isoformat()
        }
    }
```

### 5.4 实现步骤

**Step 1: 基础设施 (2-3 天)**
- 项目结构搭建
- Claude Agent SDK 集成
- MCP 工具框架搭建

**Step 2: L2 环境收集 (2-3 天)**
- network_env_tool 封装
- L2 subagent prompt 设计

**Step 3: L3 测量协调 (3-4 天)**
- measurement_tool 封装 (含 receiver-first)
- SSH 执行器集成
- L3 subagent prompt 设计

**Step 4: L4 分析 (2-3 天)**
- analysis_tool 封装
- latency-analysis skill 集成
- L4 subagent prompt 设计

**Step 5: 集成测试 (2 天)**
- 端到端测试
- CLI 完善

---

## 六、关键技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| Agent 框架 | Claude Agent SDK | MVP 最优，MCP 原生支持 |
| SSH | Paramiko (复用) | 已有稳定实现 |
| CLI | Click | 简洁、易测试 |
| API (P2) | FastAPI | 异步支持 |
| 编排 (P2+) | 待定 | 按需引入 LangGraph/Agno |

---

## 七、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| Claude SDK 仅支持 Claude | 模型锁定 | P2 可引入多模型框架 |
| Prompt 控制流不够精确 | 诊断路径偏离 | 严格的 system prompt + 工具约束 |
| 状态管理需自建 | 长运行任务困难 | P2 引入编排层 |

---

## 八、待确认事项

1. **依赖安装**: 目标环境是否可以安装 `claude-agent-sdk`？
2. **SSH 凭证**: 测试环境的 SSH key 存放位置和格式？
3. **Grafana API**: Phase 2 需要 Grafana API 端点和认证信息

---

## 九、参考资料

### 调研文档
- [框架深度调研笔记](./framework-research-notes.md)
- [调研计划](./research-plan.md)

### 框架官方文档
- [Claude Agent SDK](https://platform.claude.com/docs/en/agent-sdk/overview)
- [LangGraph](https://docs.langchain.com/oss/python/langgraph/)
- [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/)
- [PydanticAI](https://ai.pydantic.dev/)
- [Agno](https://docs.agno.com/)

### 现有资产
- `troubleshooting-tools/test/tools/network_env_collector.py` - L2 核心逻辑
- `troubleshooting-tools/test/automate-performance-test/src/core/ssh_manager.py` - SSH 连接池
- `troubleshooting-tools/.claude/skills/latency-analysis/SKILL.md` - L4 分析方法论
