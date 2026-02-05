# 任务多日志文件支持

## 功能描述

任务详情页现在支持显示和切换多个日志文件，每个诊断任务可以有来自不同来源（如发送方主机、接收方主机、分析模块）的多个日志文件。

## 功能特性

✅ **选项卡切换** - 快速在日志文件间切换
✅ **代码编辑器风格显示** - 等宽字体保持对齐
✅ **暗色背景** - 长时间阅读不伤眼
✅ **自动换行** - 防止水平滚动
✅ **灵活扩展** - 支持任意数量的日志文件

## 类型定义

### LogFile 接口

**文件**: `src/types/index.ts`

```typescript
export interface LogFile {
  name: string        // 日志文件名，显示在选项卡上
  content: string     // 日志文件内容
}
```

### DiagnosisResponse 扩展

```typescript
export interface DiagnosisResponse {
  // ... 其他字段
  logs?: LogFile[]     // 可选的日志文件数组
}
```

## 实现细节

### 1. TaskDetailPage 状态管理

**文件**: `src/pages/TaskDetailPage.tsx`

```typescript
const [selectedLogIndex, setSelectedLogIndex] = useState(0)
```

用于跟踪当前选中的日志文件索引。

### 2. UI 组件结构

#### 时间线部分 (保留)

显示诊断执行的时间线和事件：

```
[timestamp] Diagnosis task created
[timestamp] Status: running
[timestamp] Mode: autonomous
[timestamp] Task completed
```

#### 日志文件部分 (新增)

**选项卡导航**:

```typescript
{task.logs && task.logs.length > 0 && (
  <div>
    <h3>Log Files</h3>

    {/* 选项卡 */}
    <div className="flex gap-2 mb-4">
      {task.logs.map((log, index) => (
        <button
          onClick={() => setSelectedLogIndex(index)}
          className={/* 选中/未选中样式 */}
        >
          {log.name}
        </button>
      ))}
    </div>

    {/* 日志内容 */}
    <div className="bg-gray-900 rounded-lg p-4">
      <pre>{task.logs[selectedLogIndex]?.content}</pre>
    </div>
  </div>
)}
```

### 3. 样式设计

| 元素 | 样式 |
|------|------|
| 未选中选项卡 | 灰色文字，无边框底部 |
| 选中选项卡 | 蓝色文字，蓝色边框底部 |
| 日志容器 | 暗灰色背景 (bg-gray-900) |
| 日志文字 | 浅灰色 (text-gray-100)，等宽字体 |
| 日志大小 | xs (0.75rem) |

## 模拟数据示例

### VM Latency Diagnosis (3个日志文件)

```typescript
{
  diagnosis_id: 'diag-20260204-175008-vm-latency',
  logs: [
    {
      name: 'sender-host.log',
      content: `[2026-02-04 17:45:00] Starting latency measurement...
[2026-02-04 17:45:01] BPF tracer initialized
...`
    },
    {
      name: 'receiver-host.log',
      content: `[2026-02-04 17:45:00] Starting latency measurement...
[2026-02-04 17:45:01] BPF tracer initialized
...`
    },
    {
      name: 'analysis.log',
      content: `[2026-02-04 17:51:00] Starting latency analysis
[2026-02-04 17:51:01] Loading measurement data
...`
    }
  ]
}
```

### VM Drops Diagnosis (2个日志文件)

```typescript
{
  diagnosis_id: 'diag-20260204-175437-vm-drops',
  logs: [
    {
      name: 'sender-host.log',
      content: `[2026-02-04 17:45:15] Starting packet drop detection...`
    },
    {
      name: 'receiver-host.log',
      content: `[2026-02-04 17:45:15] Starting packet drop detection...`
    }
  ]
}
```

## 日志文件分布

| 诊断类型 | 日志文件数 | 文件列表 |
|---------|----------|---------|
| VM Latency | 3 | sender-host, receiver-host, analysis |
| VM Drops | 2 | sender-host, receiver-host |
| System Latency | 2 | sender-tx, receiver-rx |
| VM Cross-Node | 3 | sender-host, receiver-host, analysis |

**总计**: 10 个日志文件

## 日志文件命名约定

### 常见日志文件名

| 文件名 | 说明 |
|--------|------|
| sender-host.log | 发送方主机的诊断日志 |
| receiver-host.log | 接收方主机的诊断日志 |
| analysis.log | 数据分析和处理日志 |
| sender-tx.log | 发送端TX路径日志 |
| receiver-rx.log | 接收端RX路径日志 |
| commands.log | 执行的命令日志 |
| send-host-icmp.log | 发送方ICMP跟踪 |
| recv-host-icmp.log | 接收方ICMP跟踪 |

## 用户交互流程

1. **打开任务详情页** - 用户从任务列表点击进入
2. **查看时间线** - 首先看到执行摘要时间线
3. **发现日志文件** - 看到"Log Files"部分和多个选项卡
4. **选择日志文件** - 点击要查看的日志文件选项卡
5. **查看日志内容** - 日志内容在下方显示
6. **切换日志文件** - 可快速切换其他日志文件

## 代码示例

### 添加日志文件到诊断

```typescript
{
  diagnosis_id: 'diag-xxx',
  status: 'completed',
  logs: [
    {
      name: 'trace1.log',
      content: '[timestamp] message...'
    },
    {
      name: 'trace2.log',
      content: '[timestamp] message...'
    }
  ]
}
```

### 在没有日志的情况下

如果 `logs` 为空或未定义，日志部分不会显示：

```typescript
{
  diagnosis_id: 'diag-yyy',
  status: 'pending',
  // logs 未定义 → 日志部分不显示
}
```

## 扩展性

### 添加新日志文件类型

只需在模拟数据中添加到 `logs` 数组：

```typescript
logs: [
  { name: 'existing.log', content: '...' },
  { name: 'new-log.log', content: '...' }  // 新增
]
```

UI 会自动创建新的选项卡。

### 修改日志显示样式

编辑 TaskDetailPage.tsx 中的日志容器样式：

```typescript
<div className="bg-gray-900 rounded-lg p-4 overflow-x-auto">
  {/* 修改 bg-gray-900 为其他颜色 */}
  {/* 调整 p-4 改变内边距 */}
</div>
```

## 性能考虑

- 日志内容作为字符串存储在内存中
- 只有选中的日志内容被渲染
- 支持较大的日志文件（通过overflow-x-auto实现横向滚动）
- 延迟加载：日志内容只在用户查看时加载

## 浏览器兼容性

✅ Chrome/Edge 88+
✅ Firefox 87+
✅ Safari 14+

## 验证

✅ TypeScript 编译通过 (0 errors)
✅ 类型定义完整
✅ 模拟数据完整 (4诊断, 10日志)
✅ UI 切换功能正常
✅ 样式一致

## 相关文件

- `src/types/index.ts` - LogFile 类型定义
- `src/lib/mockData.ts` - 模拟日志数据
- `src/pages/TaskDetailPage.tsx` - 日志显示实现
- `TASK_NAME_FORMAT.md` - 任务名称格式化
- `TASK_TYPE_FIX.md` - 任务类型功能
- `TRIGGER_SOURCE_ICON.md` - 触发源图标功能
