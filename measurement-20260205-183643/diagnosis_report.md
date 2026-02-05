# VM Cross-Node ICMP Latency Diagnosis Report

**Measurement Directory**: `measurement-20260205-183643`
**Analysis Time**: 2026-02-05T18:37:40.438495

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 60736.59 µs (60.737 ms) |
| **Primary Contributor** | VM Internal Kernel Stack |
| **Contribution** | 99.2% |
| **Sample Count** | 22 |
| **Validation Error** | 0.01% |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| VM Internal Kernel Stack | 60243.10 | 99.2% | A, F, G, H, M |
| Host OVS/Bridge Forwarding | 257.68 | 0.4% | B, D, I, K |
| Virtualization TX Path (KVM→TUN) | 108.95 | 0.2% | B_1, I_1 |
| Virtualization RX Path (TUN→KVM) | 97.12 | 0.2% | E, L |
| Physical Network (Wire/Switch) | 26.63 | 0.0% | C_J |

## Segment Breakdown

| Segment | Description | Avg (µs) | StdDev | Min | Max | Samples |
|---------|-------------|----------|--------|-----|-----|---------|
| A | Sender VM kernel TX processing | 60105.02 | 13.75 | 60085.31 | 60135.45 | 22 |
| M | Sender VM kernel RX processing | 38.87 | 8.13 | 24.48 | 58.78 | 22 |
| F | Receiver VM kernel RX processi | 48.41 | 10.67 | 35.98 | 80.23 | 22 |
| G | Receiver VM ICMP echo processi | 17.55 | 3.90 | 14.28 | 29.40 | 22 |
| H | Receiver VM kernel TX processi | 33.25 | 8.46 | 20.94 | 62.09 | 22 |
| B | Sender Host OVS request forwar | 61.49 | 9.46 | 48.50 | 79.70 | 19 |
| K | Sender Host OVS reply forwardi | 54.07 | 10.46 | 29.70 | 74.20 | 19 |
| D | Receiver Host OVS request forw | 85.28 | 19.48 | 55.30 | 127.10 | 21 |
| I | Receiver Host OVS reply forwar | 56.85 | 8.42 | 40.70 | 77.70 | 21 |
| E | Receiver vhost→KVM IRQ injecti | 55.65 | 8.36 | 46.00 | 82.00 | 20 |
| L | Sender vhost→KVM IRQ injection | 41.47 | 11.31 | 29.00 | 78.00 | 19 |
| B_1 | Sender KVM→vhost→TUN transmiss | 71.95 | 161.34 | 0.00 | 733.00 | 19 |
| I_1 | Receiver KVM→vhost→TUN transmi | 37.00 | 8.82 | 25.00 | 60.00 | 17 |
| C_J | Physical network latency (requ | 26.63 | 0.00 | 26.63 | 26.63 | 1 |

## Data Path Diagram

```

ICMP Request Path (Sender → Receiver):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Sender VM     │    │   Sender Host   │    │   Network   │    │  Receiver Host  │    │  Receiver VM    │
│                 │    │                 │    │             │    │                 │    │                 │
│ [A] TX Kernel   │───▶│ [B] OVS Fwd     │───▶│ [C] Wire    │───▶│ [D] OVS Fwd     │───▶│ [F] RX Kernel   │
│   A=60105.0us   │    │    B=61.5us     │    │             │    │    D=85.3us     │    │    F=48.4us     │
│                 │    │ [B_1] KVM→TUN   │    │             │    │ [E] TUN→KVM     │    │ [G] ICMP Proc   │
│                 │    │   B_1=71.9us    │    │             │    │    E=55.6us     │    │    G=17.5us     │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

ICMP Reply Path (Receiver → Sender):
┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  Receiver VM    │    │  Receiver Host  │    │   Network   │    │   Sender Host   │    │   Sender VM     │
│                 │    │                 │    │             │    │                 │    │                 │
│ [H] TX Kernel   │───▶│ [I] OVS Fwd     │───▶│ [J] Wire    │───▶│ [K] OVS Fwd     │───▶│ [M] RX Kernel   │
│    H=33.2us     │    │    I=56.8us     │    │             │    │    K=54.1us     │    │    M=38.9us     │
│                 │    │ [I_1] KVM→TUN   │    │             │    │ [L] TUN→KVM     │    │                 │
│                 │    │   I_1=37.0us    │    │             │    │    L=41.5us     │    │                 │
└─────────────────┘    └─────────────────┘    └─────────────┘    └─────────────────┘    └─────────────────┘

Physical Network (C+J): C_J=26.6us

```

## Key Findings

### Total Round-Trip Latency

- **Value**: 60736.59 µs
- **Range**: 60531.34 - 61350.38 µs
- **StdDev**: 173.44 µs

### Primary Latency Contributor

- **Layer**: VM Internal Kernel Stack
- **Latency**: 60243.10 µs (99.2%)
- **Segments**: A, F, G, H, M

### Layer Attribution Summary

- **VM Internal Kernel Stack**: 60243.10µs (99.2%)
- **Host OVS/Bridge Forwarding**: 257.68µs (0.4%)
- **Virtualization TX Path (KVM→TUN)**: 108.95µs (0.2%)
- **Virtualization RX Path (TUN→KVM)**: 97.12µs (0.2%)
- **Physical Network (Wire/Switch)**: 26.63µs (0.0%)

### Segments with Highest Variance

High variance segments:

- **B_1**: CV=224.2%, Avg=71.95µs, StdDev=161.34µs
- **D**: CV=22.9%, Avg=85.28µs, StdDev=19.48µs
- **A**: CV=0.0%, Avg=60105.02µs, StdDev=13.75µs

## Validation

| Check | Value |
|-------|-------|
| Measured Total | 60736.59 µs |
| Calculated Total | 60733.48 µs |
| Difference | 3.11 µs (0.01%) |
| Status | **Valid** |
