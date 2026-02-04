---
name: vm-network-drop-analysis
description: |
  Analyze VM network (cross-node) packet drop events by parsing dual-host
  measurement logs from vm-network-path-tracer, extracting per-drop details,
  computing location attribution, and generating diagnostic reports in Markdown format.

  Note: This skill analyzes vm-network-path-tracer output (2 hosts, vnet↔phy boundary).
  For system network drop analysis, use system-network-drop-analysis skill.

  Trigger keywords: vm drop analysis, vm packet drop, analyze vm drops,
  vm network drop report, VM丢包分析, 虚拟机丢包分析

allowed-tools: Read, Bash
---

# VM Network Drop Analysis Skill

## 执行

```bash
python3 .claude/skills/vm-network-drop-analysis/scripts/analyze_drops.py <measurement_dir>
```

## 输入

| 参数 | 说明 |
|------|------|
| `measurement_dir` | 测量目录，包含 sender-host.log 和 receiver-host.log |

## 输出

```json
{
  "report_path": "measurement-xxx/vm_drop_report.md",
  "markdown_report": "# VM Network Drop Analysis Report\n...",
  "detailed_report": {
    "summary": { "total_drops": 5, "drop_rate": 2.5, ... },
    "drops_by_location": { "sender_host": 2, "receiver_host": 3, ... },
    "drop_events": [ ... ]
  }
}
```

## 报告内容

1. **Summary** - Total Drops, Drop Rate, Flow Counts
2. **Drop Location Attribution** - 丢包位置归因
3. **Drop Breakdown by Type** - 各类型丢包计数
4. **Pattern Analysis** - 丢包模式 (burst/sporadic)
5. **Drop Event Timeline** - 丢包事件时间线
6. **Recommendations** - 诊断建议

## 丢包类型

### Sender Host (vnet→phy 边界)

| 丢包类型 | 阶段 | 含义 |
|----------|------|------|
| drop_0_1 (req_internal) | ReqInternal | 请求在 vnet→phy 路径被丢弃 |
| drop_2_3 (rep_internal) | RepInternal | 回复在 phy→vnet 路径被丢弃 |

### Receiver Host (phy→vnet→phy 边界)

| 丢包类型 | 阶段 | 含义 |
|----------|------|------|
| drop_0_1 (req_internal) | ReqInternal | 请求在 phy→vnet 路径被丢弃 |
| drop_1_2 (external) | External | VM 未生成回复 (ping timeout) |
| drop_2_3 (rep_internal) | RepInternal | 回复在 vnet→phy 路径被丢弃 |

## 数据模型

```
Sender Host                 Physical Network              Receiver Host
┌─────────────────┐         ┌───────────┐         ┌─────────────────┐
│ S.ReqInternal   │────────→│ Wire(Req) │────────→│ R.ReqInternal   │
│ (vnet→phy)      │  DROP?  │           │  DROP?  │ (phy→vnet)      │
│                 │         │           │         │      ↓          │
│                 │         │           │         │ R.External      │
│                 │         │           │         │ (VM + Virt)     │
│                 │         │           │         │      ↓    DROP? │
│ S.RepInternal   │←────────│ Wire(Rep) │←────────│ R.RepInternal   │
│ (phy→vnet)      │  DROP?  │           │  DROP?  │ (vnet→phy)      │
└─────────────────┘         └───────────┘         └─────────────────┘

Drop Attribution:
- Sender drop_0_1: Sender Host OVS issue
- Sender drop_2_3: Sender Host OVS issue (reply path)
- Receiver drop_0_1: Receiver Host OVS issue
- Receiver drop_1_2: Receiver VM issue (not responding)
- Receiver drop_2_3: Receiver Host OVS issue (reply path)
- Physical Network drop: Inferred when both hosts see partial flow
```

## 与其他 skill 的关系

- 测量: `vm-network-path-tracer` (2 hosts, vnet↔phy boundary)
- 延迟分析: `vm-network-latency-analysis`
- 系统丢包分析: `system-network-drop-analysis`
