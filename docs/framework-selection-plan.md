# 网络 Troubleshooting Agent 框架选型与实现计划

> 状态: 待审批
> 创建时间: 2026-01-11

---

## 一、框架选型结论

### 推荐方案: 混合架构 (LangGraph + Claude Agent SDK)

| 层级 | 职责 | 实现方式 |
|------|------|----------|
| **编排层** | 流程控制、状态管理、层间路由 | LangGraph |
| **执行层** | 节点内 AI 推理、工具调用 | Claude Agent SDK |

### 选型理由

| 需求 | 纯 Claude SDK | 纯 LangGraph | 混合方案 |
|------|--------------|-------------|---------|
| L3 多点协同（receiver 先于 sender）| ❌ 无法保证 | ✅ 确定性控制 | ✅ |
| 部分固定+部分灵活 | ❌ 全引导式 | ⚠️ 需额外开发 | ✅ 天然支持 |
| 上下文管理 | ✅ 自动 | ❌ 需手动 | ✅ 节点内自动 |
| 未来多模型支持 | ❌ 仅 Claude | ✅ 全支持 | ✅ 保留灵活性 |
| 复用现有 skill | ✅ 原生 | ❌ 需适配 | ✅ |

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         入口层                                   │
│  ┌─────────────┐    ┌─────────────────┐                        │
│  │  CLI REPL   │    │  FastAPI (P3)   │◀── Grafana Webhook     │
│  └──────┬──────┘    └────────┬────────┘                        │
│         └───────────┬────────┘                                  │
├─────────────────────┴───────────────────────────────────────────┤
│               LangGraph 编排层 (DiagnosticStateGraph)            │
│                                                                  │
│  [L1 Monitor] ──conditional──▶ [L2 Collect] ──fixed──▶          │
│       │                              │                           │
│       ▼                              ▼                           │
│  [L1 Classify]                 [L2 Decide]                       │
│       │                              │                           │
│       └──────conditional─────────────┴──▶ [L3 Execute] ──fixed─▶│
│                                                │                 │
│                                                ▼                 │
│                                          [L4 Analyze] ──▶ END   │
├──────────────────────────────────────────────────────────────────┤
│               Claude Agent SDK 执行层 (Per-Node)                 │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │L2 Subagent  │  │L3 协调器    │  │L4 Subagent  │              │
│  │(AI 工具选择)│  │(Python确定) │  │(+skill分析) │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
├──────────────────────────────────────────────────────────────────┤
│                      MCP Tool Layer                              │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐   │
│  │ NetworkEnv │ │    SSH     │ │    BCC     │ │  Grafana/  │   │
│  │ Collector  │ │  Executor  │ │   Tools    │ │   Loki     │   │
│  └────────────┘ └────────────┘ └────────────┘ └────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### 2.2 流程控制矩阵

| 决策点 | 固定/灵活 | 实现方式 |
|--------|----------|----------|
| L1→L2→L3→L4 主序列 | **固定** | LangGraph edges |
| 问题类型分类 | 灵活 | Claude L1 subagent |
| 跳过 L2（环境已知时）| 灵活 | Conditional edge |
| 选择哪些 BCC 工具 | 灵活 | Claude L2 subagent |
| Receiver 先于 Sender | **固定** | Python L3 协调器 |
| 分析方法选择 | 灵活 | Claude L4 + skill |

---

## 三、与现有代码库集成

### 3.1 复用组件

| 组件 | 来源路径 | 集成方式 |
|------|----------|----------|
| `NetworkEnvCollector` | `troubleshooting-tools/test/tools/network_env_collector.py` | 封装为 MCP tool |
| `SSHManager` | `troubleshooting-tools/test/automate-performance-test/src/core/ssh_manager.py` | 直接 import |
| `latency-analysis` skill | `troubleshooting-tools/.claude/skills/latency-analysis/` | L4 subagent 调用 |
| BCC 测量工具 | `troubleshooting-tools/measurement-tools/` | SSH 远程执行 |

### 3.2 MCP 工具封装示例

```python
# src/tools/network_env_tool.py
@tool
def collect_vm_network_env(vm_uuid: str, host_ip: str, ...) -> dict:
    """封装 NetworkEnvCollector.collect_vm_network_info()"""
    # 返回 VMInfo dataclass (qemu_pid, nics with vnet/tap_fds/vhost_pids)
```

---

## 四、Phase 1 MVP 实现计划

### 4.1 MVP 范围

| 维度 | MVP 范围 | 后续扩展 |
|------|----------|----------|
| 入口 | CLI 仅 | API/Webhook |
| 问题类型 | 延迟诊断 | 丢包、连通性 |
| 网络范围 | VM 网络 | 系统网络 |
| 工具数量 | 3 个核心 | 全部 57+ |

### 4.2 目录结构

```
automation-network-troubleshooting-agent/
├── src/
│   ├── state/
│   │   └── diagnostic_state.py    # LangGraph 状态 schema
│   ├── graph/
│   │   └── diagnostic_graph.py    # 工作流图定义
│   ├── nodes/
│   │   ├── l1_nodes.py            # 监控+分类节点
│   │   ├── l2_nodes.py            # 环境收集节点
│   │   ├── l3_nodes.py            # 测量协调节点 (Python)
│   │   └── l4_nodes.py            # 分析节点
│   ├── subagents/
│   │   ├── l2_subagent.py         # 环境收集 Claude subagent
│   │   └── l4_analyzer.py         # 分析 Claude subagent + skill
│   └── tools/
│       ├── network_env_tool.py    # MCP 封装
│       └── ssh_tool.py            # SSH 执行器封装
├── cli/
│   └── main.py                    # Click CLI 入口
├── docs/                          # 项目文档
├── tests/
└── pyproject.toml
```

### 4.3 实现步骤

**Week 1: 基础设施**
1. 项目结构搭建 + 依赖配置
2. `DiagnosticState` 状态 schema 定义
3. LangGraph 图结构定义（节点 + 边）
4. MCP 工具封装（network_env, ssh）
5. 基础 CLI 入口

**Week 2: L2 环境收集**
1. L2 subagent prompt 设计
2. 与 `NetworkEnvCollector` 集成
3. 工具部署决策逻辑
4. L2 单元测试

**Week 3: L3 测量协调**
1. 测量计划生成
2. 多点协调实现（receiver-first）
3. 并行工具执行 + 结果收集
4. L3 端到端测试

**Week 4: L4 分析 + 集成**
1. L4 subagent + latency-analysis skill 集成
2. 报告生成模板
3. 端到端测试
4. 文档 + 演示

---

## 五、关键技术选型

| 组件 | 选择 | 理由 |
|------|------|------|
| 编排框架 | LangGraph | 确定性流程控制 |
| AI 执行 | Claude Agent SDK | 原生 skill 支持、上下文管理 |
| SSH | Paramiko (复用) | 已有稳定实现 |
| CLI | Click | 简洁、易测试 |
| API (P3) | FastAPI | 异步支持 |

---

## 六、验证计划

### 6.1 单元测试
- L2: 验证 VM 环境收集返回正确结构
- L3: 验证 receiver 先于 sender 启动

### 6.2 集成测试
```bash
# 端到端 VM 延迟诊断
python -m cli.main diagnose latency \
    --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
    --dst-vm b7cc1234-5678-90ab-cdef-1234567890ab \
    --src-host 192.168.75.101 \
    --dst-host 192.168.75.102
```

### 6.3 预期输出
```
[L1] Problem classified: VM latency issue
[L2] Collecting environment...
[L2] Found vnet37 (vhost PIDs: 12345, 12346)
[L3] Starting measurement (receiver first)...
[L4] Analyzing with latency-analysis skill...

=== Diagnosis Report ===
Total RTT: 1250us

Attribution:
- VM Internal: 45%
- Host Internal: 25%
- Physical Network: 15%
- Virtualization: 15%
```

---

## 七、待确认事项

在开始实施前，请确认：

1. **依赖安装**: 目标环境是否可以安装 `langgraph`, `claude-agent-sdk`？
2. **SSH 凭证**: 测试环境的 SSH key 存放位置和格式？
3. **Grafana API**: Phase 3 需要 Grafana API 端点和认证信息（可后续提供）

---

## 八、关键参考文件

- `/Users/echken/workspace/troubleshooting-tools/test/tools/network_env_collector.py` - L2 核心逻辑
- `/Users/echken/workspace/troubleshooting-tools/test/automate-performance-test/src/core/ssh_manager.py` - SSH 连接池
- `/Users/echken/workspace/troubleshooting-tools/.claude/skills/latency-analysis/SKILL.md` - L4 分析方法论
- `/Users/echken/workspace/troubleshooting-tools/.claude/workflows/latency-measurement-workflow.md` - 现有工作流参考
