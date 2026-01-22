# Tool Output Mapping

## Overview

This document maps the output fields from each measurement tool to the data path segments.

## Tool Summary

| Tool | Script Location | Runs On | Purpose |
|------|-----------------|---------|---------|
| kernel_icmp_rtt.py | measurement-tools/performance/system-network/ | VM | Kernel-level ICMP RTT |
| icmp_drop_detector.py | measurement-tools/performance/system-network/ | Host | Host-level packet latency |
| tun_tx_to_kvm_irq.py | measurement-tools/kvm-virt-network/tun/ | Host | vhost→KVM IRQ injection (VM RX path) |
| kvm_vhost_tun_latency_details.py | measurement-tools/kvm-virt-network/vhost-net/ | Host | KVM→TUN latency (VM TX path) |

## kernel_icmp_rtt.py Output

### On Sender VM

Traces the complete ICMP request-reply cycle from the sender's perspective.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| Path 1 | A | TX path: icmp_send → virtio-net TX |
| Path 2 | M | RX path: virtio-net RX → icmp_rcv (reply) |
| Inter-Path Latency | B+C+D+E+F+G+H+I+J+K+L | Time outside sender VM |
| Total RTT | A+...+M | Complete end-to-end RTT |

**Sample Output**:
```
  Total Path 1:  15.234 us
  Total Path 2:  17.456 us
Inter-Path Latency (P1 end -> P2 start): 550.123 us
Total RTT (Path1 Start to Path2 End): 582.813 us
```

### On Receiver VM

Traces the ICMP request processing and reply generation.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| Path 1 | F | RX path: virtio-net RX → icmp_rcv (request) |
| Path 2 | H | TX path: icmp_reply → virtio-net TX |
| Inter-Path Latency | G | ICMP echo processing time |
| Total RTT | F+G+H | Receiver's view of request→reply |

**Sample Output**:
```
  Total Path 1:  23.644 us
  Total Path 2:   5.475 us
Inter-Path Latency (P1 end -> P2 start):   5.475 us
Total RTT (Path1 Start to Path2 End):  34.594 us
```

## icmp_drop_detector.py Output

### On Sender Host

Traces packets from VM interface to physical NIC and back.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| ReqInternal | B | Request: vnet RX → phy NIC TX |
| External | C+D+E+F+G+H+I+J | Time outside sender host |
| RepInternal | K | Reply: phy NIC RX → vnet TX |
| Total | B+External+K | Complete host-level RTT |

**Sample Output**:
```
Latency: ReqInternal=15.234 us | External=429.700 us | RepInternal=12.456 us | Total=457.390 us
```

### On Receiver Host

Traces packets from physical NIC to VM interface and back.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| ReqInternal | D | Request: phy NIC RX → vnet TX |
| External | E+F+G+H+I | Time inside receiver (including VM) |
| RepInternal | I | Reply: vnet RX → phy NIC TX |
| Total | D+External+I | Receiver host-level latency |

**Sample Output**:
```
Latency: ReqInternal=12.345 us | External=260.123 us | RepInternal=16.789 us | Total=289.257 us
```

## tun_tx_to_kvm_irq.py Output

### On Receiver Host (for incoming request)

Traces the vhost→KVM IRQ injection path for ICMP request.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| Total Delay (S1→S5) | E | Complete vhost→KVM injection |

**Stage Breakdown**:
| Stage | Probe Point | Description |
|-------|-------------|-------------|
| S1 | tun_net_xmit | TUN device transmit |
| S2 | vhost_signal_used_irq | vhost signals used buffer |
| S3 | eventfd_signal | eventfd notification |
| S4 | irqfd_wakeup | IRQ fd wakeup |
| S5 | kvm_set_irq | KVM IRQ injection |

**Sample Output**:
```
Total Delay(S1->S5):      0.098 ms
  Stage1->Stage2:         0.002 ms
  Stage2->Stage3:         0.001 ms
  Stage3->Stage4:         0.012 ms
  Stage4->Stage5:         0.083 ms
```

### On Sender Host (for incoming reply)

Same tracing as above, but for the ICMP reply entering sender host.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| Total Delay (S1→S5) | L | Complete vhost→KVM injection for reply |

## kvm_vhost_tun_latency_details.py Output

This tool measures the KVM→TUN path (VM TX direction), complementing tun_tx_to_kvm_irq.py which measures the TUN→KVM path (VM RX direction).

**Two-Phase Operation**:
1. **Discover Phase**: Identifies vhost worker TIDs and eventfd_ctx for the target flow
2. **Measure Phase**: Traces per-packet latency using the discovered profile

**Stage Breakdown (KVM→TUN path)**:
| Stage | Probe Points | Description |
|-------|--------------|-------------|
| S0 | ioeventfd_write → handle_tx_kick | KVM notifies vhost worker (often delayed by C-state) |
| S1 | handle_tx_kick → tun_sendmsg | vhost worker processes TX |
| S2 | tun_sendmsg → netif_receive_skb | TUN device transmits packet |

### On Sender Host (for outgoing request)

Traces the KVM→TUN path for ICMP request leaving sender VM.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| Total (S0+S1+S2) | B_1 | Complete KVM→TUN for sending request |

**Sample Output**:
```
[14:23:16.827] tid=73868 queue=2 s0=14us s1=5us s2=4us total=23us
[14:23:21.841] tid=73868 queue=2 s0=11us s1=3us s2=3us total=17us

Exact averages (us): S0=14.750, S1=3.500, S2=3.250, Total=21.500
```

### On Receiver Host (for outgoing reply)

Traces the KVM→TUN path for ICMP reply leaving receiver VM.

| Output Field | Segment | Description |
|--------------|---------|-------------|
| Total (S0+S1+S2) | I_1 | Complete KVM→TUN for sending reply |

## Segment to Tool Mapping Summary

| Segment | Tool | Host/VM | Output Field |
|---------|------|---------|--------------|
| A | kernel_icmp_rtt.py | Sender VM | Path 1 |
| B | icmp_drop_detector.py | Sender Host | ReqInternal |
| B_1 | kvm_vhost_tun_latency_details.py | Sender Host | Total (S0+S1+S2) |
| C | (Derived) | - | - |
| D | icmp_drop_detector.py | Receiver Host | ReqInternal |
| E | tun_tx_to_kvm_irq.py | Receiver Host | Total Delay (S1→S5) |
| F | kernel_icmp_rtt.py | Receiver VM | Path 1 |
| G | kernel_icmp_rtt.py | Receiver VM | Inter-Path |
| H | kernel_icmp_rtt.py | Receiver VM | Path 2 |
| I | icmp_drop_detector.py | Receiver Host | RepInternal |
| I_1 | kvm_vhost_tun_latency_details.py | Receiver Host | Total (S0+S1+S2) |
| J | (Derived) | - | - |
| K | icmp_drop_detector.py | Sender Host | RepInternal |
| L | tun_tx_to_kvm_irq.py | Sender Host | Total Delay (S1→S5) |
| M | kernel_icmp_rtt.py | Sender VM | Path 2 |

## Log File Naming Convention

Recommended log file names for clarity:

| Log File | Content | Segments |
|----------|---------|----------|
| `sfsvm-send.log` | kernel_icmp_rtt on sender VM | A, M |
| `sfsvm-recv.log` | kernel_icmp_rtt on receiver VM | F, G, H |
| `host-send.log` | icmp_drop_detector on sender host | B, K |
| `host-recv.log` | icmp_drop_detector on receiver host | D, I |
| `vhost-recv-request.log` | tun_tx_to_kvm_irq on receiver host (VM RX) | E |
| `vhost-send-reply.log` | tun_tx_to_kvm_irq on sender host (VM RX) | L |
| `kvm-tun-send-request.log` | kvm_vhost_tun_latency_details on sender host (VM TX) | B_1 |
| `kvm-tun-recv-reply.log` | kvm_vhost_tun_latency_details on receiver host (VM TX) | I_1 |
