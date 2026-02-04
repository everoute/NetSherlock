---
name: system-network-path-tracer
description: |
  Detect and localize system (host-to-host) network packet drops and measure
  internal latency using dual-endpoint BPF tracing. Deploys system_icmp_path_tracer
  to sender and receiver hosts, tracing the full phy→stack→phy path to identify
  where ICMP packets are dropped or delayed.

  Supports multi-protocol tracing (ICMP/TCP/UDP) with configurable focus modes
  for drop detection vs latency measurement.

  Trigger keywords: system packet drop, host drop detection, network drop,
  packet loss location, system network latency, host internal latency,
  系统丢包检测, 主机丢包定界, 系统网络延迟

allowed-tools: Read, Write, Bash, Skill
---

# System Network Packet Drop & Latency Skill (v2)

## 执行

```bash
python3 .claude/skills/system-network-path-tracer/scripts/measure.py $ARGUMENTS
```

如果参数不完整，从对话上下文获取或向用户询问。

## 参数说明

### 类型 1: L2 环境参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--sender-host-ssh` | Sender Host SSH 地址 | `smartx@192.168.70.32` |
| `--sender-ip` | Sender Host IP (ping 发起方) | `192.168.70.32` |
| `--sender-phy-if` | Sender Host 物理网卡 | `enp24s0f0np0` |
| `--receiver-host-ssh` | Receiver Host SSH 地址 | `smartx@192.168.70.31` |
| `--receiver-ip` | Receiver Host IP (ping 接收方) | `192.168.70.31` |
| `--receiver-phy-if` | Receiver Host 物理网卡 | `enp24s0f0np0` |
| `--local-tools-path` | BPF 工具本地路径 | `~/workspace/troubleshooting-tools/measurement-tools` |

### 类型 2: 协议与模式参数 (v2 新增)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--protocol` | icmp | 协议类型: icmp (MVP), tcp, udp (预留) |
| `--direction` | rx | ICMP 方向: rx (本地响应), tx (本地发起) |
| `--focus` | drop | 测量焦点: drop (丢包定界), latency (延迟定界) |
| `--output-mode` | verbose | 输出模式: verbose (每包), stats (统计) |
| `--port` | (none) | TCP/UDP 端口过滤 (预留) |
| `--stats-interval` | 5 | stats 模式统计间隔 (秒) (预留) |

### 类型 3: 全局配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--duration` | 30 | 测量持续时间 (秒) |
| `--generate-traffic` | false | 生成 ping 测试流量 |
| `--ping-interval` | 1 | ping 间隔 (秒) |
| `--timeout-ms` | 1000 | 丢包超时判定 (ms) |
| `--skip-deploy` | false | 跳过工具部署 |
| `--skip-validate` | false | 跳过 SSH 验证 |
| `--output-dir` | auto | 输出目录 |
| `--json-only` | false | 只输出 JSON |

## 测量架构

部署 system_*_path_tracer 工具到 2 台主机，每台监控本机的 phy→stack→phy 路径：

| # | 位置 | 工具 | --src-ip | --dst-ip | 追踪内容 |
|---|------|------|----------|----------|----------|
| 1 | Receiver Host | system_*_path_tracer.py | SENDER_IP | RECEIVER_IP | A→B 请求的接收和回复路径 (主要) |
| 2 | Sender Host | system_*_path_tracer.py | RECEIVER_IP | SENDER_IP | B→A 流量路径 (反向/双向) |

### 协议路径

```
ICMP RX (本地响应):
  phy RX → icmp_rcv → ip_send_skb → phy TX

ICMP TX (本地发起):
  ip_send_skb → phy TX → [network] → phy RX → ping_rcv

TCP/UDP (双向, 预留):
  Inbound:  phy RX → proto_rcv (含 OVS)
  Outbound: proto_send → phy TX (含 OVS)
```

### ICMP RX 模式 4 段追踪路径 (默认)

```
Physical NIC                    Kernel Protocol Stack
     │                                    │
     ▼                                    ▼
[0] ReqRX@phy ─── OVS datapath ───→ [1] ReqRcv@stack (icmp_rcv)
     (netif_receive_skb)                  │
                                          │ generate reply
                                          ▼
[3] RepTX@phy ←── OVS datapath ──── [2] RepSnd@stack (ip_send_skb)
     (net_dev_xmit)
```

### ICMP TX 模式 4 段追踪路径

```
Kernel Protocol Stack                   Physical NIC
       │                                     │
       ▼                                     ▼
[0] ReqSnd@stack ─── OVS datapath ───→ [1] ReqTX@phy
     (ip_send_skb)                           │
                                             │ network RTT
                                             ▼
[3] RepRcv@stack ←── OVS datapath ──── [2] RepRX@phy
     (ping_rcv)                         (netif_receive_skb)
```

### 丢包类型

**ICMP RX 模式:**

| 丢包类型 | 阶段 | 含义 |
|----------|------|------|
| req_internal (drop_0_1) | Has [0], missing [1] | 请求在 OVS/内核路径中被丢弃 |
| stack_no_reply (drop_1_2) | Has [1], missing [2] | 协议栈未生成回复 |
| rep_internal (drop_2_3) | Has [2], missing [3] | 回复在 OVS/内核路径中被丢弃 |

**ICMP TX 模式:**

| 丢包类型 | 阶段 | 含义 |
|----------|------|------|
| req_internal (drop_0_1) | Has [0], missing [1] | 请求在发送路径被丢弃 |
| external (drop_1_2) | Has [1], missing [2] | 外部丢包 (网络或对端未响应) |
| rep_internal (drop_2_3) | Has [2], missing [3] | 回复在接收路径被丢弃 |

### 延迟段

**ICMP RX 模式:**

| 段名 | 计算 | 含义 |
|------|------|------|
| ReqPath | [1] - [0] | phy NIC → icmp_rcv (含 OVS 转发) |
| Stack | [2] - [1] | icmp_rcv → ip_send_skb (协议栈处理) |
| RepPath | [3] - [2] | ip_send_skb → phy TX (含 OVS 转发) |
| Total | [3] - [0] | 完整内部往返 |

**ICMP TX 模式:**

| 段名 | 计算 | 含义 |
|------|------|------|
| ReqPath | [1] - [0] | ip_send_skb → phy TX (出向) |
| External | [2] - [1] | phy TX → phy RX (网络 RTT + 对端处理) |
| RepPath | [3] - [2] | phy RX → ping_rcv (入向) |
| Total | [3] - [0] | 完整往返含网络 |

## 输出

### JSON 输出

```json
{
  "status": "success",
  "measurement_dir": "./measurement-20260203-143000",
  "log_files": ["sender-host.log", "receiver-host.log"],
  "protocol": "icmp",
  "direction": "rx",
  "focus": "latency",
  "duration": 30
}
```

### 分析

测量完成后，根据需要使用对应的分析 skill：

**延迟分析** - 使用 `system-network-latency-analysis`:
```bash
python3 .claude/skills/system-network-latency-analysis/scripts/generate_report.py <measurement_dir>
```

延迟分析报告包含：
- 7 段延迟分解 (A/C/D/E/F/J/G)
- 3 层归因表 (Sender Host / Receiver Host / Physical Network)
- 端到端数据路径图
- 数据一致性验证

**丢包分析** - 使用 `system-network-drop-analysis`:
```bash
python3 .claude/skills/system-network-drop-analysis/scripts/analyze_drops.py <measurement_dir>
```

丢包分析报告包含：
- 丢包位置归因 (Sender/Receiver/Network)
- 丢包模式分析 (突发/偶发)
- 丢包事件时间线
- 诊断建议

### Focus 模式说明

- **`--focus drop`**: 优化丢包检测追踪
- **`--focus latency`**: 优化延迟分段追踪

## MVP 范围

| 协议 | 状态 | 说明 |
|------|------|------|
| ICMP | ✅ 完整实现 | RX/TX 模式，verbose 输出 |
| TCP | ⏳ 预留接口 | 后续实现 |
| UDP | ⏳ 预留接口 | 后续实现 |
