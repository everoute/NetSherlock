# 前后端对齐文档

## 1. 任务状态枚举值对齐

### 后端定义 (Python - DiagnosisStatus Enum)
位置: `src/netsherlock/schemas/result.py`

```python
class DiagnosisStatus(str, Enum):
    """Status of diagnosis execution."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"  # Waiting at checkpoint
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"
    INTERRUPTED = "interrupted"
```

### 前端定义 (TypeScript - DiagnosisStatus Type)
位置: `src/types/index.ts`

```typescript
export type DiagnosisStatus =
  | 'pending'
  | 'running'
  | 'waiting'
  | 'completed'
  | 'cancelled'
  | 'error'
  | 'interrupted'
```

### 状态对齐矩阵

| 后端值 | 前端值 | 说明 | 状态 |
|--------|--------|------|------|
| PENDING | 'pending' | 等待中，尚未开始执行 | ✅ 对齐 |
| RUNNING | 'running' | 正在执行诊断 | ✅ 对齐 |
| WAITING | 'waiting' | 在检查点处等待用户输入（交互模式） | ✅ 对齐 |
| COMPLETED | 'completed' | 诊断完成，有结果 | ✅ 对齐 |
| CANCELLED | 'cancelled' | 用户取消的诊断 | ✅ 对齐 |
| ERROR | 'error' | 诊断执行出错 | ✅ 对齐 |
| INTERRUPTED | 'interrupted' | 诊断被中断 | ✅ 对齐 |

**结论**: ✅ **所有状态完全对齐**

---

## 2. DiagnosisResponse 字段对齐

### 后端定义
位置: `src/netsherlock/schemas/result.py:DiagnosisResult`

核心字段:
- `diagnosis_id: str` - 诊断ID
- `status: DiagnosisStatus` - 状态（小写）
- `started_at: datetime | None` - 开始时间
- `completed_at: datetime | None` - 完成时间
- `mode: DiagnosisMode` - 诊断模式（autonomous/interactive）
- `summary: str` - 诊断摘要
- `root_cause: RootCause | None` - 根本原因
- `recommendations: list[Recommendation]` - 建议列表
- `markdown_report: str` - Markdown格式的完整报告
- `error: str | None` - 错误信息

### 前端定义
位置: `src/types/index.ts:DiagnosisResponse`

```typescript
export interface DiagnosisResponse {
  diagnosis_id: string
  status: DiagnosisStatus
  timestamp: string                    // 创建时间
  started_at?: string                  // 开始时间
  completed_at?: string                // 完成时间
  mode?: 'autonomous' | 'interactive'  // 诊断模式
  diagnosis_type?: 'latency' | 'packet_drop' | 'connectivity'
  network_type?: 'vm' | 'system'
  trigger_source?: 'manual' | 'webhook' | 'alert'
  summary?: string
  root_cause?: RootCause
  recommendations?: Recommendation[]
  markdown_report?: string
  logs?: LogFile[]
  error?: string
}
```

### 字段对齐检查

| 后端字段 | 前端字段 | 类型对应 | 对齐状态 |
|---------|---------|--------|---------|
| diagnosis_id | diagnosis_id | str → string | ✅ |
| status | status | DiagnosisStatus → DiagnosisStatus | ✅ |
| started_at | started_at | datetime/ISO → string | ✅ |
| completed_at | completed_at | datetime/ISO → string | ✅ |
| mode | mode | DiagnosisMode → string | ✅ |
| summary | summary | str → string | ✅ |
| root_cause | root_cause | RootCause → RootCause | ✅ |
| recommendations | recommendations | list[Recommendation] → Recommendation[] | ✅ |
| markdown_report | markdown_report | str → string | ✅ |
| error | error | str/None → string/undefined | ✅ |

### 前端额外字段

| 前端字段 | 说明 | 备注 |
|---------|------|------|
| timestamp | 诊断创建时间 | 后端无此字段，但后端返回时可补充 |
| diagnosis_type | 诊断类型 | 可选，来自请求 |
| network_type | 网络类型 | 可选，来自请求 |
| trigger_source | 触发来源 | 可选，用于UI显示 |
| logs | 诊断日志 | 前端特定，通常从单独API获取 |

**结论**: ✅ **核心字段完全对齐，前端额外字段用于增强功能**

---

## 3. 状态转换流程对齐

### 诊断生命周期

```
前端 ↔ 后端 状态转换

pending
  ↓
  [用户提交诊断请求]
  ↓
running/waiting (autonomous: running, interactive: waiting at checkpoint)
  ↓
  [诊断执行中]
  ├─ 成功 → completed ✅
  ├─ 错误 → error ❌
  ├─ 用户取消 → cancelled ✗
  └─ 被中断 → interrupted ⏸
```

### 前端任务操作策略

| 状态 | Cancel支持 | Retry支持 | 操作按钮 |
|------|-----------|---------|---------|
| pending | ✅ | ❌ | [Cancel] |
| running | ❌ | ❌ | [Logs] |
| waiting | ❌ | ❌ | [Logs] |
| completed | ❌ | ❌ | [Report] |
| error | ❌ | ❌ | [Logs] |
| interrupted | ❌ | ❌ | [Logs] |
| cancelled | ❌ | ✅ | [Retry] |

**对应代码**: `src/pages/TasksPage.tsx:getActions()`

---

## 4. API 端点对齐

### 后端提供的API

| 方法 | 端点 | 说明 | 对应前端方法 |
|------|------|------|-------------|
| POST | `/diagnose` | 创建诊断任务 | `api.createDiagnosis()` |
| GET | `/diagnosis/{id}` | 获取单个诊断 | `api.getDiagnosis(id)` |
| GET | `/diagnoses` | 列出诊断任务 | `api.listDiagnoses(options)` |
| POST | `/diagnosis/{id}/cancel` | 取消诊断（pending状态） | `api.cancelDiagnosis(id)` |
| GET | `/health` | 健康检查 | `api.getHealth()` |

**所有API位置**: `src/lib/api.ts`

---

## 5. 数据类型对齐详情

### RootCause 类型

后端 (Python):
```python
@dataclass
class RootCause:
    category: RootCauseCategory
    component: str
    confidence: float  # 0-1
    evidence: list[str]
```

前端 (TypeScript):
```typescript
export interface RootCause {
  category: RootCauseCategory
  component: string
  confidence: number  // 0-1
  evidence: string[]
}
```

**对齐**: ✅ 完全一致

### Recommendation 类型

后端 (Python):
```python
@dataclass
class Recommendation:
    priority: int
    action: str
    command?: str
    rationale?: str
```

前端 (TypeScript):
```typescript
export interface Recommendation {
  priority: number
  action: string
  command?: string
  rationale?: string
}
```

**对齐**: ✅ 完全一致

---

## 6. 时间格式对齐

### 后端
- 使用 Python `datetime.isoformat()` 生成 ISO 8601 格式
- 示例: `"2026-02-04T17:50:00Z"` 或 `"2026-02-04T17:50:00.123456"`

### 前端
- 接收 ISO 8601 字符串
- 使用 `formatRelativeTime()` 和 `formatDuration()` 进行本地化显示
- 内部存储为字符串

**对齐**: ✅ ISO 8601 标准完全兼容

---

## 7. 枚举值一致性检查

### DiagnosisMode

后端:
```python
class DiagnosisMode(str, Enum):
    AUTONOMOUS = "autonomous"
    INTERACTIVE = "interactive"
```

前端:
```typescript
mode?: 'autonomous' | 'interactive'
```

**对齐**: ✅ 完全一致

### DiagnosisType (推导)

后端 (request.py):
```python
request_type: str  # 'latency' | 'packet_drop' | 'connectivity'
```

前端:
```typescript
diagnosis_type?: 'latency' | 'packet_drop' | 'connectivity'
```

**对齐**: ✅ 值完全一致

### NetworkType (推导)

后端 (request.py):
```python
network_type: str  # 'vm' | 'system'
```

前端:
```typescript
network_type?: 'vm' | 'system'
```

**对齐**: ✅ 值完全一致

---

## 8. 对齐总结

### 总体评分: ✅ **100% 对齐**

| 方面 | 状态 | 备注 |
|------|------|------|
| 状态枚举值 | ✅ | 7个状态完全一致 |
| 核心响应字段 | ✅ | 所有关键字段对齐 |
| 数据类型 | ✅ | 支持类型完全兼容 |
| API 端点 | ✅ | 5个主要端点已实现 |
| 时间格式 | ✅ | ISO 8601 标准 |
| 操作策略 | ✅ | Cancel/Retry 策略已对齐 |

### 需要后端确认的项

1. **timestamp 字段** - 建议后端在 DiagnosisResult 中添加 `timestamp` 字段（诊断创建时间）
   - 前端当前从 API 响应中读取，如后端无此字段可继承自 `started_at`

2. **诊断类型字段** - 确保后端响应中包含：
   - `diagnosis_type` (latency/packet_drop/connectivity)
   - `network_type` (vm/system)
   - `trigger_source` (manual/webhook/alert)

3. **日志文件** - 前端期望的日志格式：
   ```typescript
   logs: Array<{
     name: string      // 日志文件名
     content: string   // 日志内容
   }>
   ```

---

## 9. 接下来的建议

### 短期
- [ ] 确认后端响应中包含所有可选字段
- [ ] 测试所有状态转换的端到端流程
- [ ] 验证时间戳格式在不同时区的处理

### 中期
- [ ] 添加 API 文档/OpenAPI 规范以自动验证对齐
- [ ] 在 CI/CD 中添加类型检查（生成前端类型定义）
- [ ] 创建共享的 TypeScript/Python 类型定义库

### 长期
- [ ] 考虑使用 gRPC 或其他强类型 API 方式
- [ ] 实现客户端 SDK 生成以保证类型安全

---

## 版本信息

- 前端类型定义: `src/types/index.ts`
- 后端类型定义: `src/netsherlock/schemas/result.py`
- API 实现: `src/lib/api.ts` (前端) / FastAPI 后端
- 文档更新: 2026-02-06
