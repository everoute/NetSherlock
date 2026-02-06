# VM Cross-Node ICMP Latency Diagnosis Report

**Measurement Directory**: `measurement-20260206-170006`
**Analysis Time**: 2026-02-06T17:01:02.147971

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 60711.13 µs (60.711 ms) |
| **Primary Contributor** | VM Internal Kernel Stack |
| **Contribution** | 99.3% |
| **Sample Count** | 21 |
| **Validation Error** | 0.02% |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| VM Internal Kernel Stack | 60269.32 | 99.3% | A, F, G, H, M |
| Host OVS/Bridge Forwarding | 260.07 | 0.4% | B, D, I, K |
| Virtualization RX Path (TUN→KVM) | 93.76 | 0.1% | E, L |
| Virtualization TX Path (KVM→TUN) | 70.83 | 0.1% | B_1, I_1 |
| Physical Network (Wire/Switch) | 32.13 | 0.1% | C_J |

## Segment Breakdown

| Segment | Description | Avg (µs) | StdDev | Min | Max | Samples |
|---------|-------------|----------|--------|-----|-----|---------|
| A | Sender VM kernel TX processing | 60108.54 | 22.01 | 60086.94 | 60181.24 | 21 |
| M | Sender VM kernel RX processing | 43.96 | 14.75 | 32.28 | 93.11 | 21 |
| F | Receiver VM kernel RX processi | 61.46 | 42.03 | 35.98 | 223.54 | 21 |
| G | Receiver VM ICMP echo processi | 22.46 | 21.51 | 13.72 | 112.25 | 21 |
| H | Receiver VM kernel TX processi | 32.89 | 8.32 | 24.66 | 64.81 | 21 |
| B | Sender Host OVS request forwar | 62.78 | 14.47 | 44.40 | 104.30 | 20 |
| K | Sender Host OVS reply forwardi | 55.40 | 6.82 | 41.90 | 69.20 | 20 |
| D | Receiver Host OVS request forw | 86.31 | 16.16 | 67.00 | 132.20 | 21 |
| I | Receiver Host OVS reply forwar | 55.59 | 6.67 | 40.30 | 67.00 | 21 |
| E | Receiver vhost→KVM IRQ injecti | 55.19 | 8.63 | 44.00 | 78.00 | 21 |
| L | Sender vhost→KVM IRQ injection | 38.57 | 17.36 | 28.00 | 109.00 | 21 |
| B_1 | Sender KVM→vhost→TUN transmiss | 37.00 | 14.93 | 0.00 | 52.00 | 17 |
| I_1 | Receiver KVM→vhost→TUN transmi | 33.83 | 6.96 | 24.00 | 48.00 | 18 |
| C_J | Physical network latency (requ | 32.13 | 0.00 | 32.13 | 32.13 | 1 |

## Data Path Diagram

```

ICMP Request Path (Sender → Receiver):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Sender VM     │    │   Sender Host   │    │   Network   │    │  Receiver Host  │    │  Receiver VM    │
│                 │    │                 │    │             │    │                 │    │                 │
│ [A] TX Kernel   │───▶│ [B] OVS Fwd     │───▶│ [C] Wire    │───▶│ [D] OVS Fwd     │───▶│ [F] RX Kernel   │
│   A=60108.5us   │    │    B=62.8us     │    │             │    │    D=86.3us     │    │    F=61.5us     │
│                 │    │ [B_1] KVM→TUN   │    │             │    │ [E] TUN→KVM     │    │ [G] ICMP Proc   │
│                 │    │   B_1=37.0us    │    │             │    │    E=55.2us     │    │    G=22.5us     │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

ICMP Reply Path (Receiver → Sender):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Receiver VM    │    │  Receiver Host  │    │   Network   │    │   Sender Host   │    │   Sender VM     │
│                 │    │                 │    │             │    │                 │    │                 │
│ [H] TX Kernel   │───▶│ [I] OVS Fwd     │───▶│ [J] Wire    │───▶│ [K] OVS Fwd     │───▶│ [M] RX Kernel   │
│    H=32.9us     │    │    I=55.6us     │    │             │    │    K=55.4us     │    │    M=44.0us     │
│                 │    │ [I_1] KVM→TUN   │    │             │    │ [L] TUN→KVM     │    │                 │
│                 │    │   I_1=33.8us    │    │             │    │    L=38.6us     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

Physical Network (C+J): C_J=32.1us

```

## Key Findings

### Total Round-Trip Latency

- **Value**: 60711.13 µs
- **Range**: 60585.03 - 60909.14 µs
- **StdDev**: 93.15 µs

### Primary Latency Contributor

- **Layer**: VM Internal Kernel Stack
- **Latency**: 60269.32 µs (99.3%)
- **Segments**: A, F, G, H, M

### Layer Attribution Summary

- **VM Internal Kernel Stack**: 60269.32µs (99.3%)
- **Host OVS/Bridge Forwarding**: 260.07µs (0.4%)
- **Virtualization RX Path (TUN→KVM)**: 93.76µs (0.1%)
- **Virtualization TX Path (KVM→TUN)**: 70.83µs (0.1%)
- **Physical Network (Wire/Switch)**: 32.13µs (0.1%)

### Segments with Highest Variance

High variance segments:

- **F**: CV=68.4%, Avg=61.46µs, StdDev=42.03µs
- **A**: CV=0.0%, Avg=60108.54µs, StdDev=22.01µs
- **G**: CV=95.7%, Avg=22.46µs, StdDev=21.51µs

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 60711.13 µs |
| Calculated Total | 60726.11 µs |
| Difference | 14.98 µs (0.02%) |
| Status | **Valid** |
