---
name: vm-network-latency-analysis
description: |
  Analyze VM network (cross-node) ICMP latency by parsing dual-host measurement logs
  from vm-network-path-tracer, calculating derived segments including physical network
  latency, and building attribution tables. Outputs diagnosis report in Markdown format.

  Note: This skill analyzes vm-network-path-tracer output (2 hosts, vnet↔phy boundary).
  For detailed 8-point measurement analysis, use vm-latency-analysis skill.

  Trigger keywords: vm network latency, vm boundary latency, analyze vm measurement,
  vm ovs latency, VM网络延迟分析, 虚拟机延迟分析

allowed-tools: Read, Bash
---

# VM Network Latency Analysis Skill

## 执行

```bash
python3 .claude/skills/vm-network-latency-analysis/scripts/analyze_latency.py <measurement_dir>
```

## 输入

| 参数 | 说明 |
|------|------|
| `measurement_dir` | 测量目录，包含 sender-host.log 和 receiver-host.log |

## 输出

```json
{
  "report_path": "measurement-xxx/latency_report.md",
  "markdown_report": "# VM Network Latency Analysis Report\n...",
  "detailed_report": {
    "summary": { "total_rtt_us": 396.5, "primary_contributor": "receiver_vm", ... },
    "segments": { ... },
    "layer_attribution": { ... }
  }
}
```

## 报告内容

1. **Summary** - Total RTT, Primary Contributor
2. **Layer Attribution** - 4 层归因 (Sender OVS / Physical Network / Receiver OVS / Receiver VM)
3. **Segment Breakdown** - 各分段详细统计
4. **Data Path Diagram** - ASCII 数据流图
5. **Key Findings** - 分析结论

## 数据模型

```
Sender Host                 Physical Network              Receiver Host
┌─────────────────┐         ┌───────────┐         ┌─────────────────┐
│ S.ReqInternal   │────────→│ Wire(Req) │────────→│ R.ReqInternal   │
│ (vnet→phy)      │         │           │         │ (phy→vnet)      │
│                 │         │           │         │      ↓          │
│                 │         │           │         │ R.External      │
│                 │         │           │         │ (VM + Virt)     │
│                 │         │           │         │      ↓          │
│ S.RepInternal   │←────────│ Wire(Rep) │←────────│ R.RepInternal   │
│ (phy→vnet)      │         │           │         │ (vnet→phy)      │
└─────────────────┘         └───────────┘         └─────────────────┘

Physical Network = S.External - R.Total
Unmeasured: Sender VM internal + Sender Virtualization
```

## 与其他 skill 的关系

- 测量: `vm-network-path-tracer` (2 hosts, vnet↔phy boundary)
- 详细测量: `vm-latency-measurement` (8 points, 14 segments)
- 丢包分析: `vm-network-drop-analysis`
