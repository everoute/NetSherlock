---
name: system-network-path-tracer
description: |
  Detect and localize system (host-to-host) network packet drops and measure
  internal latency using dual-endpoint BPF tracing. Deploys system_icmp_path_tracer
  to sender and receiver hosts, tracing the full phy→stack→phy path to identify
  where ICMP packets are dropped or delayed.

  Trigger keywords: system packet drop, host drop detection, network drop,
  packet loss location, system network latency, host internal latency,
  系统丢包检测, 主机丢包定界, 系统网络延迟

allowed-tools: Read, Write, Bash, Skill
---

# System Network Packet Drop & Latency Skill

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
| `--sender-ip` | Sender Host IP (ping 发起方) | `192.168.79.32` |
| `--sender-phy-if` | Sender Host 物理网卡 | `enp24s0f0np0` |
| `--receiver-host-ssh` | Receiver Host SSH 地址 | `smartx@192.168.70.31` |
| `--receiver-ip` | Receiver Host IP (ping 接收方) | `192.168.79.31` |
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

## 测量架构

部署 system_icmp_path_tracer 到 2 台主机，每台监控本机的 phy→stack→phy 路径：

| # | 位置 | 工具 | --src-ip | --dst-ip | 追踪内容 |
|---|------|------|----------|----------|----------|
| 1 | Receiver Host | system_icmp_path_tracer.py | SENDER_IP | RECEIVER_IP | A→B 请求的接收和回复路径 (主要) |
| 2 | Sender Host | system_icmp_path_tracer.py | RECEIVER_IP | SENDER_IP | B→A 流量路径 (反向/双向) |

### 4 段追踪路径 (每台主机)

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

### 丢包类型

| 丢包类型 | 阶段 | 含义 |
|----------|------|------|
| req_internal | Has [0], missing [1] | 请求在 OVS/内核路径中被丢弃 |
| stack_no_reply | Has [1], missing [2] | 协议栈未生成回复 |
| rep_internal | Has [2], missing [3] | 回复在 OVS/内核路径中被丢弃 |

### 延迟段

| 段名 | 计算 | 含义 |
|------|------|------|
| ReqPath | [1] - [0] | phy NIC → icmp_rcv (含 OVS 转发) |
| Stack | [2] - [1] | icmp_rcv → ip_send_skb (协议栈处理) |
| RepPath | [3] - [2] | ip_send_skb → phy TX (含 OVS 转发) |
| Total | [3] - [0] | 完整内部往返 |

## 输出

### JSON 输出

```json
{
  "measurement_type": "system-network-path-tracer",
  "receiver": {
    "role": "primary (traces A→B traffic)",
    "total_flows": 150,
    "complete_flows": 145,
    "drops": {
      "req_internal": 3,
      "stack_no_reply": 1,
      "rep_internal": 1
    },
    "drop_rate": 0.033,
    "latency_us": {
      "req_path": { "avg": 45.2, "min": 38.1, "max": 89.3 },
      "stack": { "avg": 5.3, "min": 2.1, "max": 12.4 },
      "rep_path": { "avg": 38.6, "min": 30.2, "max": 78.9 },
      "total": { "avg": 89.1, "min": 70.4, "max": 180.6 }
    }
  },
  "sender": {
    "role": "secondary (traces B→A traffic)",
    ...
  },
  "log_files": ["receiver-host.log", "sender-host.log"],
  "measurement_dir": "./measurement-20260202-143000"
}
```
