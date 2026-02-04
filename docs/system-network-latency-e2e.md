# System Network Latency E2E Test Guide

本文档记录完整的系统网络延迟诊断端到端测试流程，包括告警触发、Webhook 处理、自动诊断和报告生成。

## 概述

### 测试目标

验证完整的诊断流水线：

```
Prometheus → Alertmanager → Webhook → DiagnosisController → Report
     ↓             ↓            ↓              ↓               ↓
  指标采集      告警路由     接收处理      技能调度        生成报告
```

### 关键组件

| 组件 | 作用 | 验证点 |
|------|------|--------|
| Prometheus | 采集延迟指标，触发告警 | 告警规则触发 |
| Alertmanager | 路由告警到 Webhook | 告警正确投递 |
| Webhook Server | 接收告警，触发诊断 | autonomous 模式运行 |
| DiagnosisController | 调度正确的技能 | 使用 system-network-* 技能 |
| 分析技能 | 生成诊断报告 | 报告标题和内容正确 |

---

## 环境准备

### 1. 集群信息

| 节点 | 管理网 IP | 存储网 IP | 角色 |
|------|-----------|-----------|------|
| node31 | 192.168.70.31 | 70.0.0.31 | Prometheus, 测试源 |
| node32 | 192.168.70.32 | 70.0.0.32 | 测试目标 |
| node33 | 192.168.70.33 | 70.0.0.33 | 其他节点 |
| node34 | 192.168.70.34 | 70.0.0.34 | 其他节点 |

### 2. GlobalInventory 配置

Webhook 需要 hostname→IP 映射才能解析告警中的主机名：

```yaml
# config/global_inventory.yaml
hosts:
  node31:
    mgmt_ip: "192.168.70.31"
    ssh:
      user: smartx
    network_types:
      - storage
      - system

  node32:
    mgmt_ip: "192.168.70.32"
    ssh:
      user: smartx
    network_types:
      - storage
      - system

  node33:
    mgmt_ip: "192.168.70.33"
    ssh:
      user: smartx
    network_types:
      - storage
      - system

  node34:
    mgmt_ip: "192.168.70.34"
    ssh:
      user: smartx
    network_types:
      - storage
      - system

vms: {}
```

### 3. Webhook 环境变量

启用 autonomous 模式需要以下环境变量：

```bash
# 启用自主诊断模式
export DIAGNOSIS_AUTONOMOUS_ENABLED=true
export DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true

# 配置可触发自主模式的告警类型
export DIAGNOSIS_AUTONOMOUS_KNOWN_ALERT_TYPES='[
  "VMNetworkLatency",
  "HostNetworkLatency",
  "HostNetworkLatencyTest",
  "NetSherlockHostLatencyTest",
  "NetSherlockHostLatencyDevTest",
  "HostNetworkLatencySpike"
]'

# 允许无 API Key 运行（开发环境）
export WEBHOOK_ALLOW_INSECURE=true
```

---

## 测试流程

### Step 1: 启动 Webhook Server

```bash
cd /Users/admin/workspace/netsherlock

# 设置环境变量并启动
DIAGNOSIS_AUTONOMOUS_ENABLED=true \
DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true \
DIAGNOSIS_AUTONOMOUS_KNOWN_ALERT_TYPES='["VMNetworkLatency","HostNetworkLatency","HostNetworkLatencyTest","NetSherlockHostLatencyTest","NetSherlockHostLatencyDevTest"]' \
python -c "
import sys
sys.path.insert(0, 'src')
from netsherlock.api.webhook import app
import uvicorn
uvicorn.run(app, host='0.0.0.0', port=5000, log_level='info')
" > /tmp/netsherlock-webhook.log 2>&1 &

# 验证启动
sleep 3
tail -10 /tmp/netsherlock-webhook.log
```

期望输出：
```
INFO:netsherlock.api.webhook:Initializing diagnosis engine: controller
INFO:netsherlock.api.webhook:Engine initialized: controller
INFO:netsherlock.api.webhook:GlobalInventory loaded: 0 VMs
INFO:netsherlock.api.webhook:Diagnosis worker started
INFO:     Uvicorn running on http://0.0.0.0:5000
```

### Step 2: 启动本地 Alertmanager（可选）

如果需要通过 Alertmanager 路由告警：

```bash
# 使用项目配置启动
alertmanager --config.file=config/alertmanager/alertmanager.yml \
  --web.listen-address=:9093 \
  --log.level=info &
```

### Step 3: 配置 Prometheus 告警规则

告警规则已配置在集群上 (`/etc/prometheus/netsherlock_test_alert.yml`)：

```yaml
groups:
  - name: netsherlock_system_network
    interval: 15s
    rules:
      # 超低阈值测试告警 - P90 > 500μs
      - alert: NetSherlockHostLatencyDevTest
        expr: |
          max without(instance) (
            histogram_quantile(0.9, rate(host_to_host_max_ping_time_ns_bucket[1m]))
          ) > 5e+05
        for: 5s
        labels:
          network_type: "system"
          severity: "info"
          environment: "dev-test"
```

### Step 4: 注入延迟（可选 - 触发真实告警）

如果需要触发真实的 Prometheus 告警，可以注入延迟：

```bash
# 在 node31 上注入 400µs 延迟到发往 node32 的 ICMP
ssh smartx@192.168.70.31 "sudo bash" <<'EOF'
TC=/sbin/tc
$TC qdisc del dev port-mgt root 2>/dev/null || true
$TC qdisc add dev port-mgt root handle 1: htb default 10
$TC class add dev port-mgt parent 1: classid 1:10 htb rate 10gbit
$TC class add dev port-mgt parent 1: classid 1:20 htb rate 10gbit
$TC qdisc add dev port-mgt parent 1:20 handle 20: netem delay 400us
$TC filter add dev port-mgt protocol ip parent 1:0 prio 1 u32 \
    match ip dst 192.168.70.32/32 match ip protocol 1 0xff flowid 1:20
echo "Injected 400us delay for ICMP to 70.32"
EOF
```

> **重要**: tc 必须配置在 OVS 内部端口 `port-mgt`，不是物理网卡。详见 `docs/system-network-fault-injection.md`。

### Step 5: 发送测试告警

直接通过 curl 发送测试告警（无需等待 Prometheus）：

```bash
curl -s -X POST http://localhost:5000/webhook/alertmanager \
  -H "Content-Type: application/json" \
  -d '{
    "version": "4",
    "groupKey": "test-group",
    "status": "firing",
    "receiver": "netsherlock",
    "alerts": [
      {
        "status": "firing",
        "labels": {
          "alertname": "HostNetworkLatencyTest",
          "hostname": "node31",
          "to_hostname": "node32",
          "network_type": "system",
          "severity": "warning"
        },
        "annotations": {
          "summary": "System network latency test between node31 and node32"
        },
        "startsAt": "2026-02-04T08:00:00Z",
        "fingerprint": "test-system-e2e"
      }
    ]
  }'
```

期望响应（autonomous 模式）：
```json
{
  "diagnosis_id": "alert-xxx",
  "status": "queued",
  "mode": "autonomous",
  "message": "Alert queued for diagnosis in autonomous mode"
}
```

> **注意**: 如果返回 `"mode": "interactive"`，检查环境变量配置和 `alertname` 是否在 known_alert_types 列表中。

### Step 6: 监控诊断进度

```bash
# 实时监控日志
tail -f /tmp/netsherlock-webhook.log | grep -E "phase_|skill|completed|error"
```

期望看到的阶段：
```
phase_l1_monitoring
phase_l2_environment
invoking_skill ... skill=network-env-collector  # 收集源主机环境
skill_completed ... skill=network-env-collector
invoking_skill ... skill=network-env-collector  # 收集目标主机环境
skill_completed ... skill=network-env-collector
phase_classification
phase_measurement_planning
l3_measurement_starting ... skill=system-network-path-tracer  # 关键：使用 system 技能
invoking_skill ... skill=system-network-path-tracer
skill_completed ... skill=system-network-path-tracer
l4_analysis_starting
invoking_skill ... skill=system-network-latency-analysis  # 关键：使用 system 分析
skill_completed ... skill=system-network-latency-analysis
Diagnosis completed
```

### Step 7: 验证报告

```bash
# 查找最新测量目录
LATEST=$(ls -td measurement-* | head -1)
echo "Latest: $LATEST"

# 检查报告标题
head -5 $LATEST/diagnosis_report.md
```

期望输出：
```markdown
# System Network Latency Diagnosis Report

**Measurement Directory**: `measurement-20260204-155101`
**Analysis Time**: 2026-02-04T15:51:58.627085
```

### Step 8: 清理

```bash
# 移除延迟注入
ssh smartx@192.168.70.31 "sudo /sbin/tc qdisc del dev port-mgt root"

# 验证延迟恢复
ssh smartx@192.168.70.31 "ping -c 3 192.168.70.32"
# 期望: ~150-200µs
```

---

## 验证清单

### 成功标准

| 检查项 | 期望值 | 验证方法 |
|--------|--------|----------|
| Webhook 模式 | `autonomous` | 检查响应中的 mode 字段 |
| 测量技能 | `system-network-path-tracer` | 日志中的 skill 名称 |
| 分析技能 | `system-network-latency-analysis` | 日志中的 skill 名称 |
| 报告标题 | "System Network Latency Diagnosis Report" | 报告第一行 |
| 报告段落 | A, C, D, E, F, J, G | 报告 Segment Breakdown 表 |
| 无 VM 段落 | 不含 vnet、B、H、I 段 | 报告内容检查 |

### 常见问题

#### 1. 返回 interactive 模式而非 autonomous

**原因**: alertname 不在 known_alert_types 列表中

**解决**:
```bash
# 添加对应的告警类型
export DIAGNOSIS_AUTONOMOUS_KNOWN_ALERT_TYPES='["HostNetworkLatencyTest",...]'
```

#### 2. "Hostname 'nodeXX' not found in GlobalInventory"

**原因**: GlobalInventory 缺少该主机配置

**解决**: 在 `config/global_inventory.yaml` 中添加缺失的主机

#### 3. "Source host not found in inventory"

**原因**:
- GlobalInventory 未加载（检查路径）
- Webhook 使用了旧的缓存（重启 Webhook）

**解决**:
```bash
# 重启 Webhook 以加载最新配置
pkill -f "python.*webhook"
# 重新启动...
```

#### 4. 使用了 vm-network-path-tracer 而非 system-network

**原因**: 告警 labels 中 `network_type` 不是 `"system"`

**解决**: 确保告警包含正确的 label：
```json
"labels": {
  "network_type": "system",
  ...
}
```

---

## 完整运行记录示例

### 成功的 E2E 测试日志

```
2026-02-04 15:50:01 [info] engine_execute diagnosis_id=alert-0cdee44f286242c2 mode=autonomous
2026-02-04 15:50:01 [info] loading_global_inventory path=config/global_inventory.yaml
2026-02-04 15:50:01 [info] diagnosis_started diagnosis_id=6b763709 mode=autonomous
2026-02-04 15:50:01 [debug] phase_l1_monitoring
2026-02-04 15:50:01 [debug] phase_l2_environment
2026-02-04 15:50:01 [info] invoking_skill skill=network-env-collector
2026-02-04 15:50:23 [info] skill_completed skill=network-env-collector
2026-02-04 15:50:23 [info] invoking_skill skill=network-env-collector
2026-02-04 15:50:43 [info] skill_completed skill=network-env-collector
2026-02-04 15:50:43 [debug] phase_classification
2026-02-04 15:50:43 [debug] phase_measurement_planning
2026-02-04 15:50:43 [info] l2_to_l3_system_params_built focus=latency sender_ip=70.0.0.31 receiver_ip=70.0.0.32
2026-02-04 15:50:43 [info] l3_measurement_starting skill=system-network-path-tracer duration=30
2026-02-04 15:50:43 [info] invoking_skill skill=system-network-path-tracer
2026-02-04 15:51:49 [info] skill_completed skill=system-network-path-tracer
2026-02-04 15:51:49 [info] l4_analysis_starting measurement_status=success
2026-02-04 15:51:49 [info] l4_system_network_analysis_starting measurement_dir=./measurement-20260204-155101
2026-02-04 15:51:49 [info] invoking_skill skill=system-network-latency-analysis
2026-02-04 15:52:06 [info] skill_completed skill=system-network-latency-analysis
2026-02-04 15:52:06 [info] l4_system_network_analysis_completed primary_contributor='Receiver Host Internal' total_rtt_us=227.9
INFO:netsherlock.api.webhook:Diagnosis completed: alert-0cdee44f286242c2
```

### 生成的报告摘要

```markdown
# System Network Latency Diagnosis Report

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 227.90 µs (0.228 ms) |
| **Primary Contributor** | Receiver Host Internal |
| **Contribution** | 45.4% |
| **Sample Count** | 231 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Receiver Host Internal | 103.40 | 45.4% | D, E, F |
| Sender Host Internal | 99.40 | 43.6% | A, G |
| Physical Network | 25.20 | 11.1% | C, J |
```

---

## 相关文档

- [系统网络故障注入指南](system-network-fault-injection.md) - tc/netem 配置方法
- [Webhook E2E 测试计划](plans/2026-02-04-webhook-e2e-test.md) - 原始测试计划
- [tc 延迟注入计划](plans/2026-02-04-tc-latency-injection.md) - 延迟注入验证
