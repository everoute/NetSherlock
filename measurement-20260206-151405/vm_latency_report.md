# VM Network Latency Analysis Report

**Measurement Directory**: `/Users/admin/workspace/netsherlock/measurement-20260206-151405`
**Analysis Time**: 2026-02-06T15:15:00.977932

## Summary

| Metric | Value |
|--------|-------|
| **Sender Total RTT** | 935.00 us |
| **Receiver Total RTT** | 0.00 us |
| **Physical Network (derived)** | 836.10 us |
| **Primary Contributor** | Physical Network |
| **Sample Count** | 25 |

## Layer Attribution

| Layer | Latency (us) | Percentage | Segments |
|-------|-------------|------------|----------|
| Physical Network | 836.10 | 89.4% | Physical |
| Sender Host OVS | 98.80 | 10.6% | S_ReqInternal, S_RepInternal |
| Receiver Host OVS | 0.00 | 0.0% | R_ReqInternal, R_RepInternal |
| Receiver VM + Virtualization | 0.00 | 0.0% | R_External |

*Note: Sender VM internal + Sender Virtualization not measured (ping originates inside VM)*

## Segment Breakdown

| Segment | Latency (us) | Source | Description |
|---------|-------------|--------|-------------|
| Sender ReqInternal | 51.20 | sender_host | Sender Host: vnet→phy (OVS forwarding, r |
| Physical Network | 836.10 | derived | Wire latency (both directions) |
| Receiver ReqInternal | 0.00 | receiver_host | Receiver Host: phy→vnet (OVS forwarding, |
| Receiver External | 0.00 | receiver_host | Receiver: vnet→VM→vnet (VM + virtualizat |
| Receiver RepInternal | 0.00 | receiver_host | Receiver Host: vnet→phy (OVS forwarding, |
| Sender RepInternal | 47.60 | sender_host | Sender Host: phy→vnet (OVS forwarding, r |

## Data Path Diagram

```
Sender VM    Sender Host (vnet->phy)          Physical Network         Receiver Host (phy->vnet)    Receiver VM
[Unmeasured] [S.ReqInternal:   51.2us]      [Physical:  836.1us]      [R.ReqInternal:    0.0us]   [R.External]
             vnet ---------> phy        ---->  Wire (Req)  ---->       phy ---------> vnet        -> VM
                                                                                                     |
                                                                                          0.0us
                                                                                                     |
             vnet <--------- phy        <----  Wire (Rep)  <----       phy <--------- vnet        <- VM
[Unmeasured] [S.RepInternal:   47.6us]                                [R.RepInternal:    0.0us]

Sender Total: 935.0us | Receiver Total: 0.0us
Physical Network (derived) = Sender.External - Receiver.Total = 836.1us
Unmeasured: Sender VM internal + Sender Virtualization (ping originates inside VM)
```

## Key Findings

- **Primary Bottleneck**: Physical Network (836.1us, 89.4%)
- **Physical Network**: 836.1us - check switch/cable quality
- **Unmeasured**: Sender VM internal + Sender Virtualization (ping originates inside VM)
