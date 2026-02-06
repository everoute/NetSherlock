# 系统网络探测任务 - 完整指南

> 如何通过 NetSherlock API 创建和管理系统网络（主机到主机）诊断探测任务

---

## 📋 目录

1. [概述](#概述)
2. [系统网络探测类型](#系统网络探测类型)
3. [快速开始](#快速开始)
4. [使用 curl 创建任务](#使用-curl-创建任务)
5. [使用 Python 脚本](#使用-python-脚本)
6. [使用 Bash 脚本](#使用-bash-脚本)
7. [API 请求格式](#api-请求格式)
8. [响应示例](#响应示例)
9. [监控任务状态](#监控任务状态)
10. [常见问题](#常见问题)

---

## 概述

### 什么是系统网络探测？

系统网络探测是对**主机到主机**（host-to-host）网络连接进行诊断的过程。它测量和分析两个物理主机或虚拟机宿主机之间的网络性能。

### 支持的探测类型

| 探测类型 | 说明 | 用途 |
|---------|------|------|
| **latency** | 延迟测量 | 测量主机间网络延迟，定位延迟瓶颈 |
| **packet_drop** | 丢包检测 | 检测主机间是否存在丢包问题 |
| **connectivity** | 连通性测试 | 验证两主机间的网络连接是否正常 |

### 网络类型

```
┌─────────────────────────────────────┐
│          网络类型                    │
├─────────────────┬───────────────────┤
│  VM Network     │   System Network  │
│  (虚拟机网络)   │   (主机网络)      │
├─────────────────┼───────────────────┤
│ VM ↔ VM         │  Host ↔ Host      │
│ 跨主机虚拟机    │  物理或虚拟机宿主 │
└─────────────────┴───────────────────┘
```

---

## 系统网络探测类型

### 1. 延迟探测 (Latency)

**目的**: 测量和分析主机间的网络延迟

**应用场景**:
- 应用响应时间慢
- 需要定位延迟瓶颈
- 优化网络路径

**测量指标**:
- RTT（往返时间）
- 延迟分布
- 路径延迟

**示例请求**:
```bash
curl -X POST http://localhost:8000/diagnose \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12"
  }'
```

---

### 2. 丢包检测 (Packet Drop)

**目的**: 检测主机间的丢包问题

**应用场景**:
- 间歇性连接问题
- 数据传输错误
- 网络不稳定

**检测方法**:
- 持续发送数据包
- 统计丢包数和丢包率
- 定位丢包位置

**示例请求**:
```bash
curl -X POST http://localhost:8000/diagnose \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "packet_drop",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12"
  }'
```

---

### 3. 连通性测试 (Connectivity)

**目的**: 验证主机间的基本网络连接

**应用场景**:
- 验证网络连接是否正常
- 故障排查的第一步
- 配置验证

**检查项**:
- ICMP 可达性
- TCP/UDP 连接
- DNS 解析

**示例请求**:
```bash
curl -X POST http://localhost:8000/diagnose \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "connectivity",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12"
  }'
```

---

## 快速开始

### 前置条件

- NetSherlock 后端服务已启动（默认地址: `http://localhost:8000`）
- 获得 API Key（默认: `test-key-12345`）
- 已获取源和目的主机的管理 IP 地址

### 最简单的方式

使用 curl 创建一个延迟探测任务：

```bash
curl -X POST http://localhost:8000/diagnose \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12",
    "description": "测试主机11到主机12的延迟"
  }'
```

**预期响应**:
```json
{
  "diagnosis_id": "diag-20260206-120000-system-latency",
  "status": "pending",
  "timestamp": "2026-02-06T12:00:00Z",
  "mode": "autonomous"
}
```

---

## 使用 curl 创建任务

### 基本命令格式

```bash
curl -X POST {API_URL}/diagnose \
  -H "X-API-Key: {API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{JSON_BODY}'
```

### 示例 1: 创建延迟探测

```bash
curl -X POST http://localhost:8000/diagnose \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12",
    "description": "诊断主机间的网络延迟"
  }'
```

### 示例 2: 创建丢包检测

```bash
curl -X POST http://localhost:8000/diagnose \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "packet_drop",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12",
    "description": "检测主机间是否存在丢包"
  }'
```

### 示例 3: 创建交互模式探测

```bash
curl -X POST http://localhost:8000/diagnose \
  -H "X-API-Key: test-key-12345" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12",
    "mode": "interactive",
    "description": "交互模式下的延迟诊断"
  }'
```

### 环境变量方式

设置环境变量后可以简化命令：

```bash
export API_URL="http://localhost:8000"
export API_KEY="test-key-12345"
export SRC_HOST="192.168.79.11"
export DST_HOST="192.168.79.12"

curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"network_type\": \"system\",
    \"diagnosis_type\": \"latency\",
    \"src_host\": \"$SRC_HOST\",
    \"dst_host\": \"$DST_HOST\"
  }"
```

---

## 使用 Python 脚本

### 前置条件

```bash
pip install requests
```

### 运行脚本

```bash
# 创建延迟探测
python3 create_system_network_probe.py latency

# 创建丢包检测
python3 create_system_network_probe.py packet_drop

# 创建连通性测试
python3 create_system_network_probe.py connectivity
```

### 自定义参数

```bash
# 指定源和目的主机
python3 create_system_network_probe.py latency \
  --src-host 192.168.79.11 \
  --dst-host 192.168.79.12

# 指定交互模式
python3 create_system_network_probe.py latency \
  --mode interactive

# 添加描述
python3 create_system_network_probe.py latency \
  --description "故障排查：测试主机间延迟"
```

### 环境变量

```bash
export API_URL="http://localhost:8000"
export API_KEY="test-key-12345"
export SRC_HOST="192.168.79.11"
export DST_HOST="192.168.79.12"

python3 create_system_network_probe.py latency
```

---

## 使用 Bash 脚本

### 运行脚本

```bash
# 创建延迟探测
bash create_system_network_probe.sh latency

# 创建丢包检测
bash create_system_network_probe.sh packet_drop

# 创建连通性测试
bash create_system_network_probe.sh connectivity
```

### 自定义参数

```bash
# 指定源和目的主机
API_URL=http://localhost:8000 \
API_KEY=test-key-12345 \
SRC_HOST=192.168.79.11 \
DST_HOST=192.168.79.12 \
bash create_system_network_probe.sh latency
```

### 前置条件

- bash >= 4.0
- curl
- jq（用于 JSON 格式化，可选）

---

## API 请求格式

### 请求端点

```
POST /diagnose
```

### 请求头

| 字段 | 值 | 说明 |
|------|-----|------|
| `X-API-Key` | `{api_key}` | 认证密钥（必需）|
| `Content-Type` | `application/json` | 内容类型（必需）|

### 请求体参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `network_type` | string | ✅ | - | 网络类型：`system` |
| `diagnosis_type` | string | ❌ | `latency` | 诊断类型：`latency`, `packet_drop`, `connectivity` |
| `src_host` | string | ✅ | - | 源主机管理 IP |
| `dst_host` | string | ✅ | - | 目标主机管理 IP |
| `mode` | string | ❌ | 自动 | 诊断模式：`autonomous`, `interactive` |
| `description` | string | ❌ | - | 问题描述 |

### 最小请求示例

```json
{
  "network_type": "system",
  "src_host": "192.168.79.11",
  "dst_host": "192.168.79.12"
}
```

### 完整请求示例

```json
{
  "network_type": "system",
  "diagnosis_type": "latency",
  "src_host": "192.168.79.11",
  "dst_host": "192.168.79.12",
  "mode": "autonomous",
  "description": "诊断主机间网络延迟问题"
}
```

---

## 响应示例

### 成功响应 (HTTP 200)

```json
{
  "diagnosis_id": "diag-20260206-120000-system-latency",
  "status": "pending",
  "timestamp": "2026-02-06T12:00:00Z",
  "mode": "autonomous",
  "summary": "System network latency diagnosis initiated",
  "message": "Diagnosis request queued for processing"
}
```

### 响应字段说明

| 字段 | 说明 |
|------|------|
| `diagnosis_id` | 诊断任务的唯一 ID，用于跟踪 |
| `status` | 当前状态：`pending`, `running`, `waiting`, `completed`, `error`, `interrupted`, `cancelled` |
| `timestamp` | 任务创建时间 (ISO 8601 格式) |
| `mode` | 诊断模式：`autonomous` 或 `interactive` |
| `summary` | 任务摘要 |
| `message` | 返回的消息 |

### 常见错误响应

#### 缺少必需参数

```json
{
  "detail": [
    {
      "loc": ["body", "src_host"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

#### 认证失败

```json
{
  "detail": "Invalid or missing API key"
}
```

#### 无效的网络类型

```json
{
  "detail": "Invalid network_type. Must be 'vm' or 'system'"
}
```

---

## 监控任务状态

### 获取单个任务状态

```bash
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/{diagnosis_id}"
```

**示例**:
```bash
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/diag-20260206-120000-system-latency"
```

### 列出所有任务

```bash
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnoses?limit=10"
```

### 获取诊断报告

等任务完成后，获取诊断报告：

```bash
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/{diagnosis_id}/report"
```

### 取消任务

只能取消处于 `pending` 或 `waiting` 状态的任务：

```bash
curl -X POST \
  -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/{diagnosis_id}/cancel"
```

### 监控任务进度的完整流程

```bash
#!/bin/bash

DIAGNOSIS_ID="diag-20260206-120000-system-latency"
API_KEY="test-key-12345"
API_URL="http://localhost:8000"

# 1. 创建任务
echo "创建任务..."
RESPONSE=$(curl -s -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "192.168.79.11",
    "dst_host": "192.168.79.12"
  }')

DIAGNOSIS_ID=$(echo $RESPONSE | jq -r '.diagnosis_id')
echo "任务 ID: $DIAGNOSIS_ID"

# 2. 轮询任务状态
echo "等待任务完成..."
while true; do
  STATUS=$(curl -s -H "X-API-Key: $API_KEY" \
    "$API_URL/diagnose/$DIAGNOSIS_ID" | jq -r '.status')
  
  echo "状态: $STATUS"
  
  if [[ "$STATUS" == "completed" ]] || [[ "$STATUS" == "error" ]]; then
    break
  fi
  
  sleep 5
done

# 3. 获取报告
echo "获取诊断报告..."
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/$DIAGNOSIS_ID/report" | jq '.'
```

---

## 常见问题

### Q: 任务在什么时候完成？

**A**: 任务完成时间取决于：
- 诊断类型（latency 通常最快，packet_drop 需要更多时间）
- 网络状况
- 系统负载

一般来说：
- 延迟测试: 30 秒 - 2 分钟
- 丢包检测: 1 - 5 分钟
- 连通性测试: 10 - 30 秒

### Q: 如何中途停止任务？

**A**: 只能取消处于 `pending` 或 `waiting` 状态的任务。对于 `running` 状态的任务，需要等待其完成或出错。

```bash
curl -X POST \
  -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/{id}/cancel"
```

### Q: 如何重新执行一个已取消的任务？

**A**: 使用相同的参数再次调用 API 创建新任务。系统会分配新的 diagnosis_id。

### Q: API 返回 401 错误是什么原因？

**A**: 这表示 API 认证失败。检查：
1. X-API-Key header 是否设置正确
2. API Key 是否过期
3. 请求是否包含了该 header

### Q: 如何指定测试 IP 地址？

**A**: 使用 `src_test_ip` 和 `dst_test_ip` 参数：

```json
{
  "network_type": "system",
  "diagnosis_type": "latency",
  "src_host": "192.168.79.11",
  "dst_host": "192.168.79.12",
  "src_test_ip": "10.0.1.100",
  "dst_test_ip": "10.0.2.100"
}
```

### Q: 如何查看完整的诊断日志？

**A**: 在任务状态为 `running` 时，访问任务详情页面：

```bash
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/{id}"
```

任务完成后，获取完整报告：

```bash
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/{id}/report"
```

### Q: 可以同时运行多个任务吗？

**A**: 可以。每个任务都有独立的 diagnosis_id，可以并行运行多个诊断任务。

---

## 相关文档

- 📄 [诊断状态对齐报告](../docs/diagnosis-status-alignment-report.md)
- 📋 [诊断状态摘要](../docs/diagnosis-status-analysis-summary.md)
- ⚡ [快速参考](../docs/diagnosis-status-quick-reference.md)
- 📚 [API 规范](../docs/api-specification.md)

---

**版本**: 1.0  
**最后更新**: 2026-02-06
