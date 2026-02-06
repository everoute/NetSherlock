# NetSherlock 诊断状态 - 快速参考

> 快速查阅文档：状态定义、转换规则、API 端点、前端映射

---

## 状态清单

| 状态值 | 含义 | 模式 | 可取消 | 可见 |
|--------|------|------|:-----:|:---:|
| `pending` | 等待执行 | 两种 | ✅ | ✅ |
| `running` | 正在执行 | 两种 | ❌ | ✅ |
| `waiting` | 等待输入 | 交互 | ✅ | ✅ |
| `completed` | 成功完成 | 两种 | ❌ | ✅ |
| `cancelled` | 已取消 | 交互 | ❌ | ✅ |
| `error` | 执行错误 | 两种 | ❌ | ✅ |
| `interrupted` | 已中断 | 两种 | ❌ | ✅ |

---

## 状态转换规则

```
PENDING  →  RUNNING  ⟿  COMPLETED
               ↓         ERROR
            WAITING ⟿  INTERRUPTED
               ↓
            CANCELLED
```

**转换表**:
| From | To | 触发条件 |
|------|----|---------| 
| PENDING | RUNNING | `execute()` |
| RUNNING | WAITING | 检查点（交互模式） |
| RUNNING | COMPLETED | 诊断成功 |
| RUNNING | ERROR | 执行异常 |
| RUNNING | INTERRUPTED | Ctrl+C |
| WAITING | RUNNING | 用户确认 |
| WAITING | CANCELLED | 用户取消 |

---

## API 端点

### 创建诊断
```
POST /diagnose
Content-Type: application/json
X-API-Key: <key>

{
  "network_type": "vm|system",
  "diagnosis_type": "latency|packet_drop|connectivity",
  "src_host": "host1",
  "dst_host": "host2",
  "src_vm": "vm1",
  "dst_vm": "vm2",
  "mode": "autonomous|interactive",
  "description": "optional"
}
```

### 获取诊断状态
```
GET /diagnose/{diagnosis_id}
X-API-Key: <key>

返回: {
  "diagnosis_id": "...",
  "status": "pending|running|waiting|completed|cancelled|error|interrupted",
  "timestamp": "...",
  "mode": "autonomous|interactive",
  "summary": "...",
  "root_cause": {...},
  "recommendations": [...]
}
```

### 取消诊断 ⭐ 关键端点
```
POST /diagnose/{diagnosis_id}/cancel
X-API-Key: <key>

返回 (200): {
  "message": "Diagnosis cancelled successfully",
  "diagnosis_id": "..."
}

错误 (400): 不可取消的状态
  {"detail": "Cannot cancel diagnosis in {status} status"}

错误 (404): 诊断不存在
  {"detail": "Diagnosis {id} not found"}
```

### 获取诊断列表
```
GET /diagnoses?limit=50
X-API-Key: <key>

返回: [
  {
    "diagnosis_id": "...",
    "status": "...",
    ...
  }
]
```

### 获取诊断报告
```
GET /diagnose/{diagnosis_id}/report
X-API-Key: <key>

返回: {
  "markdown_report": "# 诊断报告\n...",
  "diagnosis_id": "...",
  "timestamp": "..."
}
```

---

## 前端组件

### StatusBadge 组件
```typescript
import { StatusBadge } from '@/components/StatusBadge'

export function MyComponent() {
  return <StatusBadge status="running" size="md" />
}
```

**尺寸选项**: `sm` | `md` (默认) | `lg`

**输出**:
- 图标 + 颜色 + 标签
- RUNNING 状态显示旋转动画

### 状态工具函数
```typescript
import { getStatusColor, getStatusLabel } from '@/lib/utils'

const color = getStatusColor('running')  // 'bg-blue-100 text-blue-700'
const label = getStatusLabel('running')  // 'Running'
```

### 状态颜色映射
```typescript
const colors = {
  pending: 'bg-gray-100 text-gray-700',
  running: 'bg-blue-100 text-blue-700',
  waiting: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-gray-100 text-gray-600',
  error: 'bg-red-100 text-red-700',
  interrupted: 'bg-orange-100 text-orange-700',
}
```

### 状态标签映射
```typescript
const labels = {
  pending: 'Pending',
  running: 'Running',
  waiting: 'Waiting',
  completed: 'Completed',
  cancelled: 'Cancelled',
  error: 'Error',
  interrupted: 'Interrupted',
}
```

---

## 前端页面逻辑

### TasksPage 操作按钮
```typescript
// 根据状态显示不同的按钮
pending  → [Cancel] (取消)
running  → [Logs]   (日志)
waiting  → [Logs]   (日志)
completed → [Report] (报告)
error    → [Logs]   (日志)
interrupted → [Logs] (日志)
cancelled → [Retry] (重试)
```

### 状态过滤器
```typescript
<select>
  <option value="all">All</option>
  <option value="pending">Pending</option>
  <option value="running">Running</option>
  <option value="completed">Completed</option>
  <option value="error">Failed</option>
  {/* ❌ 缺少: waiting, interrupted, cancelled */}
</select>
```

### 轮询策略
```typescript
// 当前: 统一 5 秒轮询
const interval = setInterval(loadTasks, 5000)

// 建议: 活跃状态 2 秒，其他 5 秒
```

---

## 代码位置速查

### 后端

| 文件 | 内容 | 行号 |
|------|------|------|
| `src/netsherlock/schemas/result.py` | DiagnosisStatus 枚举 | 21-30 |
| `src/netsherlock/controller/diagnosis_controller.py` | 状态转换逻辑 | 见下表 |
| `src/netsherlock/api/webhook.py` | API 端点 | 见下表 |

**diagnosis_controller.py 状态转换**:
- L398: PENDING → RUNNING
- L439: ERROR 状态
- L498, 593: COMPLETED 状态
- L535, 563: WAITING 状态
- L556, 579: WAITING → RUNNING
- L1602: INTERRUPTED 状态

**webhook.py API 端点**:
- L644-655: DiagnosisResponse 模型
- L896: 状态值序列化
- L953-992: `/cancel` 端点

### 前端

| 文件 | 内容 |
|------|------|
| `web/src/types/index.ts` | DiagnosisStatus 类型 |
| `web/src/components/StatusBadge.tsx` | 状态徽章组件 |
| `web/src/lib/utils.ts` | 颜色/标签工具函数 |
| `web/src/pages/TasksPage.tsx` | 任务列表 & 过滤 |

---

## 常见问题

### Q: 如何取消正在执行的诊断？
**A**: 不能取消 RUNNING 状态的诊断。只有 PENDING 和 WAITING 状态可以取消。

### Q: 交互模式和自主模式有什么区别？
**A**:
- **自主模式**: 直接执行 PENDING → RUNNING → COMPLETED，无中途暂停
- **交互模式**: 可在检查点暂停为 WAITING，等待用户确认后继续

### Q: 状态转换时是否需要更新 completed_at？
**A**: 只有终止状态需要设置 completed_at：COMPLETED, CANCELLED, ERROR, INTERRUPTED

### Q: API 如何验证身份？
**A**: 所有 POST/GET 请求都需要 `X-API-Key` header

### Q: 前端轮询频率应该是多少？
**A**: 
- 活跃状态 (running, waiting): 2 秒
- 其他状态: 5 秒

---

## 待改进项

### 🔴 高优先级 (P0)

- [ ] 前端 Cancel 按钮功能未实现 (`web/src/pages/TasksPage.tsx:124-130`)
- [ ] 状态过滤器缺少 3 个选项 (`web/src/pages/TasksPage.tsx:168-173`)

### 🟡 中优先级 (P1)

- [ ] 优化轮询策略，活跃状态更频繁
- [ ] 添加前端类型注释

### 🟢 低优先级 (P3)

- [ ] 完善 API 文档和注释

---

## 文档导航

| 文档 | 用途 |
|------|------|
| 📄 [**完整报告**](./diagnosis-status-alignment-report.md) | 详细分析，包含所有细节、代码片段、测试清单 |
| 📋 [**执行摘要**](./diagnosis-status-analysis-summary.md) | 核心发现、评分、待改进项、代码片段 |
| ⚡ **本文档** | 快速参考，API/代码位置、常见问题 |

---

## 版本信息

- **报告版本**: 1.0
- **生成日期**: 2026-02-06
- **综合评分**: 90% (54/60)
- **对齐状态**: ✅ 100% 一致

---

**快速开始**: 
1. 修复 P0 项 (Cancel 按钮 + 过滤器)
2. 参考完整报告的第 6-7 章了解实现细节
3. 使用第 14 章的测试清单验证功能
