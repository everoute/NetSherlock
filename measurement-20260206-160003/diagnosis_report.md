# VM Cross-Node ICMP Latency Diagnosis Report

**Measurement Directory**: `measurement-20260206-160003`
**Analysis Time**: 2026-02-06T16:01:00.275457

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 60727.06 µs (60.727 ms) |
| **Primary Contributor** | VM Internal Kernel Stack |
| **Contribution** | 99.2% |
| **Sample Count** | 22 |
| **Validation Error** | 0.01% |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| VM Internal Kernel Stack | 60271.36 | 99.2% | A, F, G, H, M |
| Host OVS/Bridge Forwarding | 268.20 | 0.4% | B, D, I, K |
| Virtualization RX Path (TUN→KVM) | 93.42 | 0.1% | E, L |
| Virtualization TX Path (KVM→TUN) | 72.90 | 0.1% | B_1, I_1 |
| Physical Network (Wire/Switch) | 17.68 | 0.0% | C_J |

## Segment Breakdown

| Segment | Description | Avg (µs) | StdDev | Min | Max | Samples |
|---------|-------------|----------|--------|-----|-----|---------|
| A | Sender VM kernel TX processing | 60107.53 | 27.25 | 60070.10 | 60191.94 | 22 |
| M | Sender VM kernel RX processing | 42.56 | 21.41 | 25.31 | 104.63 | 22 |
| F | Receiver VM kernel RX processi | 56.27 | 15.31 | 39.01 | 93.72 | 22 |
| G | Receiver VM ICMP echo processi | 17.53 | 2.56 | 14.97 | 24.69 | 22 |
| H | Receiver VM kernel TX processi | 47.46 | 77.98 | 25.25 | 396.00 | 22 |
| B | Sender Host OVS request forwar | 65.19 | 11.28 | 49.70 | 90.20 | 16 |
| K | Sender Host OVS reply forwardi | 58.25 | 7.18 | 46.00 | 71.20 | 16 |
| D | Receiver Host OVS request forw | 91.19 | 12.67 | 68.20 | 118.40 | 19 |
| I | Receiver Host OVS reply forwar | 53.56 | 7.83 | 40.40 | 73.70 | 19 |
| E | Receiver vhost→KVM IRQ injecti | 61.05 | 10.10 | 48.00 | 80.00 | 19 |
| L | Sender vhost→KVM IRQ injection | 32.37 | 4.82 | 28.00 | 48.00 | 19 |
| B_1 | Sender KVM→vhost→TUN transmiss | 41.67 | 18.96 | 0.00 | 94.00 | 18 |
| I_1 | Receiver KVM→vhost→TUN transmi | 31.23 | 13.71 | 20.00 | 76.00 | 17 |
| C_J | Physical network latency (requ | 17.68 | 0.00 | 17.68 | 17.68 | 1 |

## Data Path Diagram

```

ICMP Request Path (Sender → Receiver):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Sender VM     │    │   Sender Host   │    │   Network   │    │  Receiver Host  │    │  Receiver VM    │
│                 │    │                 │    │             │    │                 │    │                 │
│ [A] TX Kernel   │───▶│ [B] OVS Fwd     │───▶│ [C] Wire    │───▶│ [D] OVS Fwd     │───▶│ [F] RX Kernel   │
│   A=60107.5us   │    │    B=65.2us     │    │             │    │    D=91.2us     │    │    F=56.3us     │
│                 │    │ [B_1] KVM→TUN   │    │             │    │ [E] TUN→KVM     │    │ [G] ICMP Proc   │
│                 │    │   B_1=41.7us    │    │             │    │    E=61.1us     │    │    G=17.5us     │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

ICMP Reply Path (Receiver → Sender):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Receiver VM    │    │  Receiver Host  │    │   Network   │    │   Sender Host   │    │   Sender VM     │
│                 │    │                 │    │             │    │                 │    │                 │
│ [H] TX Kernel   │───▶│ [I] OVS Fwd     │───▶│ [J] Wire    │───▶│ [K] OVS Fwd     │───▶│ [M] RX Kernel   │
│    H=47.5us     │    │    I=53.6us     │    │             │    │    K=58.2us     │    │    M=42.6us     │
│                 │    │ [I_1] KVM→TUN   │    │             │    │ [L] TUN→KVM     │    │                 │
│                 │    │   I_1=31.2us    │    │             │    │    L=32.4us     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

Physical Network (C+J): C_J=17.7us

```

## Key Findings

### Total Round-Trip Latency

- **Value**: 60727.06 µs
- **Range**: 60531.56 - 61145.22 µs
- **StdDev**: 131.34 µs

### Primary Latency Contributor

- **Layer**: VM Internal Kernel Stack
- **Latency**: 60271.36 µs (99.2%)
- **Segments**: A, F, G, H, M

### Layer Attribution Summary

- **VM Internal Kernel Stack**: 60271.36µs (99.2%)
- **Host OVS/Bridge Forwarding**: 268.20µs (0.4%)
- **Virtualization RX Path (TUN→KVM)**: 93.42µs (0.1%)
- **Virtualization TX Path (KVM→TUN)**: 72.90µs (0.1%)
- **Physical Network (Wire/Switch)**: 17.68µs (0.0%)

### Segments with Highest Variance

High variance segments:

- **H**: CV=164.3%, Avg=47.46µs, StdDev=77.98µs
- **A**: CV=0.1%, Avg=60107.53µs, StdDev=27.25µs
- **M**: CV=50.3%, Avg=42.56µs, StdDev=21.41µs

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 60727.06 µs |
| Calculated Total | 60723.56 µs |
| Difference | 3.51 µs (0.01%) |
| Status | **Valid** |
