---
name: vm-latency-measurement
description: |
  Execute coordinated latency measurement across sender and receiver VMs and hosts.
  Deploys BPF tools to 8 measurement points, starts them with receiver-first timing,
  collects logs, and triggers latency-analysis skill.

  Trigger keywords: measure VM latency, run latency measurement, collect latency data,
  deploy measurement tools, cross-node measurement, 测量延迟, 执行测量

allowed-tools: Read, Write, Bash, Skill
---
# VM Latency Measurement Skill

## Overview

This skill orchestrates end-to-end latency measurement for cross-node VM ICMP ping scenarios.
It coordinates tool deployment and execution across 8 measurement points with proper
receiver-first timing to ensure accurate data collection.

## Prerequisites

- SSH access to sender/receiver VMs and hosts
- Root/sudo access on target machines
- BPF tools available locally or pre-deployed:
  - `kernel_icmp_rtt.py` (for VMs)
  - `icmp_drop_detector.py` (for hosts)
  - `tun_tx_to_kvm_irq.py` (for hosts - VM RX path)
  - `kvm_vhost_tun_latency_details.py` (for hosts - VM TX path)

## Measurement Points (8 total)

```
Sender Side:
  1. Sender VM:   kernel_icmp_rtt.py               → Segments A, M
  2. Sender Host: icmp_drop_detector.py            → Segments B, K
  3. Sender Host: kvm_vhost_tun_latency_details.py → Segment B_1 (sending request)
  4. Sender Host: tun_tx_to_kvm_irq.py             → Segment L (receiving reply)

Receiver Side:
  5. Receiver VM:   kernel_icmp_rtt.py               → Segments F, G, H
  6. Receiver Host: icmp_drop_detector.py            → Segments D, I
  7. Receiver Host: tun_tx_to_kvm_irq.py             → Segment E (receiving request)
  8. Receiver Host: kvm_vhost_tun_latency_details.py → Segment I_1 (sending reply)
```

## Configuration Parameters

Before running, collect the following information:

```yaml
environment:
  name: "Production Cluster A"

sender:
  vm:
    ssh: "root@10.0.0.1"           # SSH to sender VM
    ip: "10.0.0.1"                 # VM's internal IP
  host:
    ssh: "root@192.168.1.10"       # SSH to sender hypervisor
    vnet_interface: "vnet0"        # VM's TAP interface on host
    phy_interface: "enps0f0"         # Physical NIC list

receiver:
  vm:
    ssh: "root@10.0.0.2"           # SSH to receiver VM
    ip: "10.0.0.2"                 # VM's internal IP
  host:
    ssh: "root@192.168.1.20"       # SSH to receiver hypervisor
    vnet_interface: "vnet0"        # VM's TAP interface on host
    phy_interface: "enps0f0"         # Physical NIC list

tools:
  local_path: "/opt/troubleshooting-tools/measurement-tools"
  # Or if pre-deployed:
  remote_path: "/tmp/bpf-tools"

measurement:
  duration: 30                     # seconds
  ping_interval: 1               # seconds between pings
```

## Execution Workflow

### Step 1: Validate Environment

Check SSH connectivity to all 4 machines:

```bash
# Test SSH connections
ssh ${SENDER_VM_SSH} "echo 'Sender VM OK'"
ssh ${SENDER_HOST_SSH} "echo 'Sender Host OK'"
ssh ${RECEIVER_VM_SSH} "echo 'Receiver VM OK'"
ssh ${RECEIVER_HOST_SSH} "echo 'Receiver Host OK'"
```

### Step 2: Deploy Tools (if needed)

```bash
# Deploy to VMs
scp ${LOCAL_TOOLS}/performance/system-network/kernel_icmp_rtt.py ${SENDER_VM_SSH}:/tmp/
scp ${LOCAL_TOOLS}/performance/system-network/kernel_icmp_rtt.py ${RECEIVER_VM_SSH}:/tmp/

# Deploy to Hosts
scp ${LOCAL_TOOLS}/performance/system-network/icmp_drop_detector.py ${SENDER_HOST_SSH}:/tmp/
scp ${LOCAL_TOOLS}/performance/system-network/icmp_drop_detector.py ${RECEIVER_HOST_SSH}:/tmp/
scp ${LOCAL_TOOLS}/kvm-virt-network/tun/tun_tx_to_kvm_irq.py ${SENDER_HOST_SSH}:/tmp/
scp ${LOCAL_TOOLS}/kvm-virt-network/tun/tun_tx_to_kvm_irq.py ${RECEIVER_HOST_SSH}:/tmp/
scp ${LOCAL_TOOLS}/kvm-virt-network/vhost-net/kvm_vhost_tun_latency_details.py ${SENDER_HOST_SSH}:/tmp/
scp ${LOCAL_TOOLS}/kvm-virt-network/vhost-net/kvm_vhost_tun_latency_details.py ${RECEIVER_HOST_SSH}:/tmp/
```

### Step 3: Pre-Discovery for kvm_vhost_tun_latency (Two-Phase Tool)

**NOTE**: The `kvm_vhost_tun_latency_details.py` tool requires a discovery phase to identify vhost worker threads before measurement. Run discovery during a brief traffic burst, then use the profile for measurement.

```bash
# 3.1 Pre-discovery on Sender Host (for outgoing ICMP request)
# Start brief ping traffic, then discover
ssh ${SENDER_VM_SSH} "ping -c 10 -i 0.1 ${RECEIVER_VM_IP}" &
ssh ${SENDER_HOST_SSH} "sudo python3 /tmp/kvm_vhost_tun_latency_details.py \
    --mode discover \
    --device ${SEND_VNET_IF} \
    --flow 'proto=icmp,src=${SENDER_VM_IP},dst=${RECEIVER_VM_IP}' \
    --duration 5 \
    --out /tmp/kvm-tun-send-profile.json"

# 3.2 Pre-discovery on Receiver Host (for outgoing ICMP reply)
ssh ${SENDER_VM_SSH} "ping -c 10 -i 0.1 ${RECEIVER_VM_IP}" &
ssh ${RECEIVER_HOST_SSH} "sudo python3 /tmp/kvm_vhost_tun_latency_details.py \
    --mode discover \
    --device ${RECV_VNET_IF} \
    --flow 'proto=icmp,src=${RECEIVER_VM_IP},dst=${SENDER_VM_IP}' \
    --duration 5 \
    --out /tmp/kvm-tun-recv-profile.json"
```

### Step 4: Start Tools (Receiver-First Order)

**CRITICAL**: Start receiver-side tools BEFORE sender-side tools to ensure no packets are missed.

**Phase A - Start Receiver Side First**:

```bash
# 1. Receiver Host - icmp_drop_detector (captures incoming request)
ssh ${RECEIVER_HOST_SSH} "sudo python3 /tmp/icmp_drop_detector.py \
    --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} \
    --phy-interface ${RECV_PHY_IF} --vm-interface ${RECV_VNET_IF}" \
    > recv-host-icmp.log 2>&1 &

# 2. Receiver Host - tun_tx_to_kvm_irq (captures vhost→KVM for incoming request)
ssh ${RECEIVER_HOST_SSH} "sudo python3 /tmp/tun_tx_to_kvm_irq.py \
    --vm-interface ${RECV_VNET_IF}" \
    > recv-host-vhost-rx.log 2>&1 &

# 3. Receiver Host - kvm_vhost_tun_latency (captures KVM→TUN for outgoing reply)
ssh ${RECEIVER_HOST_SSH} "sudo python3 /tmp/kvm_vhost_tun_latency_details.py \
    --mode measure \
    --profile /tmp/kvm-tun-recv-profile.json \
    --duration ${DURATION}" \
    > recv-host-kvm-tun.log 2>&1 &

# 4. Receiver VM - kernel_icmp_rtt (captures request processing)
ssh ${RECEIVER_VM_SSH} "sudo python3 /tmp/kernel_icmp_rtt.py \
    --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP}" \
    > recv-vm-icmp.log 2>&1 &

# Wait for receivers to be ready
sleep 2
```

**Phase B - Start Sender Side**:

```bash
# 5. Sender Host - icmp_drop_detector
ssh ${SENDER_HOST_SSH} "sudo python3 /tmp/icmp_drop_detector.py \
    --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP} \
    --phy-interface ${SEND_PHY_IF} --vm-interface ${SEND_VNET_IF}" \
    > send-host-icmp.log 2>&1 &

# 6. Sender Host - tun_tx_to_kvm_irq (captures vhost→KVM for incoming reply)
ssh ${SENDER_HOST_SSH} "sudo python3 /tmp/tun_tx_to_kvm_irq.py \
    --vm-interface ${SEND_VNET_IF}" \
    > send-host-vhost-rx.log 2>&1 &

# 7. Sender Host - kvm_vhost_tun_latency (captures KVM→TUN for outgoing request)
ssh ${SENDER_HOST_SSH} "sudo python3 /tmp/kvm_vhost_tun_latency_details.py \
    --mode measure \
    --profile /tmp/kvm-tun-send-profile.json \
    --duration ${DURATION}" \
    > send-host-kvm-tun.log 2>&1 &

# 8. Sender VM - kernel_icmp_rtt (initiates measurement)
ssh ${SENDER_VM_SSH} "sudo python3 /tmp/kernel_icmp_rtt.py \
    --src-ip ${SENDER_VM_IP} --dst-ip ${RECEIVER_VM_IP}" \
    > send-vm-icmp.log 2>&1 &
```

### Step 5: Generate Traffic

Start ICMP ping from sender VM:

```bash
ssh ${SENDER_VM_SSH} "ping -c ${PING_COUNT} -i ${PING_INTERVAL} ${RECEIVER_VM_IP}"
```

### Step 6: Wait and Stop Tools

```bash
# Wait for measurement duration
sleep ${DURATION}

# Stop all tools gracefully (Ctrl+C equivalent)
ssh ${SENDER_VM_SSH} "pkill -INT -f kernel_icmp_rtt.py" || true
ssh ${RECEIVER_VM_SSH} "pkill -INT -f kernel_icmp_rtt.py" || true
ssh ${SENDER_HOST_SSH} "pkill -INT -f 'icmp_drop_detector.py|tun_tx_to_kvm_irq.py|kvm_vhost_tun_latency'" || true
ssh ${RECEIVER_HOST_SSH} "pkill -INT -f 'icmp_drop_detector.py|tun_tx_to_kvm_irq.py|kvm_vhost_tun_latency'" || true

# Wait for graceful shutdown
sleep 3
```

### Step 7: Collect Logs

Retrieve all 8 log files:

```bash
# Create output directory
mkdir -p ./measurement-${TIMESTAMP}

# Collect logs from VMs
scp ${SENDER_VM_SSH}:/tmp/send-vm-icmp.log ./measurement-${TIMESTAMP}/
scp ${RECEIVER_VM_SSH}:/tmp/recv-vm-icmp.log ./measurement-${TIMESTAMP}/

# Collect logs from Hosts
scp ${SENDER_HOST_SSH}:/tmp/send-host-icmp.log ./measurement-${TIMESTAMP}/
scp ${SENDER_HOST_SSH}:/tmp/send-host-vhost-rx.log ./measurement-${TIMESTAMP}/
scp ${SENDER_HOST_SSH}:/tmp/send-host-kvm-tun.log ./measurement-${TIMESTAMP}/
scp ${RECEIVER_HOST_SSH}:/tmp/recv-host-icmp.log ./measurement-${TIMESTAMP}/
scp ${RECEIVER_HOST_SSH}:/tmp/recv-host-vhost-rx.log ./measurement-${TIMESTAMP}/
scp ${RECEIVER_HOST_SSH}:/tmp/recv-host-kvm-tun.log ./measurement-${TIMESTAMP}/
```

### Step 8: Trigger Analysis

Invoke the `vm-latency-analysis` skill to analyze collected logs:

```
Analyze the latency measurement logs in ./measurement-${TIMESTAMP}/:
- send-vm-icmp.log (Sender VM kernel_icmp_rtt) → A, M
- recv-vm-icmp.log (Receiver VM kernel_icmp_rtt) → F, G, H
- send-host-icmp.log (Sender Host icmp_drop_detector) → B, K
- recv-host-icmp.log (Receiver Host icmp_drop_detector) → D, I
- send-host-vhost-rx.log (Sender Host tun_tx_to_kvm_irq) → L
- recv-host-vhost-rx.log (Receiver Host tun_tx_to_kvm_irq) → E
- send-host-kvm-tun.log (Sender Host kvm_vhost_tun_latency) → B_1
- recv-host-kvm-tun.log (Receiver Host kvm_vhost_tun_latency) → I_1

Environment: ${ENVIRONMENT_NAME}
```

## Output Files

| File                   | Content                             | Segments Measured |
| ---------------------- | ----------------------------------- | ----------------- |
| send-vm-icmp.log       | Sender VM kernel_icmp_rtt           | A, M, Total RTT   |
| recv-vm-icmp.log       | Receiver VM kernel_icmp_rtt         | F, G, H           |
| send-host-icmp.log     | Sender Host icmp_drop_detector      | B, K              |
| recv-host-icmp.log     | Receiver Host icmp_drop_detector    | D, I              |
| send-host-vhost-rx.log | Sender Host tun_tx_to_kvm_irq       | L (VM RX path)    |
| recv-host-vhost-rx.log | Receiver Host tun_tx_to_kvm_irq     | E (VM RX path)    |
| send-host-kvm-tun.log  | Sender Host kvm_vhost_tun_latency   | B_1 (VM TX path)  |
| recv-host-kvm-tun.log  | Receiver Host kvm_vhost_tun_latency | I_1 (VM TX path)  |

## Error Handling

### SSH Connection Failed

- Verify network connectivity
- Check SSH key authentication
- Confirm target IP is correct

### Tool Not Found

- Verify tool path is correct
- Re-deploy tools using Step 2

### Permission Denied

- Ensure sudo/root access
- Check BPF permissions (CAP_BPF, CAP_SYS_ADMIN)

### No Output Captured

- Verify filter parameters (IPs, interfaces)
- Check that ping traffic is flowing
- Ensure tools started before traffic

### kvm_vhost_tun_latency Discovery Failed

- Ensure traffic is flowing during discovery phase
- Verify the device name (vnet interface) is correct
- Check that the flow filter matches the actual traffic (proto, src/dst IP)
- Verify the profile JSON file was created successfully
- If no associations found, the flow may be using a different vhost worker

## Integration with NetSherlock

This skill is designed to be invoked by NetSherlock's L3 measurement layer:

```python
# In DiagnosisController or L3 Subagent
await skill_executor.invoke(
    skill_name="vm-latency-measurement",
    parameters={
        "sender_vm_ssh": env.src_vm.ssh_address,
        "sender_host_ssh": env.src_host,
        "receiver_vm_ssh": env.dst_vm.ssh_address,
        "receiver_host_ssh": env.dst_host,
        "sender_vm_ip": env.src_vm.ip,
        "receiver_vm_ip": env.dst_vm.ip,
        "duration": 30,
    }
)
```

## Related Skills

- [vm-latency-analysis](../vm-latency-analysis/SKILL.md) - Analyze collected measurement data
