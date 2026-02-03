---
name: vm-network-drop
description: |
  Detect and localize VM network packet drops at host boundaries using
  dual-endpoint BPF tracing. Deploys icmp_path_tracer to sender and receiver
  hosts, monitoring vnet↔phy interface boundaries to identify where VM traffic
  is dropped on the host side.

  Trigger keywords: VM packet drop, VM drop detection, VM network drop,
  vnet drop, VM traffic loss, VM丢包检测, 虚拟机丢包定界

allowed-tools: Read, Write, Bash, Skill
---

# VM Network Drop Measurement Skill

## 执行

```bash
python3 .claude/skills/vm-network-drop/scripts/measure.py $ARGUMENTS
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

### 类型 2: 全局配置参数

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

部署 icmp_path_tracer 到 2 台主机，监控 vnet↔phy 边界：

| # | 位置 | 工具 | rx-iface | tx-iface | 检测范围 |
|---|------|------|----------|----------|----------|
| 1 | Sender Host | icmp_path_tracer.py | vnet (TAP) | phy NIC | VM发出→物理口 丢包 |
| 2 | Receiver Host | icmp_path_tracer.py | phy NIC | vnet (TAP) | 物理口→VM接收 丢包 |

### 数据路径

```
Sender VM    Sender Host                            Receiver Host    Receiver VM
┌──────┐  ┌──────────────────────────┐  Network   ┌──────────────────────────┐  ┌──────┐
│      │  │ vnet35      enp24s0f0np0 │           │ enp24s0f0np0      vnet130│  │      │
│ ping─┼─→│ [0]ReqRX ──→ [1]ReqTX   │──────────→│ [0]ReqRX ──→ [1]ReqTX   │─→│ recv │
│      │  │                          │           │                          │  │      │
│ recv─┼─←│ [3]RepTX ←── [2]RepRX   │←──────────│ [3]RepTX ←── [2]RepRX   │←─│ reply│
└──────┘  └──────────────────────────┘           └──────────────────────────┘  └──────┘

Drop types per host:
  - req_internal: Packet enters rx-iface but doesn't exit tx-iface (OVS drop)
  - external: Packet exits but no reply returns (network or peer issue)
  - rep_internal: Reply enters but doesn't exit (OVS drop on reply path)
```

**设计决策**: 不在 VM 内部部署工具。只监控 host 侧 vnet↔phy 边界，覆盖基础设施职责范围。

## 输出

```json
{
  "measurement_type": "vm-network-drop",
  "sender": {
    "boundary": "vnet→phy (VM outbound)",
    "total_flows": 150,
    "complete_flows": 148,
    "drops": { "req_internal": 1, "external": 1, "rep_internal": 0 },
    "drop_rate": 0.013,
    "latency_us": {
      "req_internal": { "avg": 45.2, "min": 38.1, "max": 89.3, "samples": 148 },
      "external": { "avg": 338.5, "min": 280.1, "max": 450.2, "samples": 148 },
      "rep_internal": { "avg": 12.8, "min": 8.2, "max": 25.1, "samples": 148 },
      "total": { "avg": 396.5, "min": 326.4, "max": 564.6, "samples": 148 }
    }
  },
  "receiver": {
    "boundary": "phy→vnet (VM inbound)",
    ...
  },
  "log_files": ["sender-host.log", "receiver-host.log"],
  "measurement_dir": "./measurement-20260202-143000"
}
```
