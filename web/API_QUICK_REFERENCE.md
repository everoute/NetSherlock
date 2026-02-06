# API 快速参考

## 状态速查表

| 状态 | 值 | 含义 | 可操作 | 按钮 |
|------|----|----|--------|------|
| ⏳ | `pending` | 等待执行 | Cancel | [Cancel] |
| ⚙️ | `running` | 执行中 | - | [Logs] |
| ⏸ | `waiting` | 检查点等待 | - | [Logs] |
| ✅ | `completed` | 完成 | - | [Report] |
| ✗ | `error` | 执行错误 | - | [Logs] |
| ⏹ | `interrupted` | 被中断 | - | [Logs] |
| 🔄 | `cancelled` | 用户取消 | Retry | [Retry] |

## API 端点速查

### 创建诊断
```
POST /diagnose
Content-Type: application/json

{
  "network_type": "vm" | "system",
  "diagnosis_type": "latency" | "packet_drop" | "connectivity",
  "src_host": "192.168.1.1",
  "src_vm": "vm-uuid",
  "dst_host": "192.168.1.2",
  "dst_vm": "vm-uuid",
  "mode": "autonomous" | "interactive"
}

Response:
{
  "diagnosis_id": "diag-...",
  "status": "pending"
}
```

### 获取诊断详情
```
GET /diagnosis/{id}

Response:
{
  "diagnosis_id": "diag-...",
  "status": "running",
  "timestamp": "2026-02-06T10:00:00Z",
  "started_at": "2026-02-06T10:01:00Z",
  "completed_at": null,
  ...
}
```

### 列表诊断
```
GET /diagnoses?limit=50&offset=0&status=running

Response:
[
  { "diagnosis_id": "...", "status": "running" },
  ...
]
```

### 取消诊断
```
POST /diagnosis/{id}/cancel

仅对 pending 状态有效
成功: 状态变为 cancelled
```

### 健康检查
```
GET /health

Response:
{
  "status": "healthy",
  "timestamp": "2026-02-06T10:00:00Z",
  "queue_size": 5
}
```

## 字段类型速查

```typescript
// 核心字段
diagnosis_id: string          // "diag-20260206-100000"
status: DiagnosisStatus       // 'pending' | 'running' | ...
timestamp: string             // ISO 8601: "2026-02-06T10:00:00Z"
mode: string                  // 'autonomous' | 'interactive'

// 诊断信息
diagnosis_type: string        // 'latency' | 'packet_drop' | 'connectivity'
network_type: string          // 'vm' | 'system'
trigger_source: string        // 'manual' | 'webhook' | 'alert'
summary: string               // 诊断摘要
error: string | null          // 错误信息

// 时间信息
started_at: string | null     // ISO 8601
completed_at: string | null   // ISO 8601

// 分析结果
root_cause: {
  category: string            // 根本原因分类
  component: string           // 故障组件
  confidence: number          // 0-1
  evidence: string[]          // 证据列表
}

recommendations: {
  priority: number            // 优先级
  action: string              // 建议动作
  command?: string            // 命令
  rationale?: string          // 理由
}[]

markdown_report: string       // Markdown 格式的完整报告
```

## 错误码速查

| 状态码 | 含义 | 处理 |
|--------|------|------|
| 200 | 成功 | 正常处理 |
| 201 | 创建成功 | 显示新任务 |
| 204 | 无内容 | 操作成功（如取消） |
| 400 | 请求错误 | 检查请求参数 |
| 404 | 未找到 | 显示"任务不存在" |
| 500 | 服务器错误 | 显示"后端错误" |

## 前端 API 客户端

```typescript
import { api } from '@/lib/api'

// 创建诊断
await api.createDiagnosis(request)

// 获取诊断
await api.getDiagnosis(id)

// 列表诊断
await api.listDiagnoses({ limit: 50 })

// 取消诊断
await api.cancelDiagnosis(id)

// 健康检查
await api.getHealth()
```

## 前端组件对应关系

| 组件 | 位置 | 功能 |
|------|------|------|
| TasksPage | `src/pages/TasksPage.tsx` | 任务列表，状态过滤 |
| TaskDetailPage | `src/pages/TaskDetailPage.tsx` | 任务详情，日志显示 |
| StatusBadge | `src/components/StatusBadge.tsx` | 状态标签显示 |
| Sidebar | `src/components/Sidebar.tsx` | 后端状态指示 |

## 时间格式化

```typescript
import { formatRelativeTime, formatDuration } from '@/lib/utils'

// 相对时间
formatRelativeTime("2026-02-06T10:00:00Z")  // "5 minutes ago"

// 时长
formatDuration("2026-02-06T10:00:00Z", "2026-02-06T10:15:00Z")  // "15 seconds"
```

## 环境变量

```bash
# API 地址（默认 http://localhost:8000）
VITE_API_URL=http://backend:8000

# 使用 Mock 数据（开发时）
VITE_USE_MOCK_DATA=true
```

## 开发命令

```bash
# 开发服务器
npm run dev

# 生产构建
npm run build

# 类型检查
npm run type-check

# 代码检查
npm run lint
```

## 常用测试数据

```typescript
// Mock 诊断状态
const mockDiagnosis = {
  pending: { status: 'pending', timestamp: '...' },
  running: { status: 'running', started_at: '...' },
  completed: { status: 'completed', completed_at: '...' },
  error: { status: 'error', error: 'Connection failed' },
  cancelled: { status: 'cancelled', completed_at: '...' },
}
```

## 状态流转图

```
                    [创建]
                      ↓
                   pending
                   /  |  \
                  /   |   \
              [Cancel] [开始] [超时]
                /       |       \
               ✗        ↓        ✗
            cancelled  running
                        / | \
                       /  |  \
                      /   |   \
                  [✓完成][错误][中断]
                   /       |      \
                  ✅       ❌      ⏹
               completed  error  interrupted
```

## 内存中的任务状态管理

```typescript
// TasksPage.tsx 中的状态
const [tasks, setTasks] = useState<DiagnosisResponse[]>([])
const [filter, setFilter] = useState<'all' | DiagnosisStatus>('all')

// 定期轮询
useEffect(() => {
  loadTasks()
  const interval = setInterval(loadTasks, 5000)  // 每 5 秒
  return () => clearInterval(interval)
}, [])

// 过滤任务
const filteredTasks = tasks.filter(
  task => filter === 'all' || task.status === filter
)
```

## 缓存策略

```typescript
// ✅ 应该缓存的
- 已完成的诊断 (completed)
- 出错的诊断 (error)
- 已取消的诊断 (cancelled)

// ⏱ 应该轮询的
- 待执行诊断 (pending)
- 执行中诊断 (running)
- 等待中诊断 (waiting)

// 轮询频率
- 执行中: 2 秒
- 其他: 5 秒
- 后端状态: 10 秒
```

## 错误处理模板

```typescript
try {
  const result = await api.getDiagnosis(id)
  setTask(result)
} catch (error) {
  if (error instanceof TypeError) {
    setError('网络连接失败')
  } else {
    setError('加载任务失败，请重试')
  }
} finally {
  setLoading(false)
}
```

## 快速诊断检查清单

开发时验证以下项目：

- [ ] 所有状态值为小写（'pending' 不是 'PENDING'）
- [ ] 时间戳为 ISO 8601 格式（带 Z 后缀表示 UTC）
- [ ] 信心度为 0-1 浮点数（不是百分比）
- [ ] 数组字段为真数组（不是逗号分隔字符串）
- [ ] 缺失字段省略或为 null（不是空字符串）
- [ ] diagnosis_id 为非空字符串
- [ ] 状态转换符合预期（pending → running → completed）
- [ ] 轮询间隔根据状态调整
- [ ] 错误消息清晰可读

---

**文档更新**: 2026-02-06
**前端版本**: React 18+ / TypeScript
**后端版本**: Python FastAPI
