# 前后端交互 API 规范

## 概述

NetSherlock 应用前后端交互使用 RESTful API，基础 URL 为 `http://localhost:8000`（可通过 `VITE_API_URL` 环境变量配置）。

## API 端点列表

### 1. 健康检查

**端点**: `GET /health`

**描述**: 检查 API 服务是否可用

**请求**:
```bash
GET http://localhost:8000/health
```

**响应** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2026-02-05T08:00:00Z",
  "queue_size": 5,
  "engine": "claude-agent-sdk"
}
```

**响应字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 服务状态（healthy/degraded/unhealthy） |
| timestamp | string | 检查时间戳（ISO 8601 格式） |
| queue_size | number | 当前诊断任务队列大小 |
| engine | string | 诊断引擎名称（可选） |

---

### 2. 创建诊断任务

**端点**: `POST /diagnose`

**描述**: 创建一个新的网络诊断任务

**请求**:
```bash
POST http://localhost:8000/diagnose
Content-Type: application/json

{
  "network_type": "vm",
  "diagnosis_type": "latency",
  "src_host": "host1",
  "src_vm": "vm-001",
  "dst_host": "host2",
  "dst_vm": "vm-002",
  "description": "Test latency between two VMs",
  "mode": "autonomous",
  "options": {
    "timeout": 30000,
    "sample_count": 100
  }
}
```

**请求字段**:
| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| network_type | string | ✅ | 诊断网络类型：`vm` 或 `system` |
| diagnosis_type | string | ✅ | 诊断类型：`latency`、`packet_drop` 或 `connectivity` |
| src_host | string | ❌ | 源主机名/IP |
| src_vm | string | ❌ | 源虚拟机 ID |
| src_vm_name | string | ❌ | 源虚拟机名称 |
| dst_host | string | ❌ | 目标主机名/IP |
| dst_vm | string | ❌ | 目标虚拟机 ID |
| dst_vm_name | string | ❌ | 目标虚拟机名称 |
| description | string | ❌ | 诊断描述 |
| mode | string | ❌ | 运行模式：`autonomous` 或 `interactive` |
| options | object | ❌ | 其他选项（灵活扩展） |

**响应** (200 OK):
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

**错误响应** (400 Bad Request):
```json
{
  "error": "Invalid network_type",
  "details": "network_type must be 'vm' or 'system'"
}
```

---

### 3. 获取诊断详情

**端点**: `GET /diagnosis/{id}`

**描述**: 获取指定诊断任务的详细信息

**请求**:
```bash
GET http://localhost:8000/diagnosis/diag-20260205-080000-vm-latency
```

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| id | string | 诊断任务 ID |

**响应** (200 OK):
```json
{
  "diagnosis_id": "diag-20260205-080000-vm-latency",
  "status": "completed",
  "timestamp": "2026-02-05T08:00:00Z",
  "started_at": "2026-02-05T08:00:05Z",
  "completed_at": "2026-02-05T08:05:00Z",
  "mode": "autonomous",
  "diagnosis_type": "latency",
  "network_type": "vm",
  "trigger_source": "manual",
  "summary": "Detected VM latency due to physical network congestion",
  "root_cause": {
    "category": "physical_network",
    "component": "Network Interface",
    "confidence": 0.85,
    "evidence": [
      "Physical link utilization at 92%",
      "Packet loss rate 2.3%",
      "Latency jitter detected"
    ]
  },
  "recommendations": [
    {
      "priority": 1,
      "action": "Upgrade network bandwidth",
      "rationale": "Current bandwidth insufficient for traffic volume"
    }
  ],
  "markdown_report": "# Diagnosis Report\n...",
  "logs": [
    {
      "name": "sender-host.log",
      "content": "[2026-02-05 08:00:05] Starting latency measurement...\n..."
    },
    {
      "name": "receiver-host.log",
      "content": "[2026-02-05 08:00:05] Receiving probe packets...\n..."
    },
    {
      "name": "analysis.log",
      "content": "[2026-02-05 08:05:00] Analysis complete...\n..."
    }
  ]
}
```

**响应字段**:
| 字段 | 类型 | 说明 |
|------|------|------|
| diagnosis_id | string | 诊断任务唯一标识 |
| status | string | 任务状态 |
| timestamp | string | 创建时间 |
| started_at | string | 开始执行时间（可选） |
| completed_at | string | 完成时间（可选） |
| mode | string | 运行模式 |
| diagnosis_type | string | 诊断类型 |
| network_type | string | 网络类型 |
| trigger_source | string | 触发源 |
| summary | string | 诊断摘要（可选） |
| root_cause | object | 根本原因分析（可选） |
| recommendations | array | 建议列表（可选） |
| markdown_report | string | 完整 Markdown 报告（可选） |
| logs | array | 诊断日志文件列表（可选） |
| error | string | 错误信息（可选） |

**错误响应** (404 Not Found):
```json
{
  "error": "Diagnosis not found",
  "diagnosis_id": "diag-20260205-080000-vm-latency"
}
```

---

### 4. 列出所有诊断任务

**端点**: `GET /diagnoses`

**描述**: 获取诊断任务列表（支持分页和过滤）

**请求**:
```bash
GET http://localhost:8000/diagnoses?limit=50&offset=0&status=completed
```

**查询参数**:
| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | number | 50 | 返回结果数量上限 |
| offset | number | 0 | 分页偏移量 |
| status | string | 无 | 过滤状态（pending/running/completed/error 等） |

**响应** (200 OK):
```json
[
  {
    "diagnosis_id": "diag-20260205-180000-system-latency",
    "status": "completed",
    "timestamp": "2026-02-05T18:00:00Z",
    "started_at": "2026-02-05T18:00:05Z",
    "completed_at": "2026-02-05T18:15:00Z",
    "diagnosis_type": "latency",
    "network_type": "system",
    "trigger_source": "alert"
  },
  {
    "diagnosis_id": "diag-20260205-170000-vm-drops",
    "status": "running",
    "timestamp": "2026-02-05T17:00:00Z",
    "started_at": "2026-02-05T17:05:00Z",
    "diagnosis_type": "packet_drop",
    "network_type": "vm",
    "trigger_source": "webhook"
  }
]
```

**分页信息**（可选响应头）:
```
X-Total-Count: 1234
X-Page-Count: 25
X-Current-Page: 1
```

---

### 5. 取消诊断任务

**端点**: `POST /diagnosis/{id}/cancel`

**描述**: 取消正在运行的诊断任务

**请求**:
```bash
POST http://localhost:8000/diagnosis/diag-20260205-080000-vm-latency/cancel
```

**路径参数**:
| 参数 | 类型 | 说明 |
|------|------|------|
| id | string | 诊断任务 ID |

**响应** (200 OK):
```json
{
  "diagnosis_id": "diag-20260205-080000-vm-latency",
  "status": "cancelled",
  "cancelled_at": "2026-02-05T08:02:30Z"
}
```

**错误响应** (400 Bad Request - 任务已完成):
```json
{
  "error": "Cannot cancel completed task",
  "current_status": "completed"
}
```

---

## 任务状态流转

```
pending → running → completed ✓
           ↓
         waiting
           ↓
       completed ✓

running/waiting → cancelled ✓

running/pending → error ✓

running → interrupted ✓
```

**状态说明**:
| 状态 | 说明 |
|------|------|
| pending | 等待执行 |
| running | 正在执行 |
| waiting | 等待资源或依赖 |
| completed | 成功完成 |
| cancelled | 用户取消 |
| error | 执行出错 |
| interrupted | 被中断 |

---

## 根本原因分类

```typescript
type RootCauseCategory =
  | 'vm_internal'        // VM 内部问题
  | 'host_internal'      // 主机内部问题
  | 'vhost_processing'   // vhost 处理问题
  | 'physical_network'   // 物理网络问题
  | 'configuration'      // 配置问题
  | 'resource_contention'// 资源竞争
  | 'unknown'            // 未知原因
```

---

## 诊断类型和网络类型组合

| 诊断类型 | 网络类型 | 说明 |
|---------|---------|------|
| latency | vm | VM 之间的延迟 |
| latency | system | 物理主机之间的延迟 |
| packet_drop | vm | VM 之间的丢包 |
| packet_drop | system | 物理主机之间的丢包 |
| connectivity | vm | VM 连通性 |
| connectivity | system | 物理主机连通性 |

---

## 错误处理

### 通用错误响应格式

```json
{
  "error": "Error message",
  "error_code": "INVALID_REQUEST",
  "details": "Additional details",
  "timestamp": "2026-02-05T08:00:00Z"
}
```

### HTTP 状态码

| 状态码 | 说明 |
|--------|------|
| 200 | 请求成功 |
| 400 | 请求参数错误 |
| 401 | 未授权 |
| 403 | 禁止访问 |
| 404 | 资源不存在 |
| 409 | 冲突（如重复创建） |
| 500 | 服务器内部错误 |
| 503 | 服务不可用 |

---

## 认证

目前前端暂未实现与后端的认证集成。后续需要添加：

- [ ] 登录 API：`POST /auth/login` - 获取认证令牌
- [ ] 登出 API：`POST /auth/logout` - 撤销认证令牌
- [ ] 刷新令牌：`POST /auth/refresh` - 刷新过期的令牌
- [ ] 验证令牌：`GET /auth/verify` - 验证令牌有效性

所有 API 请求应在 Authorization 头中包含令牌：
```
Authorization: Bearer <token>
```

---

## 环境配置

**.env 文件配置**:
```env
# API 基础 URL
VITE_API_URL=http://localhost:8000

# 是否使用模拟数据（开发用）
VITE_USE_MOCK_DATA=false
```

---

## 使用示例

### 创建并监控诊断任务

```javascript
// 1. 创建任务
const response = await api.createDiagnosis({
  network_type: 'vm',
  diagnosis_type: 'latency',
  src_vm: 'vm-001',
  dst_vm: 'vm-002',
  description: 'Check latency'
})

const diagnosisId = response.diagnosis_id

// 2. 轮询获取状态
let diagnosis = await api.getDiagnosis(diagnosisId)
while (diagnosis.status === 'running' || diagnosis.status === 'waiting') {
  await new Promise(resolve => setTimeout(resolve, 2000)) // 等待 2 秒
  diagnosis = await api.getDiagnosis(diagnosisId)
}

// 3. 获取最终结果
console.log('诊断完成:', diagnosis.summary)
console.log('根本原因:', diagnosis.root_cause)
```

---

## 实现清单

| API | 状态 | 前端调用位置 |
|-----|------|-----------|
| GET /health | ❌ 未使用 | - |
| POST /diagnose | ✅ 已实现 | NewTaskPage.tsx |
| GET /diagnosis/{id} | ✅ 已实现 | TaskDetailPage.tsx, ReportDetailPage.tsx |
| GET /diagnoses | ✅ 已实现 | TasksPage.tsx, ReportsPage.tsx |
| POST /diagnosis/{id}/cancel | ❌ 实现但未测试 | TaskDetailPage.tsx (按钮存在但无实现) |

---

## 后续需要实现的功能

- [ ] WebSocket 支持实时任务更新（替代轮询）
- [ ] 批量操作 API
- [ ] 高级搜索和过滤
- [ ] 认证和授权
- [ ] API 速率限制
- [ ] 请求签名和验证
