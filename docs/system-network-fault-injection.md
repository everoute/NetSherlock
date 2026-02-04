# System Network Fault Injection Guide

本文档记录如何在 SmartX 集群的系统网络（管理网络）上注入可控的延迟故障，用于测试诊断流水线。

## 验证环境

- **集群**: 192.168.70.31, 70.32, 70.33, 70.34
- **OVS 版本**: 3.3.5
- **验证日期**: 2026-02-04

## 关键发现

### tc 必须配置在 OVS 内部端口

| 接口类型 | 示例 | tc filter | 原因 |
|----------|------|-----------|------|
| 物理网卡 | `enp24s0f0np0` | ❌ 不生效 | OVS kernel datapath 绕过 tc hooks |
| OVS 内部端口 | `port-mgt` | ✅ 生效 | 走正常 Linux 网络栈 |

### 数据流路径

```
应用层 (ping from 70.31)
    ↓
port-mgt (OVS internal port) ← tc 在这里配置！
    ↓
ovsbr-3gzc2wj59 (local bridge)
    ↓ patch
ovsbr-3gzc2wj59-policy
    ↓ patch
ovsbr-3gzc2wj59-cls
    ↓ patch
ovsbr-3gzc2wj59-uplink
    ↓
enp24s0f0np0 (物理网卡) ← tc 在这里不生效！
    ↓
物理网络 → 目标主机
```

## 验证结果

配置 tc 只针对 70.32 后的测试结果：

| 目标 | 延迟 | 状态 |
|------|------|------|
| 70.31 → 70.32 | ~1.17ms | 注入 1ms 生效 |
| 70.31 → 70.33 | ~0.15ms | 未受影响 |
| 70.31 → 70.34 | ~0.25ms | 未受影响 |

Filter 统计显示精确匹配：`success 216` (只匹配发往 70.32 的 ICMP)

## 使用方法

### 注入固定延迟

```bash
# 在 70.31 上注入 1ms 延迟，只影响发往 70.32 的 ICMP
ssh smartx@192.168.70.31 "sudo bash" <<'EOF'
TC=/sbin/tc
$TC qdisc del dev port-mgt root 2>/dev/null || true
$TC qdisc add dev port-mgt root handle 1: htb default 10
$TC class add dev port-mgt parent 1: classid 1:10 htb rate 10gbit
$TC class add dev port-mgt parent 1: classid 1:20 htb rate 10gbit
$TC qdisc add dev port-mgt parent 1:20 handle 20: netem delay 1ms
$TC filter add dev port-mgt protocol ip parent 1:0 prio 1 u32 \
    match ip dst 192.168.70.32/32 \
    match ip protocol 1 0xff \
    flowid 1:20
echo "Injected 1ms delay for ICMP to 70.32"
EOF
```

### 注入带抖动的延迟

```bash
# 1ms ± 200us 抖动
$TC qdisc add dev port-mgt parent 1:20 handle 20: netem delay 1ms 200us
```

### 注入带相关性的延迟

```bash
# 1ms ± 200us，25% 相关性（前后包延迟相关）
$TC qdisc add dev port-mgt parent 1:20 handle 20: netem delay 1ms 200us 25%
```

### 清除注入

```bash
ssh smartx@192.168.70.31 "sudo /sbin/tc qdisc del dev port-mgt root"
```

### 查看状态

```bash
ssh smartx@192.168.70.31 "sudo /sbin/tc -s qdisc show dev port-mgt; sudo /sbin/tc -s filter show dev port-mgt"
```

## 测试告警触发

当前 Prometheus 告警阈值：500µs (500000 ns)
Baseline 延迟：~170µs

要触发告警，需注入 >330µs 延迟：

```bash
# 注入 400us 延迟，使总延迟 > 500us
$TC qdisc add dev port-mgt parent 1:20 handle 20: netem delay 400us
```

## Filter 匹配规则

### 只匹配 ICMP

```bash
$TC filter add dev port-mgt protocol ip parent 1:0 prio 1 u32 \
    match ip dst 192.168.70.32/32 \
    match ip protocol 1 0xff \
    flowid 1:20
```

### 匹配所有 IP 流量

```bash
$TC filter add dev port-mgt protocol ip parent 1:0 prio 1 u32 \
    match ip dst 192.168.70.32/32 \
    flowid 1:20
```

### 匹配特定端口 (TCP)

```bash
$TC filter add dev port-mgt protocol ip parent 1:0 prio 1 u32 \
    match ip dst 192.168.70.32/32 \
    match ip protocol 6 0xff \
    match ip dport 22 0xffff \
    flowid 1:20
```

## 注意事项

1. **必须使用 OVS 内部端口**：`port-mgt`，不是物理网卡
2. **tc 路径**：集群上是 `/sbin/tc`，不在默认 PATH 中
3. **清理**：测试完成后务必清除 tc 配置
4. **影响范围**：只影响从该主机发出的流量，不影响其他主机

## 脚本化使用

```bash
#!/bin/bash
# inject_latency.sh <host> <target_ip> <delay_us>
# Example: ./inject_latency.sh 192.168.70.31 192.168.70.32 1000

HOST="$1"
TARGET="$2"
DELAY="${3:-500}"

ssh smartx@$HOST "sudo bash" <<EOF
TC=/sbin/tc
\$TC qdisc del dev port-mgt root 2>/dev/null || true
\$TC qdisc add dev port-mgt root handle 1: htb default 10
\$TC class add dev port-mgt parent 1: classid 1:10 htb rate 10gbit
\$TC class add dev port-mgt parent 1: classid 1:20 htb rate 10gbit
\$TC qdisc add dev port-mgt parent 1:20 handle 20: netem delay ${DELAY}us
\$TC filter add dev port-mgt protocol ip parent 1:0 prio 1 u32 \
    match ip dst ${TARGET}/32 \
    match ip protocol 1 0xff \
    flowid 1:20
echo "Injected ${DELAY}us delay on \$(hostname) for ICMP to ${TARGET}"
EOF
```
