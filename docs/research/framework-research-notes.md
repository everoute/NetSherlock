# 框架选型深度调研笔记

> 调研日期: 2026-01-15
> 调研范围: 9个主流 AI Agent 框架

---

## 1. Claude Agent SDK

### 概述
Anthropic 官方提供的 Agent 构建 SDK，支持 MCP 工具协议。原名 Claude Code SDK，后更名以反映更广泛的应用场景。

### 核心特性
| 特性 | 描述 |
|------|------|
| **原生 Claude 支持** | 与 Claude 模型最佳集成 |
| **Subagent** | 支持子代理委托，可并行执行 |
| **MCP 工具协议** | 标准化工具接口，可连接 Slack/GitHub/Google Drive 等服务 |
| **Skill 系统** | 可复用的能力模块 |
| **Hook 系统** | pre-tool/post-tool 钩子支持 |

### 优势
1. 与 Claude 模型最佳集成，无需额外适配
2. Subagent 支持职责分离和并行执行
3. MCP 协议标准化工具接口，自动处理认证
4. 现有 skill (latency-analysis) 可直接复用
5. Prompt 驱动，快速迭代

### 劣势
1. **仅支持 Claude 模型** - 无多模型支持
2. 工作流控制依赖 Prompt 而非代码
3. 确定性流程控制相对较弱（无状态图）

### 关键约束满足
- **receiver-first 时序**: 需通过工具封装实现，SDK 本身无原生支持
- **MCP 工具支持**: ✅ 原生支持
- **多点协同**: 通过 Subagent 并行实现

### MVP 适用性: ⭐⭐⭐⭐⭐
### 复杂功能适用性: ⭐⭐⭐⭐

---

## 2. LangGraph

### 概述
LangChain 团队的图工作流框架，专为复杂、有状态的 Agent 工作流设计。

### 核心特性
| 特性 | 描述 |
|------|------|
| **图结构** | 节点(Nodes) + 边(Edges) 的显式控制流 |
| **状态管理** | 内置状态机，支持 checkpoint |
| **条件路由** | Conditional edges 实现动态分支 |
| **人机交互** | Human-in-the-loop 中断支持 |
| **调试工具** | LangSmith 集成，支持 time-travel debugging |

### 性能特征
- 在多个评测中是**延迟最低**的框架
- 但**token 使用量最高**

### 优势
1. **确定性流程控制**: 代码级别的工作流定义
2. **状态管理完善**: 支持 checkpoint 和 time-travel
3. **可视化调试**: 与 LangSmith 深度集成
4. **生产就绪**: 适合需要可靠性的场景

### 劣势
1. **学习曲线陡峭**: 图、子图、状态对象等多层抽象
2. **调试困难**: 错误发生时需穿透多层抽象定位
3. **文档分散**: 多种冲突的模式说明
4. **API 变更频繁**: 生产环境需额外封装

### 关键约束满足
- **receiver-first 时序**: ✅ 可通过图节点顺序精确控制
- **MCP 工具支持**: ⚠️ 需额外适配
- **多点协同**: ✅ 原生支持节点编排

### MVP 适用性: ⭐⭐⭐
### 复杂功能适用性: ⭐⭐⭐⭐⭐

---

## 3. OpenAI Agents SDK

### 概述
OpenAI 官方 Agent SDK，2025年3月发布，是实验性 Swarm 项目的生产级升级版。

### 核心特性
| 特性 | 描述 |
|------|------|
| **四个核心原语** | Agents, Handoffs, Guardrails, Sessions |
| **函数工具** | 自动 schema 生成 + Pydantic 验证 |
| **内置追踪** | 可视化调试和监控 |
| **双语言支持** | Python 和 TypeScript 功能对等 |
| **Temporal 集成** | 持久化长运行工作流 |

### 架构特点
- **轻量级**: 核心原语仅 4 个，易于理解
- **委托模式**: 与 LangGraph 的图模式不同，采用直接委托
- **Provider-agnostic**: 支持 100+ LLMs（虽然名称是 OpenAI）

### 优势
1. 极简设计，学习曲线平缓
2. 内置 Guardrails 支持输入/输出验证
3. TypeScript/Python 双语言同等支持
4. Temporal 集成支持人机交互工作流
5. **MCP 支持**: Codex 支持 AGENTS.md 和 MCP

### 劣势
1. 相对较新，生态不如 LangChain
2. 复杂状态管理需要额外工作
3. 与 OpenAI 生态关联较紧

### 关键约束满足
- **receiver-first 时序**: 需通过工具封装实现
- **MCP 工具支持**: ✅ 支持 MCP
- **多点协同**: ✅ 通过 Handoffs 实现

### MVP 适用性: ⭐⭐⭐⭐⭐
### 复杂功能适用性: ⭐⭐⭐⭐

---

## 4. PydanticAI

### 概述
Pydantic 团队打造的 Agent 框架，目标是将 FastAPI 的开发体验带到 GenAI 领域。

### 核心特性
| 特性 | 描述 |
|------|------|
| **类型安全** | Pydantic 原生验证 |
| **模型无关** | 支持几乎所有模型提供商 |
| **MCP/A2A 集成** | 支持 Model Context Protocol 和 Agent2Agent |
| **Streamed Outputs** | 实时验证的流式输出 |
| **Durable Execution** | 跨故障保持进度 |

### 工具系统
- `@agent.tool` - 需要上下文的工具
- `@agent.tool_plain` - 无上下文工具
- **Toolsets** - 工具集合，支持 MCP servers
- **内置工具**: WebFetchTool, MemoryTool

### 优势
1. **类型安全**: 编译时检查，代码质量高
2. **FastAPI 风格**: Python 开发者友好
3. **Human-in-the-loop**: 工具调用审批支持
4. **MCP 原生支持**: 可直接使用 MCP 服务器
5. 验证失败自动重试

### 劣势
1. 工具装饰器创建紧耦合
2. 声明顺序敏感
3. 多 agent 编排能力相对较弱

### 关键约束满足
- **receiver-first 时序**: 需通过工具封装实现
- **MCP 工具支持**: ✅ 原生支持
- **多点协同**: ⚠️ 需额外设计

### MVP 适用性: ⭐⭐⭐⭐⭐
### 复杂功能适用性: ⭐⭐⭐

---

## 5. AutoGen / Microsoft Agent Framework

### 概述
微软 AutoGen 框架，2025年10月与 Semantic Kernel 合并为 Microsoft Agent Framework。

### 核心特性 (AutoGen v0.4+)
| 特性 | 描述 |
|------|------|
| **异步事件驱动** | 解决了早期版本的阻塞问题 |
| **模块化设计** | 可插拔的 agents/tools/memory/models |
| **跨语言支持** | Python 和 .NET |
| **扩展模块** | 高级模型客户端、多 agent 团队 |

### Microsoft Agent Framework (2025.10)
- AutoGen + Semantic Kernel 合并
- 企业级特性: 线程状态管理、类型安全、过滤器、遥测
- **四大支柱**: MCP, A2A, OpenAPI, 跨运行时可移植

### 工作流编排
- Sequential, Concurrent, Hand-off, Magentic 模式
- 可组合嵌套的工作流
- 持久状态管理支持长运行场景

### 优势
1. 企业级特性完善
2. 深度 Azure 集成
3. MCP/A2A/OpenAPI 标准支持
4. 强类型 + 遥测

### 劣势
1. v0.4 API 变更大，迁移成本高
2. 学习曲线较陡
3. GA 预计 Q1 2026，目前仍在预览

### 关键约束满足
- **receiver-first 时序**: ✅ 工作流编排支持
- **MCP 工具支持**: ✅ 原生支持
- **多点协同**: ✅ 多 agent 团队原生支持

### MVP 适用性: ⭐⭐⭐
### 复杂功能适用性: ⭐⭐⭐⭐⭐

---

## 6. CrewAI

### 概述
基于角色的多 Agent 协作框架，强调 Agent 之间的任务分工。

### 核心特性
| 特性 | 描述 |
|------|------|
| **角色分工** | 每个 Agent 有专门功能 |
| **Flows** | 生产级事件驱动工作流 |
| **实时追踪** | 详细的步骤追踪 |
| **Agent 训练** | 自动化 + 人工训练 |

### CrewAI 2.0 (2025)
- 从编排器升级为完整平台
- 工具中央化部署管理
- 工具兼容性和安全性增强

### 优势
1. 角色概念直观，易于理解
2. Crews + Flows 结合使用强大
3. 企业版 (AMP) 提供高级功能

### 劣势
1. **更适合原型/演示**: 生产需额外改造
2. 小模型(7B)支持不佳
3. 缺乏内置监控、错误恢复、扩展机制
4. 多 Agent 规模增长后维护困难

### 关键约束满足
- **receiver-first 时序**: 需通过 Flow 实现
- **MCP 工具支持**: ⚠️ 需适配
- **多点协同**: ✅ 原生支持任务分发

### MVP 适用性: ⭐⭐⭐⭐
### 复杂功能适用性: ⭐⭐⭐

---

## 7. smolagents

### 概述
HuggingFace 的轻量级 Agent 库，核心代码约 1000 行，强调简洁。

### 核心特性
| 特性 | 描述 |
|------|------|
| **极简设计** | ~1000 行核心代码 |
| **Code Agent** | Agent 用 Python 代码执行动作，而非 JSON |
| **安全沙箱** | E2B, Modal, Docker, Pyodide 支持 |
| **多模态** | 文本、图像、音频、视频 |
| **Hub 集成** | 分享和拉取工具/Agent |

### 快速上手
```python
from smolagents import CodeAgent, WebSearchTool, InferenceClientModel
model = InferenceClientModel()
agent = CodeAgent(tools=[WebSearchTool()], model=model)
agent.run("question")
```

### 优势
1. **极简**: 3 行代码即可创建 Agent
2. **Code-first**: Python 代码执行比 JSON 更快更准确
3. **模型无关**: 支持本地/云端各种模型
4. **MCP 支持**: 可使用任意 MCP server 工具

### 劣势
1. 文档中工具模式说明不清晰
2. 入门体验粗糙
3. 复杂编排能力有限
4. 是 transformers.agents 的替代品，生态转型中

### 关键约束满足
- **receiver-first 时序**: 需自行实现
- **MCP 工具支持**: ✅ 支持 MCP server
- **多点协同**: ⚠️ 有限支持

### MVP 适用性: ⭐⭐⭐⭐
### 复杂功能适用性: ⭐⭐

---

## 8. Agno

### 概述
高性能 Agent 框架，强调速度和资源效率。

### 核心特性
| 特性 | 描述 |
|------|------|
| **极速实例化** | ~2μs，比 LangGraph 快 529x |
| **低内存** | 比 LangGraph 低 24x |
| **Teams & Workflows** | 高级多 Agent 编排 |
| **模型无关** | 支持任意模型 |
| **MCP 支持** | 单行集成主流服务 |

### 性能数据
- Agent 实例化: ~2 微秒
- 比 LangGraph 快 5000x (官方声称)
- 内存使用低 50x

### 集成生态
- 向量数据库: Pinecone, Weaviate, Qdrant
- 云存储: AWS S3, GCP
- 协作工具: Slack, Notion
- MCP 支持

### 优势
1. **极致性能**: 横向扩展无阻塞
2. 优秀的文档和源码可读性
3. Session memory 支持
4. 私有部署，无供应商锁定

### 劣势
1. 相对较新，社区较小
2. 部分高级功能在付费版
3. 生产案例相对较少

### 关键约束满足
- **receiver-first 时序**: 通过 Workflow 实现
- **MCP 工具支持**: ✅ 原生支持
- **多点协同**: ✅ Teams 原生支持

### MVP 适用性: ⭐⭐⭐⭐
### 复杂功能适用性: ⭐⭐⭐⭐

---

## 综合对比矩阵

### 特性对比

| 框架 | MCP 支持 | 多 Agent | 状态管理 | 学习曲线 | 模型支持 |
|------|---------|---------|---------|---------|---------|
| Claude Agent SDK | ✅ 原生 | ✅ Subagent | ⚠️ 需自建 | 低 | Claude only |
| LangGraph | ⚠️ 需适配 | ✅ 节点图 | ✅ 完善 | 高 | 多模型 |
| OpenAI Agents SDK | ✅ 支持 | ✅ Handoffs | ✅ Sessions | 低 | 100+ LLM |
| PydanticAI | ✅ 原生 | ⚠️ 有限 | ✅ Durable | 低 | 多模型 |
| AutoGen/MS Agent | ✅ 原生 | ✅ Teams | ✅ 企业级 | 高 | 多模型 |
| CrewAI | ⚠️ 需适配 | ✅ Crews | ⚠️ 需加强 | 中 | 多模型 |
| smolagents | ✅ 支持 | ⚠️ 有限 | ⚠️ 基础 | 中 | 多模型 |
| Agno | ✅ 原生 | ✅ Teams | ✅ Session | 低 | 多模型 |

### 性能对比

| 框架 | 延迟 | Token 效率 | 内存使用 |
|------|------|-----------|---------|
| LangGraph | 最低 | 最差 | 高 |
| OpenAI/CrewAI | 相近 | 相近 | 中 |
| Agno | 优秀 | 优秀 | 最低 |
| smolagents | 中等 | 中等 | 低 |

### 生产就绪度

| 框架 | 企业采用 | 文档质量 | 社区活跃度 | 稳定性 |
|------|---------|---------|-----------|--------|
| LangGraph | 高 | 中 | 高 | 中(API变动) |
| OpenAI Agents SDK | 中 | 高 | 中 | 高 |
| Claude Agent SDK | 中 | 高 | 中 | 高 |
| PydanticAI | 中 | 高 | 中 | 高 |
| AutoGen | 中 | 中 | 高 | 低(v0.4变动) |
| CrewAI | 中 | 中 | 高 | 中 |
| smolagents | 低 | 中 | 中 | 中 |
| Agno | 低 | 高 | 中 | 高 |

---

## 项目需求关键约束分析

### 核心约束
1. **receiver-first 时序**: L3 测量层必须保证接收端先于发送端启动
2. **MCP 工具集成**: 需要与 Grafana/Loki/SSH 等外部系统集成
3. **四层职责分离**: L1监控 → L2环境 → L3测量 → L4分析
4. **多点协同测量**: 跨主机并行执行 BPF 工具

### 约束满足度评估

| 框架 | receiver-first | MCP | 四层分离 | 多点协同 | 总评 |
|------|---------------|-----|---------|---------|------|
| Claude Agent SDK | 需封装 | ✅ | ✅ Subagent | ✅ | ⭐⭐⭐⭐⭐ |
| LangGraph | ✅ 图控制 | 需适配 | ✅ 节点 | ✅ | ⭐⭐⭐⭐ |
| OpenAI Agents SDK | 需封装 | ✅ | ✅ Handoffs | ✅ | ⭐⭐⭐⭐ |
| PydanticAI | 需封装 | ✅ | ⚠️ 较弱 | ⚠️ | ⭐⭐⭐ |
| AutoGen | ✅ Workflow | ✅ | ✅ Teams | ✅ | ⭐⭐⭐⭐ |
| CrewAI | 需 Flow | 需适配 | ✅ Crews | ✅ | ⭐⭐⭐ |
| smolagents | 需自建 | ✅ | ⚠️ 较弱 | ⚠️ | ⭐⭐ |
| Agno | ✅ Workflow | ✅ | ✅ Teams | ✅ | ⭐⭐⭐⭐ |

---

## 更新日志

### 2026-01-15
- 完成 9 个框架深度调研
- 完成综合对比矩阵
- 完成项目约束满足度评估
