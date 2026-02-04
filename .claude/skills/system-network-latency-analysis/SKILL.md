---
name: system-network-latency-analysis
description: |
  Analyze system network (host-to-host) ICMP latency by parsing dual-host
  measurement logs, calculating derived segments, and building attribution tables.
  Outputs diagnosis report in Markdown format.

  Trigger keywords: system network analysis, host latency analysis,
  analyze system measurement, 系统网络分析, 主机延迟分析

allowed-tools: Read, Bash
---

# System Network Latency Analysis Skill

## 执行

```bash
python3 .claude/skills/system-network-latency-analysis/scripts/generate_report.py <measurement_dir>
```

脚本功能：
1. 解析 sender-host.log (TX mode) 和 receiver-host.log (RX mode)
2. 构建端到端数据路径模型
3. 计算各分段延迟和层级归因
4. 生成 Markdown 报告到 `<measurement_dir>/diagnosis_report.md`
5. 输出 JSON 结果

## 输入参数

| 参数 | 说明 |
|------|------|
| `measurement_dir` | 测量目录路径，包含 sender-host.log 和 receiver-host.log |

## 输出

脚本输出 JSON 格式：

```json
{
  "report_path": "measurement-xxx/diagnosis_report.md",
  "markdown_report": "# System Network Latency Diagnosis Report\n...",
  "detailed_report": {
    "summary": { "total_rtt_us": 248.7, "primary_contributor": "network", ... },
    "segments": { ... },
    "layer_attribution": { ... },
    "validation": { ... },
    "findings": [ ... ],
    "data_path_diagram": "..."
  }
}
```

## 报告文件

生成的 `diagnosis_report.md` 包含：

1. **Summary** - Total RTT, Primary Contributor, Sample Count
2. **Layer Attribution** - 3 层归因表 (Sender/Receiver/Network)
3. **Segment Breakdown** - 各分段的详细统计
4. **Data Path Diagram** - ASCII 数据流图 (含双端视角)
5. **Drop Statistics** - 丢包统计 (如有)
6. **Key Findings** - 分析结论
7. **Validation** - 数据一致性检查

## 数据路径模型

详见 data-path-model.md
