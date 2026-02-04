---
name: system-network-drop-analysis
description: |
  Analyze system network (host-to-host) packet drop events by parsing dual-host
  measurement logs, extracting per-drop details, computing location attribution,
  and generating diagnostic reports in Markdown format.

  Trigger keywords: system drop analysis, host drop analysis, packet drop report,
  analyze system drops, 系统丢包分析, 主机丢包分析

allowed-tools: Read, Bash
---

# System Network Drop Analysis Skill

## 执行

```bash
python3 .claude/skills/system-network-drop-analysis/scripts/analyze_drops.py <measurement_dir>
```

## 输入参数

| 参数 | 说明 |
|------|------|
| `measurement_dir` | 测量目录路径，包含 sender-host.log 和 receiver-host.log |

## 输出

脚本输出 JSON 格式：

```json
{
  "report_path": "measurement-xxx/drop_report.md",
  "markdown_report": "# System Network Drop Analysis Report\n...",
  "detailed_report": {
    "summary": { "total_drops": 2, "drop_rate": 0.008, ... },
    "drop_events": [ ... ],
    "location_attribution": { ... },
    "pattern_analysis": { ... }
  }
}
```

## 报告内容

1. **Summary** - 丢包总数、丢包率、测量时长
2. **Drop Location Attribution** - 丢包位置归因 (Sender/Receiver/Network)
3. **Drop Timeline** - 丢包事件时间线
4. **Pattern Analysis** - 丢包模式 (突发/偶发)
5. **Recommendations** - 诊断建议

## 与延迟分析的关系

- 测量数据: 复用 `system-network-path-tracer` 输出
- 延迟分析: 使用 `system-network-latency-analysis`
- 丢包分析: 使用本 skill (职责分离)
