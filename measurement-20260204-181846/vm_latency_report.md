# VM Network Latency Analysis Report

**Measurement Directory**: `/Users/admin/workspace/netsherlock/measurement-20260204-181846`
**Analysis Time**: 2026-02-04T18:19:40.812869

## Summary

| Metric | Value |
|--------|-------|
| **Sender Total RTT** | 404.90 us |
| **Receiver Total RTT** | 277.70 us |
| **Physical Network (derived)** | 30.90 us |
| **Primary Contributor** | Receiver VM + Virtualization |
| **Sample Count** | 24 |

## Layer Attribution

| Layer | Latency (us) | Percentage | Segments |
|-------|-------------|------------|----------|
| Receiver VM + Virtualization | 154.80 | 38.2% | R_External |
| Receiver Host OVS | 122.90 | 30.4% | R_ReqInternal, R_RepInternal |
| Sender Host OVS | 96.30 | 23.8% | S_ReqInternal, S_RepInternal |
| Physical Network | 30.90 | 7.6% | Physical |

*Note: Sender VM internal + Sender Virtualization not measured (ping originates inside VM)*

## Segment Breakdown

| Segment | Latency (us) | Source | Description |
|---------|-------------|--------|-------------|
| Sender ReqInternal | 50.50 | sender_host | Sender Host: vnet→phy (OVS forwarding, r |
| Physical Network | 30.90 | derived | Wire latency (both directions) |
| Receiver ReqInternal | 71.10 | receiver_host | Receiver Host: phy→vnet (OVS forwarding, |
| Receiver External | 154.80 | receiver_host | Receiver: vnet→VM→vnet (VM + virtualizat |
| Receiver RepInternal | 51.80 | receiver_host | Receiver Host: vnet→phy (OVS forwarding, |
| Sender RepInternal | 45.80 | sender_host | Sender Host: phy→vnet (OVS forwarding, r |

## Data Path Diagram

```
Sender VM    Sender Host (vnet->phy)          Physical Network         Receiver Host (phy->vnet)    Receiver VM
[Unmeasured] [S.ReqInternal:   50.5us]      [Physical:   30.9us]      [R.ReqInternal:   71.1us]   [R.External]
             vnet ---------> phy        ---->  Wire (Req)  ---->       phy ---------> vnet        -> VM
                                                                                                     |
                                                                                        154.8us
                                                                                                     |
             vnet <--------- phy        <----  Wire (Rep)  <----       phy <--------- vnet        <- VM
[Unmeasured] [S.RepInternal:   45.8us]                                [R.RepInternal:   51.8us]

Sender Total: 404.9us | Receiver Total: 277.7us
Physical Network (derived) = Sender.External - Receiver.Total = 30.9us
Unmeasured: Sender VM internal + Sender Virtualization (ping originates inside VM)
```

## Key Findings

- **Primary Bottleneck**: Receiver VM + Virtualization (154.8us, 38.2%)
- **Physical Network**: 30.9us - within normal range
- **Unmeasured**: Sender VM internal + Sender Virtualization (ping originates inside VM)
