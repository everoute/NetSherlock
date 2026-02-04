# VM Network Drop Analysis Report

**Measurement Directory**: `measurement-20260204-182308`
**Analysis Time**: 2026-02-04T18:24:09.911149

## Summary

| Metric | Value |
|--------|-------|
| **Total Drops** | 0 |
| **Drop Rate** | 0.00% |
| **Total Flows** | 30 |
| **Complete Flows** | 26 |

## Drop Breakdown by Type

### Sender Host

| Drop Type | Count | Description |
|-----------|-------|-------------|
| drop_0_1 | 0 | vnet→phy (request path) |
| drop_2_3 | 0 | phy→vnet (reply path) |

### Receiver Host

| Drop Type | Count | Description |
|-----------|-------|-------------|
| drop_0_1 | 0 | phy→vnet (request path) |
| drop_1_2 | 0 | VM no reply |
| drop_2_3 | 0 | vnet→phy (reply path) |

## Pattern Analysis

- **Pattern Type**: none
- **Burst Events**: 0
- **Sporadic Events**: 0
- **Average Interval**: 0.0 ms

## Recommendations

- No drops detected - VM network path is stable
