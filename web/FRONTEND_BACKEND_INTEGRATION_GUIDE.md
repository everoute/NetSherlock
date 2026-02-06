# 前后端集成指南

## 概览

本文档提供前端开发者与后端 API 对接的具体指导，确保数据类型、状态管理和 API 调用的一致性。

---

## 1. 类型定义导入

### 前端类型（TypeScript）

```typescript
// src/types/index.ts 中定义的所有类型
import type {
  DiagnosisStatus,          // 'pending' | 'running' | 'waiting' | 'completed' | 'cancelled' | 'error' | 'interrupted'
  DiagnosisResponse,        // API 响应主体
  RootCause,               // 根本原因
  Recommendation,          // 建议
  LogFile,                 // 日志文件
  HealthResponse,          // 健康检查响应
} from '@/types'
```

### 后端类型（Python）

```python
# src/netsherlock/schemas/result.py
from netsherlock.schemas.result import (
    DiagnosisStatus,       # Enum: PENDING, RUNNING, WAITING, COMPLETED, CANCELLED, ERROR, INTERRUPTED
    DiagnosisResult,       # 完整的诊断结果对象
)

# 使用小写值
status = DiagnosisStatus.PENDING.value  # "pending"
```

---

## 2. API 响应处理

### 创建诊断 (POST /diagnose)

**前端调用**:
```typescript
// src/lib/api.ts
async createDiagnosis(request: DiagnosticRequest): Promise<DiagnosisResponse> {
  const response = await fetch(`${API_BASE_URL}/diagnose`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  return response.json()
}
```

**后端返回格式**:
```json
{
  "diagnosis_id": "abc123",
  "status": "pending",
  "timestamp": "2026-02-06T10:00:00Z",
  "mode": "autonomous",
  "diagnosis_type": "latency",
  "network_type": "vm",
  "trigger_source": "manual"
}
```

**前端处理**:
```typescript
const response = await api.createDiagnosis(request)
// response: DiagnosisResponse
// status: 'pending'
// 显示在任务列表中
```

### 获取单个诊断 (GET /diagnosis/{id})

**前端调用**:
```typescript
async getDiagnosis(id: string): Promise<DiagnosisResponse> {
  const response = await fetch(`${API_BASE_URL}/diagnosis/${id}`)
  return response.json()
}
```

**后端返回格式** (根据状态变化):
```json
{
  "diagnosis_id": "abc123",
  "status": "running",
  "timestamp": "2026-02-06T10:00:00Z",
  "started_at": "2026-02-06T10:01:00Z",
  "mode": "autonomous",
  "diagnosis_type": "latency",
  "network_type": "vm",
  "trigger_source": "manual",
  "summary": "正在测量延迟..."
}
```

**前端处理**:
```typescript
const diagnosis = await api.getDiagnosis(id)

// 根据状态显示不同 UI
switch (diagnosis.status) {
  case 'pending':
  case 'running':
  case 'waiting':
    // 显示进度条
    break
  case 'completed':
    // 显示报告按钮
    break
  case 'error':
  case 'interrupted':
    // 显示错误信息和日志
    break
  case 'cancelled':
    // 显示重试按钮
    break
}
```

### 列出诊断 (GET /diagnoses)

**前端调用**:
```typescript
async listDiagnoses(options?: ListOptions): Promise<DiagnosisResponse[]> {
  const params = new URLSearchParams()
  if (options?.limit) params.append('limit', options.limit.toString())
  if (options?.offset) params.append('offset', options.offset.toString())
  if (options?.status) params.append('status', options.status)

  const response = await fetch(`${API_BASE_URL}/diagnoses?${params}`)
  return response.json()
}
```

**后端返回格式**:
```json
[
  {
    "diagnosis_id": "abc123",
    "status": "completed",
    "timestamp": "2026-02-06T10:00:00Z",
    "started_at": "2026-02-06T10:01:00Z",
    "completed_at": "2026-02-06T10:15:00Z",
    "mode": "autonomous",
    "diagnosis_type": "latency",
    "network_type": "vm",
    "trigger_source": "manual",
    "summary": "VM 网络延迟分析完成"
  }
]
```

**前端处理** (TasksPage.tsx):
```typescript
const [tasks, setTasks] = useState<DiagnosisResponse[]>([])

useEffect(() => {
  loadTasks()
  const interval = setInterval(loadTasks, 5000) // 定期轮询
  return () => clearInterval(interval)
}, [])

async function loadTasks() {
  const data = await api.listDiagnoses({ limit: 50 })
  setTasks(data)
}
```

### 取消诊断 (POST /diagnosis/{id}/cancel)

**前端调用**:
```typescript
async cancelDiagnosis(id: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/diagnosis/${id}/cancel`, {
    method: 'POST',
  })
  if (!response.ok) {
    throw new Error(`Failed to cancel diagnosis: ${response.statusText}`)
  }
}
```

**后端应该返回**:
- 状态码 200/204
- 可选返回更新后的 DiagnosisResponse（status 变为 'cancelled'）

**前端处理**:
```typescript
// 仅在 pending 状态时显示取消按钮
if (task.status === 'pending') {
  const handleCancel = async () => {
    try {
      await api.cancelDiagnosis(task.diagnosis_id)
      // 刷新任务列表
      await loadTasks()
    } catch (error) {
      console.error('Failed to cancel:', error)
    }
  }
}
```

### 健康检查 (GET /health)

**前端调用**:
```typescript
async getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`)
  return response.json()
}
```

**后端返回格式**:
```json
{
  "status": "healthy",
  "timestamp": "2026-02-06T10:00:00Z",
  "queue_size": 5,
  "engine": "claude-haiku-4-5"
}
```

**前端处理** (Sidebar.tsx - useBackendStatus hook):
```typescript
const [status, setStatus] = useState<'healthy' | 'degraded' | 'offline'>('offline')

useEffect(() => {
  const checkHealth = async () => {
    try {
      const health = await api.getHealth()
      setStatus(health.status === 'healthy' ? 'healthy' : 'degraded')
    } catch {
      setStatus('offline')
    }
  }

  checkHealth()
  const interval = setInterval(checkHealth, 10000) // 每10秒检查一次
  return () => clearInterval(interval)
}, [])
```

---

## 3. 状态转换处理

### 状态机示意

```
创建
  ↓
pending (等待)
  ├─ [用户点击取消] → cancelled ✗
  └─ [诊断开始] → running/waiting
      ↓
      running/waiting (执行中)
        ├─ [成功完成] → completed ✅
        ├─ [执行出错] → error ❌
        └─ [被中断] → interrupted ⏸
```

### 前端状态管理示例

```typescript
// TaskDetailPage.tsx
const [task, setTask] = useState<DiagnosisResponse | null>(null)
const [loading, setLoading] = useState(true)

useEffect(() => {
  if (!id) return
  loadTask()
  // 根据状态决定轮询频率
  const interval = setInterval(
    loadTask,
    task?.status === 'running' || task?.status === 'waiting' ? 2000 : 5000
  )
  return () => clearInterval(interval)
}, [id, task?.status])

async function loadTask() {
  const data = await api.getDiagnosis(id!)
  setTask(data)

  // 如果已完成，停止轮询
  if (data.status === 'completed' || data.status === 'error' ||
      data.status === 'cancelled' || data.status === 'interrupted') {
    setLoading(false)
  }
}
```

---

## 4. 字段映射表

### 时间戳处理

后端发送 ISO 8601 格式:
```
"2026-02-06T10:30:45.123456Z"
```

前端转换为本地时间显示:
```typescript
import { formatRelativeTime } from '@/lib/utils'

const relativeTime = formatRelativeTime(timestamp)  // "5 minutes ago"
const duration = formatDuration(started_at, completed_at)  // "15 seconds"
```

### 状态显示

根据前端的状态定义，显示对应的操作按钮：

| 状态 | 显示 | 备注 |
|------|------|------|
| pending | [Cancel] | 仅在 pending 时允许取消 |
| running | [Logs] | 显示实时日志 |
| waiting | [Logs] | 等待用户输入 |
| completed | [Report] | 查看完整报告 |
| error | [Logs] | 显示错误日志 |
| interrupted | [Logs] | 显示中断日志 |
| cancelled | [Retry] | 允许重新执行 |

**实现位置**: `src/pages/TasksPage.tsx:getActions()`

---

## 5. 错误处理

### 网络错误

```typescript
async function loadTasks() {
  try {
    const data = await api.listDiagnoses({ limit: 50 })
    setTasks(data)
  } catch (error) {
    console.error('Failed to load tasks:', error)
    // 显示错误提示或重试按钮
    setError('Unable to load tasks. Please check your connection.')
  } finally {
    setLoading(false)
  }
}
```

### 后端错误响应

预期的错误格式:
```json
{
  "error": "Invalid diagnosis ID",
  "status_code": 404
}
```

前端应该将此映射到错误消息:
```typescript
try {
  await api.getDiagnosis(id)
} catch (error) {
  if (error.status === 404) {
    return <p>Diagnosis not found</p>
  }
  return <p>Error loading diagnosis</p>
}
```

---

## 6. 类型一致性检查清单

### 每次集成时检查

- [ ] **状态值**: 确保所有状态值为小写 ('pending', 不是 'PENDING')
- [ ] **时间格式**: 所有时间戳为 ISO 8601 字符串
- [ ] **数字精度**: 信心度 (confidence) 为 0-1 之间的浮点数
- [ ] **数组类型**: recommendations 和 evidence 为数组，非逗号分隔字符串
- [ ] **可选字段**: 不存在的字段应省略或设为 null/undefined，而非空字符串
- [ ] **ID 格式**: diagnosis_id 应为字符串，长度合理

### 示例验证

```typescript
// ✅ 正确的响应
{
  "diagnosis_id": "diag-20260206-100000",
  "status": "running",           // 小写!
  "timestamp": "2026-02-06T10:00:00Z",  // ISO 8601!
  "started_at": "2026-02-06T10:01:00Z",
  "mode": "autonomous",
  "diagnosis_type": "latency",
  "network_type": "vm",
  "confidence": 0.85             // 浮点数!
}

// ❌ 错误的响应
{
  "diagnosis_id": "abc123",
  "status": "RUNNING",           // 大写 ❌
  "timestamp": "2026-02-06 10:00:00",   // 非 ISO 格式 ❌
  "started_at": null,
  "confidence": "0.85"           // 字符串 ❌
}
```

---

## 7. 开发工作流

### 本地开发

1. **使用 Mock 数据**:
   ```bash
   VITE_USE_MOCK_DATA=true npm run dev
   ```

2. **测试 API 集成**:
   ```bash
   VITE_API_URL=http://localhost:8000 npm run dev
   ```

3. **监控网络请求**:
   - 打开浏览器 DevTools → Network 标签
   - 检查 `/diagnose`, `/diagnosis/...`, `/diagnoses` 请求
   - 验证响应格式与文档一致

### 调试技巧

```typescript
// 在 API 响应后添加日志
async function listDiagnoses(options?: ListOptions): Promise<DiagnosisResponse[]> {
  const response = await fetch(`${API_BASE_URL}/diagnoses?${params}`)
  const data = await response.json()

  // 调试日志
  console.log('API Response:', data)
  console.log('First task status:', data[0]?.status)

  return data
}
```

---

## 8. 常见问题

### Q: 后端返回的 timestamp 和 started_at 有什么区别?

A:
- `timestamp`: 诊断任务创建的时间
- `started_at`: 诊断执行开始的时间

实际场景:
```
timestamp: 2026-02-06 10:00:00  (用户提交)
  ↓ 等待 1 分钟...
started_at: 2026-02-06 10:01:00 (开始执行)
```

### Q: 如何处理时区问题?

A: 后端返回 UTC 时间（Z 后缀），前端的 `formatRelativeTime()` 会自动转换为本地时间。

```typescript
formatRelativeTime("2026-02-06T10:00:00Z")  // 自动处理时区
// 显示: "5 minutes ago" 等相对时间
```

### Q: cancelled 和 interrupted 的区别是什么?

A:
- **cancelled**: 用户主动取消的诊断 (✗ 可重试)
- **interrupted**: 系统中断的诊断 (⏸ 可查看日志)

前端处理:
- cancelled 显示 [Retry] 按钮
- interrupted 只显示 [Logs] 按钮

---

## 9. 性能优化

### 轮询策略

```typescript
// 智能轮询：根据状态调整频率
const pollInterval =
  task?.status === 'running' || task?.status === 'waiting'
    ? 2000    // 执行中: 2秒轮询一次
    : 5000    // 其他状态: 5秒轮询一次
```

### 缓存策略

```typescript
// 已完成的任务不需要继续轮询
if (['completed', 'error', 'cancelled', 'interrupted'].includes(task.status)) {
  clearInterval(interval)
}
```

---

## 10. 测试清单

### 单元测试

```typescript
describe('DiagnosisResponse', () => {
  it('should handle all status values', () => {
    const statuses: DiagnosisStatus[] = [
      'pending', 'running', 'waiting', 'completed',
      'cancelled', 'error', 'interrupted'
    ]
    statuses.forEach(status => {
      expect(isValidStatus(status)).toBe(true)
    })
  })

  it('should format timestamps correctly', () => {
    const response: DiagnosisResponse = {
      diagnosis_id: 'test',
      status: 'completed',
      timestamp: '2026-02-06T10:00:00Z',
      started_at: '2026-02-06T10:01:00Z',
      completed_at: '2026-02-06T10:15:00Z'
    }
    expect(formatRelativeTime(response.timestamp)).toBeTruthy()
  })
})
```

### 集成测试

```typescript
describe('API Integration', () => {
  it('should fetch diagnosis list with correct types', async () => {
    const tasks = await api.listDiagnoses({ limit: 10 })
    expect(Array.isArray(tasks)).toBe(true)
    tasks.forEach(task => {
      expect(['pending', 'running', 'waiting', 'completed',
              'cancelled', 'error', 'interrupted']).toContain(task.status)
    })
  })
})
```

---

## 版本历史

- 2026-02-06: 初始版本，涵盖所有核心 API 和状态定义
