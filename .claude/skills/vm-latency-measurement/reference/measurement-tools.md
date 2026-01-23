# Measurement Tools Reference

This document describes the 8 BPF measurement tools used for VM latency measurement.

## Overview

The measurement uses 4 different BPF tools, deployed to 4 machines (2 VMs + 2 hosts),
resulting in 8 measurement tool instances.

## Tool Instances

```
┌─────────────────────────────────────────────────────────────┐
│ Sender Side (4 tools)                                       │
├─────────────────────────────────────────────────────────────┤
│ Sender VM:                                                  │
│   1. kernel_icmp_rtt.py      → Segments A, M, Total RTT     │
│                                                             │
│ Sender Host:                                                │
│   2. icmp_drop_detector.py   → Segments B, K                │
│   3. kvm_vhost_tun_latency   → Segment B_1 (TX path)        │
│   4. tun_tx_to_kvm_irq.py    → Segment L (RX path)          │
├─────────────────────────────────────────────────────────────┤
│ Receiver Side (4 tools)                                     │
├─────────────────────────────────────────────────────────────┤
│ Receiver VM:                                                │
│   5. kernel_icmp_rtt.py      → Segments F, G, H             │
│                                                             │
│ Receiver Host:                                              │
│   6. icmp_drop_detector.py   → Segments D, I                │
│   7. kvm_vhost_tun_latency   → Segment I_1 (TX path)        │
│   8. tun_tx_to_kvm_irq.py    → Segment E (RX path)          │
└─────────────────────────────────────────────────────────────┘
```

## Tool Details

### 1. kernel_icmp_rtt.py

**Purpose**: Measure ICMP processing latency within VM kernel.

**Location**: `${LOCAL_TOOLS}/performance/system-network/`

**Deployment**: Both sender and receiver VMs

**Arguments**:
- `--src-ip`: Source IP address
- `--dst-ip`: Destination IP address
- `--interface`: Network interface (e.g., ens4)
- `--direction`: `tx` for sender, `rx` for receiver
- `--disable-kernel-stacks`: Reduce overhead

**Output Segments**:
- Sender VM: A (Path 1), M (Path 2), Total RTT
- Receiver VM: F (Path 1), G (Inter-Path), H (Path 2)

**Sample Output**:
```
Total Path 1:  15.234 us
Total Path 2:  17.456 us
Inter-Path Latency (P1 end -> P2 start): 550.123 us
Total RTT (Path1 Start to Path2 End): 582.813 us
```

### 2. icmp_drop_detector.py

**Purpose**: Track ICMP packet latency through host network stack.

**Location**: `${LOCAL_TOOLS}/linux-network-stack/packet-drop/`

**Deployment**: Both sender and receiver hosts

**Arguments**:
- `--src-ip`: Source IP address
- `--dst-ip`: Destination IP address
- `--rx-iface`: Receive interface (packet entry point)
- `--tx-iface`: Transmit interface (packet exit point)

**Output Segments**:
- ReqInternal: Request path internal latency (B on sender, D on receiver)
- External: Time between request TX and reply RX (includes network + remote processing)
- RepInternal: Reply path internal latency (K on sender, I on receiver)
- Total: Sum of all above

**Sample Output**:
```
Latency: ReqInternal=15.234 us | External=429.700 us | RepInternal=12.456 us | Total=457.390 us
```

### 3. tun_tx_to_kvm_irq.py

**Purpose**: Measure vhost-net to KVM IRQ injection latency (VM RX path).

**Location**: `${LOCAL_TOOLS}/kvm-virt-network/tun/`

**Deployment**: Both sender and receiver hosts

**Arguments**:
- `--device`: TUN/TAP device (vnet interface)
- `--src-ip`: Source IP address
- `--dst-ip`: Destination IP address
- `--protocol`: Protocol filter (icmp)

**Output Segments**:
- Receiver Host: E (receiving ICMP request)
- Sender Host: L (receiving ICMP reply)

**Sample Output**:
```
Total Delay(S1->S5):      0.098 ms
```

Note: Output is in **milliseconds**, converted to microseconds in parsing.

### 4. kvm_vhost_tun_latency_details.py

**Purpose**: Measure KVM to TUN latency (VM TX path).

**Location**: `${LOCAL_TOOLS}/kvm-virt-network/vhost-net/`

**Deployment**: Both sender and receiver hosts

**Two-Phase Operation**:
1. **Discover phase**: Identify vhost worker threads
2. **Measure phase**: Capture latency using discovered profile

**Discover Arguments**:
- `--mode discover`
- `--device`: TUN/TAP device (vnet interface)
- `--flow`: Flow filter (e.g., `proto=icmp,src=x.x.x.x,dst=y.y.y.y`)
- `--duration`: Discovery duration in seconds
- `--out`: Output profile JSON path

**Measure Arguments**:
- `--mode measure`
- `--profile`: Path to discovery profile JSON

**Output Segments**:
- Sender Host: B_1 (sending ICMP request)
- Receiver Host: I_1 (sending ICMP reply)

**Sample Output**:
```
[14:23:16.827] tid=73868 queue=2 s0=14us s1=5us s2=4us total=23us
Exact averages (us): S0=14.750, S1=3.500, S2=3.250, Total=21.500
```

## Segment Mapping Summary

| Segment | Tool | Location | Description |
|---------|------|----------|-------------|
| A | kernel_icmp_rtt | Sender VM | Request TX kernel path |
| B | icmp_drop_detector | Sender Host | Request internal (vnet→phy) |
| B_1 | kvm_vhost_tun_latency | Sender Host | KVM→TUN (request leaving VM) |
| C+J | Derived | - | Physical network (wire + switch) |
| D | icmp_drop_detector | Receiver Host | Request internal (phy→vnet) |
| E | tun_tx_to_kvm_irq | Receiver Host | TUN→KVM IRQ (request entering VM) |
| F | kernel_icmp_rtt | Receiver VM | Request RX kernel path |
| G | kernel_icmp_rtt | Receiver VM | Inter-path (request→reply in VM) |
| H | kernel_icmp_rtt | Receiver VM | Reply TX kernel path |
| I | icmp_drop_detector | Receiver Host | Reply internal (vnet→phy) |
| I_1 | kvm_vhost_tun_latency | Receiver Host | KVM→TUN (reply leaving VM) |
| K | icmp_drop_detector | Sender Host | Reply internal (phy→vnet) |
| L | tun_tx_to_kvm_irq | Sender Host | TUN→KVM IRQ (reply entering VM) |
| M | kernel_icmp_rtt | Sender VM | Reply RX kernel path |
