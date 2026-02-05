# 任务名称格式化

## 功能描述

将冗长的诊断ID自动转换为简洁的 `measurement-*` 格式显示，提高任务列表的可读性。

## 格式转换

### 转换规则

```
Input:  diag-YYYYMMDD-HHMMSS-description
Output: measurement-YYYYMMDD-HHMMSS
```

### 转换示例

| 原始诊断ID | 显示格式 |
|-----------|---------|
| diag-20260204-175008-vm-latency | measurement-20260204-175008 |
| diag-20260204-175437-vm-drops | measurement-20260204-175437 |
| diag-20260204-175710-system-latency | measurement-20260204-175710 |
| diag-20260204-180934-vm-cross-node | measurement-20260204-180934 |
| diag-20260205-120000-new-latency | measurement-20260205-120000 |
| diag-20260205-120100-pending-drops | measurement-20260205-120100 |
| diag-20260205-115900-interactive | measurement-20260205-115900 |
| diag-20260205-110000-failed | measurement-20260205-110000 |

## 实现细节

### 1. formatTaskName() 函数

**文件**: `src/lib/utils.ts`

```typescript
export function formatTaskName(diagnosisId: string): string {
  // Extract the date and time parts from diagnosis_id
  // Format: diag-YYYYMMDD-HHMMSS-description
  const parts = diagnosisId.split('-')

  if (parts.length >= 3 && parts[0] === 'diag') {
    // Get date (YYYYMMDD) and time (HHMMSS)
    const date = parts[1] // e.g., 20260204
    const time = parts[2] // e.g., 175008

    // Return in format: measurement-YYYYMMDD-HHMMSS
    return `measurement-${date}-${time}`
  }

  // Fallback to original ID if format doesn't match
  return diagnosisId
}
```

### 2. 在页面中使用

**文件**: `src/pages/TasksPage.tsx`

```typescript
// 导入函数
import { formatTaskName } from '@/lib/utils'

// 在任务列表中使用
<Link
  to={`/tasks/${task.diagnosis_id}`}
  title={task.diagnosis_id}
>
  {formatTaskName(task.diagnosis_id)}
</Link>
```

## 用户体验

### 之前

```
任务列表显示: diag-20260204-175008-vm-latency
问题:
  • 行过长，超出表格边界
  • 诊断类型信息冗余
  • 难以快速扫描
```

### 现在

```
任务列表显示: measurement-20260204-175008
优点:
  • 简洁紧凑
  • 保留核心信息 (日期、时间)
  • 易于快速识别
  • 鼠标悬停显示完整ID
```

## 显示效果

### 任务列表表格

| Icon | Name/ID | Type | Status |
|------|---------|------|--------|
| ✋ | measurement-20260204-175008 | Latency (VM) | ✅ Done |
| 🔗 | measurement-20260204-175437 | Packet Drop (VM) | ✅ Done |
| ✋ | measurement-20260204-175710 | Latency (SYSTEM) | ✅ Done |
| 🔔 | measurement-20260204-180934 | Latency (VM) | ✅ Done |

### Tooltip 信息

当用户鼠标悬停在任务名称上时，显示完整的诊断ID：

```
Hover: measurement-20260204-175008
↓
Title: diag-20260204-175008-vm-latency
```

## 格式说明

### measurement-YYYYMMDD-HHMMSS

| 部分 | 说明 | 示例 |
|------|------|------|
| measurement | 类型标记 | measurement |
| YYYY | 年 | 2026 |
| MM | 月 | 02 |
| DD | 日 | 04 |
| HH | 小时 (24小时制) | 17 |
| MM | 分钟 | 50 |
| SS | 秒 | 08 |

## 特性

✅ **自动格式化** - 无需手动配置
✅ **保留完整信息** - Tooltip 显示原始ID
✅ **容错处理** - 不匹配格式时使用原始ID
✅ **零性能影响** - 字符串处理在客户端
✅ **易于维护** - 独立函数，易于修改

## 扩展性

### 修改格式

如需修改输出格式，只需修改 `formatTaskName()` 函数：

```typescript
// 例如：仅显示日期
export function formatTaskName(diagnosisId: string): string {
  const parts = diagnosisId.split('-')
  if (parts.length >= 2 && parts[0] === 'diag') {
    return `task-${parts[1]}`  // 输出: task-20260204
  }
  return diagnosisId
}
```

## 验证

✅ TypeScript 编译通过 (0 errors)
✅ 函数逻辑正确
✅ 格式转换准确
✅ Tooltip 显示原始ID
✅ 链接导航正常

## 相关文件

- `src/lib/utils.ts` - formatTaskName() 函数定义
- `src/pages/TasksPage.tsx` - 页面实现
- `TASK_TYPE_FIX.md` - 任务类型功能
- `TRIGGER_SOURCE_ICON.md` - 触发源图标功能
