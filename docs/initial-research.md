# AI 驱动网络运维与 Troubleshooting Agent 功能调研

## 1. 调研背景

### 1.1 现有资源
- **测量工具体系**: 57个 Python BCC 工具 + 20个 bpftrace 脚本
- **监控数据**: Grafana 暴露的集群指标
- **日志系统**: Loki (Grafana 原生，支持 LogQL 查询)
- **Agent 定义**: 已有 6 个专业 agents (research, prd, design, development, testing, debug)
- **工作流编排**: debug-fix-workflow, latency-measurement-workflow

### 1.2 目标
使用 Claude Code Agent SDK 开发 AI 驱动的自动网络运维与 troubleshooting agent

### 1.3 网络问题范围

**KVM 虚拟化环境下的网络问题**，包括两类：

1. **虚拟机网络 (VM Network)**
   - 数据路径：VM -> virtio-net -> vhost-net -> OVS kernel datapath -> vhost-net -> virtio-net -> VM
   - 涉及组件：virtio-net 驱动、vhost-net 加速、TUN/TAP 设备、OVS 内核数据路径

2. **系统网络 (System Network)**
   - 数据路径：Host -> OVS internal port -> OVS kernel datapath -> 物理网络 -> 远端节点
   - 涉及组件：OVS internal port、OVS 内核数据路径、物理网卡/bond

### 1.4 现有监控能力（Layer 1 数据源）

**系统网络**：
- Pingmesh 监控结果统计 → 存储在集群节点特定目录 log 中
- 日志位置：节点本地（可能未收集到 Loki）

**VM 网络**：
- vnet 相关丢包告警 → Grafana（有）
- 延迟数据 → 无

**结论**：Layer 1 需要混合数据源
- Grafana/Loki：已收集的告警和日志
- 节点直接访问：SSH 读取 pingmesh 等本地日志

### 1.5 分层诊断架构

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: 诊断分析层                                          │
│   - 测量数据分析                                             │
│   - 根因定位                                                 │
│   - 诊断报告生成                                             │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: 精确测量层                                          │
│   - BCC/eBPF 工具执行                                        │
│   - 延迟/丢包数据收集                                        │
│   - 多点协同测量                                             │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: 环境感知层                                          │
│   - 问题类型识别                                             │
│   - 环境信息收集 (env collector)                             │
│   - 工具部署决策（范围、参数、访问方式）                      │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: 基础监控层（混合数据源）                             │
│   - Grafana 指标/告警（vnet 丢包等）                         │
│   - Loki 日志（如有收集）                                    │
│   - 节点本地日志（SSH 直接读取 pingmesh 等）                  │
│   - 问题范围初步界定                                         │
└─────────────────────────────────────────────────────────────┘
```

### 1.6 Grafana Webhook 触发机制

```
Grafana Alert Rule 触发
        │
        ▼
┌─────────────────────────────────┐
│ Contact Point (Webhook 类型)    │
│ - URL: http://agent-api/webhook │
│ - 发送告警 JSON payload        │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ Agent API 接收并路由            │
│ - 按 alertname 路由到诊断流程   │
│ - labels 提供诊断上下文         │
│ - 触发 Layer 2 -> 3 -> 4       │
└─────────────────────────────────┘
```

**告警类型与诊断流程映射**：
| 告警类型 (alertname) | 触发的诊断流程 | 关键 labels |
|---------------------|---------------|-------------|
| `VnetPacketDrop` | VM 丢包诊断 | instance, vm_name |
| `SystemLatencyHigh` | 系统网络延迟诊断 | src_host, dst_host |
| `VMLatencyAnomaly` | VM 延迟诊断 | src_vm, dst_vm |
| `OVSDatapathDrop` | OVS 数据路径诊断 | bridge, instance |

**Webhook Payload 示例**：
```json
{
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname": "VnetPacketDrop",
      "instance": "host-01",
      "vm_name": "vm-123",
      "severity": "warning"
    },
    "annotations": {
      "summary": "vnet 丢包率超过阈值"
    }
  }]
}
```

### 1.7 部署要求
- **CLI 交互式**: 工程师通过命令行与 agent 对话
- **API 服务**: 作为后端服务，接收 Grafana webhook 触发自动诊断

---

## 2. Claude Agent SDK 核心能力

### 2.1 两种使用模式

| 模式 | 适用场景 | 特点 |
|------|---------|------|
| `query()` | 单次任务 | 简单调用，无状态 |
| `ClaudeSDKClient` | 持续运维 | 持久会话，上下文保持 |

**建议**: 网络运维场景使用 `ClaudeSDKClient`，保持对网络状态的持续感知

### 2.2 内置工具

```
Read, Write, Edit, Bash, Glob, Grep, WebSearch, WebFetch, Task, AskUserQuestion
```

### 2.3 关键扩展能力

1. **自定义 MCP 工具**: 将现有 BCC 工具包装为可调用能力
2. **Subagents**: 定义专业子代理（诊断、优化、验证）
3. **Hooks**: 行为拦截和审计
4. **Sessions**: 跨时间的上下文保持

---

## 3. 架构设计方案

### 3.1 整体架构（对应分层诊断）

```
┌─────────────────────────────────────────────────────────────┐
│                  Network Ops Agent (主控)                    │
├─────────────────────────────────────────────────────────────┤
│                     Subagent Layer                          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │
│  │  analysis   │ │ measurement │ │    env      │           │
│  │   agent     │ │   agent     │ │  collector  │           │
│  │  (Layer 4)  │ │  (Layer 3)  │ │  (Layer 2)  │           │
│  └─────────────┘ └─────────────┘ └─────────────┘           │
├─────────────────────────────────────────────────────────────┤
│                     MCP Tool Layer                          │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Grafana │ │ Loki   │ │  BCC   │ │  SSH   │ │Network │    │
│  │Metrics │ │ Logs   │ │ Tools  │ │Executor│ │  Env   │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
├─────────────────────────────────────────────────────────────┤
│                   External Systems                          │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐    │
│  │Grafana │ │  Loki  │ │ Target │ │  OVS   │ │  KVM   │    │
│  │  API   │ │  API   │ │ Hosts  │ │Bridges │ │  VMs   │    │
│  └────────┘ └────────┘ └────────┘ └────────┘ └────────┘    │
└─────────────────────────────────────────────────────────────┘
```

### 3.2 分层 Subagents 设计

| Layer | Subagent | 职责 | 可用工具 |
|-------|----------|------|---------|
| L4 | **analysis-agent** | 测量数据分析、根因定位、诊断报告 | 分析脚本、报告模板 |
| L3 | **measurement-agent** | 工具部署执行、多点协同、数据收集 | BCC tools, SSH executor |
| L2 | **env-collector-agent** | 环境收集、问题识别、工具决策 | network_env_collector, 拓扑分析 |
| L1 | (主控 agent) | 告警监听、问题分流、流程编排 | Grafana/Loki API |

### 3.3 诊断流程编排

```
告警触发 (Layer 1)
    │
    ▼
┌─────────────────────────────────────────┐
│ 1. 问题分类                              │
│    - 延迟问题 / 丢包问题 / 连通性问题      │
│    - VM网络 / 系统网络                    │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 2. 环境收集 (env-collector-agent)        │
│    - 确定涉及节点（源/目的 Host + VM）     │
│    - 收集 OVS 拓扑、vnet 映射、vhost PID  │
│    - 生成工具部署决策                     │
│      * 部署位置（哪些 Host/VM）           │
│      * 工具参数（接口名、IP 过滤条件）     │
│      * 访问方式（SSH 连接信息）            │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 3. 精确测量 (measurement-agent)          │
│    - 按决策部署 BCC 工具                  │
│    - 协同多点测量（receiver 先于 sender） │
│    - 收集测量数据                         │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│ 4. 分析诊断 (analysis-agent)             │
│    - 解析工具输出                         │
│    - 延迟分段归因 / 丢包位置定位          │
│    - 生成诊断报告                         │
└─────────────────────────────────────────┘
```

### 3.4 MCP 工具层设计

#### 3.4.1 Layer 1: 监控告警工具（混合数据源）

**Grafana/Loki API**:
| 工具 | 功能 | 说明 |
|------|------|------|
| `grafana_query_metrics` | PromQL 查询 | 获取监控指标 |
| `loki_query_logs` | LogQL 查询 | 获取已收集日志 |
| `grafana_get_alerts` | 获取告警 | vnet 丢包等告警 |

**节点本地日志（SSH 直接读取）**:
| 工具 | 功能 | 说明 |
|------|------|------|
| `read_pingmesh_logs` | 读取 pingmesh 日志 | 系统网络延迟/丢包统计 |
| `read_node_logs` | 通用节点日志读取 | 指定路径的日志文件 |
| `parse_pingmesh_stats` | 解析 pingmesh 统计 | 提取延迟/丢包指标 |

#### 3.4.2 Layer 2: 环境收集工具
| 工具 | 功能 | 说明 |
|------|------|------|
| `collect_system_network_env` | 系统网络环境 | OVS bridges, physical NICs, bonds |
| `collect_vm_network_env` | VM 网络环境 | virtio NICs, vnet mapping, vhost PIDs |
| `resolve_network_path` | 路径解析 | 根据源/目的确定完整数据路径 |

#### 3.4.3 Layer 3: 测量工具（按网络类型）

**VM 网络测量**:
| 工具 | 场景 | 原工具 |
|------|------|--------|
| `measure_vm_icmp_rtt` | VM间延迟 | kernel_icmp_rtt.py |
| `detect_vm_packet_drops` | VM丢包检测 | icmp_drop_detector.py |
| `measure_vm_latency_breakdown` | 延迟分段 | vm_network_latency_summary.py |
| `trace_tun_to_kvm_irq` | TUN到IRQ延迟 | tun_tx_to_kvm_irq.py |
| `monitor_vhost_stats` | vhost统计 | vhost-net/ 工具 |
| `monitor_virtio_stats` | virtio统计 | virtio-net/ 工具 |

**系统网络测量**:
| 工具 | 场景 | 原工具 |
|------|------|--------|
| `measure_system_icmp_rtt` | 系统网络延迟 | kernel_icmp_rtt.py (internal port) |
| `detect_system_packet_drops` | 系统丢包检测 | eth_drop.py |
| `monitor_ovs_datapath` | OVS数据路径 | ovs/ 工具 |

#### 3.4.4 Layer 4: 分析工具
| 工具 | 功能 | 说明 |
|------|------|------|
| `analyze_latency_segments` | 延迟分段分析 | 参考 latency-analysis skill |
| `analyze_drop_location` | 丢包位置分析 | 基于 stack trace 定位 |
| `generate_diagnosis_report` | 生成报告 | 结构化诊断报告 |

---

## 4. 功能模块规划

### 4.1 Phase 1: 分层基础能力（MVP）

**目标**: 实现完整的分层诊断流程（单一问题类型）

**Layer 1 - 监控告警**:
- Grafana API 集成（指标查询）
- Loki API 集成（日志查询）
- 告警接收和问题分类

**Layer 2 - 环境收集**:
- `env-collector-agent` 实现
- 基于现有 `network_env_collector.py` 扩展
- 输出：工具部署决策（位置、参数、访问方式）

**Layer 3 - 精确测量**:
| 工具 | 场景 | 原工具 |
|------|------|--------|
| `measure_vm_icmp_rtt` | VM延迟 | kernel_icmp_rtt.py |
| `detect_vm_packet_drops` | VM丢包 | icmp_drop_detector.py |
| `measure_vm_latency_breakdown` | 延迟分段 | vm_network_latency_summary.py |

**Layer 4 - 分析诊断**:
- 参考现有 `latency-analysis` skill
- 延迟分段归因报告

**CLI 入口**:
```bash
# 交互式诊断（触发完整分层流程）
network-ops-agent diagnose --type latency --src VM1 --dst VM2

# 指定从某层开始（跳过告警触发）
network-ops-agent diagnose --from-layer 2 --src-host host1 --dst-host host2
```

### 4.2 Phase 2: 完整网络类型覆盖

**目标**: 支持 VM 网络 + 系统网络的完整诊断

**扩展 Layer 2**:
- 系统网络环境收集（OVS internal port 拓扑）
- 网络路径自动推断

**扩展 Layer 3**:
- 系统网络测量工具封装
- vhost/virtio 深度测量工具
- OVS 数据路径监控

**多问题类型支持**:
- 延迟问题诊断流程
- 丢包问题诊断流程
- 连通性问题诊断流程

### 4.3 Phase 3: API 服务与自动化

**目标**: Grafana Webhook 触发的全自动诊断

**API 端点设计**:

```python
# 1. Grafana Webhook 接收（自动触发）
POST /api/v1/webhook/grafana
Content-Type: application/json

# Grafana 发送的告警 payload
{
    "alerts": [{
        "status": "firing",
        "labels": {
            "alertname": "VnetPacketDrop",  # 用于路由到诊断流程
            "instance": "host-01",
            "vm_name": "vm-123"
        },
        "annotations": {"summary": "..."}
    }]
}

# 响应：异步诊断任务已创建
{"task_id": "diag-12345", "status": "accepted", "diagnosis_type": "vm_packet_drop"}
```

```python
# 2. 手动触发诊断（CLI/API）
POST /api/v1/diagnosis
{
    "type": "vm_latency",           # 诊断类型
    "params": {
        "src_vm": "vm-123",
        "dst_vm": "vm-456"
    }
}
```

```python
# 3. 查询诊断状态和结果
GET /api/v1/diagnosis/{task_id}

# 响应
{
    "task_id": "diag-12345",
    "status": "completed",          # pending/running/completed/failed
    "layers_completed": ["L1", "L2", "L3", "L4"],
    "report": { ... },              # Layer 4 诊断报告
    "created_at": "...",
    "completed_at": "..."
}
```

**告警路由逻辑**:
```python
ALERT_ROUTING = {
    "VnetPacketDrop":     "vm_packet_drop_diagnosis",
    "VMLatencyAnomaly":   "vm_latency_diagnosis",
    "SystemLatencyHigh":  "system_latency_diagnosis",
    "OVSDatapathDrop":    "ovs_datapath_diagnosis",
}
```

**自动化能力**:
- Grafana Contact Point 配置指向 Agent API
- 告警触发 -> 自动路由 -> 分层诊断 -> 报告生成
- 诊断报告推送（Slack/邮件/Grafana annotation）
- 历史诊断结果归档和趋势分析

---

## 5. 待调研/确认事项

### 5.1 数据源集成（需确认/补充）

**Grafana/Loki**:
- [ ] Grafana API 端点和认证方式
- [x] Loki 日志收集范围：**部分日志**，pingmesh 等可能未收集
- [x] VM 网络监控：**只有 vnet 丢包告警**，无延迟数据
- [ ] 现有告警规则和 webhook 配置

**节点本地日志**:
- [ ] Pingmesh 日志路径（如 /var/log/pingmesh/）
- [ ] Pingmesh 日志格式（结构化/非结构化）
- [ ] 节点 SSH 访问方式（密钥/跳板机）

### 5.2 技术实现（SDK 研究结论）
- [x] Claude Agent SDK: Python `claude-agent-sdk` 包
- [x] MCP Server: 支持 stdio 进程和 HTTP 两种模式
- [x] 会话管理: `ClaudeSDKClient` 支持持久会话
- [x] Subagent: SDK 原生支持 agents 参数定义子代理

### 5.3 安全与权限设计
- SSH 密钥: 复用现有 `test/tools/` 中的 SSH Manager
- 操作审计: 通过 SDK Hooks 机制实现
- 危险命令拦截: PreToolUse hook 过滤

---

## 6. 实现路线图

### Phase 1: MVP（4周）

**Week 1: 基础设施**
```
[环境] SDK 安装验证
    -> [L1] Grafana/Loki API 工具封装
    -> [POC] 单工具 MCP 调用验证
```

**Week 2: Layer 2 环境收集**
```
[L2] env-collector-agent 实现
    -> 基于 network_env_collector.py 扩展
    -> 工具部署决策输出格式定义
```

**Week 3: Layer 3 测量 + Layer 4 分析**
```
[L3] 3个核心 VM 测量工具封装
    -> [L4] 延迟分析工具（参考 latency-analysis skill）
    -> 分层流程串联
```

**Week 4: CLI 入口 + 端到端验证**
```
[CLI] 交互式入口开发
    -> [测试] VM 延迟诊断端到端测试
    -> [文档] 使用说明
```

### Phase 2: 完整覆盖（3周）

**Week 5-6: 网络类型扩展**
```
[L2] 系统网络环境收集
    -> [L3] 系统网络测量工具
    -> [L3] vhost/virtio 深度测量工具
```

**Week 7: 多问题类型**
```
[流程] 丢包诊断流程
    -> [流程] 连通性诊断流程
    -> [测试] 多场景验证
```

### Phase 3: API 服务（2周）

**Week 8-9: API 与自动化**
```
[API] FastAPI 服务框架
    -> [API] Webhook 接收器
    -> [集成] Grafana 告警对接
    -> [测试] 自动触发验证
```

---

## 7. 技术栈选择

| 组件 | 选择 | 理由 |
|------|------|------|
| Agent 框架 | Claude Agent SDK (Python) | 原生支持，功能完整 |
| MCP 工具 | In-process MCP Server | 简化部署，低延迟 |
| API 框架 | FastAPI | 异步支持，与 SDK 契合 |
| SSH 执行 | Paramiko (复用现有) | 已有稳定实现 |
| 配置管理 | YAML | 与现有工具一致 |

---

## 8. 参考资料

- Claude Agent SDK 官方文档: https://platform.claude.com/docs/en/agent-sdk/overview
- Claude Agent SDK Python: https://platform.claude.com/docs/en/agent-sdk/python
- Claude Agent SDK 示例: https://github.com/anthropics/claude-agent-sdk-demos
- Grafana HTTP API: https://grafana.com/docs/grafana/latest/developers/http_api/
- Loki LogQL: https://grafana.com/docs/loki/latest/query/
