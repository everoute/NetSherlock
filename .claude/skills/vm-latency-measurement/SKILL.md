---
name: vm-latency-measurement
description: |
  Execute coordinated latency measurement across sender and receiver VMs and hosts.
  Deploys BPF tools to 8 measurement points, starts them with receiver-first timing,
  collects logs, and outputs structured JSON with segment latencies.

  Trigger keywords: measure VM latency, run latency measurement, collect latency data,
  deploy measurement tools, cross-node measurement, 测量延迟, 执行测量

allowed-tools: Read, Write, Bash, Skill
---

# VM Latency Measurement Skill

## 执行

```bash
python3 .claude/skills/vm-latency-measurement/scripts/measure.py $ARGUMENTS
```

如果参数不完整，从对话上下文获取或向用户询问。

## 参数说明

### 类型 1: L2 环境参数 (来自 network-env-collector skill)

这些参数由上游 L2 skill 收集，按约定命名传入：

| 参数 | 说明 | 示例 |
|------|------|------|
| `--sender-vm-ssh` | Sender VM SSH 地址 | `root@192.168.77.83` |
| `--sender-vm-ip` | Sender VM IP (BPF 过滤) | `192.168.77.83` |
| `--sender-host-ssh` | Sender Host SSH 地址 | `smartx@192.168.70.32` |
| `--send-vnet-if` | Sender VM 的 TAP 接口 | `vnet35` |
| `--send-phy-if` | Sender Host 物理网卡 | `enp24s0f0np0` |
| `--send-vm-if` | Sender VM 内部网卡 | `ens4` |
| `--receiver-vm-ssh` | Receiver VM SSH 地址 | `root@192.168.76.244` |
| `--receiver-vm-ip` | Receiver VM IP (BPF 过滤) | `192.168.76.244` |
| `--receiver-host-ssh` | Receiver Host SSH 地址 | `smartx@192.168.70.31` |
| `--recv-vnet-if` | Receiver VM 的 TAP 接口 | `vnet130` |
| `--recv-phy-if` | Receiver Host 物理网卡 | `enp24s0f0np0` |
| `--recv-vm-if` | Receiver VM 内部网卡 | `ens4` |
| `--local-tools-path` | BPF 工具本地路径 | `~/workspace/troubleshooting-tools/measurement-tools` |

### 类型 2: 全局配置参数

这些参数有默认值，可由用户指定或根据上下文决定：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--duration` | 30 | 测量持续时间 (秒) |
| `--generate-traffic` | false | 是否生成测试流量 |
| `--receiver-warmup` | 2 | receiver 工具预热时间 (秒) |
| `--shutdown-wait` | 3 | 优雅关闭等待时间 (秒) |
| `--ping-interval` | 1 | ping 间隔，仅 --generate-traffic 时有效 |
| `--skip-deploy` | false | 跳过工具部署 (工具已部署时使用) |
| `--skip-validate` | false | 跳过 SSH 连接验证 |
| `--output-dir` | auto | 输出目录，默认 ./measurement-TIMESTAMP |
| `--json-only` | false | 只输出 JSON，不显示进度 |

## 调用示例

### 完整参数调用

```bash
python3 .claude/skills/vm-latency-measurement/scripts/measure.py \
    --sender-vm-ssh root@192.168.77.83 \
    --sender-vm-ip 192.168.77.83 \
    --sender-host-ssh smartx@192.168.70.32 \
    --send-vnet-if vnet35 \
    --send-phy-if enp24s0f0np0 \
    --send-vm-if ens4 \
    --receiver-vm-ssh root@192.168.76.244 \
    --receiver-vm-ip 192.168.76.244 \
    --receiver-host-ssh smartx@192.168.70.31 \
    --recv-vnet-if vnet130 \
    --recv-phy-if enp24s0f0np0 \
    --recv-vm-if ens4 \
    --local-tools-path ~/workspace/troubleshooting-tools/measurement-tools \
    --duration 30
```

### 生成测试流量

```bash
python3 .../measure.py \
    ... (L2 参数) ... \
    --generate-traffic \
    --duration 60
```

### 跳过部署 (工具已部署)

```bash
python3 .../measure.py \
    ... (L2 参数) ... \
    --skip-deploy
```

## 流量生成模式

| 模式 | 参数 | 行为 |
|------|------|------|
| **默认** | (无) | 不生成流量，依赖背景流量 |
| **生成** | `--generate-traffic` | 整个流程开始时启动 ping，结束时停止 |

**注意**: kvm_vhost_tun_latency 工具需要有流量才能匹配。如果没有背景流量，使用 `--generate-traffic`。

## 8 个测量工具

| # | 位置 | 工具 | 测量段 |
|---|------|------|--------|
| 1 | Sender VM | kernel_icmp_rtt.py | A, M, Total RTT |
| 2 | Sender Host | icmp_drop_detector.py | B, K |
| 3 | Sender Host | kvm_vhost_tun_latency_no_discovery.py | B_1 |
| 4 | Sender Host | tun_tx_to_kvm_irq.py | L |
| 5 | Receiver VM | kernel_icmp_rtt.py | F, G, H |
| 6 | Receiver Host | icmp_drop_detector.py | D, I |
| 7 | Receiver Host | kvm_vhost_tun_latency_no_discovery.py | I_1 |
| 8 | Receiver Host | tun_tx_to_kvm_irq.py | E |

详见 [reference/measurement-tools.md](reference/measurement-tools.md)。

## 输出

### JSON 输出

```json
{
  "total_rtt_us": 582.813,
  "segments": {
    "A": 15.234, "B": 12.456, "B_1": 21.500,
    "C_J": 168.443,
    "D": 12.345, "E": 98.000,
    "F": 23.644, "G": 5.475, "H": 5.475,
    "I": 16.789, "I_1": 18.200,
    "K": 12.456, "L": 95.000, "M": 17.456
  },
  "log_files": ["send-vm-icmp.log", ...],
  "measurement_dir": "./measurement-20240115-143000"
}
```

### 日志文件

| 文件 | 内容 | 测量段 |
|------|------|--------|
| send-vm-icmp.log | Sender VM kernel_icmp_rtt | A, M, Total RTT |
| recv-vm-icmp.log | Receiver VM kernel_icmp_rtt | F, G, H |
| send-host-icmp.log | Sender Host icmp_drop_detector | B, K |
| recv-host-icmp.log | Receiver Host icmp_drop_detector | D, I |
| send-host-vhost-rx.log | Sender Host tun_tx_to_kvm_irq | L |
| recv-host-vhost-rx.log | Receiver Host tun_tx_to_kvm_irq | E |
| send-host-kvm-tun.log | Sender Host kvm_vhost_tun_latency | B_1 |
| recv-host-kvm-tun.log | Receiver Host kvm_vhost_tun_latency | I_1 |

## 前置条件

- SSH 密钥认证到所有 4 台机器
- 目标机器有 root/sudo 权限
- BPF 工具在 `--local-tools-path` 路径下

## 相关 Skill

- [network-env-collector](../network-env-collector/SKILL.md) - L2 环境信息收集
- [vm-latency-analysis](../vm-latency-analysis/SKILL.md) - L4 延迟分析
