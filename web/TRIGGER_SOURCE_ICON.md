# 任务触发源图标功能

## 功能描述

在任务列表中，每个任务名称前显示一个图标，标注该任务的触发源。用户可以通过图标和颜色快速识别任务来自哪里。

## 图标设计

| 触发源 | 图标 | 颜色 | 说明 |
|--------|------|------|------|
| Manual | ✋ Hand | 蓝色 (#2563eb) | 用户手动创建的诊断任务 |
| Webhook | 🔗 Webhook | 绿色 (#16a34a) | 外部系统通过webhook API触发 |
| Alert | 🔔 Bell | 橙色 (#ea580c) | 监控告警系统自动触发 |

## 实现细节

### 1. 类型定义

**文件**: `src/types/index.ts`

```typescript
export interface DiagnosisResponse {
  // ... 其他字段
  trigger_source?: 'manual' | 'webhook' | 'alert'
}
```

### 2. 模拟数据

**文件**: `src/lib/mockData.ts`

为所有8个诊断数据添加 `trigger_source` 字段：

```typescript
{
  diagnosis_id: 'diag-20260204-175008-vm-latency',
  trigger_source: 'manual',
  // ... 其他字段
}
```

#### 分布

- **Manual (手动)**: 4 个诊断
  - diag-20260204-175008-vm-latency
  - diag-20260204-175710-system-latency
  - diag-20260205-120100-pending-drops

- **Webhook**: 3 个诊断
  - diag-20260204-175437-vm-drops
  - diag-20260205-120000-new-latency
  - diag-20260205-110000-failed

- **Alert**: 2 个诊断
  - diag-20260204-180934-vm-cross-node
  - diag-20260205-115900-interactive

### 3. 页面实现

**文件**: `src/pages/TasksPage.tsx`

#### 导入图标

```typescript
import { Hand, Webhook, Bell } from 'lucide-react'
```

#### getTriggerIcon() 函数

```typescript
const getTriggerIcon = (source?: string) => {
  switch (source) {
    case 'manual':
      return {
        Icon: Hand,
        color: 'text-blue-600',
        title: 'Manual Trigger',
      }
    case 'webhook':
      return {
        Icon: Webhook,
        color: 'text-green-600',
        title: 'Webhook Trigger',
      }
    case 'alert':
      return {
        Icon: Bell,
        color: 'text-orange-600',
        title: 'Alert Trigger',
      }
    default:
      return {
        Icon: Hand,
        color: 'text-gray-600',
        title: 'Unknown Trigger',
      }
  }
}
```

#### HTML 实现

在表格的 "Name/ID" 列中显示图标：

```typescript
<td className="px-6 py-4">
  <div className="flex items-center gap-2">
    {(() => {
      const { Icon, color, title } = getTriggerIcon(task.trigger_source)
      return (
        <div title={title}>
          <Icon className={`h-4 w-4 ${color} flex-shrink-0`} />
        </div>
      )
    })()}
    <Link to={`/tasks/${task.diagnosis_id}`}>
      {task.diagnosis_id}
    </Link>
  </div>
</td>
```

## UI 展示

### 任务列表表格

```
┌──────────────────────────────────────┬────────────────────┬────────────┐
│ Name/ID                              │ Type               │ Status     │
├──────────────────────────────────────┼────────────────────┼────────────┤
│ ✋ diag-20260204-175008-vm-latency    │ Latency (VM)       │ ✅ Done    │
│ 🔗 diag-20260204-175437-vm-drops     │ Packet Drop (VM)   │ ✅ Done    │
│ ✋ diag-20260204-175710-system-lat    │ Latency (SYSTEM)   │ ✅ Done    │
│ 🔔 diag-20260204-180934-vm-cross     │ Latency (VM)       │ ✅ Done    │
└──────────────────────────────────────┴────────────────────┴────────────┘
```

### 鼠标悬停 Tooltip

鼠标悬停在图标上会显示完整的触发源说明：
- "Manual Trigger"
- "Webhook Trigger"
- "Alert Trigger"

## 样式特性

- **紧凑**: 图标小而精致 (4x4 单位)
- **易读**: 不同颜色便于快速识别
- **一致**: 颜色与 Tailwind 调色板一致
- **响应式**: 在各种屏幕尺寸下表现良好
- **无障碍**: 包含 title 属性用于 Tooltip

## 使用场景

### 手动触发 (Manual)

**何时使用**:
- 运维人员主动创建诊断任务
- 排查特定问题
- 测试新配置

**特点**:
- 诊断细节由用户控制
- 灵活的参数设置
- 适合一次性诊断

### Webhook 触发

**何时使用**:
- 外部系统集成
- CI/CD 管道自动化
- 第三方工具调用

**特点**:
- 自动化工作流
- 可集成现有系统
- 适合批量诊断

### 告警触发

**何时使用**:
- 监控系统检测异常
- 自动故障响应
- 性能指标下降

**特点**:
- 快速反应
- 自动化处理
- 最少人工干预

## 扩展性

### 添加新触发源

要添加新的触发源：

1. 更新 `types/index.ts`:
```typescript
trigger_source?: 'manual' | 'webhook' | 'alert' | 'scheduled'
```

2. 在 `getTriggerIcon()` 中添加新分支:
```typescript
case 'scheduled':
  return {
    Icon: Clock,
    color: 'text-purple-600',
    title: 'Scheduled Trigger',
  }
```

3. 导入对应的图标:
```typescript
import { Clock } from 'lucide-react'
```

## 性能

- **图标库**: Lucide React (轻量级, ~1KB)
- **渲染性能**: 原生 React 条件渲染
- **无额外请求**: 所有资源本地加载

## 验证

✅ TypeScript 编译通过 (0 errors)
✅ 所有模拟数据完整
✅ 图标正确显示
✅ 颜色一致
✅ Tooltip 工作正常

## 相关文件

- `src/types/index.ts` - 类型定义
- `src/lib/mockData.ts` - 模拟数据
- `src/pages/TasksPage.tsx` - 页面实现
- `TASK_TYPE_FIX.md` - 任务类型功能文档
