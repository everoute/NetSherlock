# API 快速参考

## 汇总表

| # | 方法 | 端点 | 说明 | 前端使用 | 状态 |
|---|------|------|------|---------|------|
| 1 | GET | `/health` | 健康检查 | - | ❌ 未使用 |
| 2 | POST | `/diagnose` | 创建诊断任务 | NewTaskPage.tsx | ✅ |
| 3 | GET | `/diagnosis/{id}` | 获取诊断详情 | TaskDetailPage, ReportDetailPage | ✅ |
| 4 | GET | `/diagnoses` | 列表诊断任务 | TasksPage, ReportsPage | ✅ |
| 5 | POST | `/diagnosis/{id}/cancel` | 取消诊断任务 | TaskDetailPage | ❌ 未实现 |

---

## 详细接口

### 1️⃣ 健康检查
```
GET /health
→ { status, timestamp, queue_size, engine }
```

### 2️⃣ 创建诊断任务
```
POST /diagnose
← {
    network_type: 'vm'|'system',
    diagnosis_type: 'latency'|'packet_drop'|'connectivity',
    src_host?, src_vm?, src_vm_name?,
    dst_host?, dst_vm?, dst_vm_name?,
    description?, mode?, options?
  }
→ { diagnosis_id, status, timestamp, ... }
```

### 3️⃣ 获取诊断详情
```
GET /diagnosis/{id}
→ {
    diagnosis_id, status, timestamp,
    started_at?, completed_at?,
    mode, diagnosis_type, network_type, trigger_source,
    summary?, root_cause?, recommendations?,
    markdown_report?, logs?, error?
  }
```

### 4️⃣ 列表诊断任务
```
GET /diagnoses?limit=50&offset=0&status=...
→ [{ diagnosis_id, status, timestamp, ... }]
```

### 5️⃣ 取消诊断任务
```
POST /diagnosis/{id}/cancel
→ { diagnosis_id, status, cancelled_at }
```

---

## 任务状态 (status)

```
pending → running → { completed ✓ | error ✗ | interrupted ✗ }
        → waiting → completed ✓

running/pending → cancelled ✗
```

**终止状态**: `completed`, `cancelled`, `error`, `interrupted`

---

## 诊断类型 (diagnosis_type)

- `latency` - 延迟诊断
- `packet_drop` - 丢包诊断
- `connectivity` - 连通性诊断

---

## 网络类型 (network_type)

- `vm` - 虚拟机间通信
- `system` - 物理主机间通信

---

## 根本原因分类 (root_cause.category)

- `vm_internal` - VM 内部问题
- `host_internal` - 主机内部问题
- `vhost_processing` - vhost 处理问题
- `physical_network` - 物理网络问题
- `configuration` - 配置问题
- `resource_contention` - 资源竞争
- `unknown` - 未知

---

## 触发源 (trigger_source)

- `manual` - 手动触发 👋
- `webhook` - Webhook 触发 🔗
- `alert` - 告警触发 🔔

---

## 响应示例

### 诊断创建成功
```json
{
  "diagnosis_id": "diag-20260205-080000-vm-latency",
  "status": "pending",
  "timestamp": "2026-02-05T08:00:00Z",
  "mode": "autonomous",
  "diagnosis_type": "latency",
  "network_type": "vm",
  "trigger_source": "manual"
}
```

### 诊断完成
```json
{
  "diagnosis_id": "diag-20260205-080000-vm-latency",
  "status": "completed",
  "timestamp": "2026-02-05T08:00:00Z",
  "started_at": "2026-02-05T08:00:05Z",
  "completed_at": "2026-02-05T08:05:00Z",
  "summary": "检测到 VM 延迟原因为物理网络拥塞",
  "root_cause": {
    "category": "physical_network",
    "component": "Network Interface",
    "confidence": 0.85,
    "evidence": ["物理链接利用率 92%", "丢包率 2.3%", "延迟抖动"]
  },
  "recommendations": [
    {
      "priority": 1,
      "action": "升级网络带宽",
      "rationale": "当前带宽不足"
    }
  ],
  "logs": [
    { "name": "sender-host.log", "content": "..." },
    { "name": "receiver-host.log", "content": "..." },
    { "name": "analysis.log", "content": "..." }
  ]
}
```

---

## 前端轮询实现

```typescript
// 轮询诊断状态（TaskDetailPage.tsx 中使用）
useEffect(() => {
  if (!id) return

  loadTask()

  // 每 2 秒检查一次
  const interval = setInterval(loadTask, 2000)

  return () => clearInterval(interval)
}, [id])

async function loadTask() {
  const data = await api.getDiagnosis(id)
  setTask(data)

  // 任务完成时停止轮询
  if (['completed', 'error', 'cancelled', 'interrupted'].includes(data.status)) {
    // 可选：clearInterval(interval)
  }
}
```

---

## 环境变量

```bash
# .env
VITE_API_URL=http://localhost:8000      # API 基础 URL
VITE_USE_MOCK_DATA=true                 # 是否使用模拟数据（开发用）
```

---

## 后端实现建议

### 基础框架（Python FastAPI）

```python
from fastapi import FastAPI, HTTPException
from typing import Optional, List

app = FastAPI()

# 1. 健康检查
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": ...,
        "queue_size": ...,
        "engine": "diagnosis-engine"
    }

# 2. 创建诊断
@app.post("/diagnose")
async def create_diagnosis(request: DiagnosticRequest):
    # 验证参数
    # 创建任务
    # 入队执行
    return DiagnosisResponse(...)

# 3. 获取诊断详情
@app.get("/diagnosis/{diagnosis_id}")
async def get_diagnosis(diagnosis_id: str):
    # 查询数据库
    # 返回详情
    return DiagnosisResponse(...)

# 4. 列表诊断
@app.get("/diagnoses")
async def list_diagnoses(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None
):
    # 查询数据库（支持分页和过滤）
    # 返回列表
    return List[DiagnosisResponse]

# 5. 取消诊断
@app.post("/diagnosis/{diagnosis_id}/cancel")
async def cancel_diagnosis(diagnosis_id: str):
    # 查找任务
    # 如果运行中，发送取消信号
    # 更新状态为 cancelled
    return {"diagnosis_id": ..., "status": "cancelled"}
```

---

## HTTP 状态码

| 代码 | 说明 | 场景 |
|------|------|------|
| 200 | 成功 | 正常请求 |
| 400 | 请求错误 | 参数验证失败 |
| 401 | 未授权 | 需要认证 |
| 404 | 不存在 | 诊断 ID 不存在 |
| 409 | 冲突 | 任务已存在/状态冲突 |
| 500 | 服务器错误 | 后端异常 |
| 503 | 服务不可用 | 维护中 |

---

## 最后更新

- 📅 文档更新时间: 2026-02-05
- 🔄 API 版本: v1.0
- ✅ 前端实现: 4/5 端点
- 🚀 后端实现: 待开发
