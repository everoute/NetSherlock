# Curl 快速参考 - 系统网络探测

> 常用的 curl 命令速查表

---

## 基本设置

### 设置环境变量

```bash
export API_URL="http://localhost:8000"
export API_KEY="test-key-12345"
export SRC_HOST="192.168.79.11"
export DST_HOST="192.168.79.12"
```

### 验证设置

```bash
echo "API URL: $API_URL"
echo "API Key: $API_KEY"
echo "Source: $SRC_HOST"
echo "Destination: $DST_HOST"
```

---

## 创建诊断任务

### 1. 延迟探测 (Latency)

```bash
curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'",
    "description": "测试延迟"
  }'
```

### 2. 丢包检测 (Packet Drop)

```bash
curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "packet_drop",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'",
    "description": "测试丢包"
  }'
```

### 3. 连通性测试 (Connectivity)

```bash
curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "connectivity",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'",
    "description": "测试连通性"
  }'
```

### 4. 交互模式诊断

```bash
curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'",
    "mode": "interactive"
  }'
```

### 5. 最小请求 (最少参数)

```bash
curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'"
  }'
```

---

## 查询任务状态

### 1. 获取单个任务

```bash
# 替换 {DIAGNOSIS_ID} 为实际的任务 ID
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}"

# 示例
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/diag-20260206-120000-system-latency"
```

### 2. 获取最新 10 个任务

```bash
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnoses?limit=10"
```

### 3. 获取最新 50 个任务

```bash
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnoses?limit=50"
```

### 4. 分页查询

```bash
# 获取第 2 页（跳过前 10 个）
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnoses?limit=10&offset=10"
```

### 5. 带 jq 格式化的查询

```bash
# 仅显示关键信息
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}" | \
  jq '{id: .diagnosis_id, status: .status, timestamp: .timestamp}'

# 列出所有任务的摘要
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnoses?limit=10" | \
  jq '.[] | {id: .diagnosis_id, status: .status, type: .diagnosis_type}'
```

---

## 获取诊断报告

### 1. 获取完整报告

```bash
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}/report" | jq '.'
```

### 2. 仅提取摘要

```bash
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}/report" | \
  jq '.summary'
```

### 3. 保存报告到文件

```bash
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}/report" | \
  jq '.' > report-{DIAGNOSIS_ID}.json
```

---

## 任务管理

### 1. 取消任务

```bash
curl -X POST \
  -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}/cancel"
```

### 2. 验证任务被取消

```bash
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}" | \
  jq '.status'
```

---

## 组合操作

### 1. 创建任务并保存 ID

```bash
DIAGNOSIS_ID=$(curl -s -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'"
  }' | jq -r '.diagnosis_id')

echo "Created task: $DIAGNOSIS_ID"
```

### 2. 创建任务并立即检查状态

```bash
# 创建任务
RESPONSE=$(curl -s -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'"
  }')

DIAGNOSIS_ID=$(echo $RESPONSE | jq -r '.diagnosis_id')
echo "Task created: $DIAGNOSIS_ID"

# 检查状态
sleep 2
curl -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/$DIAGNOSIS_ID" | jq '.status'
```

### 3. 监控任务直到完成

```bash
DIAGNOSIS_ID="diag-20260206-120000-system-latency"

while true; do
  STATUS=$(curl -s -H "X-API-Key: $API_KEY" \
    "$API_URL/diagnose/$DIAGNOSIS_ID" | jq -r '.status')
  
  echo "Status: $STATUS - $(date)"
  
  if [[ "$STATUS" == "completed" ]] || [[ "$STATUS" == "error" ]]; then
    break
  fi
  
  sleep 5
done

echo "Task finished with status: $STATUS"
```

### 4. 创建任务、监控并获取报告

```bash
#!/bin/bash

# 1. 创建任务
echo "Creating diagnosis task..."
DIAGNOSIS_ID=$(curl -s -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'"
  }' | jq -r '.diagnosis_id')

echo "Task ID: $DIAGNOSIS_ID"

# 2. 监控任务
echo "Waiting for task completion..."
while true; do
  STATUS=$(curl -s -H "X-API-Key: $API_KEY" \
    "$API_URL/diagnose/$DIAGNOSIS_ID" | jq -r '.status')
  
  echo -ne "\rStatus: $STATUS"
  
  if [[ "$STATUS" == "completed" ]] || [[ "$STATUS" == "error" ]]; then
    echo ""
    break
  fi
  
  sleep 5
done

# 3. 获取报告
echo "Fetching report..."
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/$DIAGNOSIS_ID/report" | jq '.'
```

---

## 批量操作

### 1. 创建多个并行任务

```bash
for probe_type in latency packet_drop connectivity; do
  echo "Creating $probe_type probe..."
  
  RESPONSE=$(curl -s -X POST $API_URL/diagnose \
    -H "X-API-Key: $API_KEY" \
    -H "Content-Type: application/json" \
    -d '{
      "network_type": "system",
      "diagnosis_type": "'$probe_type'",
      "src_host": "'$SRC_HOST'",
      "dst_host": "'$DST_HOST'"
    }')
  
  DIAGNOSIS_ID=$(echo $RESPONSE | jq -r '.diagnosis_id')
  echo "  Task ID: $DIAGNOSIS_ID"
  
  sleep 1
done
```

### 2. 查询所有任务并按状态分类

```bash
echo "=== By Status ===" && \
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnoses?limit=50" | \
  jq 'group_by(.status) | map({status: .[0].status, count: length})'
```

### 3. 查询所有任务并按类型统计

```bash
echo "=== By Diagnosis Type ===" && \
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnoses?limit=50" | \
  jq 'group_by(.diagnosis_type) | map({type: .[0].diagnosis_type, count: length})'
```

---

## 高级用法

### 1. 使用 Headers 文件

创建 `headers.txt`：
```
X-API-Key: test-key-12345
Content-Type: application/json
```

使用：
```bash
curl -X POST $API_URL/diagnose \
  -H @headers.txt \
  -d @request.json
```

### 2. 从文件读取请求体

创建 `request.json`：
```json
{
  "network_type": "system",
  "diagnosis_type": "latency",
  "src_host": "192.168.79.11",
  "dst_host": "192.168.79.12"
}
```

使用：
```bash
curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d @request.json
```

### 3. 输出详细调试信息

```bash
curl -v -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "system",
    "diagnosis_type": "latency",
    "src_host": "'$SRC_HOST'",
    "dst_host": "'$DST_HOST'"
  }'
```

### 4. 设置超时时间

```bash
# 10 秒超时
curl --max-time 10 \
  -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}"
```

### 5. 使用代理

```bash
curl -x http://proxy.example.com:8080 \
  -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/{DIAGNOSIS_ID}"
```

---

## 常用一行命令

```bash
# 列出所有任务的 ID 和状态
curl -s -H "X-API-Key: $API_KEY" "$API_URL/diagnoses" | jq '.[] | "\(.diagnosis_id) - \(.status)"'

# 查找 completed 状态的任务
curl -s -H "X-API-Key: $API_KEY" "$API_URL/diagnoses" | jq '.[] | select(.status=="completed") | .diagnosis_id'

# 统计各状态的任务数
curl -s -H "X-API-Key: $API_KEY" "$API_URL/diagnoses" | jq 'group_by(.status) | map({status: .[0].status, count: length})'

# 获取最新任务的报告
LATEST=$(curl -s -H "X-API-Key: $API_KEY" "$API_URL/diagnoses?limit=1" | jq -r '.[0].diagnosis_id') && \
curl -s -H "X-API-Key: $API_KEY" "$API_URL/diagnose/$LATEST/report" | jq '.'

# 创建任务并打印完整响应
curl -s -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"network_type":"system","diagnosis_type":"latency","src_host":"'$SRC_HOST'","dst_host":"'$DST_HOST'"}' | jq '.'
```

---

## 错误排查

### 检查 API 是否可用

```bash
curl -v http://localhost:8000/
```

### 检查认证

```bash
curl -H "X-API-Key: wrong-key" "$API_URL/diagnose"
```

### 验证请求格式

```bash
curl -X POST $API_URL/diagnose \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"network_type":"system","src_host":"192.168.79.11"}' \
  -w "\nStatus: %{http_code}\n"
```

---

**提示**: 将常用的 curl 命令保存为 bash 别名或脚本，以便快速执行！

---

版本: 1.0 | 最后更新: 2026-02-06
