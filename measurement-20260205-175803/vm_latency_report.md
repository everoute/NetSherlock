# VM Network Latency Analysis Report

**Measurement Directory**: `measurement-20260205-175803`
**Analysis Time**: 2026-02-05T17:59:00.824128

## Summary

| Metric | Value |
|--------|-------|
| **Sender Total RTT** | 386.10 us |
| **Receiver Total RTT** | 250.00 us |
| **Physical Network (derived)** | 24.20 us |
| **Primary Contributor** | Receiver VM + Virtualization |
| **Sample Count** | 33 |

## Layer Attribution

| Layer | Latency (us) | Percentage | Segments |
|-------|-------------|------------|----------|
| Receiver VM + Virtualization | 129.50 | 33.5% | R_External |
| Receiver Host OVS | 120.40 | 31.2% | R_ReqInternal, R_RepInternal |
| Sender Host OVS | 111.90 | 29.0% | S_ReqInternal, S_RepInternal |
| Physical Network | 24.20 | 6.3% | Physical |

*Note: Sender VM internal + Sender Virtualization not measured (ping originates inside VM)*

## Segment Breakdown

| Segment | Latency (us) | Source | Description |
|---------|-------------|--------|-------------|
| Sender ReqInternal | 62.40 | sender_host | Sender Host: vnet→phy (OVS forwarding, r |
| Physical Network | 24.20 | derived | Wire latency (both directions) |
| Receiver ReqInternal | 71.20 | receiver_host | Receiver Host: phy→vnet (OVS forwarding, |
| Receiver External | 129.50 | receiver_host | Receiver: vnet→VM→vnet (VM + virtualizat |
| Receiver RepInternal | 49.20 | receiver_host | Receiver Host: vnet→phy (OVS forwarding, |
| Sender RepInternal | 49.50 | sender_host | Sender Host: phy→vnet (OVS forwarding, r |

## Data Path Diagram

```
Sender VM    Sender Host (vnet->phy)          Physical Network         Receiver Host (phy->vnet)    Receiver VM
[Unmeasured] [S.ReqInternal:   62.4us]      [Physical:   24.2us]      [R.ReqInternal:   71.2us]   [R.External]
             vnet ---------> phy        ---->  Wire (Req)  ---->       phy ---------> vnet        -> VM
                                                                                                     |
                                                                                        129.5us
                                                                                                     |
             vnet <--------- phy        <----  Wire (Rep)  <----       phy <--------- vnet        <- VM
[Unmeasured] [S.RepInternal:   49.5us]                                [R.RepInternal:   49.2us]

Sender Total: 386.1us | Receiver Total: 250.0us
Physical Network (derived) = Sender.External - Receiver.Total = 24.2us
Unmeasured: Sender VM internal + Sender Virtualization (ping originates inside VM)
```

## Key Findings

- **Primary Bottleneck**: Receiver VM + Virtualization (129.5us, 33.5%)
- **Physical Network**: 24.2us - within normal range
- **Unmeasured**: Sender VM internal + Sender Virtualization (ping originates inside VM)
