---
name: vm-latency-analysis
description: |
  Analyze cross-node VM ICMP ping latency by parsing measurement logs,
  calculating derived segments, and building attribution tables.
  Outputs diagnosis report in Markdown format.

  Trigger keywords: analyzing latency logs, latency breakdown, compare latency,
  analyze measurement data, 延迟分析, 延迟分解, 延迟归因, ICMP RTT analysis

allowed-tools: Read, Bash
---

# VM Latency Analysis Skill

## 执行

```bash
python3 .claude/skills/vm-latency-analysis/scripts/generate_report.py <measurement_dir>
```

脚本功能：
1. 解析 8 个测量日志文件
2. 计算 14 个分段的统计数据
3. 生成层级归因分析
4. 保存 Markdown 报告到 `<measurement_dir>/diagnosis_report.md`
5. 输出 JSON 结果

## 输入参数

| 参数 | 说明 |
|------|------|
| `measurement_dir` | 测量目录路径，包含 8 个日志文件 |

## 输出

脚本输出 JSON 格式：

```json
{
  "report_path": "measurement-xxx/diagnosis_report.md",
  "markdown_report": "# VM Cross-Node ICMP Latency Diagnosis Report\n...",
  "detailed_report": {
    "summary": { "total_rtt_us": 632.11, "primary_contributor": "host_ovs", ... },
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
2. **Layer Attribution** - 5 层归因表 (按贡献比例排序)
3. **Segment Breakdown** - 14 个分段的详细统计
4. **Data Path Diagram** - ASCII 数据流图
5. **Key Findings** - 分析结论
6. **Validation** - 数据一致性检查

## 调用示例

```bash
python3 .claude/skills/vm-latency-analysis/scripts/generate_report.py measurement-20260126-140444
```
