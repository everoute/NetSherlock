# 前后端对接问题分析

> 生成时间: 2026-02-06
> 分支: dev (已 rebase zwtop/web)

## 概述

zwtop/web 分支增加了前端展示功能，但前后端尚未对接。本文档详细列出所有不匹配和缺失项。

## P0: 阻塞性问题 (前端无法编译)

### 1. `web/src/lib/` 目录完全为空 — 缺少核心模块

所有页面都 import 了三个不存在的模块：

| 缺失模块 | 被依赖的页面 |
|----------|-------------|
| `@/lib/api` | NewTaskPage, TasksPage, TaskDetailPage, ReportsPage, ReportDetailPage |
| `@/lib/utils` | TaskDetailPage (`formatRelativeTime`, `formatDuration`, `copyToClipboard`), TasksPage (`formatRelativeTime`, `formatTaskName`) |
| `@/lib/auth` | LoginPage (`useAuth` hook), ProtectedRoute |

**前端目前无法编译。** 需要创建这三个文件。

## P1: API 不匹配 (会导致运行时错误)

### 2. 端口不匹配

| 端 | 端口 |
|----|------|
| 前端 `.env.example` | `VITE_API_URL=http://localhost:8000` |
| 后端 CLI 默认值 | `--port 8080` |

### 3. 无 CORS 配置

后端 `webhook.py` 没有配置 `CORSMiddleware`。前端 Vite dev server 通常运行在 `localhost:5173`，跨域请求会被浏览器拦截。

### 4. 后端 `DiagnosisResponse` 缺失大量前端需要的字段

前端 `types/index.ts` 定义的 `DiagnosisResponse` 有 12 个字段，后端只返回 7 个：

| 字段 | 前端期望 | `GET /diagnose/{id}` 返回 | `GET /diagnoses` 返回 |
|------|---------|--------------------------|---------------------|
| `diagnosis_id` | string | 有 | 有 |
| `status` | DiagnosisStatus | 有 | 有 |
| `timestamp` | string | 有 | 有 |
| `mode` | string | 无 | 无 |
| `summary` | string | 有 | 有 |
| `root_cause` | typed object | 有 | 无 |
| `recommendations` | typed array | 有 | 无 |
| `started_at` | string | **无** | **无** |
| `completed_at` | string | **无** | **无** |
| `diagnosis_type` | string | **无** | **无** |
| `network_type` | string | **无** | **无** |
| `trigger_source` | string | **无** | **无** |
| `markdown_report` | string | **无** | **无** |
| `logs` | LogFile[] | **无** | **无** |
| `error` | string | **无** | **无** |
| `message` | (后端有，前端无) | 有 | — |

**影响分析：**
- `started_at` / `completed_at` 缺失 → TaskDetailPage 的时间线和耗时计算显示 "N/A"
- `diagnosis_type` / `network_type` 缺失 → TasksPage 类型列显示 "Unknown"
- `trigger_source` 缺失 → TasksPage 触发源图标全部显示默认的 "Unknown Trigger"
- `markdown_report` 缺失 → TaskDetailPage 和 ReportDetailPage 的完整报告 Markdown 渲染区不会显示
- `logs` 缺失 → TaskDetailPage 的日志查看器 Tab 不会出现
- `error` 缺失 → TaskDetailPage 错误信息不会显示

### 5. Status 值不匹配

| 场景 | 后端实际返回 | 前端期望 |
|------|------------|---------|
| 创建诊断任务后 | `"queued"` (webhook.py:803) | `"pending"` |
| 执行中（注释中提到） | `"processing"` | `"running"` |

后端 `DiagnosisResult` 内部用的 `DiagnosisStatus` enum 值是 `pending/running/...`，但 webhook handler 直接硬编码返回 `"queued"`。

### 6. `/diagnoses` 列表接口返回数据过于简略

后端 (webhook.py:880-892) 只返回 `diagnosis_id, status, timestamp, summary`。
前端 TasksPage 需要 `diagnosis_type`, `network_type`, `trigger_source`, `started_at`；
ReportsPage 需要 `root_cause`。

## P2: 功能缺失 (前端有按钮但后端无实现)

### 7. 缺少 Cancel 端点

- 前端 TaskDetailPage 和 TasksPage 都有 Cancel 按钮
- 后端没有 `POST /diagnosis/{id}/cancel` 端点

### 8. 缺少 Retry 端点

- 前端 TasksPage 对 error/interrupted/cancelled 状态显示 Retry 按钮
- 后端没有 retry 相关端点

### 9. 缺少 Status 过滤参数

- 前端 TasksPage 有状态过滤下拉框
- 后端 `GET /diagnoses` 只支持 `limit` 和 `offset`，不支持 `status` 参数

### 10. Download PDF 按钮无实现

- ReportDetailPage 有 "Download PDF" 按钮
- 后端没有 PDF 生成/下载端点

## P3: 架构/配置问题

### 11. 认证体系不完整

- 前端 LoginPage 使用本地 mock auth，hardcoded admin/admin
- 后端使用 `X-API-Key` header 认证
- 两套认证体系完全独立

### 12. `DiagnosisResult` 有丰富数据但 API 层未透传

后端内部 `DiagnosisResult` (schemas/result.py) 已经存储了 `started_at`, `completed_at`, `markdown_report`, `error`, `mode` 等字段，但 webhook.py 的 API 响应序列化时没有包含这些字段。

## 关键发现

后端 `DiagnosisResult` dataclass 已经有前端需要的所有数据，问题只是 webhook.py 的 API 响应模型没有透传这些字段。修复成本很低——扩展 `DiagnosisResponse` + 修改序列化逻辑即可。
