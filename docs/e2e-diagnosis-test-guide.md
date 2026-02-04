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
4. [Scenario 1: System Network Latency Boundary](#scenario-1-system-network-latency-boundary)
5. [Scenario 2: System Network Packet Drop Boundary](#scenario-2-system-network-packet-drop-boundary)
6. [Scenario 3: VM Network Latency Boundary](#scenario-3-vm-network-latency-boundary)
7. [Scenario 4: VM Network Packet Drop Boundary](#scenario-4-vm-network-packet-drop-boundary)
8. [Scenario 5: VM Network Full-Path Segment Analysis](#scenario-5-vm-network-full-path-segment-analysis)
9. [Cleanup and Success Criteria](#cleanup-and-success-criteria)

---

## Test Scenarios Overview

| # | Network Type | Problem Type | Mode | Fault Injection Point | Alert Source |
|---|--------------|--------------|------|----------------------|---------------|
| 1 | System | Latency | Boundary | Host `port-storage` (node33) | Prometheus `NetSherlockHostLatencyDevTest` |
| 2 | System | Packet Drop | Boundary | Host `port-storage` (node33) | Prometheus `HostNetworkPacketLossDevTest` |
| 3 | VM | Latency | Boundary | Host `vnet35` via IFB (node32) | ping_monitor `VMNetworkLatencyHigh` |
| 4 | VM | Packet Drop | Boundary | Host `vnet35` via IFB (node32) | ping_monitor `VMNetworkPacketLoss` |
| 5 | VM | Latency | Segment | VM internal `ens4` (sender VM) | ping_monitor `VMNetworkLatencyCritical` |

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

| Alert Name | Threshold | For Duration | Fault Required | Labels |
|------------|-----------|--------------|----------------|--------|
| `NetSherlockHostLatencyDevTest` | P90 > 0.5ms (500μs) | 5s | 1ms delay | `network_type="system"` |
| `HostNetworkPacketLossDevTest` | loss > 0.1% | 10s | 5% packet loss | `network_type="system"`, `problem_type="packet_drop"` |

**Important**: System network metrics are collected **centrally by node33 only** (tuna-exporter on 70.0.0.33:10404). This means:
- Only paths **from node33 to other nodes** are monitored
- To trigger alerts, inject faults on **node33's outgoing interfaces** (`port-storage` for storage network)

### VM Network Alerts (ping_monitor → Direct POST to /diagnose)

| Threshold Type | Warning Level | Critical Level | Diagnosis Mode |
|----------------|---------------|----------------|----------------|
| RTT | > 5ms | > 20ms | boundary / segment |
| Packet Loss | > 10% | > 50% | boundary |

| Alert Name | Threshold | Trigger Condition | Diagnosis Mode |
|------------|-----------|-------------------|----------------|
| `VMNetworkLatencyHigh` | RTT > 5ms for 2/3 cycles | 10ms delay injection | boundary |
| `VMNetworkLatencyCritical` | RTT > 20ms for 2/3 cycles | 25ms delay injection | segment |
| `VMNetworkPacketLoss` | Loss > 10% for 2/3 cycles | 20% loss injection | boundary |

---

## Suite-Level Prerequisites

**CRITICAL:** Complete ALL prerequisites before starting ANY test scenario.

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Test Environment Overview                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌───────────────────────┐     ┌───────────────────────┐                    │
│  │    Prometheus         │     │    Agent Host          │                   │
│  │    (192.168.79.79)    │     │    (192.168.10.175)    │                   │
│  │                       │     │                        │                   │
│  │  Alert Rules ────────────▶  │  Alertmanager (:9093)  │                   │
│  │  (netsherlock_test_   │     │         │              │                   │
│  │   alert.yml)          │     │         ▼              │                   │
│  └───────────────────────┘     │  Webhook Server (:8080)│                   │
│                                │         │              │                   │
│                                │         ▼              │                   │
│                                │  Diagnosis Controller  │                   │
│                                └────────────────────────┘                   │
│                                          │                                   │
│          ┌───────────────────────────────┼───────────────────────────────┐  │
│          ▼                               ▼                               ▼  │
│  ┌───────────────┐            ┌───────────────┐            ┌───────────────┐│
│  │   node31      │            │   node32      │            │   node33      ││
│  │ (192.168.70.31)           │ (192.168.70.32)           │ (192.168.70.33)││
│  │               │            │               │            │ * PINGMESH    ││
│  │ VM-receiver   │            │ VM-sender     │            │   COLLECTOR   ││
│  │ (76.244)      │            │ (77.83)       │            │               ││
│  └───────────────┘            └───────────────┘            └───────────────┘│
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Task P1: Configure Host-side Prerequisites (One-time setup)

#### Step 1: Verify Prometheus Alert Rule Deployed

Check that `netsherlock_test_alert.yml` is loaded on Prometheus:

```bash
ssh smartx@192.168.70.31 "curl -s 'http://prometheus:HC%21r0cks@70.0.0.31:9090/api/v1/rules'" | \
  python3 -c "
import json,sys
data = json.load(sys.stdin)
rules = [r['name'] for g in data['data']['groups'] for r in g.get('rules', [])]
expected = ['NetSherlockHostLatencyDevTest', 'HostNetworkPacketLossDevTest']
found = [r for r in expected if any(r in name for name in rules)]
missing = [r for r in expected if r not in found]
print('✅ Alert rules loaded:' if not missing else '❌ Missing rules:')
for r in (found or missing): print(f'  - {r}')
"
```

**Expected:** All expected alert rules are loaded

**If missing, deploy alert rules:**
```bash
# Copy rule file to Prometheus host (node31 as jump)
scp config/prometheus/netsherlock_test_alert.yml smartx@192.168.70.31:/tmp/

# Install and reload
ssh smartx@192.168.70.31 "
  scp /tmp/netsherlock_test_alert.yml smartx@192.168.79.79:/tmp/ && \
  ssh smartx@192.168.79.79 'sudo cp /tmp/netsherlock_test_alert.yml /etc/prometheus/ && sudo kill -HUP \$(pgrep prometheus)'
"
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

# Grafana Settings
GRAFANA_BASE_URL=http://192.168.79.79/grafana
GRAFANA_USERNAME=o11y
GRAFANA_PASSWORD=HC!r0cks

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
  rtt_warning_ms: 5.0
  rtt_critical_ms: 20.0
  loss_warning_pct: 10.0
  loss_critical_pct: 50.0
  cooldown_seconds: 60

monitors:
  - src_vm_name: "vm-sender"
    src_test_ip: "192.168.77.83"
    targets:
      - dst_vm_name: "vm-receiver"
        dst_test_ip: "192.168.76.244"
EOF

scp /tmp/ping_monitor_config.yaml root@192.168.77.83:/etc/ping_monitor/config.yaml
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

# Check 4: No existing fault injection on node33
echo "4. Checking node33 has no existing qdisc..."
ssh smartx@192.168.70.33 "tc qdisc show dev port-storage 2>/dev/null | grep -v 'pfifo_fast\|noqueue'" | \
  python3 -c "
import sys
lines = sys.stdin.read().strip()
print('   ✅ No custom qdisc on port-storage' if not lines else '   ⚠️  Existing qdisc: ' + lines)
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

## Scenario 1: System Network Latency Boundary

### Alert Trigger Condition

| Property | Value |
|----------|-------|
| **Alert Name** | `NetSherlockHostLatencyDevTest` |
| **Metric** | `host_to_host_max_ping_time_ns_bucket` |
| **Condition** | P90 histogram quantile > 500,000 ns (0.5ms) |
| **For Duration** | 5 seconds |
| **Fault Required** | **≥1ms latency** on `port-storage` of node33 |
| **Labels** | `network_type="system"`, `severity="info"` |

### Task 1.1: Pre-Case Verification

```bash
# Run system network pre-case check (see above)
# Ensure all checks pass before proceeding
```

### Task 1.2: Verify Baseline

```bash
# Verify baseline latency between nodes
ssh smartx@192.168.70.33 "ping -c 5 70.0.0.31"
```

**Expected:** RTT ~0.1-0.3ms (baseline)

### Task 1.3: Inject Fault

**Inject 1ms delay on node33's port-storage (target: node31)**

```bash
ssh smartx@192.168.70.33 "sudo bash" <<'EOF'
TC=/sbin/tc
DEV=port-storage
TARGET=70.0.0.31

# Clean any existing qdisc
$TC qdisc del dev $DEV root 2>/dev/null || true

# Setup HTB with selective delay
$TC qdisc add dev $DEV root handle 1: htb default 10
$TC class add dev $DEV parent 1: classid 1:10 htb rate 10gbit
$TC class add dev $DEV parent 1: classid 1:20 htb rate 10gbit
$TC qdisc add dev $DEV parent 1:20 handle 20: netem delay 1ms

# Filter: ICMP packets to target
$TC filter add dev $DEV protocol ip parent 1:0 prio 1 u32 \
    match ip dst ${TARGET}/32 \
    match ip protocol 1 0xff \
    flowid 1:20

echo "✅ Injected 1ms delay for ICMP to $TARGET on $DEV"
$TC qdisc show dev $DEV
EOF
```

### Task 1.4: Verify Fault Effective

```bash
ssh smartx@192.168.70.33 "ping -c 5 70.0.0.31"
```

**Expected:** RTT ~1.1-1.3ms (baseline + 1ms injection)

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
ssh smartx@192.168.70.33 "sudo /sbin/tc qdisc del dev port-storage root 2>/dev/null && echo '✅ Cleaned' || echo '⚠️  Nothing to clean'"
```

---

## Scenario 2: System Network Packet Drop Boundary

### Alert Trigger Condition

| Property | Value |
|----------|-------|
| **Alert Name** | `HostNetworkPacketLossDevTest` |
| **Metric** | `host_network_ping_packet_loss_percent{_network="storage"}` |
| **Condition** | loss > 0.001 (0.1%) |
| **For Duration** | 10 seconds |
| **Fault Required** | **≥5% packet loss** on `port-storage` of node33 |
| **Labels** | `network_type="system"`, `problem_type="packet_drop"` |

### Task 2.1: Pre-Case Verification

```bash
# Run system network pre-case check
# Ensure all checks pass before proceeding
```

### Task 2.2: Inject Fault

**Inject 10% packet loss on node33's port-storage (target: node31)**

```bash
ssh smartx@192.168.70.33 "sudo bash" <<'EOF'
TC=/sbin/tc
DEV=port-storage
TARGET=70.0.0.31

# Clean any existing qdisc
$TC qdisc del dev $DEV root 2>/dev/null || true

# Setup HTB with selective packet loss
$TC qdisc add dev $DEV root handle 1: htb default 10
$TC class add dev $DEV parent 1: classid 1:10 htb rate 10gbit
$TC class add dev $DEV parent 1: classid 1:20 htb rate 10gbit
$TC qdisc add dev $DEV parent 1:20 handle 20: netem loss 10%

# Filter: ICMP packets to target
$TC filter add dev $DEV protocol ip parent 1:0 prio 1 u32 \
    match ip dst ${TARGET}/32 \
    match ip protocol 1 0xff \
    flowid 1:20

echo "✅ Injected 10% packet loss for ICMP to $TARGET on $DEV"
EOF
```

### Task 2.3: Verify Fault Effective

```bash
ssh smartx@192.168.70.33 "ping -c 20 70.0.0.31"
```

**Expected:** ~10% packet loss in statistics

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
ssh smartx@192.168.70.33 "sudo /sbin/tc qdisc del dev port-storage root"
```

---

## Scenario 3: VM Network Latency Boundary

### Alert Trigger Condition

| Property | Value |
|----------|-------|
| **Alert Name** | `VMNetworkLatencyHigh` (from ping_monitor) |
| **Source** | VM ping_monitor → POST /diagnose |
| **Condition** | avg RTT > 5ms for 2 out of 3 consecutive cycles |
| **Fault Required** | **≥10ms latency** on `vnet35` (host-side IFB redirect) |
| **Request Fields** | `network_type="vm"`, `request_type="latency"` |

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

**Inject 10ms delay on vnet35 using IFB redirect**

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

# Apply 10ms delay on IFB
tc qdisc add dev ifb0 root handle 1: netem delay 10ms

echo "✅ Injected 10ms delay on vnet35 for traffic to 192.168.76.244"
tc qdisc show dev vnet35
tc qdisc show dev ifb0
EOF
```

### Task 3.4: Verify Fault Effective

```bash
ssh root@192.168.77.83 "ping -c 5 192.168.76.244"
```

**Expected:** RTT ~10-12ms

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

| Property | Value |
|----------|-------|
| **Alert Name** | `VMNetworkPacketLoss` (from ping_monitor) |
| **Source** | VM ping_monitor → POST /diagnose |
| **Condition** | loss > 10% for 2 out of 3 consecutive cycles |
| **Fault Required** | **≥20% packet loss** on `vnet35` (host-side IFB redirect) |
| **Request Fields** | `network_type="vm"`, `request_type="packet_drop"` |

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

| Property | Value |
|----------|-------|
| **Alert Name** | `VMNetworkLatencyCritical` (from ping_monitor) |
| **Source** | VM ping_monitor → POST /diagnose with `options.segment=true` |
| **Condition** | avg RTT > 20ms for 2 out of 3 consecutive cycles |
| **Fault Required** | **≥25ms latency** inside VM on `ens4` |
| **Request Fields** | `network_type="vm"`, `request_type="latency"`, mode="segment" |

### Task 5.1: Pre-Case Verification

```bash
# Run VM network pre-case check
```

### Task 5.2: Inject Fault (VM Internal)

**Inject 25ms delay inside sender VM on ens4**

```bash
ssh root@192.168.77.83 "bash" <<'EOF'
# Load netem module
modprobe sch_netem

# Clean previous config
tc qdisc del dev ens4 root 2>/dev/null

# Apply prio qdisc with selective delay (ICMP only)
tc qdisc add dev ens4 root handle 1: prio bands 3 priomap 1 2 2 2 1 2 0 0 1 1 1 1 1 1 1 1
tc qdisc add dev ens4 parent 1:3 handle 30: netem delay 25ms
tc filter add dev ens4 protocol ip parent 1:0 prio 3 u32 \
    match ip dst 192.168.76.244/32 \
    match ip protocol 1 0xff \
    flowid 1:3

echo "✅ Injected 25ms delay inside VM for traffic to 192.168.76.244"
tc qdisc show dev ens4
EOF
```

### Task 5.3: Verify Fault Effective

```bash
ssh root@192.168.77.83 "ping -c 5 192.168.76.244"
```

**Expected:** RTT ~25-27ms

### Task 5.4: Monitor ping_monitor for Critical Alert

```bash
echo "Waiting for critical alert (RTT > 20ms)..."
for i in {1..20}; do
  ssh root@192.168.77.83 "tail -3 /var/log/ping_monitor.log"
  sleep 3
done
```

**Expected:** Alert with `severity: critical` and `mode: segment`

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

# System network cleanup (node33)
echo "1. Cleaning node33 port-storage..."
ssh smartx@192.168.70.33 "sudo /sbin/tc qdisc del dev port-storage root 2>/dev/null && echo '   Cleaned' || echo '   Nothing to clean'"

# VM network host-side cleanup (node32)
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

| Scenario | Fault | Alert | Measurement Skill | Analysis Skill | Pass Criteria |
|----------|-------|-------|-------------------|----------------|---------------|
| 1 | 1ms delay on port-storage | `NetSherlockHostLatencyDevTest` | system-network-path-tracer | system-network-latency-analysis | Latency attribution in report |
| 2 | 10% loss on port-storage | `HostNetworkPacketLossDevTest` | system-network-path-tracer | system-network-drop-analysis | Drop location in report |
| 3 | 10ms delay on vnet35+IFB | `VMNetworkLatencyHigh` | vm-network-path-tracer | vm-network-latency-analysis | VM boundary attribution |
| 4 | 20% loss on vnet35+IFB | `VMNetworkPacketLoss` | vm-network-path-tracer | vm-network-drop-analysis | VM drop location |
| 5 | 25ms delay on VM ens4 | `VMNetworkLatencyCritical` | vm-latency-measurement | vm-latency-analysis | 8-segment breakdown |

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

## Test Environment Reference

```yaml
# System Network (Host-to-Host) - Pingmesh collected by node33
pingmesh_collector: 192.168.70.33 (node33)
injection_host: 192.168.70.33 (node33)
injection_interface: port-storage
target_hosts: [node31, node32, node34]
network_subnet: 70.0.0.x (storage)

# VM Network (Cross-Node)
sender_vm: 192.168.77.83 (on host node32/70.32)
receiver_vm: 192.168.76.244 (on host node31/70.31)
sender_host: 192.168.70.32 (node32)
receiver_host: 192.168.70.31 (node31)
sender_vnet: vnet35 (on node32)
vm_interface: ens4

# Services
webhook_server: localhost:8080
alertmanager: localhost:9093
prometheus: 70.0.0.31:9090 (access via storage network)
prometheus_auth: prometheus:HC!r0cks
```

---

## Appendix A: Alertmanager 配置与告警触发时机

### Alertmanager 关键配置项

当前配置文件：`config/alertmanager/alertmanager.yml`

```yaml
route:
  group_by: ['alertname', 'hostname', 'to_hostname']
  group_wait: 10s        # 全局默认
  group_interval: 30s    # 全局默认
  repeat_interval: 4h    # 全局默认

  routes:
    - match_re:
        alertname: 'HostNetworkLatency.*|HostNetworkPacketLoss.*|NetSherlock.*'
      receiver: 'netsherlock'
      group_wait: 5s     # NetSherlock 路由覆盖
      group_interval: 1m # NetSherlock 路由覆盖
```

### 配置项说明

| 配置项 | 当前值 | 含义 | 对测试的影响 |
|--------|--------|------|-------------|
| **group_wait** | 5s | 收到**第一个**告警后，等待 5 秒再发送 webhook（等待同组其他告警聚合） | 告警触发后 **~5 秒** 才会调用 webhook |
| **group_interval** | 1m | 同一组告警的**后续**通知间隔（新告警加入已有组时） | 如果已发送过，需等 1 分钟才会再次通知 |
| **repeat_interval** | 4h | 同一告警**持续 firing** 时的重复通知间隔 | 同一告警 4 小时内不会重复触发诊断 |
| **group_by** | `[alertname, hostname, to_hostname]` | 按这些标签分组，同组告警聚合发送 | node33→node31 和 node33→node32 是不同组 |

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
   - 同一告警组已触发过后，需等待 `group_interval: 1m`
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
  rtt_warning_ms: 5.0      # RTT > 5ms → warning（boundary 模式）
  rtt_critical_ms: 20.0    # RTT > 20ms → critical（segment 模式）
  loss_warning_pct: 10.0   # 丢包 > 10% → warning
  loss_critical_pct: 50.0  # 丢包 > 50% → critical
  cooldown_seconds: 60     # 触发后 60 秒内不重复告警

collection:
  count: 5              # 每周期 5 个 ping 包
  cycle_pause: 2        # 周期间隔 2 秒
```

### 告警触发条件

| 告警类型 | 触发条件 | 诊断模式 |
|----------|----------|----------|
| `VMNetworkLatencyHigh` | RTT > 5ms，连续 3 个周期中有 2 个超标 | boundary |
| `VMNetworkLatencyCritical` | RTT > 20ms，连续 3 个周期中有 2 个超标 | segment |
| `VMNetworkPacketLoss` | Loss > 10%，连续 3 个周期中有 2 个超标 | boundary |

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

- 告警触发后 **60 秒内**不会重复触发同一目标的告警
- 重复测试时需等待 cooldown 或重启 ping_monitor：
  ```bash
  ssh root@192.168.77.83 "pkill -f ping_monitor; sleep 1; nohup python3 /usr/local/bin/ping_monitor.py --config /etc/ping_monitor/config.yaml > /var/log/ping_monitor.log 2>&1 &"
  ```
