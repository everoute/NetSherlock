# E2E Diagnosis Test Plan - Complete 5-Scenario Workflow

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Validate complete diagnosis workflows for all 5 supported scenarios through fault injection and alert triggering

**Architecture:** Each scenario follows: Pre-Check → Fault Injection → Alert Triggering → Alertmanager/ping_monitor → Webhook → Diagnosis Controller → Measurement → Analysis Report

**Tech Stack:** tc/netem (fault injection), Prometheus/Alertmanager (system alerts), VM ping_monitor (VM alerts), FastAPI webhook, BPF tools (measurement), Python analysis skills

---

## Table of Contents

1. [Test Scenarios Overview](#test-scenarios-overview)
2. [Alert Trigger Conditions Summary](#alert-trigger-conditions-summary)
3. [Suite-Level Prerequisites](#suite-level-prerequisites)
4. [Per-Case Mandatory Configuration Check (Task 0)](#per-case-mandatory-configuration-check-task-0) ⭐ **每个 Case 前必须执行**
5. [Per-Case Alert and Queue Status Check (Task 0.5)](#per-case-alert-and-queue-status-check-task-05) ⭐ **每个 Case 前必须执行**
6. [Scenario 1: System Network Latency Boundary](#scenario-1-system-network-latency-boundary)
7. [Scenario 2: System Network Packet Drop Boundary](#scenario-2-system-network-packet-drop-boundary)
8. [Scenario 3: VM Network Latency Boundary](#scenario-3-vm-network-latency-boundary)
9. [Scenario 4: VM Network Packet Drop Boundary](#scenario-4-vm-network-packet-drop-boundary)
10. [Scenario 5: VM Network Full-Path Segment Analysis](#scenario-5-vm-network-full-path-segment-analysis)
11. [Cleanup and Success Criteria](#cleanup-and-success-criteria)

---

## Test Environment Reference

**Configuration File:** `config/test-e2e-diagnosis.yaml`

```yaml
# Test topology (management network IPs)
host-sender:   smartx@192.168.70.32 (node32)
host-receiver: smartx@192.168.70.31 (node31, also runs Prometheus)
vm-sender:     root@192.168.77.83   (on node32)
vm-receiver:   root@192.168.76.244  (on node31)

# Prometheus location
prometheus: node31 (listening on 70.0.0.31:9090 via storage network)
prometheus_auth: prometheus:HC!r0cks
```

---

## Test Scenarios Overview

| # | Network Type | Problem Type | Mode     | Fault Injection Point            | Alert Source                                 |
| - | ------------ | ------------ | -------- | -------------------------------- | -------------------------------------------- |
| 1 | System       | Latency      | Boundary | Host management NIC (node32)     | Prometheus `NetSherlockHostLatencyDevTest` |
| 2 | System       | Packet Drop  | Boundary | Host storage NIC (node32)        | Prometheus `HostNetworkPacketLossDevTest`  |
| 3 | VM           | Latency      | Boundary | Host `vnet35` via IFB (node32) | ping_monitor `VMNetworkLatencyHigh`        |
| 4 | VM           | Packet Drop  | Boundary | Host `vnet35` via IFB (node32) | ping_monitor `VMNetworkPacketLoss`         |
| 5 | VM           | Latency      | Segment  | VM internal `ens4` (sender VM) | ping_monitor `VMNetworkLatencyCritical`    |

### Workflow Routing Table (from diagnosis_controller.py)

```python
WORKFLOW_TABLE = {
    # (network_type, request_type, mode) → (measurement_skill, analysis_skill, param_builder)

    # Boundary Mode
    ("system", "latency", "boundary"):     ("system-network-path-tracer", "system-network-latency-analysis", ...),
    ("system", "packet_drop", "boundary"): ("system-network-path-tracer", "system-network-drop-analysis", ...),
    ("vm", "latency", "boundary"):         ("vm-network-path-tracer", "vm-network-latency-analysis", ...),
    ("vm", "packet_drop", "boundary"):     ("vm-network-path-tracer", "vm-network-drop-analysis", ...),

    # Segment Mode (Full-path)
    ("vm", "latency", "segment"):          ("vm-latency-measurement", "vm-latency-analysis", ...),
}
```

---

## Alert Trigger Conditions Summary

### System Network Alerts (Prometheus → Alertmanager → Webhook)

| Alert Name                        | Threshold  | For Duration | Fault Required | Labels                                                    |
| --------------------------------- | ---------- | ------------ | -------------- | --------------------------------------------------------- |
| `NetSherlockHostLatencyDevTest` | P90 > 15ms | 10s          | 20ms delay     | `network_type="system"`                                 |
| `HostNetworkPacketLossDevTest`  | loss > 3%  | 10s          | 10% packet loss | `network_type="system"`, `problem_type="packet_drop"` |

**Note:** Only these 2 alert rules are enabled to avoid duplicate triggers from multiple thresholds.

**Important**: System network tests monitor **storage network** (70.0.0.x), NOT management network:

- **host-sender (node32)**: Inject faults on `port-storage` to affect traffic to node31
- **host-receiver (node31)**: Prometheus runs here, receives test traffic
- **Fault injection target**: 70.0.0.31 (storage IP), use `ip route get 70.0.0.31` to find `port-storage`
- SSH access uses management network (192.168.70.x), but fault injection targets storage network

### VM Network Alerts (ping_monitor → Direct POST to /diagnose)

| Threshold Type | Warning Level | Critical Level | Diagnosis Mode     |
| -------------- | ------------- | -------------- | ------------------ |
| RTT            | > 15ms        | > 50ms         | boundary / segment |
| Packet Loss    | > 10%         | > 50%          | boundary           |

| Alert Name                   | Threshold                 | Trigger Condition    | Diagnosis Mode |
| ---------------------------- | ------------------------- | -------------------- | -------------- |
| `VMNetworkLatencyHigh`     | RTT > 15ms for 2/3 cycles | 20ms delay injection | boundary       |
| `VMNetworkLatencyCritical` | RTT > 50ms for 2/3 cycles | 60ms delay injection | segment        |
| `VMNetworkPacketLoss`      | Loss > 10% for 2/3 cycles | 20% loss injection   | boundary       |

**Note:** Critical severity automatically triggers segment mode via `options.segment=True` in the webhook payload.

**Important - Single Alert Per Fault:** ping_monitor uses **highest-severity-first** evaluation:

- If RTT exceeds critical threshold (50ms), only `VMNetworkLatencyCritical` fires (warning is skipped)
- If RTT exceeds warning threshold (15ms) but not critical, only `VMNetworkLatencyHigh` fires
- Each severity level has independent cooldown (1 hour), so same-severity alerts won't repeat within 1 hour

### Fault Injection Lifecycle Management

**CRITICAL:** Faults must persist until diagnosis completes. Premature cleanup causes measurement to see normal values.

| Network Type        | Diagnosis Duration | Fault Minimum Duration               |
| ------------------- | ------------------ | ------------------------------------ |
| System (Prometheus) | 2-3 minutes        | ~4 minutes (alert delay + diagnosis) |
| VM (ping_monitor)   | 30-60 seconds      | ~2 minutes (trigger + diagnosis)     |

**Recommended workflow:**

1. Inject fault
2. Wait for diagnosis to start (check `/diagnoses` endpoint)
3. Poll diagnosis status until `status: completed`
4. Then cleanup fault

### ⚠️ 诊断 ID 使用说明 (API 设计注意事项)

**ID 类型说明:**

| ID 类型          | 格式示例                   | 来源                | 用途                    |
| ---------------- | -------------------------- | ------------------- | ----------------------- |
| `request_id`   | `alert-d20632d21b044dbc` | Webhook POST 返回   | 查询诊断状态            |
| `diagnosis_id` | `76c09bf2`               | Controller 内部生成 | `/diagnoses` 列表显示 |

**⚠️ 重要:** `/diagnoses` 列表显示的 `diagnosis_id` 与查询所需的 ID **不同**！

- 列表显示: `diagnosis_id: 76c09bf2` (内部 ID)
- 查询需要: `alert-d20632d21b044dbc` (request_id)

**正确的监控方式:**

```bash
# 方法 1: 从 Webhook POST 响应获取 request_id (推荐)
# 触发告警后，webhook 返回 request_id，使用它来监控
REQUEST_ID="alert-d20632d21b044dbc"  # 从 POST 响应获取

# 查询端点是 /diagnose/ (单数)，不是 /diagnoses/
while true; do
  STATUS=$(curl -s "http://localhost:8080/diagnose/$REQUEST_ID" | jq -r '.status // "not_found"')
  echo "Status: $STATUS"
  [ "$STATUS" = "completed" ] || [ "$STATUS" = "failed" ] && break
  sleep 5
done
```

```bash
# 方法 2: 监控最新诊断完成 (简化方式)
# 适用于单次测试，通过列表监控最新诊断状态
BEFORE_COUNT=$(curl -s http://localhost:8080/diagnoses | jq 'length')

# ... 注入故障，等待告警触发 ...

# 等待新诊断完成
while true; do
  LATEST=$(curl -s http://localhost:8080/diagnoses | jq '.[0]')
  STATUS=$(echo "$LATEST" | jq -r '.status')
  COUNT=$(curl -s http://localhost:8080/diagnoses | jq 'length')
  echo "Diagnoses: $COUNT, Latest status: $STATUS"
  [ "$COUNT" -gt "$BEFORE_COUNT" ] && [ "$STATUS" = "completed" ] && break
  sleep 5
done
echo "Diagnosis completed"
echo "$LATEST" | jq .
```

### Repeat Alert Timing (Same Fault Continuous Injection)

| Source                               | First Alert          | Second Alert (same severity)              |
| ------------------------------------ | -------------------- | ----------------------------------------- |
| **Prometheus → Alertmanager** | ~25s after injection | **4 hours** (repeat_interval)       |
| **ping_monitor**               | ~6s after injection  | **1 hour** (cooldown_seconds: 3600) |

**Note:** Alertmanager's `repeat_interval: 4h` means a continuously firing alert will only re-trigger webhook every 4 hours. For repeat testing, restart Alertmanager to clear state.

### ⚠️ Alertmanager 路由配置 (重要)

**问题:** 如果 Alertmanager 路由配置不正确，生产告警会干扰测试。

**正确配置:** `config/alertmanager/alertmanager.yml` 路由规则应**只匹配自定义测试告警**:

```yaml
routes:
  # NetSherlock E2E 测试告警 -> NetSherlock webhook
  # 只匹配我们自定义的测试告警，避免接收生产告警
  - match_re:
      alertname: 'NetSherlock.*|HostNetworkPacketLossDevTest'
    receiver: 'netsherlock'
    group_wait: 5s
    group_interval: 20m
    continue: false
```

**错误配置示例 (会导致干扰):**

```yaml
# ❌ 不要包含 host_to_host_max_ping_time_ns.* - 这会匹配生产告警
alertname: 'host_to_host_max_ping_time_ns.*|HostNetworkLatency.*|NetSherlock.*'
```

**验证路由是否正确:**

```bash
# 查看告警路由分配
curl -s http://localhost:9093/api/v2/alerts | jq '[.[] | {alertname: .labels.alertname, receivers: [.receivers[].name]}] | group_by(.receivers[0]) | .[] | {receiver: .[0].receivers[0], alerts: [.[].alertname]}'

# 期望结果:
# - netsherlock receiver: 只有 NetSherlock* 和 HostNetworkPacketLossDevTest
# - null receiver: 生产告警 (host_to_host_max_ping_time_ns:* 等)
```

---

## Suite-Level Prerequisites

**CRITICAL:** Complete ALL prerequisites before starting ANY test scenario.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Test Environment Overview                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                        Agent Host (192.168.10.175)                      │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │ │
│  │  │ Alertmanager    │  │ Webhook Server  │  │ Diagnosis Controller    │ │ │
│  │  │ (:9093)         │→ │ (:8080)         │→ │                         │ │ │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────────────┘ │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│                 ▲                                      │                     │
│                 │ alerts                               │ SSH + BPF tools     │
│                 │                                      ▼                     │
│  ┌──────────────────────────────────┐    ┌──────────────────────────────┐   │
│  │  node31 (host-receiver)          │    │  node32 (host-sender)        │   │
│  │  192.168.70.31                   │    │  192.168.70.32               │   │
│  │  ┌────────────────────────────┐  │    │  ┌────────────────────────┐  │   │
│  │  │ Prometheus (70.0.0.31:9090)│  │    │  │ Fault Injection Point  │  │   │
│  │  │ Alert Rules: /etc/prometheus│  │    │  │ (tc/netem on NICs)     │  │   │
│  │  └────────────────────────────┘  │    │  └────────────────────────┘  │   │
│  │  ┌────────────────────────────┐  │    │  ┌────────────────────────┐  │   │
│  │  │ VM-receiver (76.244)       │  │    │  │ VM-sender (77.83)      │  │   │
│  │  │                            │  │    │  │ + ping_monitor         │  │   │
│  │  └────────────────────────────┘  │    │  └────────────────────────┘  │   │
│  └──────────────────────────────────┘    └──────────────────────────────┘   │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Prerequisites Checklist Summary

| Task                  | Component                        | Location             | Config File                                    | Expected State                  | Frequency              |
| --------------------- | -------------------------------- | -------------------- | ---------------------------------------------- | ------------------------------- | ---------------------- |
| **P-1** ⭐      | **清理本地进程和队列**     | **Agent Host** | -                                              | **无残留进程/空队列**     | **Suite 首次**   |
| **Task 0**      | **Mandatory Config Check** | **见下方**     | -                                              | **两个 ✅**               | **每个 Case 前** |
| **Task 0.5** ⭐ | **告警与队列状态检查**     | **见下方**     | -                                              | **无 active 告警/空队列** | **每个 Case 前** |
| P0.1                  | Prometheus Alert Rules           | node31               | `/etc/prometheus/netsherlock_test_alert.yml` | Exactly 2 rules                 | Suite 首次             |
| P0.2                  | ping_monitor Config              | VM-sender            | `/etc/ping_monitor/config.yaml`              | Correct thresholds              | Suite 首次             |
| P0.3                  | Prometheus → Alertmanager       | node31               | `/etc/prometheus/prometheus.yml`             | 192.168.10.175:9093 configured  | Suite 首次             |
| P1                    | No Residual Faults               | node32, VM           | tc qdisc                                       | No custom qdisc                 | Suite 首次             |
| P2.1                  | Alertmanager                     | Agent Host           | -                                              | Running on :9093                | Suite 首次             |
| P2.2                  | Webhook Server                   | Agent Host           | -                                              | Running on :8080                | Suite 首次             |
| P2.3                  | ping_monitor                     | VM-sender            | -                                              | Running process                 | Suite 首次             |

> **⚠️ 重要:** Task 0 (Per-Case Mandatory Configuration Check) 必须在每个测试场景开始前执行，用于验证配置是否正确并在需要时自动部署+热重载。详见 [Per-Case Mandatory Configuration Check](#per-case-mandatory-configuration-check-task-0) 节。

> **⚠️ 重要:** Task 0.5 (告警与队列状态检查) 必须在每个测试场景开始前执行，确保无残留告警和诊断请求干扰测试。详见 [Per-Case Alert and Queue Status Check](#per-case-alert-and-queue-status-check-task-05) 节。

---

### Task P-1: 清理本地进程和队列 ⭐ (Suite 首次必须执行)

**目的:** 确保测试开始前本地没有残留的 webhook/netsherlock 进程，诊断队列已清空。

> **⚠️ 重要:** 这是测试前的**第一步**，必须在启动任何服务之前执行。残留进程会导致端口冲突、队列混乱、诊断结果不可预测。

**Step 1: 停止所有本地 webhook/netsherlock 进程**

```bash
echo "=== 清理本地 NetSherlock 进程 ==="

# 查找并终止所有 uvicorn webhook 进程
echo "1. 检查 uvicorn webhook 进程:"
WEBHOOK_PIDS=$(pgrep -f "uvicorn.*webhook" 2>/dev/null)
if [ -n "$WEBHOOK_PIDS" ]; then
  echo "   发现进程: $WEBHOOK_PIDS"
  echo "   正在终止..."
  kill $WEBHOOK_PIDS 2>/dev/null
  sleep 2
  # 强制终止仍存活的进程
  pgrep -f "uvicorn.*webhook" 2>/dev/null && kill -9 $(pgrep -f "uvicorn.*webhook") 2>/dev/null
  echo "   ✅ 已终止"
else
  echo "   ✅ 无残留 webhook 进程"
fi

# 查找并终止所有 netsherlock 相关进程
echo "2. 检查其他 netsherlock 进程:"
NS_PIDS=$(pgrep -f "netsherlock" 2>/dev/null | grep -v $$)
if [ -n "$NS_PIDS" ]; then
  echo "   发现进程: $NS_PIDS"
  echo "   正在终止..."
  kill $NS_PIDS 2>/dev/null
  sleep 2
  echo "   ✅ 已终止"
else
  echo "   ✅ 无残留 netsherlock 进程"
fi

# 查找并终止 alertmanager 进程
echo "3. 检查 alertmanager 进程:"
AM_PIDS=$(pgrep -f "alertmanager" 2>/dev/null)
if [ -n "$AM_PIDS" ]; then
  echo "   发现进程: $AM_PIDS"
  echo "   正在终止..."
  kill $AM_PIDS 2>/dev/null
  sleep 2
  echo "   ✅ 已终止"
else
  echo "   ✅ 无残留 alertmanager 进程"
fi

# 验证端口已释放
echo "4. 验证端口已释放:"
for PORT in 8080 9093; do
  if lsof -i :$PORT >/dev/null 2>&1; then
    echo "   ⚠️ 端口 $PORT 仍被占用:"
    lsof -i :$PORT
  else
    echo "   ✅ 端口 $PORT 已释放"
  fi
done
```

**Step 2: 清理诊断队列和状态数据**

```bash
echo "=== 清理队列和状态数据 ==="

# 清理 webhook 日志
echo "1. 清理 webhook 日志:"
rm -f /tmp/webhook.log && echo "   ✅ /tmp/webhook.log 已删除" || echo "   ℹ️ 文件不存在"

# 清理 alertmanager 数据目录
echo "2. 清理 alertmanager 数据:"
rm -rf /tmp/alertmanager-data/* 2>/dev/null && echo "   ✅ /tmp/alertmanager-data/ 已清空" || echo "   ℹ️ 目录不存在或为空"

# 清理 netsherlock 临时文件
echo "3. 清理 netsherlock 临时文件:"
rm -rf /tmp/netsherlock-* 2>/dev/null && echo "   ✅ /tmp/netsherlock-* 已删除" || echo "   ℹ️ 无临时文件"

# 清理 alertmanager 日志
echo "4. 清理 alertmanager 日志:"
rm -f /tmp/alertmanager.log && echo "   ✅ /tmp/alertmanager.log 已删除" || echo "   ℹ️ 文件不存在"

echo ""
echo "=== 清理完成 ==="
echo "现在可以继续执行 Task P0 及后续步骤"
```

**Expected:** 所有检查项显示 ✅，端口 8080 和 9093 已释放。

---

### Task P0: 部署和验证告警规则 (首次设置 / 规则变更后)

#### P0.1: Prometheus 告警规则 (Host 端)

**目的:** 确保 Prometheus 上仅加载 2 条测试告警规则，避免重复告警。

**本地规则文件:** `config/prometheus/netsherlock_test_alert.yml`

**Step 1: 检查当前规则**

```bash
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/rules'" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
netsherlock_rules = []
for g in data['data']['groups']:
    if 'netsherlock' in g.get('file', '').lower():
        for r in g.get('rules', []):
            netsherlock_rules.append(r['name'])

expected = ['NetSherlockHostLatencyDevTest', 'HostNetworkPacketLossDevTest']
extra = [r for r in netsherlock_rules if r not in expected]
missing = [r for r in expected if r not in netsherlock_rules]

print('=== Prometheus Alert Rules Check ===')
print(f'Rules count: {len(netsherlock_rules)} (expected: 2)')
for r in netsherlock_rules: print(f'  - {r}')

if len(netsherlock_rules) == 2 and not missing and not extra:
    print('✅ PASS: Exactly 2 expected rules loaded')
else:
    if missing: print(f'❌ MISSING: {missing}')
    if extra: print(f'❌ EXTRA (will cause duplicate alerts): {extra}')
    print('⚠️  Run Step 2 to deploy correct rules')
"
```

**Step 2: 部署正确的规则文件 (如果 Step 1 失败)**

```bash
# Copy rule file to node31 and reload Prometheus
scp config/prometheus/netsherlock_test_alert.yml smartx@192.168.70.31:/tmp/
ssh smartx@192.168.70.31 "sudo cp /tmp/netsherlock_test_alert.yml /etc/prometheus/ && sudo kill -HUP \$(pgrep prometheus)"
echo "Waiting for Prometheus reload..."
sleep 3
```

> **Note:** 使用 `kill -HUP` (SIGHUP) 让 Prometheus 热重载配置，无需重启服务。这比 restart 更快且不会丢失内存中的时间序列数据。

**Step 3: 验证部署生效**

```bash
# Re-run Step 1 to verify
# Expected: "✅ PASS: Exactly 2 expected rules loaded"
```

> **⚠️ 重要:** 部署告警规则后，还需要确保 Prometheus 配置了正确的 Alertmanager 目标。详见 [P0.3: Prometheus → Alertmanager 连接](#p03-prometheus--alertmanager-连接)。Prometheus 需要同时配置：
> - 生产 Alertmanager: `169.254.169.254:9903`（保持原有配置）
> - 本地 Alertmanager: `192.168.10.175:9093`（追加配置，用于接收测试告警）
>
> 如果只配置了生产 Alertmanager，测试告警将无法发送到本地 webhook，导致诊断无法触发。

---

#### P0.2: ping_monitor 配置 (VM 端)

**目的:** 确保 VM 上的 ping_monitor 配置正确的阈值，保证单告警行为。

**本地配置模板:** 见下方

> **⚠️ 重要:** 必须在每次测试前执行此检查。如果 Step 1 检查失败，**必须执行 Step 2 部署正确配置**，否则 cooldown 机制可能不生效，导致告警风暴。

**Step 1: 检查当前配置**

```bash
ssh root@192.168.77.83 "cat /etc/ping_monitor/config.yaml 2>/dev/null" | \
  python3 -c "
import yaml,sys
try:
    config = yaml.safe_load(sys.stdin)
    thresholds = config.get('thresholds', {})
    expected = {
        'rtt_warning_ms': 15.0,
        'rtt_critical_ms': 50.0,
        'loss_warning_pct': 10.0,
        'loss_critical_pct': 50.0,
        'cooldown_seconds': 3600
    }
    print('=== ping_monitor Thresholds Check ===')
    all_match = True
    for key, exp_val in expected.items():
        actual = thresholds.get(key)
        match = actual == exp_val
        status = '✅' if match else '❌'
        print(f'{status} {key}: {actual} (expected: {exp_val})')
        if not match: all_match = False
    if all_match:
        print('✅ PASS: All thresholds correct')
    else:
        print('⚠️  Run Step 2 to deploy correct config')
except Exception as e:
    print(f'❌ Config not found or invalid: {e}')
    print('⚠️  Run Step 2 to deploy config')
"
```

**Step 2: 部署正确的配置 (如果 Step 1 失败，必须执行)**

```bash
# Create config file from local template
cat > /tmp/ping_monitor_config.yaml << 'EOF'
netsherlock:
  url: "http://192.168.10.175:8080"
  api_key: ""

collection:
  count: 5
  cycle_pause: 2

evaluation:
  window_size: 3
  trigger_count: 2

thresholds:
  rtt_warning_ms: 15.0      # RTT > 15ms → warning (boundary mode)
  rtt_critical_ms: 50.0     # RTT > 50ms → critical (segment mode)
  loss_warning_pct: 10.0    # Loss > 10% → warning
  loss_critical_pct: 50.0   # Loss > 50% → critical
  cooldown_seconds: 3600    # 1 hour cooldown

monitors:
  - src_vm_name: "vm-sender"
    src_test_ip: "192.168.77.83"
    targets:
      - dst_vm_name: "vm-receiver"
        dst_test_ip: "192.168.76.244"
EOF

# Deploy to VM
ssh root@192.168.77.83 "mkdir -p /etc/ping_monitor"
scp /tmp/ping_monitor_config.yaml root@192.168.77.83:/etc/ping_monitor/config.yaml
echo "✅ Config deployed"
```

**Step 3: 部署 ping_monitor 脚本 (如果首次部署)**

```bash
# Copy ping_monitor script to VM
scp tools/vm-monitoring/ping_monitor.py root@192.168.77.83:/usr/local/bin/

# Install dependencies (if needed)
ssh root@192.168.77.83 "pip3 install pyyaml requests 2>/dev/null || echo 'Dependencies already installed'"
```

**Step 4: 验证部署生效 (必须)**

```bash
# Re-run Step 1 to verify - 必须看到所有 ✅ 才能继续
# Expected: "✅ PASS: All thresholds correct"
# 特别注意: cooldown_seconds 必须是 3600，不是 60 或其他值
```

---

#### P0.3: Prometheus → Alertmanager 连接

**目的:** 确保 Prometheus 配置为发送告警到本地 Alertmanager (192.168.10.175:9093)。

**Step 1: 检查 Alertmanager 配置**

```bash
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alertmanagers'" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
urls = [am['url'] for am in data['data']['activeAlertmanagers']]
local_am = any('192.168.10.175:9093' in url for url in urls)

print('=== Prometheus Alertmanager Config ===')
print('Active Alertmanagers:')
for url in urls: print(f'  - {url}')
if local_am:
    print('✅ PASS: Local Alertmanager (192.168.10.175:9093) configured')
else:
    print('❌ FAIL: Local Alertmanager NOT configured')
    print('⚠️  Add alerting config to /etc/prometheus/prometheus.yml on node31')
"
```

**Expected Output:**

```
=== Prometheus Alertmanager Config ===
Active Alertmanagers:
  - http://169.254.169.254:9903/prometheus/api/v1/alerts
  - http://192.168.10.175:9093/api/v2/alerts
✅ PASS: Local Alertmanager (192.168.10.175:9093) configured
```

**如果未配置，添加到 node31 的 `/etc/prometheus/prometheus.yml`:**

```yaml
alerting:
  alertmanagers:
  - api_version: v2
    static_configs:
    - targets: [192.168.10.175:9093]
```

然后重新加载: `ssh smartx@192.168.70.31 "sudo kill -HUP \$(pgrep prometheus)"`

---

### Task P1: 验证环境无残留故障

**目的:** 确保所有测试节点上没有残留的故障注入 (qdisc/netem)。

```bash
echo "=== Checking for residual faults ==="

# 1. node32 存储网卡 (port-storage) - System Network 测试使用
echo "1. node32 storage NIC (port-storage):"
ssh smartx@192.168.70.32 "DEV=\$(ip route get 70.0.0.31 | grep -oP 'dev \K\S+'); echo \"   Interface: \$DEV\"; tc qdisc show dev \$DEV 2>/dev/null | grep -v 'pfifo_fast\|noqueue\|mq\|fq_codel'" | \
  python3 -c "import sys; lines=sys.stdin.read().strip(); parts=lines.split('\n'); iface=parts[0] if parts else ''; rest='\n'.join(parts[1:]).strip() if len(parts)>1 else ''; print(iface); print('   ✅ Clean' if not rest else '   ⚠️ Residual: '+rest)"

# 2. node32 vnet35 (VM Network 测试使用)
echo "2. node32 vnet35:"
ssh smartx@192.168.70.32 "tc qdisc show dev vnet35 2>/dev/null | grep -v 'pfifo_fast\|noqueue\|mq\|fq_codel'" | \
  python3 -c "import sys; lines=sys.stdin.read().strip(); print('   ✅ Clean' if not lines else '   ⚠️ Residual: '+lines)"

# 3. node32 ifb0
echo "3. node32 ifb0:"
ssh smartx@192.168.70.32 "ip link show ifb0 2>/dev/null" | \
  python3 -c "import sys; lines=sys.stdin.read().strip(); print('   ⚠️ ifb0 exists (cleanup needed)' if lines else '   ✅ No ifb0')"

# 4. VM ens4
echo "4. VM-sender ens4:"
ssh root@192.168.77.83 "tc qdisc show dev ens4 2>/dev/null | grep -E 'netem|htb'" | \
  python3 -c "import sys; lines=sys.stdin.read().strip(); print('   ✅ Clean' if not lines else '   ⚠️ Residual: '+lines)"

echo "=== Check complete ==="
```

**如果有残留，执行清理:**

```bash
# Cleanup all residual faults (storage NIC + vnet35 + ifb0 + VM)
ssh smartx@192.168.70.32 "sudo bash -c 'STORAGE_DEV=\$(ip route get 70.0.0.31 | grep -oP \"dev \\K\\S+\"); tc qdisc del dev \$STORAGE_DEV root 2>/dev/null; tc qdisc del dev vnet35 ingress 2>/dev/null; ip link del ifb0 2>/dev/null'"
ssh root@192.168.77.83 "tc qdisc del dev ens4 root 2>/dev/null"
echo "✅ Cleanup done"
```

---

### Task P2: 启动测试服务

**目的:** 启动所有必要的服务并验证它们正常运行。

#### P2.1: 启动 Alertmanager (Agent Host)

```bash
# Check if already running
if curl -s http://localhost:9093/api/v2/status | jq -e '.cluster.status' > /dev/null 2>&1; then
  echo "✅ Alertmanager already running"
else
  echo "Starting Alertmanager..."
  /tmp/alertmanager-0.27.0.darwin-arm64/alertmanager \
    --config.file=/Users/admin/workspace/netsherlock/config/alertmanager/alertmanager.yml \
    --web.listen-address=:9093 \
    --storage.path=/tmp/alertmanager-data > /tmp/alertmanager.log 2>&1 &
  sleep 3
fi

# Verify
curl -s http://localhost:9093/api/v2/status | jq '{cluster: .cluster.status}'
```

**Expected:** `{"cluster": "ready"}` 或 `{"cluster": "settling"}`

#### P2.2: 启动 Webhook Server (Agent Host)

> **⚠️ 重要:** 必须同时设置以下两个环境变量才能启用自动诊断模式：
>
> - `DIAGNOSIS_AUTONOMOUS_ENABLED=true` - 启用自动诊断功能
> - `DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true` - 启用自动执行循环
>
> 缺少任何一个都会导致诊断在 interactive 模式下等待用户确认！

```bash
# Check if already running
if curl -s http://localhost:8080/health | jq -e '.status' > /dev/null 2>&1; then
  echo "✅ Webhook server already running"
else
  echo "Starting Webhook server..."
  cd /Users/admin/workspace/netsherlock
  GLOBAL_INVENTORY_PATH=config/global_inventory.yaml \
  DIAGNOSIS_ENGINE=controller \
  DIAGNOSIS_AUTONOMOUS_ENABLED=true \
  DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true \
  uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080 > /tmp/webhook.log 2>&1 &
  sleep 3
fi

# Verify
curl -s http://localhost:8080/health | jq .
```

**Expected:** `{"status": "healthy", ...}`

**关键环境变量:**

| 变量                                       | 值                               | 说明                                            |
| ------------------------------------------ | -------------------------------- | ----------------------------------------------- |
| `GLOBAL_INVENTORY_PATH`                  | `config/global_inventory.yaml` | VM 清单配置文件路径                             |
| `DIAGNOSIS_ENGINE`                       | `controller`                   | 使用 controller 引擎                            |
| `DIAGNOSIS_AUTONOMOUS_ENABLED`           | `true`                         | **必须设置** - 启用自动诊断功能           |
| `DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP`   | `true`                         | **必须设置** - 启用自动执行循环           |
| `DIAGNOSIS_AUTONOMOUS_KNOWN_ALERT_TYPES` | (见下方)                         | **必须设置** - 允许自动诊断的告警类型列表 |

**完整启动命令:**

```bash
GLOBAL_INVENTORY_PATH=config/global_inventory.yaml \
DIAGNOSIS_ENGINE=controller \
DIAGNOSIS_AUTONOMOUS_ENABLED=true \
DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true \
DIAGNOSIS_AUTONOMOUS_KNOWN_ALERT_TYPES='["NetSherlockHostLatencyDevTest","HostNetworkPacketLossDevTest","VMNetworkLatencyHigh","VMNetworkLatencyCritical","VMNetworkPacketLoss"]' \
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080 > /tmp/webhook.log 2>&1 &
```

> **⚠️ 注意:** 如果 `mode` 显示为 `interactive` 而不是 `autonomous`，请检查上述三个 `DIAGNOSIS_AUTONOMOUS_*` 环境变量是否都已设置。

#### P2.3: 启动 ping_monitor (VM-sender)

> **⚠️ 前置条件:** 必须先完成 P0.2 配置验证，确保 cooldown_seconds=3600。否则会导致告警风暴！

```bash
# 0. 验证配置 (必须先执行 P0.2，看到所有 ✅)
ssh root@192.168.77.83 "grep cooldown /etc/ping_monitor/config.yaml"
# 期望输出: cooldown_seconds: 3600

# 1. Kill existing (reset cooldown state)
ssh root@192.168.77.83 "pkill -f ping_monitor 2>/dev/null || true"
sleep 1

# 2. Start fresh
ssh root@192.168.77.83 "nohup python3 /usr/local/bin/ping_monitor.py \
  --config /etc/ping_monitor/config.yaml \
  > /var/log/ping_monitor.log 2>&1 &"
sleep 3

# 3. Verify running
ssh root@192.168.77.83 "pgrep -f ping_monitor > /dev/null && echo '✅ ping_monitor running' || echo '❌ ping_monitor NOT running'"
ssh root@192.168.77.83 "tail -3 /var/log/ping_monitor.log"
```

---

### Task P3: 最终验证检查清单

**在开始任何测试场景之前，确保所有检查通过:**

```bash
echo "=========================================="
echo "    E2E Test Prerequisites Final Check    "
echo "=========================================="

# P0.1: Prometheus rules
echo ""
echo "[P0.1] Prometheus Alert Rules:"
RULES_COUNT=$(ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/rules'" 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(sum(1 for g in d['data']['groups'] if 'netsherlock' in g.get('file','').lower() for r in g.get('rules',[])))" 2>/dev/null)
[ "$RULES_COUNT" = "2" ] && echo "  ✅ Exactly 2 rules" || echo "  ❌ Rules count: $RULES_COUNT (expected 2)"

# P0.2: ping_monitor config
echo ""
echo "[P0.2] ping_monitor Config:"
ssh root@192.168.77.83 "test -f /etc/ping_monitor/config.yaml && echo '  ✅ Config exists' || echo '  ❌ Config missing'"

# P0.3: Prometheus → Alertmanager
echo ""
echo "[P0.3] Prometheus → Alertmanager:"
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alertmanagers'" 2>/dev/null | \
  python3 -c "import json,sys; d=json.load(sys.stdin); urls=[am['url'] for am in d['data']['activeAlertmanagers']]; print('  ✅ Configured' if any('192.168.10.175:9093' in u for u in urls) else '  ❌ Not configured')" 2>/dev/null

# P2.1: Alertmanager
echo ""
echo "[P2.1] Alertmanager:"
curl -s http://localhost:9093/api/v2/status 2>/dev/null | jq -e '.cluster.status' > /dev/null 2>&1 && echo "  ✅ Running" || echo "  ❌ Not running"

# P2.2: Webhook
echo ""
echo "[P2.2] Webhook Server:"
curl -s http://localhost:8080/health 2>/dev/null | jq -e '.status' > /dev/null 2>&1 && echo "  ✅ Running" || echo "  ❌ Not running"

# P2.3: ping_monitor
echo ""
echo "[P2.3] ping_monitor:"
ssh root@192.168.77.83 "pgrep -f ping_monitor > /dev/null 2>&1 && echo '  ✅ Running' || echo '  ❌ Not running'"

echo ""
echo "=========================================="
```

**所有检查必须显示 ✅ 才能开始测试。**

---

### Task P1 (Legacy): Configure Host-side Prerequisites (One-time setup)

> **Note:** This section is kept for reference. Use Task P0-P3 above for the complete checklist.

#### Step 1: Verify Prometheus Alert Rules (CRITICAL - Avoid Duplicate Alerts)

**IMPORTANT:** The Prometheus server must have ONLY the 2 expected alert rules loaded. Extra rules will cause duplicate alerts during testing, which invalidates the single-alert guarantee.

Check that `netsherlock_test_alert.yml` is loaded with **exactly** the expected rules:

```bash
# Prometheus runs on node31, listening on storage network (70.0.0.31:9090)
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/rules'" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)

# Get all NetSherlock/HostNetwork rules from the test alert file
netsherlock_rules = []
for g in data['data']['groups']:
    if 'netsherlock' in g.get('file', '').lower():
        for r in g.get('rules', []):
            netsherlock_rules.append(r['name'])

expected = ['NetSherlockHostLatencyDevTest', 'HostNetworkPacketLossDevTest']
extra = [r for r in netsherlock_rules if r not in expected]
missing = [r for r in expected if r not in netsherlock_rules]

print('=== Prometheus Alert Rules Check ===')
print(f'Rules in netsherlock_test_alert.yml: {len(netsherlock_rules)}')
for r in netsherlock_rules: print(f'  - {r}')

if not missing and not extra:
    print('✅ PASS: Exactly 2 expected rules loaded, no extra rules')
else:
    if missing:
        print(f'❌ MISSING rules: {missing}')
    if extra:
        print(f'❌ EXTRA rules (will cause duplicate alerts): {extra}')
    print('⚠️  Re-deploy the alert rules file to fix this issue')
"
```

**Expected Output:**

```
=== Prometheus Alert Rules Check ===
Rules in netsherlock_test_alert.yml: 2
  - NetSherlockHostLatencyDevTest
  - HostNetworkPacketLossDevTest
✅ PASS: Exactly 2 expected rules loaded, no extra rules
```

**If missing or extra rules exist, re-deploy the correct rule file:**

```bash
# Copy the CORRECT rule file from local (only 2 rules) to node31
# Prometheus runs on node31, alert rules are in /etc/prometheus/
scp config/prometheus/netsherlock_test_alert.yml smartx@192.168.70.31:/tmp/

# Deploy to Prometheus config directory and reload (requires sudo)
ssh smartx@192.168.70.31 "sudo cp /tmp/netsherlock_test_alert.yml /etc/prometheus/ && sudo kill -HUP \$(pgrep prometheus)"

# Wait for reload and verify again
sleep 5
# Re-run the verification script above
```

#### Step 2: Verify Prometheus Alertmanager Configuration

Prometheus must send alerts to local Alertmanager (192.168.10.175:9093):

```bash
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alertmanagers'" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
urls = [am['url'] for am in data['data']['activeAlertmanagers']]
local_am = any('192.168.10.175:9093' in url for url in urls)
print('✅ Local Alertmanager configured' if local_am else '❌ Local Alertmanager NOT configured')
print('Active Alertmanagers:')
for url in urls: print(f'  - {url}')
"
```

**Expected:**

```
✅ Local Alertmanager configured
Active Alertmanagers:
  - http://169.254.169.254:9903/prometheus/api/v1/alerts
  - http://192.168.10.175:9093/api/v2/alerts
```

**If local Alertmanager missing, configure Prometheus:**

```bash
ssh smartx@192.168.70.31 "
# Add local Alertmanager to prometheus.yml (backup first)
sudo cp /etc/prometheus/prometheus.yml /etc/prometheus/prometheus.yml.bak

# Check if already configured
if ! grep -q '192.168.10.175:9093' /etc/prometheus/prometheus.yml; then
  echo 'Adding local Alertmanager configuration...'
  # You'll need to manually add the alerting section
fi
"
```

Add to `/etc/prometheus/prometheus.yml` on node31:

```yaml
alerting:
  alertmanagers:
  - api_version: v1
    path_prefix: /prometheus
    static_configs:
    - targets: [169.254.169.254:9903]
  - api_version: v2
    static_configs:
    - targets: [192.168.10.175:9093]
```

Then reload: `ssh smartx@192.168.70.31 "sudo kill -HUP \$(pgrep prometheus)"`

### Task P2: Configure Agent Host Prerequisites (One-time setup)

#### Step 1: Create/Verify .env Configuration

```bash
cat > /Users/admin/workspace/netsherlock/.env << 'EOF'
# NetSherlock E2E Test Configuration
DEBUG=false

# SSH Settings
SSH_DEFAULT_USER=smartx
SSH_DEFAULT_PORT=22
SSH_PRIVATE_KEY_PATH=~/.ssh/id_rsa
SSH_CONNECT_TIMEOUT=10
SSH_COMMAND_TIMEOUT=60


# BPF Tools Settings
BPF_LOCAL_TOOLS_PATH=/Users/admin/workspace/troubleshooting-tools/measurement-tools
BPF_REMOTE_TOOLS_PATH=/tmp/netsherlock-tools
BPF_DEPLOY_MODE=auto

# LLM Settings
LLM_MODEL=claude-haiku-4-5-20251001

# Diagnosis Settings
DIAGNOSIS_DEFAULT_MODE=autonomous
DIAGNOSIS_AUTONOMOUS_ENABLED=true
DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true

# Webhook Settings
WEBHOOK_ALLOW_INSECURE=true

# Engine and Inventory
DIAGNOSIS_ENGINE=controller
GLOBAL_INVENTORY_PATH=/Users/admin/workspace/netsherlock/config/global_inventory.yaml
PROJECT_PATH=/Users/admin/workspace/netsherlock
EOF
```

#### Step 2: Verify GlobalInventory Configuration

```bash
python3 -c "
import yaml
with open('config/global_inventory.yaml') as f:
    inv = yaml.safe_load(f)
hosts = inv.get('hosts', {})
vms = inv.get('vms', {})
required_hosts = ['node31', 'node32', 'node33', 'node34']
required_vms = ['vm-sender', 'vm-receiver']
missing_hosts = [h for h in required_hosts if h not in hosts]
missing_vms = [v for v in required_vms if v not in vms]
if missing_hosts or missing_vms:
    print('❌ Missing inventory entries:')
    for h in missing_hosts: print(f'  - host: {h}')
    for v in missing_vms: print(f'  - vm: {v}')
else:
    print('✅ GlobalInventory configured correctly')
    print('Hosts:', list(hosts.keys()))
    print('VMs:', list(vms.keys()))
"
```

### Task P3: Deploy VM ping_monitor (One-time setup for VM tests)

#### Step 1: Deploy ping_monitor Script to Sender VM

```bash
# Copy ping_monitor script
scp tools/vm-monitoring/ping_monitor.py root@192.168.77.83:/usr/local/bin/

# Create config directory
ssh root@192.168.77.83 "mkdir -p /etc/ping_monitor"

# Install dependencies
ssh root@192.168.77.83 "pip3 install pyyaml requests"
```

#### Step 2: Create ping_monitor Configuration

```bash
cat > /tmp/ping_monitor_config.yaml << 'EOF'
netsherlock:
  url: "http://192.168.10.175:8080"
  api_key: ""

collection:
  count: 5
  cycle_pause: 2

evaluation:
  window_size: 3
  trigger_count: 2

thresholds:
  rtt_warning_ms: 15.0      # RTT > 15ms → warning (boundary mode)
  rtt_critical_ms: 50.0     # RTT > 50ms → critical (segment mode)
  loss_warning_pct: 10.0    # Loss > 10% → warning
  loss_critical_pct: 50.0   # Loss > 50% → critical
  cooldown_seconds: 3600    # 1 hour

monitors:
  - src_vm_name: "vm-sender"
    src_test_ip: "192.168.77.83"
    targets:
      - dst_vm_name: "vm-receiver"
        dst_test_ip: "192.168.76.244"
EOF

scp /tmp/ping_monitor_config.yaml root@192.168.77.83:/etc/ping_monitor/config.yaml
```

#### Step 3: Verify ping_monitor Configuration (CRITICAL - Avoid Duplicate VM Alerts)

**IMPORTANT:** The ping_monitor config must have the correct thresholds to ensure single-alert behavior:

- Warning thresholds trigger boundary mode diagnosis
- Critical thresholds trigger segment mode diagnosis
- Only the highest-severity alert fires (not both warning and critical)

```bash
ssh root@192.168.77.83 "cat /etc/ping_monitor/config.yaml" | \
  python3 -c "
import yaml,sys
config = yaml.safe_load(sys.stdin)
thresholds = config.get('thresholds', {})

expected = {
    'rtt_warning_ms': 15.0,
    'rtt_critical_ms': 50.0,
    'loss_warning_pct': 10.0,
    'loss_critical_pct': 50.0,
    'cooldown_seconds': 3600
}

print('=== ping_monitor Threshold Configuration ===')
all_match = True
for key, expected_val in expected.items():
    actual_val = thresholds.get(key)
    match = actual_val == expected_val
    status = '✅' if match else '❌'
    print(f'{status} {key}: {actual_val} (expected: {expected_val})')
    if not match:
        all_match = False

if all_match:
    print('✅ PASS: All thresholds match expected values')
else:
    print('❌ FAIL: Some thresholds do not match - re-deploy config')
"
```

**Expected Output:**

```
=== ping_monitor Threshold Configuration ===
✅ rtt_warning_ms: 15.0 (expected: 15.0)
✅ rtt_critical_ms: 50.0 (expected: 50.0)
✅ loss_warning_pct: 10.0 (expected: 10.0)
✅ loss_critical_pct: 50.0 (expected: 50.0)
✅ cooldown_seconds: 3600 (expected: 3600)
✅ PASS: All thresholds match expected values
```

**If thresholds don't match, re-deploy the config:**

```bash
# Re-run Step 2 above to create and deploy the correct config
```

### Task P4: Start Agent Host Services

#### Step 1: Start Local Alertmanager

```bash
# Download if not present
if [ ! -f /tmp/alertmanager-0.27.0.darwin-arm64/alertmanager ]; then
  cd /tmp
  curl -sLO "https://github.com/prometheus/alertmanager/releases/download/v0.27.0/alertmanager-0.27.0.darwin-arm64.tar.gz"
  tar xzf alertmanager-0.27.0.darwin-arm64.tar.gz
fi

# Start Alertmanager
/tmp/alertmanager-0.27.0.darwin-arm64/alertmanager \
  --config.file=/Users/admin/workspace/netsherlock/config/alertmanager/alertmanager.yml \
  --web.listen-address=:9093 \
  --storage.path=/tmp/alertmanager-data &

# Verify
sleep 2
curl -s http://localhost:9093/api/v2/status | jq '{cluster: .cluster.status}'
```

**Expected:** `{"cluster": "ready"}`

#### Step 2: Start Webhook Server

```bash
cd /Users/admin/workspace/netsherlock

# Option 1: CLI (recommended)
netsherlock serve --engine controller --inventory config/global_inventory.yaml --port 8080 &

# Option 2: Direct uvicorn
GLOBAL_INVENTORY_PATH=config/global_inventory.yaml \
DIAGNOSIS_ENGINE=controller \
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080 &

# Verify
sleep 2
curl -s http://localhost:8080/health | jq .
```

**Expected:** `{"status": "healthy"}`

#### Step 3: Start ping_monitor on Sender VM (for VM tests)

```bash
ssh root@192.168.77.83 "nohup python3 /usr/local/bin/ping_monitor.py \
  --config /etc/ping_monitor/config.yaml \
  > /var/log/ping_monitor.log 2>&1 &"

# Verify
sleep 3
ssh root@192.168.77.83 "pgrep -f ping_monitor && echo '✅ ping_monitor running' || echo '❌ ping_monitor NOT running'"
ssh root@192.168.77.83 "tail -3 /var/log/ping_monitor.log"
```

---

## Pre-Case Verification Checklist

**Run this checklist BEFORE each test scenario to ensure both host-side configurations are normal.**

### For System Network Tests (Scenario 1 & 2)

```bash
echo "=== Pre-Case Check: System Network Tests ==="

# Check 1: Prometheus Alertmanagers active
echo "1. Checking Prometheus Alertmanagers..."
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alertmanagers'" | \
  python3 -c "
import json,sys
d = json.load(sys.stdin)
urls = [am['url'] for am in d['data']['activeAlertmanagers']]
local = any('192.168.10.175:9093' in u for u in urls)
print('   ✅ Local Alertmanager active' if local else '   ❌ Local Alertmanager MISSING')
"

# Check 2: Local Alertmanager running
echo "2. Checking Local Alertmanager..."
curl -s http://localhost:9093/api/v2/status | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
    print('   ✅ Alertmanager running (cluster:', d.get('cluster',{}).get('status','?'), ')')
except: print('   ❌ Alertmanager NOT running')
"

# Check 3: Webhook server running
echo "3. Checking Webhook Server..."
curl -s http://localhost:8080/health | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
    print('   ✅ Webhook server healthy' if d.get('status')=='healthy' else '   ❌ Webhook unhealthy')
except: print('   ❌ Webhook server NOT running')
"

# Check 4: No existing fault injection on node32 (host-sender)
echo "4. Checking node32 has no existing qdisc on management NIC..."
ssh smartx@192.168.70.32 "tc qdisc show dev \$(ip route get 192.168.70.31 | grep -oP 'dev \K\S+') 2>/dev/null | grep -v 'pfifo_fast\|noqueue\|mq\|fq_codel'" | \
  python3 -c "
import sys
lines = sys.stdin.read().strip()
print('   ✅ No custom qdisc' if not lines else '   ⚠️  Existing qdisc: ' + lines)
"

echo "=== Pre-Case Check Complete ==="
```

### For VM Network Tests (Scenario 3, 4, 5)

```bash
echo "=== Pre-Case Check: VM Network Tests ==="

# Check 1: Webhook server running
echo "1. Checking Webhook Server..."
curl -s http://localhost:8080/health | python3 -c "
import json,sys
try:
    d = json.load(sys.stdin)
    print('   ✅ Webhook server healthy' if d.get('status')=='healthy' else '   ❌ Webhook unhealthy')
except: print('   ❌ Webhook server NOT running')
"

# Check 2: ping_monitor running on sender VM
echo "2. Checking ping_monitor on sender VM..."
ssh root@192.168.77.83 "pgrep -f ping_monitor >/dev/null && echo '   ✅ ping_monitor running' || echo '   ❌ ping_monitor NOT running'"

# Check 3: No existing fault injection on host vnet35
echo "3. Checking no existing qdisc on vnet35 (host node32)..."
ssh smartx@192.168.70.32 "tc qdisc show dev vnet35 2>/dev/null | grep -v 'pfifo_fast\|noqueue'" | \
  python3 -c "
import sys
lines = sys.stdin.read().strip()
print('   ✅ No custom qdisc on vnet35' if not lines else '   ⚠️  Existing qdisc: ' + lines)
"

# Check 4: No existing IFB device
echo "4. Checking no existing ifb0 device..."
ssh smartx@192.168.70.32 "ip link show ifb0 2>/dev/null" | \
  python3 -c "
import sys
lines = sys.stdin.read().strip()
print('   ⚠️  ifb0 exists (cleanup needed)' if lines else '   ✅ No ifb0 device')
"

# Check 5: No existing qdisc on VM ens4 (for Scenario 5)
echo "5. Checking no existing qdisc on VM ens4..."
ssh root@192.168.77.83 "tc qdisc show dev ens4 2>/dev/null | grep -v 'pfifo_fast\|noqueue'" | \
  python3 -c "
import sys
lines = sys.stdin.read().strip()
print('   ✅ No custom qdisc on VM ens4' if not lines else '   ⚠️  Existing qdisc: ' + lines)
"

echo "=== Pre-Case Check Complete ==="
```

---

## Per-Case Mandatory Configuration Check (Task 0)

> **⚠️ 关键:** 此检查必须在每个测试场景的 Task X.1 之前执行。配置不正确会导致测试失败或告警风暴。

**目的:** 确保 host 端 Prometheus 规则和 VM 端 ping_monitor 配置都已正确部署，并在需要时自动从本地 scp 部署并使其生效。

### 本地标准配置文件 (Source of Truth)

| 组件                | 本地文件                                         | 远程位置                                              | 生效方式                      |
| ------------------- | ------------------------------------------------ | ----------------------------------------------------- | ----------------------------- |
| Prometheus 告警规则 | `config/prometheus/netsherlock_test_alert.yml` | node31:`/etc/prometheus/netsherlock_test_alert.yml` | `kill -HUP` (SIGHUP 热重载) |
| ping_monitor 配置   | 内嵌模板 (见下方)                                | VM:`/etc/ping_monitor/config.yaml`                  | 重启 ping_monitor 进程        |

**本地规则文件特点:**

- **仅包含 2 条测试所需的告警规则**（`NetSherlockHostLatencyDevTest`, `HostNetworkPacketLossDevTest`）
- 避免其他规则导致重复告警
- 阈值已针对测试场景优化

### Task 0.1: 检查并部署 Prometheus 告警规则 (Host 端)

**流程:** 检查远程规则 → 不符合预期则 scp 本地文件 → SIGHUP 热重载 Prometheus → 验证生效

```bash
echo "=== Task 0.1: Prometheus Alert Rules Check ==="

# 1. 检查当前规则
RESULT=$(ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/rules'" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
netsherlock_rules = []
for g in data['data']['groups']:
    if 'netsherlock' in g.get('file', '').lower():
        for r in g.get('rules', []):
            netsherlock_rules.append(r['name'])

expected = ['NetSherlockHostLatencyDevTest', 'HostNetworkPacketLossDevTest']
missing = [r for r in expected if r not in netsherlock_rules]
extra = [r for r in netsherlock_rules if r not in expected]

if len(netsherlock_rules) == 2 and not missing and not extra:
    print('OK')
else:
    print('NEED_DEPLOY')
" 2>/dev/null)

if [ "$RESULT" = "OK" ]; then
  echo "  ✅ Prometheus rules already correct (2 rules)"
else
  echo "  ⚠️ Rules need deployment, deploying..."

  # 2. 部署规则文件
  scp config/prometheus/netsherlock_test_alert.yml smartx@192.168.70.31:/tmp/
  ssh smartx@192.168.70.31 "sudo cp /tmp/netsherlock_test_alert.yml /etc/prometheus/"

  # 3. SIGHUP 热重载 Prometheus
  ssh smartx@192.168.70.31 "sudo kill -HUP \$(pgrep prometheus)"
  echo "  ⏳ Waiting for Prometheus hot reload..."
  sleep 3

  # 4. 验证部署
  ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/rules'" | \
    python3 -c "
import json,sys
data = json.load(sys.stdin)
count = sum(1 for g in data['data']['groups'] if 'netsherlock' in g.get('file','').lower() for r in g.get('rules',[]))
print(f'  ✅ Prometheus reloaded: {count} rules loaded' if count == 2 else f'  ❌ FAILED: {count} rules (expected 2)')
"
fi
```

### Task 0.2: 检查并部署 ping_monitor 配置 (VM 端)

**流程:** 检查远程配置 → 不符合预期则 scp 本地模板 → 重启 ping_monitor 进程 → 验证生效

**本地配置模板特点:**

- `cooldown_seconds: 3600` (1小时冷却，避免告警风暴)
- 正确的阈值分级 (warning 15ms/10%, critical 50ms/50%)
- webhook URL 指向本地 Agent Host

```bash
echo "=== Task 0.2: ping_monitor Config Check ==="

# 1. 检查当前配置
RESULT=$(ssh root@192.168.77.83 "cat /etc/ping_monitor/config.yaml 2>/dev/null" | \
  python3 -c "
import yaml,sys
try:
    config = yaml.safe_load(sys.stdin)
    thresholds = config.get('thresholds', {})
    expected = {
        'rtt_warning_ms': 15.0,
        'rtt_critical_ms': 50.0,
        'loss_warning_pct': 10.0,
        'loss_critical_pct': 50.0,
        'cooldown_seconds': 3600
    }
    all_match = all(thresholds.get(k) == v for k, v in expected.items())
    print('OK' if all_match else 'NEED_DEPLOY')
except:
    print('NEED_DEPLOY')
" 2>/dev/null)

if [ "$RESULT" = "OK" ]; then
  echo "  ✅ ping_monitor config already correct"
else
  echo "  ⚠️ Config needs deployment, deploying..."

  # 2. 创建并部署配置
  cat > /tmp/ping_monitor_config.yaml << 'EOF'
netsherlock:
  url: "http://192.168.10.175:8080"
  api_key: ""

collection:
  count: 5
  cycle_pause: 2

evaluation:
  window_size: 3
  trigger_count: 2

thresholds:
  rtt_warning_ms: 15.0
  rtt_critical_ms: 50.0
  loss_warning_pct: 10.0
  loss_critical_pct: 50.0
  cooldown_seconds: 3600

monitors:
  - src_vm_name: "vm-sender"
    src_test_ip: "192.168.77.83"
    targets:
      - dst_vm_name: "vm-receiver"
        dst_test_ip: "192.168.76.244"
EOF

  ssh root@192.168.77.83 "mkdir -p /etc/ping_monitor"
  scp /tmp/ping_monitor_config.yaml root@192.168.77.83:/etc/ping_monitor/config.yaml

  # 3. 重启 ping_monitor 使配置生效 (如果正在运行)
  ssh root@192.168.77.83 "pkill -f ping_monitor 2>/dev/null && sleep 1 && nohup python3 /usr/local/bin/ping_monitor.py --config /etc/ping_monitor/config.yaml > /var/log/ping_monitor.log 2>&1 &" 2>/dev/null
  sleep 2

  # 4. 验证部署
  ssh root@192.168.77.83 "grep cooldown /etc/ping_monitor/config.yaml" | \
    python3 -c "import sys; line=sys.stdin.read().strip(); print('  ✅ Config deployed: ' + line if '3600' in line else '  ❌ FAILED')"
fi

echo "=== Task 0 Complete - Ready for test scenario ==="
```

> **生效机制说明:**
>
> - **Prometheus (Host):** 使用 `kill -HUP` (SIGHUP) 信号触发热重载，无需重启服务。优点：速度快，不丢失内存中的时间序列数据。
> - **ping_monitor (VM):** 使用进程重启使新配置生效。重启同时会清除 cooldown 状态，确保测试场景可以立即触发告警。

---

## Per-Case Alert and Queue Status Check (Task 0.5)

**目的:** 在每个测试场景开始前，验证：

1. **Alertmanager 路由配置正确** - Prometheus 必须指向 webhook 机器的 Alertmanager
2. **告警规则数量正确** - 只有预期的 2 条测试规则，无多余规则
3. **无残留活跃告警** - 确保之前测试的告警已清除
4. **诊断队列为空** - 无待处理的诊断请求

> **⚠️ 重要:** 此检查必须在故障注入之前执行。配置错误或残留状态会导致测试结果不可预测。

### Step 1: 验证 Prometheus → Alertmanager 路由配置

```bash
echo "=== 检查 Prometheus Alertmanager 配置 ==="
AM_CONFIG=$(ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alertmanagers'")
echo "$AM_CONFIG" | python3 -c "
import json,sys
d = json.load(sys.stdin)
active = d['data']['activeAlertmanagers']
print(f'Active Alertmanagers: {len(active)}')
for am in active:
    url = am['url']
    if '192.168.10.175:9093' in url:
        print(f'  ✅ {url} (正确指向 webhook 机器)')
    else:
        print(f'  ❌ {url} (错误! 应指向 192.168.10.175:9093)')
if not active:
    print('  ❌ 无活跃 Alertmanager! 需要配置 Prometheus')
"
```

**预期输出:** `✅ http://192.168.10.175:9093/api/v2/alerts (正确指向 webhook 机器)`

**如果配置错误，修复方法:**

```bash
# 修复 Prometheus alertmanager 配置
ssh smartx@192.168.70.31 "sudo bash" << 'EOF'
awk '
/^  alertmanagers:/ { in_section=1; print "  alertmanagers:"; print "  - static_configs:"; print "    - targets:"; print "      - 192.168.10.175:9093"; next }
in_section && /^[a-z]/ { in_section=0 }
in_section { next }
{ print }
' /etc/prometheus/prometheus.yml > /tmp/prometheus_fixed.yml
cp /tmp/prometheus_fixed.yml /etc/prometheus/prometheus.yml
pkill -HUP prometheus
echo "✅ 已修复并重载"
EOF
```

### Step 2: 验证告警规则数量和内容

```bash
echo "=== 检查 Prometheus 告警规则 ==="
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/rules'" | python3 -c "
import json,sys
data = json.load(sys.stdin)
ns_rules = []
for g in data['data']['groups']:
    if 'netsherlock' in g['name'].lower():
        for r in g['rules']:
            if r['type'] == 'alerting':
                ns_rules.append(r['name'])

print(f'NetSherlock 测试规则数量: {len(ns_rules)}')
expected = ['NetSherlockHostLatencyDevTest', 'HostNetworkPacketLossDevTest']
for rule in ns_rules:
    if rule in expected:
        print(f'  ✅ {rule}')
    else:
        print(f'  ❌ {rule} (多余规则! 可能产生干扰)')

for exp in expected:
    if exp not in ns_rules:
        print(f'  ❌ 缺少规则: {exp}')

if set(ns_rules) == set(expected):
    print('✅ 规则配置正确 (恰好 2 条)')
else:
    print('⚠️  规则配置不符合预期，请检查 /etc/prometheus/netsherlock_test_alert.yml')
"
```

**预期输出:** `✅ 规则配置正确 (恰好 2 条)`

### Step 3: 检查 Prometheus 中的活跃告警

```bash
echo "=== 检查 Prometheus 活跃告警 ==="
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alerts'" | python3 -c "
import json,sys
data = json.load(sys.stdin)
ns_alerts = [a for a in data['data']['alerts'] if 'NetSherlock' in a['labels'].get('alertname','') or 'HostNetwork' in a['labels'].get('alertname','')]
firing = [a for a in ns_alerts if a['state'] == 'firing']
pending = [a for a in ns_alerts if a['state'] == 'pending']

print(f'NetSherlock 相关告警: firing={len(firing)}, pending={len(pending)}')
if firing:
    print('⚠️  FIRING 告警:')
    for a in firing:
        h = a['labels'].get('hostname','?')
        t = a['labels'].get('to_hostname','?')
        print(f'    {a[\"labels\"][\"alertname\"]}: {h} → {t}')
if pending:
    print('⚠️  PENDING 告警:')
    for a in pending:
        h = a['labels'].get('hostname','?')
        t = a['labels'].get('to_hostname','?')
        print(f'    {a[\"labels\"][\"alertname\"]}: {h} → {t}')
if not firing and not pending:
    print('✅ 无活跃 NetSherlock 告警')
"
```

**预期输出:** `✅ 无活跃 NetSherlock 告警`

### Step 4: 检查 Alertmanager 中的告警

```bash
echo "=== 检查 Alertmanager 告警状态 ==="
curl -s http://localhost:9093/api/v2/alerts | python3 -c "
import json,sys
alerts = json.load(sys.stdin)
ns_alerts = [a for a in alerts if 'NetSherlock' in a['labels'].get('alertname','') or 'HostNetwork' in a['labels'].get('alertname','')]

print(f'Alertmanager 中 NetSherlock 相关告警: {len(ns_alerts)}')
for a in ns_alerts:
    name = a['labels'].get('alertname','?')
    h = a['labels'].get('hostname','?')
    t = a['labels'].get('to_hostname','?')
    state = a['status']['state']
    print(f'  ⚠️  {name}: {h} → {t} (state={state})')
if not ns_alerts:
    print('✅ Alertmanager 无 NetSherlock 告警')
"
```

**预期输出:** `✅ Alertmanager 无 NetSherlock 告警`

### Step 5: 检查 Webhook 诊断队列

```bash
echo "=== 检查 Webhook 诊断队列 ==="
HEALTH=$(curl -s http://localhost:8080/health 2>/dev/null)
if [ -z "$HEALTH" ]; then
    echo "❌ Webhook 服务未运行"
else
    echo "$HEALTH" | python3 -c "
import json,sys
d = json.load(sys.stdin)
queue_size = d.get('queue_size', 0)
print(f'诊断队列大小: {queue_size}')
if queue_size > 0:
    print(f'⚠️  队列中有 {queue_size} 个待处理诊断请求')
    print('    等待队列清空或重启 webhook 服务')
else:
    print('✅ 诊断队列为空')
"
fi
```

**预期输出:** `✅ 诊断队列为空`

### 处理残留告警/诊断

**如果发现残留告警:**

1. 等待告警自动恢复（清除故障注入后通常 1-2 分钟）
2. 或者重启 Alertmanager 清除告警状态：
   ```bash
   pkill alertmanager
   rm -rf /tmp/alertmanager-data
   # 重新启动 Alertmanager
   ```

**如果队列中有诊断请求:**

1. 等待诊断完成（检查 webhook 日志中的 `diagnosis_completed`）
2. 或者重启 webhook 服务清空队列

---

## Scenario 1: System Network Latency Boundary

### Alert Trigger Condition

| Property                 | Value                                                                      |
| ------------------------ | -------------------------------------------------------------------------- |
| **Alert Name**     | `NetSherlockHostLatencyDevTest`                                          |
| **Metric**         | `host_to_host_max_ping_time_ns_bucket`                                   |
| **Condition**      | P90 histogram quantile > 15,000,000 ns (15ms)                              |
| **For Duration**   | 10 seconds                                                                 |
| **Fault Required** | **≥20ms latency** on `port-storage` of node32 (target: 70.0.0.31) |
| **Labels**         | `network_type="system"`, `severity="info"`                             |

### Task 1.0: Mandatory Configuration Check

```bash
# 执行 Per-Case Mandatory Configuration Check (Task 0) - 见上方
# 必须看到两个 ✅ 才能继续
```

### Task 1.1: Pre-Case Verification

```bash
# Run system network pre-case check (see above)
# Ensure all checks pass before proceeding
```

### Task 1.2: Verify Baseline

```bash
# Verify baseline latency from node32 to node31 via STORAGE network (70.0.0.x)
ssh smartx@192.168.70.32 "ping -c 5 70.0.0.31"
```

**Expected:** RTT ~0.1-0.3ms (baseline via storage network)

### Task 1.3: Inject Fault

**Inject 20ms delay on node32's `port-storage` NIC (target: 70.0.0.31 storage network)**

```bash
ssh smartx@192.168.70.32 "sudo bash" <<'EOF'
TC=/sbin/tc
# Auto-detect the NIC used for STORAGE network (70.0.0.x)
DEV=$(ip route get 70.0.0.31 | grep -oP 'dev \K\S+')
TARGET=70.0.0.31

echo "Detected storage NIC: $DEV (should be port-storage)"

# Clean any existing qdisc
$TC qdisc del dev $DEV root 2>/dev/null || true

# Setup HTB with selective delay
$TC qdisc add dev $DEV root handle 1: htb default 10
$TC class add dev $DEV parent 1: classid 1:10 htb rate 10gbit
$TC class add dev $DEV parent 1: classid 1:20 htb rate 10gbit
$TC qdisc add dev $DEV parent 1:20 handle 20: netem delay 20ms

# Filter: ICMP packets to target (storage network)
$TC filter add dev $DEV protocol ip parent 1:0 prio 1 u32 \
    match ip dst ${TARGET}/32 \
    match ip protocol 1 0xff \
    flowid 1:20

echo "✅ Injected 20ms delay for ICMP to $TARGET on $DEV"
$TC qdisc show dev $DEV
EOF
```

### Task 1.4: Verify Fault Effective

```bash
# Verify latency on STORAGE network (must ping 70.0.0.31, not management network)
ssh smartx@192.168.70.32 "ping -c 5 70.0.0.31"
```

**Expected:** RTT ~20.1-20.3ms (baseline + 20ms injection via storage network)

### Task 1.5: Wait for Alert to Fire

```bash
echo "Waiting for alert to fire (timeout: 2 minutes)..."
for i in {1..24}; do
  ALERT=$(ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alerts'" | \
    python3 -c "
import json,sys
data = json.load(sys.stdin)
alerts = [a for a in data['data']['alerts'] if 'NetSherlock' in a['labels'].get('alertname','') and 'Latency' in a['labels'].get('alertname','')]
firing = [a for a in alerts if a['state']=='firing']
if firing:
    print('FIRING: ' + firing[0]['labels']['alertname'])
elif alerts:
    print('PENDING')
else:
    print('NONE')
" 2>/dev/null)
  echo "[$i/24] Alert status: $ALERT"
  [[ "$ALERT" == FIRING* ]] && break
  sleep 5
done
```

**Expected:** Alert fires within 30-60 seconds

### Task 1.6: Verify Diagnosis Triggered

```bash
# Check webhook received alert and started diagnosis
curl -s http://localhost:8080/diagnoses | jq '.[-1] | {request_id, status, network_type, request_type}'
```

**Expected:**

```json
{
  "request_id": "...",
  "status": "running" or "completed",
  "network_type": "system",
  "request_type": "latency"
}
```

### Task 1.7: Wait for Diagnosis Completion

```bash
DIAG_ID=$(curl -s http://localhost:8080/diagnoses | jq -r '.[-1].request_id')
echo "Monitoring diagnosis: $DIAG_ID"

for i in {1..60}; do
  STATUS=$(curl -s "http://localhost:8080/diagnoses/$DIAG_ID" | jq -r '.status')
  echo "[$i/60] Status: $STATUS"
  [ "$STATUS" = "completed" ] && break
  sleep 5
done
```

### Task 1.8: Verify Results

```bash
# Check measurement directory created
ls -la measurement-*/ | tail -5

# Check analysis report
LATEST_DIR=$(ls -td measurement-*/ | head -1)
cat "${LATEST_DIR}diagnosis_report.md" | head -50

# Verify correct skill was used
grep -E "system-network|System Network" "${LATEST_DIR}"*.md
```

**Expected:** Report shows "System Network Latency Analysis" with boundary attribution

### Task 1.9: Cleanup Fault Injection

```bash
# Cleanup fault on node32 (host-sender) STORAGE NIC (port-storage)
ssh smartx@192.168.70.32 "sudo bash -c 'DEV=\$(ip route get 70.0.0.31 | grep -oP \"dev \\K\\S+\"); /sbin/tc qdisc del dev \$DEV root 2>/dev/null && echo \"✅ Cleaned \$DEV\" || echo \"⚠️  Nothing to clean\"'"
```

---

## Scenario 2: System Network Packet Drop Boundary

> **⚠️ 阈值调整说明:** 告警阈值从原来的 1% 调整为 3%，因为存储网络 (node31 ↔ node32) 存在约 1.3% 的真实丢包。使用 1% 阈值会导致误报。故障注入量相应从 5% 提高到 10%，确保能可靠触发告警。

### Alert Trigger Condition

| Property                 | Value                                                                        |
| ------------------------ | ---------------------------------------------------------------------------- |
| **Alert Name**     | `HostNetworkPacketLossDevTest`                                             |
| **Metric**         | `host_network_ping_packet_loss_percent`                                    |
| **Condition**      | loss > 0.03 (3%)                                                             |
| **For Duration**   | 10 seconds                                                                   |
| **Fault Required** | **≥10% packet loss** on `port-storage` of node32 (target: 70.0.0.31) |
| **Labels**         | `network_type="system"`, `problem_type="packet_drop"`                    |

### Task 2.0: Mandatory Configuration Check

```bash
# 执行 Per-Case Mandatory Configuration Check (Task 0) - 见 Scenario 1 上方
# 必须看到两个 ✅ 才能继续
```

### Task 2.1: Pre-Case Verification

```bash
# Run system network pre-case check
# Ensure all checks pass before proceeding
```

### Task 2.2: Inject Fault

**Inject 10% packet loss on node32's `port-storage` NIC (target: 70.0.0.31 storage network)**

> **⚠️ 重要:** 必须使用下方的 HTB+filter 方法实现**精确丢包**，只影响 node32→node31 的 ICMP 流量。
>
> **禁止使用:** `tc qdisc add dev $DEV root netem loss 10%` - 这会影响 node32 到**所有节点**的流量，导致多个告警触发，干扰测试结果。

```bash
ssh smartx@192.168.70.32 "sudo bash" <<'EOF'
TC=/sbin/tc
# Auto-detect the NIC used for STORAGE network (70.0.0.x)
DEV=$(ip route get 70.0.0.31 | grep -oP 'dev \K\S+')
TARGET=70.0.0.31

echo "Detected storage NIC: $DEV (should be port-storage)"

# Clean any existing qdisc
$TC qdisc del dev $DEV root 2>/dev/null || true

# Setup HTB with selective packet loss
$TC qdisc add dev $DEV root handle 1: htb default 10
$TC class add dev $DEV parent 1: classid 1:10 htb rate 10gbit
$TC class add dev $DEV parent 1: classid 1:20 htb rate 10gbit
$TC qdisc add dev $DEV parent 1:20 handle 20: netem loss 10%

# Filter: ICMP packets to target (storage network)
$TC filter add dev $DEV protocol ip parent 1:0 prio 1 u32 \
    match ip dst ${TARGET}/32 \
    match ip protocol 1 0xff \
    flowid 1:20

echo "✅ Injected 10% packet loss for ICMP to $TARGET on $DEV"
EOF
```

### Task 2.3: Verify Fault Effective

```bash
# Verify packet loss on STORAGE network (must ping 70.0.0.31, not management network)
ssh smartx@192.168.70.32 "ping -c 20 70.0.0.31"
```

**Expected:** ~10% packet loss in statistics (via storage network)

### Task 2.4: Wait for Alert to Fire

```bash
echo "Waiting for packet loss alert to fire..."
for i in {1..24}; do
  ALERT=$(ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alerts'" | \
    python3 -c "
import json,sys
data = json.load(sys.stdin)
alerts = [a for a in data['data']['alerts'] if 'PacketLoss' in a['labels'].get('alertname','')]
firing = [a for a in alerts if a['state']=='firing']
if firing:
    print('FIRING: ' + firing[0]['labels']['alertname'])
elif alerts:
    print('PENDING')
else:
    print('NONE')
" 2>/dev/null)
  echo "[$i/24] Alert status: $ALERT"
  [[ "$ALERT" == FIRING* ]] && break
  sleep 5
done
```

### Task 2.5: Verify Diagnosis & Results

```bash
# Check diagnosis started
curl -s http://localhost:8080/diagnoses | jq '.[-1] | {status, network_type, request_type}'

# Wait and check report
LATEST_DIR=$(ls -td measurement-*/ | head -1)
cat "${LATEST_DIR}diagnosis_report.md" | grep -E "Drop|Loss|Layer" | head -10
```

**Expected:** Report shows packet drop analysis with location attribution

### Task 2.6: Cleanup

```bash
# Cleanup fault on node32 (host-sender) STORAGE NIC (port-storage)
ssh smartx@192.168.70.32 "sudo bash -c 'DEV=\$(ip route get 70.0.0.31 | grep -oP \"dev \\K\\S+\"); /sbin/tc qdisc del dev \$DEV root 2>/dev/null && echo \"✅ Cleaned \$DEV\" || echo \"⚠️  Nothing to clean\"'"
```

---

## Scenario 3: VM Network Latency Boundary

### Alert Trigger Condition

| Property                 | Value                                                           |
| ------------------------ | --------------------------------------------------------------- |
| **Alert Name**     | `VMNetworkLatencyHigh` (from ping_monitor)                    |
| **Source**         | VM ping_monitor → POST /diagnose                               |
| **Condition**      | avg RTT > 15ms for 2 out of 3 consecutive cycles                |
| **Fault Required** | **≥20ms latency** on `vnet35` (host-side IFB redirect) |
| **Request Fields** | `network_type="vm"`, `request_type="latency"`               |

### Task 3.0: Mandatory Configuration Check

```bash
# 执行 Per-Case Mandatory Configuration Check (Task 0) - 见 Scenario 1 上方
# 必须看到两个 ✅ 才能继续
# VM 测试尤其重要：cooldown_seconds 必须是 3600，否则会触发告警风暴
```

### Task 3.1: Pre-Case Verification

```bash
# Run VM network pre-case check
# Ensure all checks pass before proceeding
```

### Task 3.2: Verify Baseline

```bash
ssh root@192.168.77.83 "ping -c 5 192.168.76.244"
```

**Expected:** RTT ~0.5-1.0ms (baseline)

### Task 3.3: Inject Fault (Host-side IFB)

**Inject 20ms delay on vnet35 using IFB redirect**

```bash
ssh smartx@192.168.70.32 "sudo bash" <<'EOF'
# Load modules
modprobe sch_netem 2>/dev/null
modprobe ifb 2>/dev/null

# Clean previous config
tc qdisc del dev vnet35 ingress 2>/dev/null
tc qdisc del dev ifb0 root 2>/dev/null
ip link del ifb0 2>/dev/null

# Create IFB device
ip link add ifb0 type ifb
ip link set dev ifb0 up

# Configure ingress redirect on vnet35 (ICMP only)
tc qdisc add dev vnet35 ingress
tc filter add dev vnet35 parent ffff: protocol ip u32 \
    match ip dst 192.168.76.244/32 \
    match ip protocol 1 0xff \
    action mirred egress redirect dev ifb0

# Apply 20ms delay on IFB
tc qdisc add dev ifb0 root handle 1: netem delay 20ms

echo "✅ Injected 20ms delay on vnet35 for traffic to 192.168.76.244"
tc qdisc show dev vnet35
tc qdisc show dev ifb0
EOF
```

### Task 3.4: Verify Fault Effective

```bash
ssh root@192.168.77.83 "ping -c 5 192.168.76.244"
```

**Expected:** RTT ~20-22ms (above 15ms warning threshold)

### Task 3.5: Monitor ping_monitor Alert

```bash
echo "Monitoring ping_monitor for alert trigger..."
for i in {1..20}; do
  LOG=$(ssh root@192.168.77.83 "tail -5 /var/log/ping_monitor.log 2>/dev/null")
  echo "[$i] Recent logs:"
  echo "$LOG" | head -3

  # Check if alert was sent
  if echo "$LOG" | grep -q "ALERT\|triggered\|POST"; then
    echo "✅ Alert triggered!"
    break
  fi
  sleep 3
done
```

### Task 3.6: Verify Diagnosis Triggered

```bash
curl -s http://localhost:8080/diagnoses | jq '.[-1] | {request_id, status, network_type, request_type}'
```

**Expected:**

```json
{
  "network_type": "vm",
  "request_type": "latency"
}
```

### Task 3.7: Verify Results

```bash
LATEST_DIR=$(ls -td measurement-*/ | head -1)

# Check correct measurement tool used
cat "${LATEST_DIR}commands.log" 2>/dev/null | grep -E "icmp_path_tracer|vm-network" | head -3

# Check analysis report
cat "${LATEST_DIR}diagnosis_report.md" | grep -E "VM|vnet|boundary|Host" | head -10
```

**Expected:** Report shows VM network boundary analysis

### Task 3.8: Cleanup

```bash
ssh smartx@192.168.70.32 "sudo bash -c 'tc qdisc del dev vnet35 ingress 2>/dev/null; ip link del ifb0 2>/dev/null' && echo '✅ Cleaned'"
```

---

## Scenario 4: VM Network Packet Drop Boundary

### Alert Trigger Condition

| Property                 | Value                                                              |
| ------------------------ | ------------------------------------------------------------------ |
| **Alert Name**     | `VMNetworkPacketLoss` (from ping_monitor)                        |
| **Source**         | VM ping_monitor → POST /diagnose                                  |
| **Condition**      | loss > 10% for 2 out of 3 consecutive cycles                       |
| **Fault Required** | **≥20% packet loss** on `vnet35` (host-side IFB redirect) |
| **Request Fields** | `network_type="vm"`, `request_type="packet_drop"`              |

### Task 4.0: Mandatory Configuration Check

```bash
# 执行 Per-Case Mandatory Configuration Check (Task 0) - 见 Scenario 1 上方
# 必须看到两个 ✅ 才能继续
```

### Task 4.1: Pre-Case Verification

```bash
# Run VM network pre-case check
```

### Task 4.2: Inject Fault

**Inject 20% packet loss on vnet35 using IFB redirect**

```bash
ssh smartx@192.168.70.32 "sudo bash" <<'EOF'
modprobe ifb 2>/dev/null

# Clean previous config
tc qdisc del dev vnet35 ingress 2>/dev/null
tc qdisc del dev ifb0 root 2>/dev/null
ip link del ifb0 2>/dev/null

# Create IFB
ip link add ifb0 type ifb
ip link set dev ifb0 up

# Configure ingress redirect (ICMP only)
tc qdisc add dev vnet35 ingress
tc filter add dev vnet35 parent ffff: protocol ip u32 \
    match ip dst 192.168.76.244/32 \
    match ip protocol 1 0xff \
    action mirred egress redirect dev ifb0

# Apply 20% packet loss
tc qdisc add dev ifb0 root handle 1: netem loss 20%

echo "✅ Injected 20% packet loss on vnet35"
EOF
```

### Task 4.3: Verify Fault Effective

```bash
ssh root@192.168.77.83 "ping -c 20 192.168.76.244"
```

**Expected:** ~20% packet loss

### Task 4.4: Monitor & Verify

```bash
# Wait for ping_monitor alert
sleep 15

# Check diagnosis
curl -s http://localhost:8080/diagnoses | jq '.[-1] | {status, network_type, request_type}'

# Check report
LATEST_DIR=$(ls -td measurement-*/ | head -1)
cat "${LATEST_DIR}diagnosis_report.md" | grep -E "Drop|Loss|vnet" | head -10
```

### Task 4.5: Cleanup

```bash
ssh smartx@192.168.70.32 "sudo bash -c 'tc qdisc del dev vnet35 ingress; ip link del ifb0'"
```

---

## Scenario 5: VM Network Full-Path Segment Analysis

### Alert Trigger Condition

| Property                 | Value                                                                       |
| ------------------------ | --------------------------------------------------------------------------- |
| **Alert Name**     | `VMNetworkLatencyCritical` (from ping_monitor)                            |
| **Source**         | VM ping_monitor → POST /diagnose with `options.segment=true`             |
| **Condition**      | avg RTT > 50ms for 2 out of 3 consecutive cycles                            |
| **Fault Required** | **≥60ms latency** inside VM on `ens4`                              |
| **Request Fields** | `network_type="vm"`, `request_type="latency"`, `options.segment=true` |

### Task 5.0: Mandatory Configuration Check

```bash
# 执行 Per-Case Mandatory Configuration Check (Task 0) - 见 Scenario 1 上方
# 必须看到两个 ✅ 才能继续
# Scenario 5 触发 critical 级别告警，cooldown 正确配置尤为重要
```

### Task 5.1: Pre-Case Verification

```bash
# Run VM network pre-case check
```

### Task 5.2: Inject Fault (VM Internal)

**Inject 60ms delay inside sender VM on ens4**

```bash
ssh root@192.168.77.83 "bash" <<'EOF'
# Load netem module
modprobe sch_netem

# Clean previous config
tc qdisc del dev ens4 root 2>/dev/null

# Apply HTB qdisc with selective delay (ICMP only)
tc qdisc add dev ens4 root handle 1: htb default 10
tc class add dev ens4 parent 1: classid 1:10 htb rate 1gbit
tc class add dev ens4 parent 1: classid 1:3 htb rate 1gbit
tc filter add dev ens4 protocol ip parent 1:0 prio 1 u32 \
    match ip dst 192.168.76.244/32 \
    match ip protocol 1 0xff \
    flowid 1:3
tc qdisc add dev ens4 parent 1:3 handle 30: netem delay 60ms

echo "✅ Injected 60ms delay inside VM for traffic to 192.168.76.244"
tc qdisc show dev ens4
EOF
```

### Task 5.3: Verify Fault Effective

```bash
ssh root@192.168.77.83 "ping -c 5 192.168.76.244"
```

**Expected:** RTT ~60-62ms (above 50ms critical threshold)

### Task 5.4: Monitor ping_monitor for Critical Alert

```bash
echo "Waiting for critical alert (RTT > 50ms)..."
for i in {1..20}; do
  ssh root@192.168.77.83 "tail -3 /var/log/ping_monitor.log"
  sleep 3
done
```

**Expected:** Alert with `severity: critical` and `options.segment=true` in payload

### Task 5.5: Verify Segment Mode Diagnosis

```bash
# Check diagnosis uses segment mode
curl -s http://localhost:8080/diagnoses | jq '.[-1]'

# Verify 8-point measurement (both VMs + both hosts)
LATEST_DIR=$(ls -td measurement-*/ | head -1)
cat "${LATEST_DIR}commands.log" 2>/dev/null | wc -l
```

**Expected:** Commands deployed to 4 endpoints (2 VMs + 2 hosts), 8 measurement points

### Task 5.6: Verify Results

```bash
LATEST_DIR=$(ls -td measurement-*/ | head -1)

# Check full segment breakdown
cat "${LATEST_DIR}diagnosis_report.md" | grep -E "Segment|Layer|Attribution|A.*M" | head -20
```

**Expected:** Detailed breakdown of all 8 segments (A through M)

### Task 5.7: Cleanup

```bash
ssh root@192.168.77.83 "tc qdisc del dev ens4 root"
```

---

## Cleanup and Success Criteria

### Full Cleanup Script

```bash
echo "=== Complete Cleanup ==="

# System network cleanup (node32 management NIC)
echo "1. Cleaning node32 management NIC..."
ssh smartx@192.168.70.32 "sudo bash -c 'DEV=\$(ip route get 192.168.70.31 | grep -oP \"dev \\K\\S+\"); /sbin/tc qdisc del dev \$DEV root 2>/dev/null && echo \"   Cleaned \$DEV\" || echo \"   Nothing to clean\"'"

# VM network host-side cleanup (node32 vnet35 and ifb0)
echo "2. Cleaning node32 vnet35 and ifb0..."
ssh smartx@192.168.70.32 "sudo bash -c 'tc qdisc del dev vnet35 ingress 2>/dev/null; ip link del ifb0 2>/dev/null' && echo '   Cleaned' || echo '   Nothing to clean'"

# VM internal cleanup
echo "3. Cleaning sender VM ens4..."
ssh root@192.168.77.83 "tc qdisc del dev ens4 root 2>/dev/null && echo '   Cleaned' || echo '   Nothing to clean'"

# Stop ping_monitor
echo "4. Stopping ping_monitor..."
ssh root@192.168.77.83 "pkill -f ping_monitor && echo '   Stopped' || echo '   Not running'"

echo "=== Cleanup Complete ==="
```

### Success Criteria Summary

| Scenario | Fault                            | Alert                             | Measurement Skill          | Analysis Skill                  | Pass Criteria                 |
| -------- | -------------------------------- | --------------------------------- | -------------------------- | ------------------------------- | ----------------------------- |
| 1        | 20ms delay on node32 storage NIC | `NetSherlockHostLatencyDevTest` | system-network-path-tracer | system-network-latency-analysis | Latency attribution in report |
| 2        | 10% loss on node32 storage NIC   | `HostNetworkPacketLossDevTest`  | system-network-path-tracer | system-network-drop-analysis    | Drop location in report       |
| 3        | 20ms delay on vnet35+IFB         | `VMNetworkLatencyHigh`          | vm-network-path-tracer     | vm-network-latency-analysis     | VM boundary attribution       |
| 4        | 20% loss on vnet35+IFB           | `VMNetworkPacketLoss`           | vm-network-path-tracer     | vm-network-drop-analysis        | VM drop location              |
| 5        | 60ms delay on VM ens4            | `VMNetworkLatencyCritical`      | vm-latency-measurement     | vm-latency-analysis             | 8-segment breakdown           |

### Per-Scenario Pass Checklist

Each scenario passes when:

1. ✅ Pre-case verification passes (both host configs normal)
2. ✅ Fault injection verified via ping
3. ✅ Alert fires (Prometheus or ping_monitor)
4. ✅ Webhook receives alert / diagnosis starts
5. ✅ Measurement logs created with correct tool
6. ✅ Diagnosis completes (status: completed)
7. ✅ Analysis report generated with correct attribution

---

## Test Environment Reference (Bottom)

**See also:** Test Environment Reference section at the top of this document.

```yaml
# Configuration file: config/test-e2e-diagnosis.yaml

# System Network (Host-to-Host) - Using management network
host_sender: smartx@192.168.70.32 (node32)
host_receiver: smartx@192.168.70.31 (node31)
injection_host: node32 (management NIC, auto-detected)
target_host: node31 (192.168.70.31)
network_subnet: 192.168.70.x (management)

# VM Network (Cross-Node)
vm_sender: root@192.168.77.83 (on host node32)
vm_receiver: root@192.168.76.244 (on host node31)
sender_host: smartx@192.168.70.32 (node32)
receiver_host: smartx@192.168.70.31 (node31)
sender_vnet: vnet35 (on node32)
vm_interface: ens4

# Services (on agent host 192.168.10.175)
webhook_server: localhost:8080
alertmanager: localhost:9093

# Prometheus (on node31)
prometheus: 70.0.0.31:9090 (listening on storage network)
prometheus_ssh: smartx@192.168.70.31 (access via management network)
prometheus_auth: prometheus:HC!r0cks
alert_rules: /etc/prometheus/netsherlock_test_alert.yml
```

---

## Appendix A: Alertmanager 配置与告警触发时机

### Alertmanager 关键配置项

当前配置文件：`config/alertmanager/alertmanager.yml`

```yaml
route:
  group_by: ['alertname', 'hostname', 'to_hostname']
  group_wait: 10s        # 全局默认
  group_interval: 20m    # 全局默认
  repeat_interval: 4h    # 全局默认

  routes:
    - match_re:
        alertname: 'HostNetworkLatency.*|HostNetworkPacketLoss.*|NetSherlock.*'
      receiver: 'netsherlock'
      group_wait: 5s     # NetSherlock 路由覆盖
      group_interval: 20m # NetSherlock 路由覆盖
```

### 配置项说明

| 配置项                    | 当前值                                 | 含义                                                                        | 对测试的影响                               |
| ------------------------- | -------------------------------------- | --------------------------------------------------------------------------- | ------------------------------------------ |
| **group_wait**      | 5s                                     | 收到**第一个**告警后，等待 5 秒再发送 webhook（等待同组其他告警聚合） | 告警触发后**~5 秒** 才会调用 webhook |
| **group_interval**  | 20m                                    | 同一组告警的**后续**通知间隔（新告警加入已有组时）                    | 如果已发送过，需等 20 分钟才会再次通知     |
| **repeat_interval** | 4h                                     | 同一告警**持续 firing** 时的重复通知间隔                              | 同一告警 4 小时内不会重复触发诊断          |
| **group_by**        | `[alertname, hostname, to_hostname]` | 按这些标签分组，同组告警聚合发送                                            | node33→node31 和 node33→node32 是不同组  |

### 告警触发到 Webhook 的完整时间线

```
T+0s     故障注入生效
T+0~15s  Prometheus scrape 采集到异常指标（scrape_interval: 15s）
T+15s    Prometheus 检测到指标超过阈值，告警进入 "pending"
T+20s    告警 for 条件满足（for: 5s），变为 "firing"
T+20s    Prometheus 发送告警到 Alertmanager
T+25s    Alertmanager group_wait 结束（5s），调用 webhook
T+25s+   NetSherlock Diagnosis Controller 开始执行
```

**总延迟估算：故障注入后约 20-30 秒触发诊断**

### 测试时的注意事项

1. **首次触发延迟**：

   - 故障注入后需等待 **20-30 秒** 才会触发诊断
   - 组成：Prometheus scrape (~15s) + for duration (5s) + group_wait (5s)
2. **重复测试间隔**：

   - 同一告警组已触发过后，需等待 `group_interval: 20m`
   - 或者手动清理 Alertmanager 告警状态
3. **清理 Alertmanager 状态**（重复测试前）：

   ```bash
   # 查看当前活跃告警
   curl -s http://localhost:9093/api/v2/alerts | jq '.[].labels.alertname'

   # 重启 Alertmanager 清理状态（最简单方式）
   pkill alertmanager
   /tmp/alertmanager-0.27.0.darwin-arm64/alertmanager \
     --config.file=/Users/admin/workspace/netsherlock/config/alertmanager/alertmanager.yml \
     --web.listen-address=:9093 \
     --storage.path=/tmp/alertmanager-data &
   ```
4. **Prometheus 告警状态查询**：

   ```bash
   # 查看告警状态（pending/firing）
   ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/alerts'" | \
     jq '.data.alerts[] | {alertname: .labels.alertname, state: .state}'
   ```

---

## Appendix B: ping_monitor 告警触发机制

### ping_monitor 配置项

配置文件：`/etc/ping_monitor/config.yaml`（部署在 sender VM）

```yaml
evaluation:
  window_size: 3        # 滑动窗口大小（3 个采集周期）
  trigger_count: 2      # 触发阈值（窗口内 2 次超标则触发）

thresholds:
  rtt_warning_ms: 15.0     # RTT > 15ms → warning（boundary 模式）
  rtt_critical_ms: 50.0    # RTT > 50ms → critical（segment 模式，options.segment=true）
  loss_warning_pct: 10.0   # 丢包 > 10% → warning
  loss_critical_pct: 50.0  # 丢包 > 50% → critical
  cooldown_seconds: 3600    # 1 hour - 触发后 1 小时内不重复告警

collection:
  count: 5              # 每周期 5 个 ping 包
  cycle_pause: 2        # 周期间隔 2 秒
```

### 告警触发条件

| 告警类型                     | 触发条件                               | 诊断模式                           |
| ---------------------------- | -------------------------------------- | ---------------------------------- |
| `VMNetworkLatencyHigh`     | RTT > 15ms，连续 3 个周期中有 2 个超标 | boundary                           |
| `VMNetworkLatencyCritical` | RTT > 50ms，连续 3 个周期中有 2 个超标 | segment (via options.segment=true) |
| `VMNetworkPacketLoss`      | Loss > 10%，连续 3 个周期中有 2 个超标 | boundary                           |

### ping_monitor 触发时间线

```
T+0s     故障注入生效
T+2s     第 1 个采集周期完成（5 pings）
T+4s     第 2 个采集周期完成（5 pings）
T+6s     第 3 个采集周期完成（5 pings）
T+6s     滑动窗口评估：2/3 周期超标 → 触发告警
T+6s     POST /diagnose 到 webhook
T+6s+    NetSherlock Diagnosis Controller 开始执行
```

**总延迟估算：故障注入后约 6-10 秒触发诊断**

### Cooldown 机制

- 告警触发后 **1 小时内**不会重复触发同一目标、同一级别的告警
- Cooldown 按 `(target, severity)` 分别计算，critical 和 warning 独立
- 重复测试时需等待 cooldown 或重启 ping_monitor：
  ```bash
  ssh root@192.168.77.83 "pkill -f ping_monitor; sleep 1; nohup python3 /usr/local/bin/ping_monitor.py --config /etc/ping_monitor/config.yaml > /var/log/ping_monitor.log 2>&1 &"
  ```

### 严重级别优先级（单告警保证）

ping_monitor 使用 **highest-first** 评估策略，确保每次评估只触发一个告警：

```python
# 评估顺序（代码逻辑）
1. RTT critical (> 50ms)  → 触发后立即返回
2. Loss critical (> 50%)  → 触发后立即返回
3. RTT warning (> 15ms)   → 触发后立即返回
4. Loss warning (> 10%)   → 触发后立即返回
```

**效果**：

- 注入 60ms 延迟 → 只触发 `VMNetworkLatencyCritical`（不会同时触发 warning）
- 注入 20ms 延迟 → 只触发 `VMNetworkLatencyHigh`
- 注入 20% 丢包 → 只触发 `VMNetworkPacketLoss`（warning 级别）

这保证了每种故障类型在每个评估周期最多触发一个诊断请求。
