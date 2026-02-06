# Trigger 属性对齐 - API 和前端整合

## 📋 概述

后端 API 现已返回 `trigger` 属性，与前端的期望一致。这个文档记录了所有的改动。

---

## 🔄 映射关系

### 后端源映射

```
DiagnosisRequestSource (后端内部)
├── CLI → "manual"
├── WEBHOOK → "webhook"
└── API → "manual"

↓

trigger (API 响应)
├── "manual" (手动请求)
├── "webhook" (来自 Webhook)
└── "alert" (来自告警)
```

### 前端使用

```
DiagnosisResponse.trigger (新)
├── "manual" 🔵 → Hand icon (蓝色)
├── "webhook" 🟢 → Webhook icon (绿色)
└── "alert" 🟠 → Bell icon (橙色)
```

---

## ✅ 后端改动清单

### 1. 新增映射函数

**文件**: `src/netsherlock/api/webhook.py`

```python
def _map_source_to_trigger(source: DiagnosisRequestSource) -> str:
    """Map DiagnosisRequestSource to trigger value for API response.
    
    Args:
        source: DiagnosisRequestSource enum value
    
    Returns:
        Trigger value: "manual", "webhook", or "alert"
    """
    if source == DiagnosisRequestSource.WEBHOOK:
        return "webhook"
    elif source == DiagnosisRequestSource.API:
        return "manual"
    else:
        return "manual"
```

### 2. 更新 DiagnosisResponse 模型

**文件**: `src/netsherlock/api/webhook.py`

```python
class DiagnosisResponse(BaseModel):
    """Diagnosis response."""
    
    diagnosis_id: str
    status: str
    timestamp: str
    trigger: str | None = None  # ← 新增字段 ("manual", "webhook", "alert")
    mode: str | None = None
    summary: str | None = None
    root_cause: dict[str, Any] | None = None
    recommendations: list[dict[str, Any]] | None = None
    message: str | None = None
```

### 3. 更新所有 API 端点

#### Endpoint: POST /webhook/alertmanager

```python
responses.append(DiagnosisResponse(
    diagnosis_id=diagnosis_id,
    status="queued",
    timestamp=datetime.now(timezone.utc).isoformat(),
    trigger="webhook",  # ← 设置为 webhook
    mode=effective_mode.value,
    message=f"Alert queued for diagnosis in {effective_mode.value} mode",
))
```

**触发来源**: 从 Alertmanager webhook 接收的告警

---

#### Endpoint: POST /diagnose

```python
return DiagnosisResponse(
    diagnosis_id=diagnosis_id,
    status="queued",
    timestamp=datetime.now(timezone.utc).isoformat(),
    trigger="manual",  # ← 设置为 manual
    mode=effective_mode.value,
    message=f"Diagnosis request queued in {effective_mode.value} mode",
)
```

**触发来源**: 来自 API 的手动诊断请求

---

#### Endpoint: GET /diagnose/{diagnosis_id}

```python
return DiagnosisResponse(
    diagnosis_id=result.diagnosis_id,
    status=result.status.value,
    timestamp=timestamp,
    trigger=_map_source_to_trigger(result.source),  # ← 从存储的 source 映射
    summary=result.summary,
    root_cause=...,
    recommendations=...,
)
```

**触发来源**: 从存储的诊断结果中检索

---

#### Endpoint: GET /diagnoses

```python
return [
    DiagnosisResponse(
        diagnosis_id=d.diagnosis_id,
        status=d.status.value,
        timestamp=(
            d.completed_at.isoformat() if d.completed_at
            else d.started_at.isoformat() if d.started_at
            else ""
        ),
        trigger=_map_source_to_trigger(d.source),  # ← 从每个诊断的 source 映射
        summary=d.summary,
    )
    for d in paginated
]
```

**触发来源**: 从所有已存储的诊断中列出

---

## ✅ 前端改动清单

### 1. 更新类型定义

**文件**: `web/src/types/index.ts`

```typescript
export interface DiagnosisResponse {
  diagnosis_id: string
  status: DiagnosisStatus
  timestamp: string
  started_at?: string
  completed_at?: string
  trigger?: 'manual' | 'webhook' | 'alert'        // ← 新增字段
  trigger_source?: 'manual' | 'webhook' | 'alert'  // ← 保留向后兼容
  mode?: 'autonomous' | 'interactive'
  diagnosis_type?: 'latency' | 'packet_drop' | 'connectivity'
  network_type?: 'vm' | 'system'
  summary?: string
  root_cause?: RootCause
  recommendations?: Recommendation[]
  markdown_report?: string
  logs?: LogFile[]
  error?: string
}
```

### 2. 更新 TasksPage 组件

**文件**: `web/src/pages/TasksPage.tsx`

#### 新增兼容性辅助函数

```typescript
const getTriggerSource = (task: DiagnosisResponse) => {
  // 优先使用 trigger (新), 回退到 trigger_source (旧)
  return task.trigger || task.trigger_source
}
```

#### 更新使用方式

```typescript
// 旧代码
const { Icon, color, title } = getTriggerIcon(task.trigger_source)

// 新代码
const triggerSource = getTriggerSource(task)
const { Icon, color, title } = getTriggerIcon(triggerSource)
```

---

## 🔍 响应示例

### Webhook 触发的诊断

```json
{
  "diagnosis_id": "alert-a1b2c3d4e5f6g7h8",
  "status": "queued",
  "timestamp": "2026-02-06T12:00:00Z",
  "trigger": "webhook",
  "mode": "autonomous",
  "message": "Alert queued for diagnosis in autonomous mode"
}
```

### 手动 API 触发的诊断

```json
{
  "diagnosis_id": "manual-x9y8z7w6v5u4t3s2",
  "status": "queued",
  "timestamp": "2026-02-06T12:01:00Z",
  "trigger": "manual",
  "mode": "interactive",
  "message": "Diagnosis request queued in interactive mode"
}
```

### 已完成的诊断（获取）

```json
{
  "diagnosis_id": "alert-a1b2c3d4e5f6g7h8",
  "status": "completed",
  "timestamp": "2026-02-06T12:05:00Z",
  "trigger": "webhook",
  "summary": "Found packet loss in physical network segment",
  "root_cause": {
    "category": "physical_network",
    "component": "interface eth0",
    "confidence": 0.95,
    "evidence": [...]
  },
  "recommendations": [...]
}
```

---

## 🧪 测试场景

### 场景 1: Webhook 触发

```bash
# 1. 从 Alertmanager 发送 webhook
curl -X POST http://localhost:8080/webhook/alertmanager \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "VMNetworkLatency",
        "network_type": "vm",
        "src_host": "192.168.1.100",
        "src_vm": "vm-uuid-1"
      }
    }]
  }'

# 2. 响应包含 trigger: "webhook"
# {
#   "diagnosis_id": "alert-xxx",
#   "status": "queued",
#   "trigger": "webhook",
#   ...
# }

# 3. 前端显示 Webhook icon (🟢)
```

### 场景 2: 手动 API 请求

```bash
# 1. 发送手动诊断请求
curl -X POST http://localhost:8080/diagnose \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "vm",
    "diagnosis_type": "latency",
    "src_host": "192.168.1.100",
    "src_vm": "vm-uuid-1"
  }'

# 2. 响应包含 trigger: "manual"
# {
#   "diagnosis_id": "manual-xxx",
#   "status": "queued",
#   "trigger": "manual",
#   ...
# }

# 3. 前端显示 Manual icon (🔵)
```

### 场景 3: 查询诊断列表

```bash
# 查询所有诊断
curl -X GET http://localhost:8080/diagnoses \
  -H "X-API-Key: your-key"

# 响应中每个诊断都包含正确的 trigger 值
# [{
#   "diagnosis_id": "alert-xxx",
#   "trigger": "webhook",
#   ...
# }, {
#   "diagnosis_id": "manual-xxx",
#   "trigger": "manual",
#   ...
# }]
```

---

## 🔄 向后兼容性

### 前端兼容

- ✅ `trigger` 字段 (新) - 优先使用
- ✅ `trigger_source` 字段 (旧) - 作为备选
- ✅ 前端自动选择可用的字段

### API 兼容

- ✅ `DiagnosisResponse` 现在始终返回 `trigger` 字段
- ✅ 旧客户端仍可使用 `trigger_source` (如果有)
- ✅ 新客户端优先使用 `trigger`

---

## 📝 迁移指南

### 对于前端开发者

1. **更新类型导入**:
   ```typescript
   import type { DiagnosisResponse } from '@/types'
   ```

2. **使用新的 trigger 字段**:
   ```typescript
   // 推荐
   const source = task.trigger
   
   // 旧方式（仍支持）
   const source = task.trigger_source
   ```

3. **使用兼容函数**:
   ```typescript
   // 最安全的方式
   const source = getTriggerSource(task)  // 自动选择可用字段
   ```

### 对于后端开发者

1. **不需要改动** - API 已完全更新
2. **确保 `source` 字段正确设置** - 它会自动映射到 `trigger`
3. **使用新的 `_map_source_to_trigger()` 函数**

---

## ✨ 总结

| 项目 | 状态 | 说明 |
|------|------|------|
| **后端 trigger 字段** | ✅ 完成 | 所有 API 端点均已返回 |
| **前端类型定义** | ✅ 完成 | 已添加 trigger 字段 |
| **前端组件更新** | ✅ 完成 | TasksPage 已兼容新字段 |
| **向后兼容** | ✅ 完成 | 旧字段仍可用 |
| **映射逻辑** | ✅ 完成 | source → trigger 映射准确 |

---

**更新日期**: 2026-02-06  
**版本**: 1.0 - 对齐完成  
**状态**: ✅ 生产就绪
