import type { DiagnosisResponse } from '@/types'

/**
 * Mock diagnosis data based on real measurement-* directories
 * Used for development and testing when the backend API is not available
 */
export const mockDiagnoses: DiagnosisResponse[] = [
  // Completed: VM Latency Diagnosis from measurement-20260204-175008
  {
    diagnosis_id: 'diag-20260204-175008-vm-latency',
    status: 'completed',
    timestamp: '2026-02-04T17:50:00Z',
    started_at: '2026-02-04T17:45:00Z',
    completed_at: '2026-02-04T17:51:07Z',
    mode: 'autonomous',
    diagnosis_type: 'latency',
    network_type: 'vm',
    trigger_source: 'manual',
    summary:
      'VM network latency analysis completed. Primary bottleneck identified in Receiver Host OVS with 118.0us latency (33.4% of total).',
    logs: [
      {
        name: 'sender-host.log',
        content: `[2026-02-04 17:45:00] Starting latency measurement on sender host
[2026-02-04 17:45:01] BPF tracer initialized successfully
[2026-02-04 17:45:02] Sending ICMP ping packets (24 samples)
[2026-02-04 17:45:10] Sample 1: 353.80 us (sender total), 229.00 us (receiver total)
[2026-02-04 17:45:15] Collecting packet timestamps...
[2026-02-04 17:45:20] Sender host vnet→phy latency: 57.90 us (average)
[2026-02-04 17:45:25] Sender host phy→vnet latency: 43.90 us (average)
[2026-02-04 17:45:30] Analysis complete. Samples: 24, Errors: 0`,
      },
      {
        name: 'receiver-host.log',
        content: `[2026-02-04 17:45:00] Starting latency measurement on receiver host
[2026-02-04 17:45:01] BPF tracer initialized successfully
[2026-02-04 17:45:02] Waiting for incoming ICMP packets...
[2026-02-04 17:45:10] Received first packet: latency 229.00 us
[2026-02-04 17:45:15] Receiver Host OVS phy→vnet latency: 71.00 us
[2026-02-04 17:45:20] Receiver VM latency: 111.00 us
[2026-02-04 17:45:25] Receiver Host OVS vnet→phy latency: 47.00 us
[2026-02-04 17:45:30] Analysis complete. Samples: 24, Errors: 0`,
      },
      {
        name: 'analysis.log',
        content: `[2026-02-04 17:51:00] Starting latency analysis
[2026-02-04 17:51:01] Loading measurement data from 2 hosts
[2026-02-04 17:51:02] Computing segment latencies...
[2026-02-04 17:51:03] Layer Attribution:
  - Receiver Host OVS: 118.00 us (33.4%)
  - Receiver VM + Virtualization: 111.00 us (31.4%)
  - Sender Host OVS: 101.80 us (28.8%)
  - Physical Network: 23.00 us (6.5%)
[2026-02-04 17:51:04] Physical network latency (derived): 23.00 us
[2026-02-04 17:51:05] Primary bottleneck: Receiver Host OVS
[2026-02-04 17:51:06] Generating markdown report...
[2026-02-04 17:51:07] Analysis complete`,
      },
    ],
    root_cause: {
      category: 'vhost_processing',
      component: 'Receiver Host OVS',
      confidence: 0.92,
      evidence: [
        'Receiver Host OVS latency: 118.0us (33.4% of total)',
        'Consistent high latency across 24 samples',
        'OVS forwarding operations in request/reply path: 118.0us',
        'Physical network contribution minimal: 23.0us (6.5%)',
      ],
    },
    recommendations: [
      {
        priority: 1,
        action: 'Optimize OVS forwarding pipeline configuration',
        rationale:
          'OVS is contributing 33.4% of total latency. Review flow cache settings and forwarding rules.',
        command: 'ovs-vsctl list-br && ovs-ofctl dump-flows br0',
      },
      {
        priority: 2,
        action: 'Enable OVS hardware offloading if available',
        rationale:
          'Hardware offloading can reduce software forwarding overhead.',
        command: 'ethtool -k <iface> | grep offload',
      },
      {
        priority: 3,
        action: 'Monitor VM vhost thread CPU usage',
        rationale: 'High latency may indicate CPU saturation.',
        command: 'ps aux | grep vhost',
      },
    ],
    markdown_report: `# VM Network Latency Analysis Report

**Measurement Directory**: \`measurement-20260204-175008\`
**Analysis Time**: 2026-02-04T17:51:07.441925

## Summary

| Metric | Value |
|--------|-------|
| **Sender Total RTT** | 353.80 us |
| **Receiver Total RTT** | 229.00 us |
| **Physical Network (derived)** | 23.00 us |
| **Primary Contributor** | Receiver Host OVS |
| **Sample Count** | 24 |

## Layer Attribution

| Layer | Latency (us) | Percentage | Segments |
|-------|-------------|------------|----------|
| Receiver Host OVS | 118.00 | 33.4% | R_ReqInternal, R_RepInternal |
| Receiver VM + Virtualization | 111.00 | 31.4% | R_External |
| Sender Host OVS | 101.80 | 28.8% | S_ReqInternal, S_RepInternal |
| Physical Network | 23.00 | 6.5% | Physical |

## Key Findings

- **Primary Bottleneck**: Receiver Host OVS (118.0us, 33.4%)
- **Physical Network**: 23.0us - within normal range
- **Unmeasured**: Sender VM internal + Sender Virtualization (ping originates inside VM)`,
  },

  // Completed: VM Drop Analysis from measurement-20260204-175437
  {
    diagnosis_id: 'diag-20260204-175437-vm-drops',
    status: 'completed',
    timestamp: '2026-02-04T17:50:15Z',
    started_at: '2026-02-04T17:45:15Z',
    completed_at: '2026-02-04T17:55:35Z',
    mode: 'autonomous',
    diagnosis_type: 'packet_drop',
    network_type: 'vm',
    trigger_source: 'webhook',
    summary: 'VM network drop analysis completed. No packet drops detected. Network path is stable.',
    logs: [
      {
        name: 'sender-host.log',
        content: `[2026-02-04 17:45:15] Starting packet drop detection on sender host
[2026-02-04 17:45:16] BPF tracer initialized (kfree_skb monitoring)
[2026-02-04 17:45:17] Sending test packets (27 flows)
[2026-02-04 17:45:25] Flow 1-27: No drops detected in vnet→phy path
[2026-02-04 17:45:35] Flow 1-27: No drops detected in phy→vnet path
[2026-02-04 17:55:30] Analysis complete. Flows: 27, Drops: 0`,
      },
      {
        name: 'receiver-host.log',
        content: `[2026-02-04 17:45:15] Starting packet drop detection on receiver host
[2026-02-04 17:45:16] BPF tracer initialized (kfree_skb monitoring)
[2026-02-04 17:45:17] Monitoring incoming packets...
[2026-02-04 17:45:25] phy→vnet path: 27/27 packets received (0% loss)
[2026-02-04 17:45:35] VM processing: 27/27 packets processed (0% loss)
[2026-02-04 17:45:45] vnet→phy path: 27/27 replies sent (0% loss)
[2026-02-04 17:55:30] Analysis complete. Packets: 27, Drops: 0`,
      },
    ],
    root_cause: {
      category: 'unknown',
      component: 'None - No drops detected',
      confidence: 0.98,
      evidence: [
        'Total flows analyzed: 27',
        'Drop rate: 0.00%',
        'All measurement points stable',
        'Request and reply paths clean',
      ],
    },
    recommendations: [
      {
        priority: 1,
        action: 'Continue monitoring for anomalies',
        rationale: 'Network is healthy. Establish baseline metrics for future comparison.',
        command: 'ping -c 100 <destination> | grep -o "[0-9]*%"',
      },
      {
        priority: 2,
        action: 'Review latency optimization opportunities',
        rationale: 'While no drops, latency optimization may improve performance.',
      },
    ],
    markdown_report: `# VM Network Drop Analysis Report

**Measurement Directory**: \`measurement-20260204-175437\`
**Analysis Time**: 2026-02-04T17:55:35.139692

## Summary

| Metric | Value |
|--------|-------|
| **Total Drops** | 0 |
| **Drop Rate** | 0.00% |
| **Total Flows** | 27 |
| **Complete Flows** | 0 |

## Pattern Analysis

- **Pattern Type**: none
- **Burst Events**: 0
- **Sporadic Events**: 0
- **Average Interval**: 0.0 ms

## Recommendations

- No drops detected - VM network path is stable`,
  },

  // Completed: System Latency from measurement-20260204-175710
  {
    diagnosis_id: 'diag-20260204-175710-system-latency',
    status: 'completed',
    timestamp: '2026-02-04T17:55:00Z',
    started_at: '2026-02-04T17:50:00Z',
    completed_at: '2026-02-04T17:58:02Z',
    mode: 'autonomous',
    diagnosis_type: 'latency',
    network_type: 'system',
    trigger_source: 'manual',
    summary:
      'System network latency diagnosis completed. Total RTT 227.50 µs is excellent. Primary contributor is Sender Host Internal (45.3%).',
    logs: [
      {
        name: 'sender-tx.log',
        content: `[2026-02-04 17:50:00] Starting system latency measurement (sender TX)
[2026-02-04 17:50:01] BPF probes attached to TCP/IP stack
[2026-02-04 17:50:02] Tracing ip_send_skb and receive paths
[2026-02-04 17:50:10] Sender ReqPath latency: 48.90 us (avg)
[2026-02-04 17:50:20] Sender RepPath latency: 54.10 us (avg)
[2026-02-04 17:58:00] Samples collected: 228, Errors: 0
[2026-02-04 17:58:01] Analysis complete`,
      },
      {
        name: 'receiver-rx.log',
        content: `[2026-02-04 17:50:00] Starting system latency measurement (receiver RX)
[2026-02-04 17:50:01] BPF probes attached to receive path
[2026-02-04 17:50:02] Monitoring netif_receive_skb and icmp_rcv
[2026-02-04 17:50:10] Receiver ReqPath latency: 57.60 us (avg)
[2026-02-04 17:50:15] ICMP echo processing: 9.80 us (avg)
[2026-02-04 17:50:20] Receiver RepPath latency: 31.40 us (avg)
[2026-02-04 17:58:00] Samples collected: 228, Errors: 0
[2026-02-04 17:58:01] Analysis complete`,
      },
    ],
    root_cause: {
      category: 'host_internal',
      component: 'Sender Host Internal Processing',
      confidence: 0.96,
      evidence: [
        'Total RTT: 227.50 µs (0.228 ms)',
        'Sender Host Internal: 103.00 µs (45.3%)',
        'Receiver Host Internal: 98.80 µs (43.4%)',
        'Physical Network: 25.60 µs (11.3%)',
        'Overall latency within excellent range',
      ],
    },
    recommendations: [
      {
        priority: 2,
        action: 'Minor optimization opportunity in Sender kernel processing',
        rationale:
          'Sender host shows slightly higher latency (103us vs receiver 98.8us). Could optimize TX path.',
        command: 'perf record -e cycles,instructions -p <pid> -- sleep 1',
      },
      {
        priority: 3,
        action: 'Continue monitoring physical network latency',
        rationale: 'Physical network is well-tuned at 25.60us. Maintain current configuration.',
      },
    ],
    markdown_report: `# System Network Latency Diagnosis Report

**Measurement Directory**: \`measurement-20260204-175710\`
**Analysis Time**: 2026-02-04T17:58:02.314063

## Summary

| Metric | Value |
|--------|-------|
| **Total RTT** | 227.50 µs (0.228 ms) |
| **Primary Contributor** | Sender Host Internal |
| **Contribution** | 45.3% |
| **Sample Count** | 228 |

## Layer Attribution

| Layer | Latency (µs) | Percentage | Segments |
|-------|-------------|------------|----------|
| Sender Host Internal | 103.00 | 45.3% | A, G |
| Receiver Host Internal | 98.80 | 43.4% | D, E, F |
| Physical Network | 25.60 | 11.3% | C, J |

## Key Findings

### Total Round-Trip Latency
- **Value**: 227.5 µs (Excellent)
- **Status**: All layers well-optimized`,
  },

  // Completed: VM Cross-Node Latency from measurement-20260204-180934
  {
    diagnosis_id: 'diag-20260204-180934-vm-cross-node',
    status: 'completed',
    timestamp: '2026-02-04T18:00:00Z',
    started_at: '2026-02-04T17:55:00Z',
    completed_at: '2026-02-04T18:10:25Z',
    mode: 'autonomous',
    diagnosis_type: 'latency',
    network_type: 'vm',
    trigger_source: 'alert',
    summary:
      'VM Cross-Node latency analysis completed. Total RTT 662.89 µs. Primary bottleneck is Host OVS/Bridge Forwarding (37.4%) with high variance in virtualization TX path.',
    logs: [
      {
        name: 'sender-host.log',
        content: `[2026-02-04 17:55:00] Starting cross-node VM latency measurement (sender)
[2026-02-04 17:55:01] Tracing sender VM kernel stack and OVS forwarding
[2026-02-04 17:55:10] Sender VM TX kernel: 57.34 us (avg, σ=15.23)
[2026-02-04 17:55:15] Sender Host OVS request forward: 49.93 us (avg)
[2026-02-04 17:55:20] Sender Host OVS reply forward: 56.35 us (avg)
[2026-02-04 17:55:25] Sender KVM→vhost transmission: 29.13 us (avg)
[2026-02-04 18:10:20] Samples collected: 26, Errors: 0`,
      },
      {
        name: 'receiver-host.log',
        content: `[2026-02-04 17:55:00] Starting cross-node VM latency measurement (receiver)
[2026-02-04 17:55:01] Tracing receiver host OVS and VM paths
[2026-02-04 17:55:10] Receiver Host OVS request forward: 81.54 us (avg, σ=7.52)
[2026-02-04 17:55:15] Receiver Host OVS reply forward: 60.07 us (avg)
[2026-02-04 17:55:20] Receiver TUN→KVM IRQ injection: 57.46 us (avg)
[2026-02-04 17:55:25] Receiver KVM→vhost transmission: 41.64 us (avg, σ=35.00)
[2026-02-04 18:10:20] Samples collected: 26, Errors: 0`,
      },
      {
        name: 'analysis.log',
        content: `[2026-02-04 18:10:22] Starting VM cross-node latency analysis
[2026-02-04 18:10:23] Processing 26 samples from both hosts
[2026-02-04 18:10:24] Computing segment latencies...
[2026-02-04 18:10:24] Primary Contributor: Host OVS/Bridge Forwarding (247.90 us, 37.4%)
[2026-02-04 18:10:24] Secondary: VM Internal Kernel Stack (203.38 us, 30.7%)
[2026-02-04 18:10:24] Note: High variance detected in I_1 segment (CV=84.1%)
[2026-02-04 18:10:25] Report generated successfully`,
      },
    ],
    root_cause: {
      category: 'vhost_processing',
      component: 'Host OVS/Bridge Forwarding & Virtualization TX Path',
      confidence: 0.88,
      evidence: [
        'Host OVS/Bridge Forwarding: 247.90 µs (37.4%)',
        'VM Internal Kernel Stack: 203.38 µs (30.7%)',
        'High variance in I_1 segment (Receiver KVM→TUN): CV=84.1%',
        'Cross-node communication adds 49.12 µs physical latency',
      ],
    },
    recommendations: [
      {
        priority: 1,
        action: 'Investigate high variance in vhost TX path (I_1 segment)',
        rationale: 'I_1 shows 84.1% coefficient of variation. May indicate CPU scheduling issues.',
        command: 'perf record -e context-switches -p <vhost-pid> -- sleep 5',
      },
      {
        priority: 2,
        action: 'Optimize OVS flow caching for cross-node traffic',
        rationale:
          'OVS forwarding contributes 37.4%. Cache optimization can reduce latency variance.',
        command: 'ovs-vsctl -- set Open_vSwitch . other_config:cmesg-level=dbg',
      },
      {
        priority: 3,
        action: 'Profile VM kernel stack for bottlenecks',
        rationale: 'VM internal kernel contributes 30.7%. Profile RX/TX paths.',
        command: 'netperf -t TCP_RR -H <peer> -- -r 1024,1024',
      },
    ],
    markdown_report: `# VM Cross-Node ICMP Latency Diagnosis Report

**Measurement Directory**: \`measurement-20260204-180934\`
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

## Key Findings

### Primary Latency Contributor
- **Layer**: Host OVS/Bridge Forwarding
- **Latency**: 247.90 µs (37.4%)
- **Segments**: B, D, I, K

### Segments with Highest Variance
- **I_1**: CV=84.1%, Avg=41.64µs, StdDev=35.00µs
- **F**: CV=50.6%, Avg=47.40µs, StdDev=23.98µs`,
  },

  // Running: New diagnosis task
  {
    diagnosis_id: 'diag-20260205-120000-new-latency',
    status: 'running',
    timestamp: '2026-02-05T12:00:00Z',
    started_at: '2026-02-05T12:00:00Z',
    mode: 'autonomous',
    diagnosis_type: 'latency',
    network_type: 'vm',
    trigger_source: 'webhook',
    summary: 'Measuring VM network latency between host-01 and host-02...',
  },

  // Pending: Queued diagnosis
  {
    diagnosis_id: 'diag-20260205-120100-pending-drops',
    status: 'pending',
    timestamp: '2026-02-05T12:01:00Z',
    mode: 'interactive',
    diagnosis_type: 'packet_drop',
    network_type: 'system',
    trigger_source: 'manual',
    summary: 'Queued for analysis: System packet drop detection',
  },

  // Waiting: Interactive mode diagnosis
  {
    diagnosis_id: 'diag-20260205-115900-interactive',
    status: 'waiting',
    timestamp: '2026-02-05T11:59:00Z',
    started_at: '2026-02-05T11:59:00Z',
    mode: 'interactive',
    diagnosis_type: 'connectivity',
    network_type: 'vm',
    trigger_source: 'alert',
    summary: 'Waiting for user input to proceed with advanced analysis options',
  },

  // Error: Failed diagnosis
  {
    diagnosis_id: 'diag-20260205-110000-failed',
    status: 'error',
    timestamp: '2026-02-05T11:00:00Z',
    started_at: '2026-02-05T10:55:00Z',
    completed_at: '2026-02-05T11:05:00Z',
    mode: 'autonomous',
    diagnosis_type: 'latency',
    network_type: 'system',
    trigger_source: 'webhook',
    summary: 'Connection failed during measurement',
    error:
      'Unable to establish SSH connection to receiver host. Verify network connectivity and SSH credentials.',
  },
]

/**
 * Get mock diagnosis by ID
 */
export function getMockDiagnosis(id: string): DiagnosisResponse | undefined {
  return mockDiagnoses.find((d) => d.diagnosis_id === id)
}

/**
 * Get mock diagnoses with filtering
 */
export function getMockDiagnosesList(options?: {
  limit?: number
  offset?: number
  status?: string
}): DiagnosisResponse[] {
  let results = [...mockDiagnoses]

  // Filter by status
  if (options?.status) {
    results = results.filter((d) => d.status === options.status)
  }

  // Apply offset and limit
  const offset = options?.offset || 0
  const limit = options?.limit || 50
  return results.slice(offset, offset + limit)
}
