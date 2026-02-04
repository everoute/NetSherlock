# 网络故障注入指南

本文档描述如何使用 `tc qdisc` 注入网络故障，用于测试网络诊断工具。

支持两种注入位置：
- **VM 内部注入**: 在 VM 内部的网卡上配置，影响该 VM 的所有/指定出向流量
- **Host 端注入**: 在 Host 的 vnet TAP 设备上配置，可精确控制特定 VM 到特定目的地的流量

---

# Part 1: VM 内部故障注入

## 前置条件

### 检查 netem 模块

```bash
lsmod | grep sch_netem
```

如果未加载，尝试加载：

```bash
modprobe sch_netem
```

### 安装 netem 模块 (Rocky/CentOS 9)

如果模块不存在，需要安装 `kernel-modules-extra`：

```bash
# 检查当前内核版本
KERNEL_VER=$(uname -r)
echo $KERNEL_VER

# 方式 1: 从仓库安装 (如果版本匹配)
dnf install -y kernel-modules-extra

# 方式 2: 从 vault 下载旧版本 (如 5.14.0-70.13.1.el9_0)
RPM_URL="https://dl.rockylinux.org/vault/rocky/9.0/BaseOS/x86_64/kickstart/Packages/k/kernel-modules-extra-${KERNEL_VER}.x86_64.rpm"
curl -LO "$RPM_URL"
dnf install -y kernel-modules-extra-${KERNEL_VER}.x86_64.rpm

# 加载模块
modprobe sch_netem
```

## 延迟注入

### 原理

使用 `tc` (traffic control) 的分层 qdisc 实现选择性延迟：

```
eth0 ─┬─► prio qdisc (root handle 1:)
      │    ├─► 1:1 (high prio) ─► 正常流量
      │    ├─► 1:2 (medium prio) ─► 正常流量
      │    └─► 1:3 (low prio) ─► netem delay
      │                              ▲
      │                              │
      └─► filter: dst=TARGET_IP ─────┘
```

### 注入命令

```bash
# 配置变量
IFACE=ens4                    # 网卡名称
TARGET_IP=192.168.76.244      # 目标 IP (仅此 IP 受影响)
DELAY=50ms                    # 延迟时间

# 1. 清除现有配置
tc qdisc del dev $IFACE root 2>/dev/null

# 2. 添加 prio 根 qdisc (3 个优先级队列)
tc qdisc add dev $IFACE root handle 1: prio bands 3 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1

# 3. 添加 netem delay 到 band 3
tc qdisc add dev $IFACE parent 1:3 handle 30: netem delay $DELAY

# 4. 添加 filter 将目标 IP 流量导向 band 3
tc filter add dev $IFACE protocol ip parent 1:0 prio 3 u32 match ip dst $TARGET_IP/32 flowid 1:3
```

### 验证配置

```bash
# 查看 qdisc 配置
tc qdisc show dev $IFACE

# 预期输出:
# qdisc prio 1: root refcnt 9 bands 3 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1
# qdisc netem 30: parent 1:3 limit 1000 delay 50ms

# 查看 filter 配置
tc filter show dev $IFACE

# 预期输出:
# filter parent 1: protocol ip pref 3 u32 chain 0 fh 800::800 order 2048 key ht 800 bkt 0 flowid 1:3
#   match c0a84cf4/ffffffff at 16    # c0a84cf4 = 192.168.76.244 的十六进制
```

### 测试延迟效果

```bash
# 测试到目标 IP (应有延迟)
ping -c 5 $TARGET_IP

# 测试到其他 IP (不应受影响)
ping -c 3 192.168.64.1
```

## 丢包注入

### 固定丢包率

```bash
# 配置 10% 丢包率
tc qdisc add dev $IFACE parent 1:3 handle 30: netem loss 10%
```

### 延迟 + 丢包组合

```bash
# 50ms 延迟 + 5% 丢包
tc qdisc add dev $IFACE parent 1:3 handle 30: netem delay 50ms loss 5%
```

### 突发丢包

```bash
# 5% 丢包率，25% 相关性 (突发丢包)
tc qdisc add dev $IFACE parent 1:3 handle 30: netem loss 5% 25%
```

## 带宽限制

```bash
# 限制带宽为 1Mbit/s
tc qdisc add dev $IFACE parent 1:3 handle 30: tbf rate 1mbit burst 32kbit latency 400ms
```

## 抖动注入

```bash
# 50ms 延迟 ± 10ms 抖动 (正态分布)
tc qdisc add dev $IFACE parent 1:3 handle 30: netem delay 50ms 10ms distribution normal
```

## 清理

```bash
# 删除所有 tc 配置，恢复默认
tc qdisc del dev $IFACE root
```

## 完整脚本

### inject_latency.sh

```bash
#!/bin/bash
# VM 延迟注入脚本
# 用法: ./inject_latency.sh <interface> <target_ip> <delay>
# 示例: ./inject_latency.sh ens4 192.168.76.244 50ms

IFACE=${1:-ens4}
TARGET_IP=${2:-192.168.76.244}
DELAY=${3:-50ms}

echo "注入延迟: $DELAY 到 $TARGET_IP (接口: $IFACE)"

# 确保 netem 模块已加载
modprobe sch_netem 2>/dev/null

# 清除现有配置
tc qdisc del dev $IFACE root 2>/dev/null

# 配置延迟
tc qdisc add dev $IFACE root handle 1: prio bands 3 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1
tc qdisc add dev $IFACE parent 1:3 handle 30: netem delay $DELAY
tc filter add dev $IFACE protocol ip parent 1:0 prio 3 u32 match ip dst $TARGET_IP/32 flowid 1:3

echo "配置完成:"
tc qdisc show dev $IFACE | grep -E "prio|netem"
```

### cleanup_tc.sh

```bash
#!/bin/bash
# 清理 TC 配置
# 用法: ./cleanup_tc.sh [interface]

IFACE=${1:-ens4}
tc qdisc del dev $IFACE root 2>/dev/null && echo "已清理 $IFACE" || echo "无需清理"
```

## 测试环境信息

| 项目 | 值 |
|------|-----|
| VM Sender | 192.168.77.83 (ens4) |
| VM Receiver | 192.168.76.244 |
| 内核版本 | 5.14.0-70.13.1.el9_0.x86_64 |
| 模块包 | kernel-modules-extra |

## 注意事项

1. **仅影响出向流量**: 上述配置只对从本机发出的流量生效，入向流量需要在对端配置
2. **双向延迟**: 如需双向延迟，需在两端 VM 都配置
3. **SSH 连接**: 配置时注意不要影响 SSH 管理连接，使用 filter 精确匹配目标 IP
4. **清理**: 测试完成后务必清理配置
5. **权限**: 需要 root 权限执行 tc 命令

---

# Part 2: Host 端故障注入 (vnet TAP)

Host 端注入可以在不进入 VM 的情况下注入故障，并且可以精确控制只影响特定 VM 到特定目的地的流量。

## 原理

由于 TAP 设备的特性，VM 发出的数据包到达 vnet 设备时是 **ingress** 方向。需要使用 IFB (Intermediate Functional Block) 设备重定向流量来应用 netem。

```
VM 发包 ─► vnet35 (ingress) ─► IFB redirect ─► ifb0 (netem delay/loss)
                                                      │
                                                      ▼
                                              OVS Bridge ─► 物理网卡
```

## 前置条件

```bash
# 在 Host 上加载必要模块
modprobe sch_netem
modprobe ifb
```

## 选择性延迟注入 (仅特定目的地)

```bash
# 配置变量
VNET=vnet35                    # VM 的 TAP 设备名
DST_IP=192.168.76.244          # 目标 IP (仅此目的地受影响)
DELAY=50ms                     # 延迟时间

# 1. 创建并启用 IFB 设备
ip link add ifb0 type ifb 2>/dev/null
ip link set dev ifb0 up

# 2. 添加 ingress qdisc 到 vnet
tc qdisc add dev $VNET ingress

# 3. 添加 filter 重定向匹配流量到 IFB
tc filter add dev $VNET parent ffff: protocol ip u32 \
    match ip dst $DST_IP/32 \
    action mirred egress redirect dev ifb0

# 4. 在 IFB 上应用延迟
tc qdisc add dev ifb0 root handle 1: netem delay $DELAY
```

### 验证配置

```bash
# 查看 vnet ingress filter
tc filter show dev $VNET ingress

# 预期输出:
# filter protocol ip pref 49152 u32 chain 0 fh 800::800 ...
#   match c0a84cf4/ffffffff at 16
#   action order 1: mirred (Egress Redirect to device ifb0) stolen

# 查看 IFB qdisc
tc qdisc show dev ifb0

# 预期输出:
# qdisc netem 1: root refcnt 2 limit 1000 delay 50.0ms
```

## 选择性丢包注入

```bash
# 替换 IFB 上的 qdisc 为延迟+丢包
tc qdisc replace dev ifb0 root handle 1: netem delay 10ms loss 30%
```

## 清理

```bash
# 清理 vnet 上的 ingress qdisc
tc qdisc del dev $VNET ingress

# 清理 IFB 设备
tc qdisc del dev ifb0 root
ip link del ifb0
```

## 完整脚本

### host_inject_fault.sh

```bash
#!/bin/bash
# Host 端故障注入脚本
# 用法: ./host_inject_fault.sh <vnet> <dst_ip> <delay> [loss%]
# 示例: ./host_inject_fault.sh vnet35 192.168.76.244 50ms 10

VNET=${1:-vnet35}
DST_IP=${2:-192.168.76.244}
DELAY=${3:-50ms}
LOSS=${4:-0}

echo "Host 端故障注入: vnet=$VNET, dst=$DST_IP, delay=$DELAY, loss=$LOSS%"

# 加载模块
modprobe sch_netem 2>/dev/null
modprobe ifb 2>/dev/null

# 清理之前的配置
tc qdisc del dev $VNET ingress 2>/dev/null
tc qdisc del dev ifb0 root 2>/dev/null
ip link del ifb0 2>/dev/null

# 创建 IFB
ip link add ifb0 type ifb
ip link set dev ifb0 up

# 配置 vnet ingress 重定向
tc qdisc add dev $VNET ingress
tc filter add dev $VNET parent ffff: protocol ip u32 \
    match ip dst $DST_IP/32 \
    action mirred egress redirect dev ifb0

# 配置 IFB netem
if [ "$LOSS" = "0" ]; then
    tc qdisc add dev ifb0 root handle 1: netem delay $DELAY
else
    tc qdisc add dev ifb0 root handle 1: netem delay $DELAY loss ${LOSS}%
fi

echo "配置完成:"
echo "=== vnet ingress filter ==="
tc filter show dev $VNET ingress
echo "=== ifb0 qdisc ==="
tc qdisc show dev ifb0
```

### host_cleanup_fault.sh

```bash
#!/bin/bash
# 清理 Host 端故障注入
# 用法: ./host_cleanup_fault.sh [vnet]

VNET=${1:-vnet35}

tc qdisc del dev $VNET ingress 2>/dev/null
tc qdisc del dev ifb0 root 2>/dev/null
ip link del ifb0 2>/dev/null

echo "已清理 Host 端故障注入 ($VNET)"
```

## Host 端 vs VM 内部注入对比

| 特性 | VM 内部注入 | Host 端注入 |
|------|------------|------------|
| 配置位置 | VM 内部 (需要 SSH 到 VM) | Host (无需进入 VM) |
| 影响范围 | VM 所有出向流量 (可用 filter 限定) | 精确控制特定流量 |
| 诊断归因 | 故障在 VM 内核栈 | 故障在 Host vnet/OVS 层 |
| 适用场景 | 模拟 VM 内部网络问题 | 模拟主机虚拟化层问题 |
| 模块依赖 | VM 内需要 sch_netem | Host 需要 sch_netem + ifb |

## 测试环境信息

| 项目 | 值 |
|------|-----|
| Sender Host | 192.168.70.32 |
| Sender VM | 192.168.77.83 |
| Sender vnet | vnet35 |
| Receiver Host | 192.168.70.31 |
| Receiver VM | 192.168.76.244 |
