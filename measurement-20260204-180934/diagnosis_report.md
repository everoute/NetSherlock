# VM Cross-Node ICMP Latency Diagnosis Report

**Measurement Directory**: `measurement-20260204-180934`
**Analysis Time**: 2026-02-04T18:10:25.875376

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 662.89 µs (0.663 ms) |
| **Primary Contributor** | Host OVS/Bridge Forwarding |
| **Contribution** | 37.4% |
| **Sample Count** | 26 |
| **Validation Error** | 0.65% |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Host OVS/Bridge Forwarding | 247.90 | 37.4% | B, D, I, K |
| VM Internal Kernel Stack | 203.38 | 30.7% | A, F, G, H, M |
| Virtualization RX Path (TUN→KVM) | 96.00 | 14.5% | E, L |
| Virtualization TX Path (KVM→TUN) | 70.77 | 10.7% | B_1, I_1 |
| Physical Network (Wire/Switch) | 49.12 | 7.4% | C_J |

## Segment Breakdown

| Segment | Description | Avg (µs) | StdDev | Min | Max | Samples |
|---------|-------------|----------|--------|-----|-----|---------|
| A | Sender VM kernel TX processing | 57.34 | 15.23 | 45.94 | 122.51 | 26 |
| M | Sender VM kernel RX processing | 51.09 | 17.88 | 18.00 | 103.41 | 26 |
| F | Receiver VM kernel RX processi | 47.40 | 23.98 | 31.18 | 160.59 | 26 |
| G | Receiver VM ICMP echo processi | 17.25 | 4.43 | 14.06 | 33.08 | 26 |
| H | Receiver VM kernel TX processi | 30.31 | 4.57 | 22.95 | 40.85 | 26 |
| B | Sender Host OVS request forwar | 49.93 | 8.18 | 41.00 | 71.10 | 19 |
| K | Sender Host OVS reply forwardi | 56.35 | 8.95 | 40.30 | 72.70 | 19 |
| D | Receiver Host OVS request forw | 81.54 | 7.52 | 64.50 | 97.40 | 25 |
| I | Receiver Host OVS reply forwar | 60.07 | 8.96 | 43.00 | 78.50 | 25 |
| E | Receiver vhost→KVM IRQ injecti | 57.46 | 9.27 | 36.00 | 78.00 | 24 |
| L | Sender vhost→KVM IRQ injection | 38.54 | 7.45 | 27.00 | 54.00 | 24 |
| B_1 | Sender KVM→vhost→TUN transmiss | 29.13 | 10.75 | 0.00 | 44.00 | 23 |
| I_1 | Receiver KVM→vhost→TUN transmi | 41.64 | 35.00 | 27.00 | 196.00 | 22 |
| C_J | Physical network latency (requ | 49.12 | 0.00 | 49.12 | 49.12 | 1 |

## Data Path Diagram

```

ICMP Request Path (Sender → Receiver):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Sender VM     │    │   Sender Host   │    │   Network   │    │  Receiver Host  │    │  Receiver VM    │
│                 │    │                 │    │             │    │                 │    │                 │
│ [A] TX Kernel   │───▶│ [B] OVS Fwd     │───▶│ [C] Wire    │───▶│ [D] OVS Fwd     │───▶│ [F] RX Kernel   │
│    A=57.3us     │    │    B=49.9us     │    │             │    │    D=81.5us     │    │    F=47.4us     │
│                 │    │ [B_1] KVM→TUN   │    │             │    │ [E] TUN→KVM     │    │ [G] ICMP Proc   │
│                 │    │   B_1=29.1us    │    │             │    │    E=57.5us     │    │    G=17.3us     │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

ICMP Reply Path (Receiver → Sender):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Receiver VM    │    │  Receiver Host  │    │   Network   │    │   Sender Host   │    │   Sender VM     │
│                 │    │                 │    │             │    │                 │    │                 │
│ [H] TX Kernel   │───▶│ [I] OVS Fwd     │───▶│ [J] Wire    │───▶│ [K] OVS Fwd     │───▶│ [M] RX Kernel   │
│    H=30.3us     │    │    I=60.1us     │    │             │    │    K=56.4us     │    │    M=51.1us     │
│                 │    │ [I_1] KVM→TUN   │    │             │    │ [L] TUN→KVM     │    │                 │
│                 │    │   I_1=41.6us    │    │             │    │    L=38.5us     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

Physical Network (C+J): C_J=49.1us

```

## Key Findings

### Total Round-Trip Latency

- **Value**: 662.89 µs
- **Range**: 521.09 - 1129.84 µs
- **StdDev**: 112.94 µs

### Primary Latency Contributor

- **Layer**: Host OVS/Bridge Forwarding
- **Latency**: 247.90 µs (37.4%)
- **Segments**: B, D, I, K

### Layer Attribution Summary

- **Host OVS/Bridge Forwarding**: 247.90µs (37.4%)
- **VM Internal Kernel Stack**: 203.38µs (30.7%)
- **Virtualization RX Path (TUN→KVM)**: 96.00µs (14.5%)
- **Virtualization TX Path (KVM→TUN)**: 70.77µs (10.7%)
- **Physical Network (Wire/Switch)**: 49.12µs (7.4%)

### Segments with Highest Variance

High variance segments:

- **I_1**: CV=84.1%, Avg=41.64µs, StdDev=35.00µs
- **F**: CV=50.6%, Avg=47.40µs, StdDev=23.98µs
- **M**: CV=35.0%, Avg=51.09µs, StdDev=17.88µs

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 662.89 µs |
| Calculated Total | 667.17 µs |
| Difference | 4.29 µs (0.65%) |
| Status | **Valid** |
