# 任务类型显示修复

## 问题描述

任务列表页面中的"Type"列始终显示 "Unknown"，而不显示实际的诊断类型。

## 根本原因

`TasksPage.tsx` 中的 `getTaskType()` 函数基于诊断ID前缀判断类型：
- `alert-` → "Alert"
- `manual-` → "Manual"
- 其他 → "Unknown"

模拟数据中所有诊断ID都使用 `diag-` 前缀，因此都返回 "Unknown"。

## 解决方案

### 1. 扩展类型定义

**文件**: `src/types/index.ts`

添加两个字段到 `DiagnosisResponse` 接口：

```typescript
diagnosis_type?: 'latency' | 'packet_drop' | 'connectivity'
network_type?: 'vm' | 'system'
```

### 2. 更新模拟数据

**文件**: `src/lib/mockData.ts`

为所有8个诊断数据添加诊断类型和网络类型：

```typescript
{
  diagnosis_id: 'diag-20260204-175008-vm-latency',
  diagnosis_type: 'latency',
  network_type: 'vm',
  // ... 其他字段
}
```

#### 诊断类型映射

| 诊断 | 类型 | 网络 | 显示 |
|------|------|------|------|
| VM 延迟分析 | latency | vm | Latency (VM) |
| VM 丢包检测 | packet_drop | vm | Packet Drop (VM) |
| 系统延迟分析 | latency | system | Latency (SYSTEM) |
| 跨节点延迟 | latency | vm | Latency (VM) |
| 新建延迟测试 | latency | vm | Latency (VM) |
| 待处理丢包检测 | packet_drop | system | Packet Drop (SYSTEM) |
| 交互式连通性 | connectivity | vm | Connectivity (VM) |
| 失败诊断 | latency | system | Latency (SYSTEM) |

### 3. 更新显示逻辑

**文件**: `src/pages/TasksPage.tsx`

将 `getTaskType()` 函数从基于ID前缀改为使用实际诊断类型：

```typescript
// 之前
const getTaskType = (id: string) => {
  if (id.startsWith('alert-')) return 'Alert'
  if (id.startsWith('manual-')) return 'Manual'
  return 'Unknown'
}

// 现在
const getTaskType = (task: DiagnosisResponse) => {
  const typeLabel = task.diagnosis_type
    ? task.diagnosis_type.charAt(0).toUpperCase() +
      task.diagnosis_type.slice(1).replace('_', ' ')
    : 'Unknown'

  const networkLabel = task.network_type
    ? ` (${task.network_type.toUpperCase()})`
    : ''

  return `${typeLabel}${networkLabel}`
}
```

同时更新调用位置：

```typescript
// 之前
{getTaskType(task.diagnosis_id)}

// 现在
{getTaskType(task)}
```

还更新了样式（从灰色改为蓝色）：

```typescript
className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
```

## 显示效果

### 任务列表示例

| Name/ID | Type | Status | Started |
|---------|------|--------|---------|
| diag-20260204-175008-vm-latency | Latency (VM) | ✅ Completed | 2 hours ago |
| diag-20260204-175437-vm-drops | Packet Drop (VM) | ✅ Completed | 2 hours ago |
| diag-20260204-175710-system-latency | Latency (SYSTEM) | ✅ Completed | 1 hour ago |
| diag-20260205-120000-new-latency | Latency (VM) | 🔄 Running | just now |
| diag-20260205-120100-pending-drops | Packet Drop (SYSTEM) | ⏳ Pending | just now |

## 诊断类型说明

### Latency (延迟)
- 测量网络延迟
- 用于性能分析
- 可应用于 VM 或系统网络

### Packet Drop (丢包)
- 检测数据包丢失
- 用于网络可靠性分析
- 可应用于 VM 或系统网络

### Connectivity (连通性)
- 测试网络连通性
- 用于诊断连接问题
- 通常用于交互模式

## 网络类型说明

### VM (虚拟机)
- 虚拟机间通信
- 跨虚拟机的网络诊断
- 考虑虚拟化层开销

### SYSTEM (系统)
- 物理主机间通信
- 纯系统层面诊断
- 不涉及虚拟化层

## 验证

✅ TypeScript 编译通过 (0 errors)
✅ 所有模拟数据完整
✅ 类型定义正确
✅ 显示逻辑正确
✅ 样式美观

## 后续改进

可选的增强功能：
- 添加诊断类型的颜色编码
- 添加网络类型的图标
- 按类型过滤任务列表
- 添加诊断类型的图例
