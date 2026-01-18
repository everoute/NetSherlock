# 网络故障排查 Agent 调研计划

## 目标
调研并选择合适的框架和架构，设计一个 AI 驱动的网络故障排查 Agent，整合内部 Grafana 监控数据源。

## 当前阶段
Phase 1: 调研完成 ✅

---

# Part 1: 已有数据源清单

本部分整理 Agent 可用的监控数据源，**不包含** eBPF 测量工具（测量工具在 Part 3）。

## 1.1 现有文档参考

| 文档 | 路径 | 内容 |
|------|------|------|
| **指标详解** | `troubleshooting-tools/docs/analysis/grafana/grafana_commonly_used_metrics.md` | CPU/OVS/网络/Loki 指标标签详解 |
| **完整清单** | `troubleshooting-tools/docs/analysis/grafana/grafana_metrics_inventory.md` | 5641 指标完整列表 |
| **综合报告** | `troubleshooting-tools/docs/analysis/grafana/grafana_metrics_report.md` | 数据源/Dashboard/集群分析 |
| **CPU统计脚本** | `troubleshooting-tools/scripts/grafana_cpu_stats.py` | OVS/网络 Cgroup CPU 查询工具 |

## 1.2 Grafana 数据源概览

**地址**: `http://192.168.79.79/grafana`
**认证**: Basic Auth (`o11y:HC!r0cks`)

| ID | 数据源 | 类型 | 说明 |
|----|--------|------|------|
| 1 | VictoriaMetrics | Prometheus | 主指标存储 (5641 指标) |
| 2 | Clickhouse | ClickHouse | 日志分析 |
| 3 | Loki | Loki | 日志聚合 |
| 8 | **traffic-visualization-query-api** | JSON API | 流量可视化 (默认) |

## 1.3 网络相关指标

| 类别 | 指标数 | 关键指标 | 用途 |
|------|--------|----------|------|
| **host_network_*** | 29 | `ping_time_ns`, `loss_rate`, `receive/transmit_speed_bitps` | 主机网络监控 |
| **node_network_*** | 36 | `receive/transmit_bytes_total`, `errs_total`, `drop_total` | 接口级流量/错误 |
| **node_netstat_*** | 42 | `Tcp_RetransSegs`, `TcpExt_ListenDrops`, `Udp_InErrors` | TCP/UDP 统计 |
| **elf_vm_network_*** | 12 | `receive/transmit_speed_bitps`, `drop`, `errors` | VM 网络监控 |
| **container_network_*** | 8 | `receive/transmit_bytes_total`, `dropped_total` | 容器网络 |
| **openvswitch_*** | 9 | `ovs_async_counter`, `ovs_vlog_counter` | OVS 内部计数 |

## 1.4 告警规则 (关键网络告警)

| 告警 | 指标 | 阈值 | 触发诊断流程 |
|------|------|------|--------------|
| 存储网络高延迟 | `host_network_ping_time_ns` | > 5ms | 系统网络延迟诊断 |
| 网络丢包 | `host_network_loss_rate` | > 1% | 系统网络丢包诊断 |
| VM vnet 丢包 | `elf_vm_network_drop` | > 0 | VM 网络丢包诊断 |
| OVS CPU 高 | `host_service_cpu_usage_percent{_service="ovs_vswitchd_svc"}` | > 80% | OVS 性能诊断 |
| 网络 Cgroup CPU 高 | `cpu_cpuset_state_percent{_cpu="cpuset:/zbs/network"}` | idle < 20% | CPU 调度诊断 |

## 1.5 节点本地日志 (SSH 读取)

| 日志 | 路径 | 说明 | 触发场景 |
|------|------|------|----------|
| network-high-latency | `/var/log/zbs/` | 网络高延迟事件 | 延迟告警 |
| l2ping | `/var/log/zbs/` | L2 ping 探测结果 | 连通性问题 |
| pingmesh | `/var/log/zbs/` | 网格 ping 统计 | 全网延迟/丢包 |

## 1.6 Loki 日志标签

| 标签 | 值数量 | 网络相关值 |
|------|--------|------------|
| `service` | 78 | `elf-vm-monitor`, `ovs-*` |
| `unit` | 123 | `NetworkManager.service`, `ovs-vswitchd.service` |
| `namespace` | 7 | `traffic-visualization` |

## 1.7 L1 数据源覆盖差距与自定义监控需求

### 当前覆盖差距分析

| 领域 | 现有覆盖 | 差距 |
|------|----------|------|
| **存储网络** | ✅ 完善 | `host_network_*` (pingmesh), 延迟/丢包/带宽告警 |
| **VM 网络** | ⚠️ 较弱 | `elf_vm_network_*` 仅有基础流量/丢包，缺乏细粒度分段监控 |
| **管理网络** | ❌ 缺失 | 无持续监控，依赖被动发现 |
| **业务网络** | ❌ 缺失 | 无持续监控，依赖用户反馈 |

### VM 网络监控差距

| 缺失项 | 说明 | 影响 |
|--------|------|------|
| vnet 口细粒度统计 | 仅有 `elf_vm_network_drop`，无 error/queue depth | 无法区分丢包原因 |
| virtio/vhost 性能指标 | 无 ring buffer 利用率、vhost 处理延迟 | L1 无法预警虚拟化瓶颈 |
| VM 网络延迟分段 | 无持续测量，只能触发式 L3 测量 | 无法建立基线，难以发现渐进劣化 |
| vhost worker CPU | 无独立监控 (仅汇总在 qemu 进程) | 难以定位 vhost 过载 |

### 非存储网络监控差距

| 缺失项 | 说明 | 影响 |
|--------|------|------|
| 管理网络 pingmesh | 无管理 IP 间的持续探测 | 管理网络故障被动发现 |
| 业务网络 pingmesh | 无业务 IP 间的持续探测 | 业务网络故障依赖用户反馈 |
| OVS 性能指标 | `openvswitch_*` 仅有 vlog/async 计数，无 upcall 率、flow table 细节 | 无法预警 OVS 慢速路径问题 |
| 多网络延迟对比 | 无法区分存储/管理/业务网络各自延迟 | 故障定界困难 |

### 需要引入的自定义监控

#### 短期方案：现有 L3 工具降级为持续监控

| 工具 | 降级用途 | 暴露指标 |
|------|----------|----------|
| `phy_net_drop_detector.py` | 轻量模式持续运行 | `custom_phy_net_drop_total{nic, reason}` |
| `vhost_queue_correlation.py` | 定期采样 | `custom_vhost_ring_util{vm, vnet}` |
| `ovs_upcall_latency_summary.py` | 周期统计 | `custom_ovs_upcall_rate`, `custom_ovs_upcall_latency_p99` |
| `kernel_drop_stack_stats_summary.py` | 持续汇总 | `custom_kernel_drop_total{location}` |

#### 长期方案：专用 Exporter 开发

| Exporter | 目标 | 指标示例 |
|----------|------|----------|
| **vhost-exporter** | VM 虚拟化网络性能 | `vhost_ring_avail_count`, `vhost_handle_latency_ns`, `vhost_worker_cpu_percent` |
| **ovs-perf-exporter** | OVS 数据路径性能 | `ovs_upcall_rate`, `ovs_megaflow_hit_rate`, `ovs_flow_table_size` |
| **multi-net-pingmesh** | 多网络平面探测 | `pingmesh_latency_ns{network="management\|business\|storage"}` |

#### 告警规则扩展

| 新增告警 | 指标 | 阈值 | 触发诊断 |
|----------|------|------|----------|
| vhost ring 高水位 | `vhost_ring_avail_count` | < 20% | virtio/vhost 诊断 |
| vhost 延迟高 | `vhost_handle_latency_ns` | P99 > 1ms | VM 网络延迟诊断 |
| OVS upcall 率高 | `ovs_upcall_rate` | > 1000/s | OVS 慢速路径诊断 |
| 管理网络延迟 | `pingmesh_latency_ns{network="management"}` | > 5ms | 管理网络诊断 |
| 业务网络丢包 | `pingmesh_loss_rate{network="business"}` | > 0.1% | 业务网络丢包诊断 |

### 实施优先级

| 优先级 | 项目 | 理由 |
|--------|------|------|
| **P0** | OVS upcall 持续监控 | 影响所有网络流量，当前完全盲区 |
| **P0** | VM vnet drop/error 细分 | 区分丢包原因的关键 |
| **P1** | vhost 性能指标 | VM 网络延迟问题定位必需 |
| **P1** | 多网络 pingmesh | 管理/业务网络持续可见性 |
| **P2** | 完整 vhost-exporter | 长期 VM 网络监控能力 |

---

# Part 2: 问题类型与诊断方法论

## 2.1 核心问题类型（MVP 范围）

### 2.1.1 丢包问题

**数据路径** (VM 网络):
```
VM1 → virtio-net → vhost-net → TUN → OVS kernel → [物理网络] → OVS kernel → TUN → vhost-net → virtio-net → VM2
```

**诊断流程**:
```
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 1: 预处理 (辅助信息，非最终结论)                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ • 网卡统计: 物理网卡 drop/error 增量、vnet 口 drop 增量                  │
│ • Kernel 统计: /proc/net/dev, netstat -s                               │
│ • 目的: 快速排除明显问题点，缩小范围                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 2: 丢包分段界定                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ 工具: icmp_drop_detector (当前 ICMP，可扩展 TCP/UDP)                    │
│ 输出: 丢包发生的分段位置                                                 │
│   - VM 内部 (guest 问题)                                                │
│   - Host 内部 (virtio→vhost→TUN→OVS)                                   │
│   - 物理网络 (交换机/链路)                                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 3: 测量结果分析                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ 场景 A: 物理网卡 && vnet 无丢包增量，kernel_drop 无丢包                  │
│   → 丢包在物理网络或对端 VM 内部                                         │
│                                                                         │
│ 场景 B: vnet 有丢包，物理网卡无丢包                                      │
│   → 丢包在 Host 内部 (virtio/vhost/TUN/OVS)                             │
│   → 转入阶段 4 细化定位                                                  │
│                                                                         │
│ 场景 C: 物理网卡有丢包                                                   │
│   → 物理网络问题 (MTU/带宽/交换机)                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 4: 例外场景深度测量 (按需触发)                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ OVS 慢速路径丢包:                                                        │
│   - ovs_upcall_latency_summary: upcall 延迟分布                         │
│   - queue_userspace_packet_retval: 用户态处理结果                       │
│   - ovs-kernel-module-drop-monitor: OVS 内核模块丢包                    │
│                                                                         │
│ virtio/vhost 丢包:                                                      │
│   - vhost_queue_correlation: 队列关联分析                               │
│   - virtio ring buffer 状态                                             │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.1.2 延迟问题

**诊断流程**:
```
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 1: 预处理 (资源利用检查)                                            │
├─────────────────────────────────────────────────────────────────────────┤
│ VM 网络:                                                                │
│   - VM 进程 (qemu) CPU 利用率                                           │
│   - vhost worker CPU 利用率                                             │
│   - 网络 Cgroup CPU (cpuset:/zbs/network)                               │
│                                                                         │
│ 系统网络:                                                                │
│   - 探测发送进程 CPU                                                    │
│   - ksoftirqd CPU                                                       │
│   - OVS 进程 CPU                                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 2: 延迟分段测量                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ VM 网络 (vm_network_latency_summary):                                   │
│   Stage 1: virtio TX → vhost handle                                    │
│   Stage 2: vhost handle → TUN sendmsg                                  │
│   Stage 3: TUN → OVS kernel                                            │
│   Stage 4: [物理网络传输]                                               │
│   Stage 5: OVS kernel → TUN receive                                    │
│   Stage 6: TUN → vhost                                                 │
│   Stage 7: vhost → virtio RX                                           │
│                                                                         │
│ 系统网络 (system_network_latency_summary):                              │
│   Stage 1: 应用层 → socket                                             │
│   Stage 2: socket → OVS internal port                                  │
│   Stage 3: OVS datapath                                                │
│   Stage 4: 物理网卡 TX                                                  │
│   Stage 5: [物理网络传输]                                               │
│   Stage 6-8: 反向路径                                                   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 3: 延迟归因分析                                                     │
├─────────────────────────────────────────────────────────────────────────┤
│ 输入: 各阶段延迟直方图 (P50/P95/P99/Max)                                │
│ 分析:                                                                   │
│   - 哪个阶段贡献最大延迟?                                               │
│   - 延迟分布是否有长尾? (调度问题 vs 处理问题)                          │
│   - 与基线对比是否异常?                                                 │
│                                                                         │
│ 输出: 延迟根因定位 + 建议                                               │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 阶段 4: 例外场景深度测量 (按需触发)                                       │
├─────────────────────────────────────────────────────────────────────────┤
│ vhost 调度延迟:                                                          │
│   - kvm_vhost_tun_latency_summary: 完整 KVM→vhost→TUN 路径             │
│   - ksoftirqd_sched_latency: 软中断调度延迟                             │
│                                                                         │
│ OVS 慢速路径延迟:                                                        │
│   - ovs_upcall_latency_summary: upcall 处理延迟                        │
│   - megaflow 效率分析                                                   │
│                                                                         │
│ TCP 层延迟:                                                              │
│   - tcp_connection_analyzer: 连接状态分析                               │
│   - tcp_rtt_inflight_hist: RTT 与在途数据关联                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## 2.2 其他问题类型 (扩展范围)

以下问题类型同样适用 **L1 监控/告警/日志 → L2 环境收集 → L3 深度测量 → L4 分析** 的多层架构：

### 2.2.1 吞吐量/带宽下降

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | `host_network_transmit_speed_bitps` < 预期 | 持续监控带宽 |
| | `elf_vm_network_transmit_speed_bitps` 低 | VM 网络吞吐 |
| **L1 预检** | NIC link speed, bond 状态, OVS port 统计 | 排除配置问题 |
| **L3 测量** | virtio ring 利用率, vhost worker CPU, NIC queue depth | 瓶颈定位 |
| **L4 分析** | 瓶颈点: virtio ring 满? vhost CPU 饱和? NIC 背压? | 根因 |

### 2.2.2 TCP 重传/拥塞

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | `node_netstat_Tcp_RetransSegs` 速率高 | TCP 重传监控 |
| | 连接 reset 率, `TcpExt_ListenDrops` | 连接异常 |
| **L1 预检** | RTT 基线, 丢包率基线 | 网络质量 |
| **L3 测量** | `tcp_connection_analyzer`, 拥塞窗口追踪 | TCP 状态分析 |
| **L4 分析** | 区分: 网络丢包 vs 接收端消费慢 vs 发送端限速 | 根因 |

### 2.2.3 OVS 慢速路径 (高 Upcall 率)

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | `openvswitch_ovs_async_counter` (upcall 计数) | upcall 监控 |
| | ovs-vswitchd CPU 高 | 资源消耗 |
| **L1 预检** | Flow table 大小, megaflow 统计 | 流表状态 |
| **L3 测量** | `ovs_upcall_latency_summary`, `ovs_userspace_megaflow` | 慢速路径分析 |
| **L4 分析** | 流表爆炸? 通配匹配低效? 新流风暴? | 根因 |

### 2.2.4 virtio/vhost 资源争用

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | VM 网络延迟高但无丢包 | 性能异常 |
| | vhost worker CPU 高 | 资源饱和 |
| **L1 预检** | vhost 线程 CPU 亲和性, NUMA 拓扑, vCPU pinning | 配置检查 |
| **L3 测量** | `vhost_queue_correlation`, virtio ring buffer 占用 | 队列分析 |
| **L4 分析** | Ring buffer 满? vhost 过载? IRQ 风暴? | 根因 |

### 2.2.5 Bond 故障切换/抖动

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | Bond member 状态变化 (日志) | 链路事件 |
| | 网络连通性抖动 | pingmesh |
| **L1 预检** | Bond 配置, member NIC 状态 | 配置检查 |
| **L3 测量** | 故障切换时序, 切换期间丢包 | 切换分析 |
| **L4 分析** | 链路抖动原因, LACP 问题, 交换机侧问题 | 根因 |

### 2.2.6 VXLAN/Overlay 问题

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | 跨节点 VM 延迟高 | 延迟监控 |
| | 分片错误 | MTU 问题 |
| **L1 预检** | VXLAN 隧道状态, MTU 配置 | 配置检查 |
| **L3 测量** | `skb_frag_list_watcher`, VXLAN 封装/解封时序 | 封装分析 |
| **L4 分析** | 分片开销? 隧道查找延迟? | 根因 |

### 2.2.7 CPU/调度争用 (网络处理)

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | `cpu_cpuset_state_percent{_cpu="cpuset:/zbs/network"}` idle 低 | Cgroup CPU |
| | ksoftirqd CPU 高 | 软中断 |
| **L1 预检** | CPU 亲和性设置, NUMA 映射 | 配置检查 |
| **L3 测量** | `ksoftirqd_sched_latency`, `offcputime-ts` | 调度分析 |
| **L4 分析** | CPU steal? IRQ 不均衡? ksoftirqd 饥饿? | 根因 |

### 2.2.8 ARP/邻居表问题

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | 间歇性连通性问题 | pingmesh |
| | ARP 超时错误 (日志) | 系统日志 |
| **L1 预检** | ARP 表大小, neighbor cache 状态 | 状态检查 |
| **L3 测量** | `trace-abnormal-arp`, neighbor 状态追踪 | ARP 分析 |
| **L4 分析** | ARP 表满? 超时? ARP 风暴? | 根因 |

### 2.2.9 Conntrack/NAT 问题

| 层级 | 数据源/工具 | 说明 |
|------|-------------|------|
| **L1 触发** | 连接建立失败 | 连接监控 |
| | conntrack 表满 (日志) | 系统日志 |
| **L1 预检** | Conntrack 表大小, NAT 规则 | 配置检查 |
| **L3 测量** | `trace_conntrack`, conntrack 条目生命周期 | 连接追踪 |
| **L4 分析** | Conntrack 耗尽? 僵尸条目? NAT 冲突? | 根因 |

---

# Part 3: 测量工具与环境关联

## 3.1 工具路径映射

**路径**: `troubleshooting-tools/measurement-tools/`
**总计**: 84 工具 (59 Python + 20 bpftrace + 5 Shell)

### 按诊断阶段分类

| 阶段 | 工具类型 | 工具 | 输入参数来源 |
|------|----------|------|--------------|
| **预处理** | 网卡统计 | `iface_netstat.py` | L2: 接口名 |
| | 进程 CPU | `cpu_monitor.sh` | L2: PID (qemu/vhost/ovs) |
| **丢包分段** | ICMP 丢包 | `icmp_drop_detector.py` | L2: src/dst IP, 接口 |
| | kernel 丢包 | `kernel_drop_stack_stats_summary.py` | L2: 接口名, IP 过滤 |
| | 物理网卡丢包 | `phy_net_drop_detector.py` | L2: 物理网卡名 |
| | OVS 丢包 | `ovs-kernel-module-drop-monitor.py` | L2: OVS bridge |
| **延迟分段** | VM 延迟 | `vm_network_latency_summary.py` | L2: vnet, phy-nic, src-ip |
| | 系统延迟 | `system_network_latency_summary.py` | L2: phy-nic, src-ip |
| | TCP 延迟 | `tcp_connection_analyzer.py` | L2: 连接四元组 |
| **例外深度** | OVS upcall | `ovs_upcall_latency_summary.py` | L2: src-ip, proto |
| | vhost 延迟 | `kvm_vhost_tun_latency_summary.py` | L2: vnet, flow |
| | 调度延迟 | `ksoftirqd_sched_latency_summary.py` | L2: CPU list |

### 工具输入参数矩阵

| 参数类型 | 参数示例 | 来源 | 获取方式 |
|----------|----------|------|----------|
| **节点信息** | mgt_ip, ssh_user, ssh_key | 告警 labels / 配置 | `instance` label 解析 |
| **VM 标识** | vm_uuid, vm_name | 告警 labels | `elf_vm_*` 指标 |
| **网络实体** | vnet 名, vhost PID | L2 收集 | `network_env_collector` |
| **OVS 拓扑** | bridge 名, port 名 | L2 收集 | `ovs-vsctl` 命令 |
| **物理网卡** | nic 名, bond 信息 | L2 收集 | `ip link`, `/sys/class/net` |
| **流量特征** | src/dst IP, port, proto | 告警 / 用户输入 | 告警 annotation |

## 3.2 环境收集抽象层 (L2)

### 目标
从 L1 告警/日志中提取最小输入，自动 bootstrap 完整环境信息。

### 最小输入 → 完整环境

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 输入源                                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│ 告警 Labels:                                                             │
│   instance: "192.168.1.10:9100"  → 节点 IP                              │
│   vm_name: "vm-123"              → VM 标识                              │
│   alertname: "VnetPacketDrop"    → 问题类型                             │
│                                                                         │
│ 告警 Annotations:                                                        │
│   summary: "vnet0 drop rate > 1%"                                       │
│   src_ip: "10.0.0.1"             → 可选流量特征                         │
│   dst_ip: "10.0.0.2"                                                    │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ L2 环境收集器 (network_env_collector 增强版)                             │
├─────────────────────────────────────────────────────────────────────────┤
│ 输入: node_ip, vm_name (或 vm_uuid)                                     │
│                                                                         │
│ 步骤 1: SSH 连接节点                                                    │
│   - 使用 ssh_manager 连接池                                             │
│   - 认证方式从配置获取                                                  │
│                                                                         │
│ 步骤 2: VM 信息收集 (如适用)                                            │
│   - virsh dominfo: vCPU, 内存                                          │
│   - virsh dumpxml: 网络设备配置                                         │
│   - qemu PID, vhost worker TID                                         │
│                                                                         │
│ 步骤 3: 网络拓扑收集                                                    │
│   - vnet 设备: 名称, MAC, 所属 bridge                                  │
│   - OVS 拓扑: bridge, port, ofport                                     │
│   - 物理网卡: 名称, bond 信息, member 列表                              │
│                                                                         │
│ 步骤 4: 输出结构化环境数据                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 输出: NetworkEnvironment                                                 │
├─────────────────────────────────────────────────────────────────────────┤
│ {                                                                       │
│   "node": {                                                             │
│     "mgt_ip": "192.168.1.10",                                          │
│     "ssh_user": "root",                                                 │
│     "ssh_key_path": "/path/to/key"                                     │
│   },                                                                    │
│   "vm": {                                                               │
│     "uuid": "xxx-xxx",                                                  │
│     "name": "vm-123",                                                   │
│     "qemu_pid": 12345,                                                  │
│     "vhost_tids": [12346, 12347]                                       │
│   },                                                                    │
│   "network": {                                                          │
│     "vnet": "vnet0",                                                    │
│     "ovs_bridge": "br-int",                                            │
│     "ovs_port": "vnet0",                                               │
│     "ofport": 10,                                                       │
│     "phy_nic": "bond0",                                                │
│     "bond_members": ["enp94s0f0np0", "enp94s0f1np1"]                   │
│   },                                                                    │
│   "flow": {                                                             │
│     "src_ip": "10.0.0.1",                                              │
│     "dst_ip": "10.0.0.2",                                              │
│     "protocol": "icmp"                                                  │
│   }                                                                     │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

### 环境收集触发场景

| 触发源 | 最小输入 | 需要收集 |
|--------|----------|----------|
| Grafana 告警 | `instance` + `alertname` | 完整 node 环境 |
| Grafana 告警 (VM) | `instance` + `vm_name` | node + VM 环境 |
| CLI 手动 | node IP + VM name | 完整环境 |
| Pingmesh 日志 | src_node + dst_node | 双端环境 |

## 3.3 L1 → L3 数据流关联

### 告警到测量的完整链路

```
┌─────────────────────────────────────────────────────────────────────────┐
│ L1: Grafana 告警触发                                                     │
│ ─────────────────                                                       │
│ alertname: "HostNetworkHighLatency"                                     │
│ labels:                                                                  │
│   instance: "192.168.1.10:9100"                                         │
│   cluster: "prod-cluster-01"                                            │
│ annotations:                                                             │
│   summary: "host_network_ping_time_ns > 5000000 (5ms)"                  │
│   dst_host: "192.168.1.20"                                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 解析告警
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 问题分类 & 参数提取                                                      │
│ ────────────────────                                                    │
│ problem_type: "system_network_latency"                                  │
│ src_node: "192.168.1.10"                                                │
│ dst_node: "192.168.1.20"                                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ L2 环境收集
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 双端环境收集                                                             │
│ ────────────                                                            │
│ src_env = collect_system_network_env("192.168.1.10")                   │
│ dst_env = collect_system_network_env("192.168.1.20")                   │
│                                                                         │
│ 输出:                                                                   │
│   src: {phy_nic: "bond0", ovs_bridge: "br-storage", internal_port: ...}│
│   dst: {phy_nic: "bond0", ovs_bridge: "br-storage", internal_port: ...}│
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ 生成测量计划
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ MeasurementPlan                                                          │
│ ───────────────                                                         │
│ {                                                                       │
│   "type": "system_network_latency",                                    │
│   "receiver": {                                                         │
│     "node": "192.168.1.20",                                            │
│     "tool": "system_network_latency_summary.py",                       │
│     "args": {                                                           │
│       "phy_interface": "bond0",                                        │
│       "src_ip": "192.168.1.10",                                        │
│       "direction": "rx"                                                 │
│     }                                                                   │
│   },                                                                    │
│   "sender": {                                                           │
│     "node": "192.168.1.10",                                            │
│     "tool": "system_network_latency_summary.py",                       │
│     "args": {                                                           │
│       "phy_interface": "bond0",                                        │
│       "dst_ip": "192.168.1.20",                                        │
│       "direction": "tx"                                                 │
│     }                                                                   │
│   }                                                                     │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ L3 协同测量 (receiver-first)
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ execute_coordinated_measurement(plan)                                    │
│ ─────────────────────────────────────                                   │
│ 1. SSH 到 receiver (192.168.1.20)                                       │
│ 2. 启动 receiver 端工具，等待 ready                                     │
│ 3. SSH 到 sender (192.168.1.10)                                        │
│ 4. 启动 sender 端工具                                                   │
│ 5. 收集双端数据                                                         │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ L4 分析
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 延迟分段分析报告                                                         │
│ ────────────────                                                        │
│ 阶段延迟分布:                                                           │
│   Stage 1 (app→socket):     P50=10us  P95=20us   ← 正常                │
│   Stage 2 (socket→OVS):     P50=15us  P95=50us   ← 正常                │
│   Stage 3 (OVS datapath):   P50=100us P95=2000us ← 异常!               │
│   Stage 4 (phy TX):         P50=5us   P95=10us   ← 正常                │
│   ...                                                                   │
│                                                                         │
│ 根因定位: OVS datapath 阶段延迟异常                                     │
│ 建议: 检查 OVS flow 规则, 可能存在慢速路径处理                          │
│ 后续: 触发 OVS upcall 深度分析                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

# Part 4: 框架选型

## 4.1 推荐方案

**纯 Claude Agent SDK + 分层 MCP 工具**

**理由**:
1. 快速 MVP 验证，无需学习 LangGraph
2. 原生 Subagent 支持四层职责分离
3. 工具封装保证关键约束 (receiver-first)
4. 与现有 skill (latency-analysis) 兼容
5. Prompt 修改即可快速迭代

## 4.2 架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    Network Troubleshooting Agent                         │
│                       (Single Claude Agent)                              │
├─────────────────────────────────────────────────────────────────────────┤
│                          System Prompt                                   │
│  - 问题类型识别规则 (丢包/延迟/吞吐/...)                                │
│  - 分层诊断方法论 (L1→L2→L3→L4)                                        │
│  - 诊断流程约束 (预处理→分段界定→分析→例外处理)                         │
├─────────────────────────────────────────────────────────────────────────┤
│                         MCP Tool Layer                                   │
│  ┌───────────────┐ ┌───────────────┐ ┌───────────────┐                 │
│  │   L1 Tools    │ │   L2 Tools    │ │   L3 Tools    │                 │
│  │ - grafana_*   │ │ - env_collect │ │ - pre_check   │                 │
│  │ - loki_*      │ │ - bootstrap   │ │ - segment_*   │                 │
│  │ - read_logs   │ │               │ │ - deep_*      │                 │
│  └───────────────┘ └───────────────┘ └───────────────┘                 │
│  ┌───────────────┐                                                      │
│  │   L4 Tools    │                                                      │
│  │ - analyze_*   │                                                      │
│  │ - report_*    │                                                      │
│  └───────────────┘                                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                        External Systems                                  │
│  Grafana API │ Loki API │ SSH (节点) │ OVS │ KVM/QEMU                   │
└─────────────────────────────────────────────────────────────────────────┘
```

## 4.3 MCP 工具分类

### L1: 监控告警
| 工具 | 功能 |
|------|------|
| `grafana_query_metrics` | PromQL 查询 |
| `grafana_get_alerts` | 获取活跃告警 |
| `loki_query_logs` | LogQL 查询 |
| `read_node_logs` | SSH 读取节点日志 |

### L2: 环境收集
| 工具 | 功能 |
|------|------|
| `bootstrap_from_alert` | 从告警提取最小输入 |
| `collect_vm_env` | VM 网络环境收集 |
| `collect_system_env` | 系统网络环境收集 |
| `resolve_network_path` | 解析完整数据路径 |

### L3: 测量执行
| 工具 | 功能 |
|------|------|
| `pre_check_stats` | 预处理统计检查 |
| `segment_packet_drops` | 丢包分段界定 |
| `segment_latency` | 延迟分段测量 |
| `deep_ovs_analysis` | OVS 深度分析 |
| `deep_vhost_analysis` | vhost 深度分析 |

### L4: 分析报告
| 工具 | 功能 |
|------|------|
| `analyze_drop_location` | 丢包位置分析 |
| `analyze_latency_attribution` | 延迟归因分析 |
| `generate_diagnosis_report` | 生成诊断报告 |

---

# 调研进度

## 2026-01-14
- [x] 确认节点本地日志路径: `/var/log/zbs/`
- [x] 细化问题类型与诊断流程 (丢包/延迟)
- [x] Brainstorm 其他问题类型 (9 类)
- [x] 完善 L1→L2→L3 数据流关联
- [x] 环境收集抽象层设计
- [x] **L1 数据源覆盖差距分析**: VM 网络、非存储网络监控较弱，需引入自定义监控

## 2026-01-13
- [x] 发现现有 Grafana 文档
- [x] Grafana Explore 调研 Loki 标签
- [x] Dashboard 清单整理
- [x] 测量工具清单整理 (84 工具)
- [x] 架构设计 (纯 Claude Agent SDK)

## 调研结论摘要

### Part 1: 数据源
- **Grafana/VictoriaMetrics**: 5641 指标，网络相关 ~130 指标
- **Loki**: 4 log_type + 78 services + 123 units
- **节点本地日志**: `/var/log/zbs/` (network-high-latency, l2ping, pingmesh)
- **⚠️ 覆盖差距**: VM 网络 (virtio/vhost 指标缺失)、非存储网络 (管理/业务网络无 pingmesh) 监控较弱
- **待引入**: vhost-exporter, ovs-perf-exporter, multi-net-pingmesh (或短期用 L3 工具降级)

### Part 2: 问题类型
- **MVP 范围**: 丢包、延迟 (4 阶段诊断流程)
- **扩展范围**: 9 类其他问题 (吞吐、TCP、OVS、vhost、Bond、VXLAN、CPU、ARP、Conntrack)

### Part 3: 工具与环境
- **84 工具**按诊断阶段分类
- **环境收集抽象**: 从告警 bootstrap 完整环境
- **L1→L3 数据流**: 告警→解析→环境收集→测量计划→协同执行

### Part 4: 框架
- **推荐**: Claude Agent SDK + 分层 MCP
