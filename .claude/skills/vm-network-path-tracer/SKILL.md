---
name: vm-network-path-tracer
description: |
  Detect and localize VM network packet drops and measure internal latency
  at host boundaries using dual-endpoint BPF tracing. Deploys icmp_path_tracer
  to sender and receiver hosts, monitoring vnet↔phy interface boundaries to
  identify where VM traffic is dropped or delayed.

  Supports multi-protocol tracing (ICMP/TCP/UDP) with configurable focus modes
  for drop detection vs latency measurement.

  Trigger keywords: VM packet drop, VM drop detection, VM network drop,
  VM latency, vnet drop, VM traffic loss, VM丢包检测, 虚拟机丢包定界,
  VM网络延迟, 虚拟机网络路径追踪

allowed-tools: Read, Write, Bash, Skill
---

# VM Network Path Tracer Skill (v2)

## 执行

```bash
python3 .claude/skills/vm-network-path-tracer/scripts/measure.py $ARGUMENTS
```

## 参数说明

### 类型 1: L2 环境参数 (来自 network-env-collector skill)

| 参数 | 说明 | 示例 |
|------|------|------|
| `--sender-host-ssh` | Sender Host SSH 地址 | `smartx@192.168.70.32` |
| `--sender-vm-ip` | Sender VM IP (BPF 过滤) | `192.168.77.83` |
| `--receiver-vm-ip` | Receiver VM IP (BPF 过滤) | `192.168.76.244` |
| `--send-vnet-if` | Sender VM 的 TAP/vnet 接口 | `vnet35` |
| `--sender-phy-if` | Sender Host 物理网卡 | `enp24s0f0np0` |
| `--receiver-host-ssh` | Receiver Host SSH 地址 | `smartx@192.168.70.31` |
| `--recv-vnet-if` | Receiver VM 的 TAP/vnet 接口 | `vnet130` |
| `--receiver-phy-if` | Receiver Host 物理网卡 | `enp24s0f0np0` |
| `--local-tools-path` | BPF 工具本地路径 | `~/workspace/troubleshooting-tools/measurement-tools` |

### 类型 2: 协议与模式参数 (v2 新增)

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--protocol` | icmp | 协议类型: icmp (MVP), tcp, udp (预留) |
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
| `--sender-vm-ssh` | (可选) | Sender VM SSH (用于从 VM 内部生成流量) |

## 测量架构

部署 *_path_tracer 到 2 台主机，监控 vnet↔phy 边界：

| # | 位置 | 工具 | rx-iface | tx-iface | 检测范围 |
|---|------|------|----------|----------|----------|
| 1 | Sender Host | *_path_tracer.py | vnet (TAP) | phy NIC | VM发出→物理口 丢包 |
| 2 | Receiver Host | *_path_tracer.py | phy NIC | vnet (TAP) | 物理口→VM接收 丢包 |

### VM 边界路径

```
VM Boundary (all protocols):
  rx-iface (vnet/phy) → OVS datapath → tx-iface (phy/vnet)

Sender Host: vnet35 (rx) → OVS → enp24s0f0np0 (tx)
Receiver Host: enp24s0f0np0 (rx) → OVS → vnet130 (tx)
```

### 数据路径

```
Sender VM    Sender Host                            Receiver Host    Receiver VM
┌──────┐  ┌──────────────────────────┐  Network   ┌──────────────────────────┐  ┌──────┐
│      │  │ vnet35      enp24s0f0np0 │           │ enp24s0f0np0      vnet130│  │      │
│ ping─┼─→│ [0]ReqRX ──→ [1]ReqTX   │──────────→│ [0]ReqRX ──→ [1]ReqTX   │─→│ recv │
│      │  │                          │           │                          │  │      │
│ recv─┼─←│ [3]RepTX ←── [2]RepRX   │←──────────│ [3]RepTX ←── [2]RepRX   │←─│ reply│
└──────┘  └──────────────────────────┘           └──────────────────────────┘  └──────┘
```

### 丢包类型

| 丢包类型 | 阶段 | 含义 |
|----------|------|------|
| req_internal | Has [0], missing [1] | 请求进入 rx-iface 但未从 tx-iface 发出 (OVS 丢包) |
| external | Has [1], missing [2] | 请求发出但无回复返回 (网络或对端问题) |
| rep_internal | Has [2], missing [3] | 回复进入但未发出 (OVS 丢包, 回复路径) |

### 延迟段

**ICMP:**

| 段名 | 计算 | 含义 |
|------|------|------|
| ReqInternal | [1] - [0] | rx-iface → tx-iface (请求穿越 OVS) |
| External | [2] - [1] | tx-iface → rx-iface 返回 (网络 + 对端) |
| RepInternal | [3] - [2] | rx-iface → tx-iface (回复穿越 OVS) |
| Total | [3] - [0] | 完整往返穿越此主机 |

**TCP/UDP (预留):**

| 段名 | 计算 | 含义 |
|------|------|------|
| FwdInternal | [1] - [0] | 正向包穿越 OVS |
| RepInternal | 同上 | 反向包穿越 OVS |

**设计决策**: 不在 VM 内部部署工具。只监控 host 侧 vnet↔phy 边界，覆盖基础设施职责范围。

## 输出

### JSON 输出

```json
{
  "measurement_type": "vm-network-path-tracer",
  "protocol": "icmp",
  "focus": "drop",
  "output_mode": "verbose",
  "sender": {
    "boundary": "vnet→phy (VM outbound)",
    "flows": {
      "total": 150,
      "complete": 148,
      "in_progress": 2
    },
    "drops": {
      "req_internal": 1,
      "external": 1,
      "rep_internal": 0
    },
    "drop_rate": 0.013,
    "latency_us": {
      "segment1": { "name": "ReqInternal", "avg": 45.2, "min": 38.1, "max": 89.3 },
      "segment2": { "name": "External", "avg": 338.5, "min": 280.1, "max": 450.2 },
      "segment3": { "name": "RepInternal", "avg": 12.8, "min": 8.2, "max": 25.1 },
      "total": { "avg": 396.5, "min": 326.4, "max": 564.6 }
    }
  },
  "receiver": {
    "boundary": "phy→vnet (VM inbound)",
    ...
  },
  "log_files": ["sender-host.log", "receiver-host.log"],
  "measurement_dir": "./measurement-20260203-143000"
}
```

### Focus 模式说明

- **`--focus drop`**: 输出强调丢包统计和定位，延迟仅显示 Total
- **`--focus latency`**: 输出强调各段延迟分解，丢包作为次要信息

## MVP 范围

| 协议 | 状态 | 说明 |
|------|------|------|
| ICMP | ✅ 完整实现 | verbose 输出 |
| TCP | ⏳ 预留接口 | 后续实现 |
| UDP | ⏳ 预留接口 | 后续实现 |
