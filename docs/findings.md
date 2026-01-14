# 调研发现记录

## 调研目标
调研网络故障排查 Agent 的实现方案、框架选择、以及内部数据源集成

---

## 1. 数据源清单

### 1.1 现有文档参考

| 文档 | 路径 | 内容 |
|------|------|------|
| **指标详解** | `troubleshooting-tools/docs/analysis/grafana/grafana_commonly_used_metrics.md` | CPU/OVS/网络/Loki 指标标签详解 |
| **完整清单** | `troubleshooting-tools/docs/analysis/grafana/grafana_metrics_inventory.md` | 5641 指标完整列表 |
| **综合报告** | `troubleshooting-tools/docs/analysis/grafana/grafana_metrics_report.md` | 数据源/Dashboard/集群分析 |
| **CPU统计脚本** | `troubleshooting-tools/scripts/grafana_cpu_stats.py` | OVS/网络 Cgroup CPU 查询工具 |

### 1.2 Grafana 数据源

**地址**: `http://192.168.79.79/grafana`
**认证**: Basic Auth (`o11y:HC!r0cks`)

| ID | 数据源 | 类型 | 说明 |
|----|--------|------|------|
| 1 | VictoriaMetrics | Prometheus | 主指标存储 (5641 指标) |
| 2 | Clickhouse | ClickHouse | 日志分析 |
| 3 | Loki | Loki | 日志聚合 |
| 8 | traffic-visualization-query-api | JSON API | 流量可视化 (默认) |

### 1.3 网络相关指标

| 类别 | 指标数 | 关键指标 | 用途 |
|------|--------|----------|------|
| **host_network_*** | 29 | `ping_time_ns`, `loss_rate`, `receive/transmit_speed_bitps` | 主机网络监控 |
| **node_network_*** | 36 | `receive/transmit_bytes_total`, `errs_total`, `drop_total` | 接口级流量/错误 |
| **node_netstat_*** | 42 | `Tcp_RetransSegs`, `TcpExt_ListenDrops`, `Udp_InErrors` | TCP/UDP 统计 |
| **elf_vm_network_*** | 12 | `receive/transmit_speed_bitps`, `drop`, `errors` | VM 网络监控 |
| **container_network_*** | 8 | `receive/transmit_bytes_total`, `dropped_total` | 容器网络 |
| **openvswitch_*** | 9 | `ovs_async_counter`, `ovs_vlog_counter` | OVS 内部计数 |

### 1.4 告警规则 (82 条)

**网络相关告警 (17 条)**:
- `everoute_service_unavailable` - 网络虚拟化服务不可用
- `everoute_license_*` - DFW/LB/VPC 许可证告警
- `alert_cgroup_*__smtx-network*` - 网络服务资源告警

**缺失告警 (需 Agent 补充)**:
- `host_network_ping_time_ns` 延迟阈值
- `host_network_loss_rate` 丢包率阈值
- VM 网络性能告警
- OVS datapath 异常

### 1.5 Loki 日志标签

| 标签 | 值数量 | 说明 |
|------|--------|------|
| `log_type` | 4 | cron, maillog, messages, secure |
| `namespace` | 7 | K8s 命名空间 |
| `service` | 78 | 应用服务 |
| `unit` | 123 | SystemD 单元 |

### 1.6 traffic-visualization-query-api

**后端**: `http://queryloader:8011`

| 端点 | 返回数据 |
|------|----------|
| `/query/overview/overall_flow_count` | 流量总数 |
| `/query/overview/overall_flow_trend` | 流量趋势 |
| `/query/overview/overall_bandwidth_trend` | 带宽趋势 |
| `/query/overview/top_n_rtt_avg_trend` | Top N RTT |

---

## 2. 测量工具清单

**路径**: `troubleshooting-tools/measurement-tools/`
**总计**: 84 工具 (59 Python + 20 bpftrace + 5 Shell)

| 目录 | 工具数 | 用途 | 关键工具 |
|------|--------|------|----------|
| **cpu/** | 8 | CPU 调度/NUMA/IRQ | `offcputime-ts.py`, `sched_latency_monitor.sh` |
| **kvm-virt-network/** | 22 | KVM 虚拟化网络 | vhost/virtio/tun 延迟测量 |
| **linux-network-stack/** | 8 | 协议栈追踪 | conntrack, ip_defrag, 丢包监控 |
| **ovs/** | 6 | OVS 性能 | upcall 延迟、megaflow、丢包 |
| **performance/** | 34 | 延迟测量 | 系统/VM 网络延迟、TCP 性能 |
| **other/** | 6 | 杂项追踪 | ARP、CT invalid、qdisc |

### 关键工具详情

**性能测量 (performance/)**:
- `system_network_latency_summary.py` - 系统网络栈延迟直方图
- `vm_network_latency_summary.py` - VM 网络栈延迟直方图
- `tcp_connection_analyzer.py` - TCP 连接分析

**丢包监控 (linux-network-stack/packet-drop/)**:
- `kernel_drop_stack_stats_summary.py` - kfree_skb 丢包位置统计
- `icmp_drop_detector.py` - ICMP 丢包检测

**KVM 虚拟化 (kvm-virt-network/)**:
- `kvm_vhost_tun_latency_summary.py` - KVM→vhost→tun 完整路径延迟
- `vhost_queue_correlation_details.py` - vhost 队列关联分析

---

## 3. 框架选型

### 3.1 框架对比

| 框架 | 优势 | 劣势 | 适用场景 |
|------|------|------|----------|
| **Claude Agent SDK** | 原生 Claude、Subagent、MCP | 仅 Claude | 生产级单 Agent |
| LangGraph | 图工作流、检查点 | 学习曲线陡 | 复杂多步流程 |
| AutoGen | 事件驱动、并发 | v0.4 变更大 | 模拟推理 |
| CrewAI | 角色协作 | 灵活性低 | 角色分工 |

### 3.2 推荐方案

**纯 Claude Agent SDK + 分层 MCP 工具**

**理由**:
1. 快速 MVP 验证，无需学习 LangGraph
2. 原生 Subagent 支持四层职责分离
3. 工具封装保证关键约束 (receiver-first)
4. 与现有 skill (latency-analysis) 兼容
5. Prompt 修改即可快速迭代

---

## 4. 架构设计

### 4.1 四层诊断架构

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 4: 诊断分析层                                          │
│   - 测量数据分析、根因定位、诊断报告生成                     │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: 精确测量层                                          │
│   - BCC/eBPF 工具执行、多点协同测量                         │
│   - 关键约束: receiver-first 时序                           │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: 环境感知层                                          │
│   - 问题类型识别、环境信息收集、工具部署决策                 │
├─────────────────────────────────────────────────────────────┤
│ Layer 1: 基础监控层（混合数据源）                            │
│   - Grafana/Loki 告警和日志                                  │
│   - 节点本地日志（SSH 读取 pingmesh 等）                     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 MCP 工具层设计

| 层级 | 工具 | 功能 |
|------|------|------|
| **L1** | `grafana_query_metrics` | PromQL 查询 |
| **L1** | `loki_query_logs` | LogQL 查询 |
| **L1** | `read_pingmesh_logs` | SSH 读取节点日志 |
| **L2** | `collect_vm_network_env` | VM 网络拓扑收集 |
| **L2** | `collect_system_network_env` | 系统网络拓扑收集 |
| **L3** | `execute_coordinated_measurement` | 协同测量 (封装 receiver-first) |
| **L3** | `measure_vm_latency_breakdown` | VM 延迟分段测量 |
| **L4** | `analyze_latency_segments` | 延迟分段归因 |
| **L4** | `generate_diagnosis_report` | 报告生成 |

### 4.3 可复用组件

| 组件 | 路径 | 复用方式 |
|------|------|----------|
| network_env_collector | test/tools/ | L2 环境收集基础 |
| ssh_manager | test/automate-performance-test/src/core/ | 远程执行连接池 |
| bpf_remote_executor | test/tools/ | L3 远程 BPF 执行 |
| latency-analysis skill | .claude/skills/ | L4 分析参考 |
| grafana_cpu_stats.py | scripts/ | L1 查询参考 |

---

## 5. 节点本地日志

| 日志 | 路径 | 说明 |
|------|------|------|
| network-high-latency | `/var/log/zbs/` | 网络高延迟日志 |
| l2ping | `/var/log/zbs/` | L2 ping 日志 |
| pingmesh | `/var/log/zbs/` | 网格 ping 统计 |

**访问方式**: SSH 读取节点本地文件

---

## 更新日志

### 2026-01-14
- 确认节点本地日志路径: `/var/log/zbs/` (network-high-latency, l2ping, pingmesh)

### 2026-01-13
- 初始化调研文档
- 完成现有项目分析
- 整理 Grafana 数据源和指标 (5641 指标)
- 整理测量工具清单 (84 工具)
- 完成框架选型分析 (推荐 Claude Agent SDK)
- 完成四层架构设计
