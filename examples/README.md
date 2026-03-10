# NetSherlock 系统网络探测 - 示例集合

> 创建和管理系统网络诊断任务的实用示例和脚本

---

## 📋 文档目录

### 主要指南

- **[SYSTEM_NETWORK_PROBE_GUIDE.md](./SYSTEM_NETWORK_PROBE_GUIDE.md)** - 完整的系统网络探测指南
  - 概述和原理
  - 探测类型详解
  - API 请求格式
  - 响应示例
  - 常见问题

### 可运行脚本

| 脚本 | 语言 | 说明 |
|------|------|------|
| [`create_system_network_probe.py`](#python-脚本) | Python | 创建单个系统网络探测任务 |
| [`create_system_network_probe.sh`](#bash-脚本) | Bash | 创建单个系统网络探测任务 |
| [`test_system_probe.sh`](#完整测试脚本) | Bash | 完整的测试流程演示 |

---

## 快速开始

### 前置条件

1. **后端服务运行中**
   ```bash
   # 假设后端服务运行在 localhost:8000
   http://localhost:8000
   ```

2. **获得 API Key**
   ```bash
   export API_KEY="test-key-12345"
   ```

3. **获得源和目的主机 IP**
   ```bash
   export SRC_HOST="192.168.79.11"
   export DST_HOST="192.168.79.12"
   ```

### 最简单的方式 - 使用 curl

创建一个延迟探测任务：

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

## Python 脚本

### 安装依赖

```bash
pip install requests
```

### 使用方式

#### 基本用法

```bash
# 创建延迟探测
python3 create_system_network_probe.py latency

# 创建丢包检测
python3 create_system_network_probe.py packet_drop

# 创建连通性测试
python3 create_system_network_probe.py connectivity
```

#### 自定义参数

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

# 指定 API 地址
python3 create_system_network_probe.py latency \
  --api-url http://192.168.1.100:8000 \
  --api-key my-secret-key
```

#### 使用环境变量

```bash
export API_URL="http://localhost:8000"
export API_KEY="test-key-12345"
export SRC_HOST="192.168.79.11"
export DST_HOST="192.168.79.12"

python3 create_system_network_probe.py latency
```

#### 完整示例

```python
#!/usr/bin/env python3
import subprocess
import sys

# 创建三种类型的诊断任务
for probe_type in ["latency", "packet_drop", "connectivity"]:
    print(f"\n创建 {probe_type} 诊断...")
    result = subprocess.run([
        "python3", "create_system_network_probe.py", probe_type,
        "--src-host", "192.168.79.11",
        "--dst-host", "192.168.79.12",
        "--description", f"自动诊断: {probe_type}"
    ])
    
    if result.returncode != 0:
        print(f"创建 {probe_type} 失败")
        sys.exit(1)
```

---

## Bash 脚本

### 前置条件

- bash >= 4.0
- curl
- jq（JSON 处理，可选但推荐）

### 安装 jq

```bash
# Ubuntu/Debian
sudo apt-get install jq

# macOS
brew install jq

# RHEL/CentOS
sudo yum install jq
```

### 使用方式

#### 基本用法

```bash
# 创建延迟探测
bash create_system_network_probe.sh latency

# 创建丢包检测
bash create_system_network_probe.sh packet_drop

# 创建连通性测试
bash create_system_network_probe.sh connectivity
```

#### 自定义参数

```bash
# 使用环境变量
API_URL=http://localhost:8000 \
API_KEY=test-key-12345 \
SRC_HOST=192.168.79.11 \
DST_HOST=192.168.79.12 \
bash create_system_network_probe.sh latency
```

#### 保存 API Key 和主机信息

创建 `.env` 文件：

```bash
cat > .env << 'EOF'
export API_URL="http://localhost:8000"
export API_KEY="test-key-12345"
export SRC_HOST="192.168.79.11"
export DST_HOST="192.168.79.12"
EOF

# 使用时
source .env
bash create_system_network_probe.sh latency
```

---

## 完整测试脚本

### 功能

`test_system_probe.sh` 是一个完整的演示脚本，展示：

1. ✅ 创建多个诊断任务（延迟、丢包、连通性）
2. ✅ 监控任务执行进度
3. ✅ 获取诊断报告
4. ✅ 演示取消任务
5. ✅ 列出所有任务

### 使用方式

```bash
# 基本运行
bash test_system_probe.sh

# 自定义参数
API_URL=http://localhost:8000 \
API_KEY=test-key-12345 \
SRC_HOST=192.168.79.11 \
DST_HOST=192.168.79.12 \
bash test_system_probe.sh
```

### 预期输出

```
╔════════════════════════════════════════════════════════════╗
║  NetSherlock 系统网络探测 - 完整测试
╚════════════════════════════════════════════════════════════╝

ℹ️  API 地址: http://localhost:8000
ℹ️  源主机: 192.168.79.11
ℹ️  目标主机: 192.168.79.12

▶ 检查 API 可用性...
✅ API 可用

📊 1️⃣  创建诊断任务
▶ 创建 latency 诊断任务...
✅ 任务已创建: diag-20260206-120000-system-latency
...
```

---

## curl 命令示例

### 1. 创建延迟探测

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

### 2. 创建丢包检测

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

### 3. 创建连通性测试

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

### 4. 查询任务状态

```bash
# 获取单个任务
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/diag-20260206-120000-system-latency"

# 列出所有任务
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnoses?limit=10"
```

### 5. 获取诊断报告

```bash
curl -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/diag-20260206-120000-system-latency/report"
```

### 6. 取消任务

```bash
curl -X POST \
  -H "X-API-Key: test-key-12345" \
  "http://localhost:8000/diagnose/diag-20260206-120000-system-latency/cancel"
```

---

## 工作流示例

### 完整的诊断流程

```bash
#!/bin/bash

# 1. 设置变量
API_URL="http://localhost:8000"
API_KEY="test-key-12345"
SRC_HOST="192.168.79.11"
DST_HOST="192.168.79.12"

# 2. 创建诊断任务
echo "创建诊断任务..."
RESPONSE=$(curl -s -X POST "$API_URL/diagnose" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"network_type\": \"system\",
    \"diagnosis_type\": \"latency\",
    \"src_host\": \"$SRC_HOST\",
    \"dst_host\": \"$DST_HOST\"
  }")

DIAGNOSIS_ID=$(echo $RESPONSE | jq -r '.diagnosis_id')
echo "任务 ID: $DIAGNOSIS_ID"

# 3. 监控任务进度
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

# 4. 获取报告
echo "获取诊断报告..."
curl -s -H "X-API-Key: $API_KEY" \
  "$API_URL/diagnose/$DIAGNOSIS_ID/report" | jq '.'

# 5. 完成
echo "诊断完成！"
```

### 批量创建多个任务

```bash
#!/bin/bash

# 为不同的主机对创建诊断
declare -a host_pairs=(
  "192.168.79.11:192.168.79.12"
  "192.168.79.11:192.168.79.13"
  "192.168.79.12:192.168.79.13"
)

for pair in "${host_pairs[@]}"; do
  src_host="${pair%:*}"
  dst_host="${pair#*:}"
  
  echo "创建 $src_host → $dst_host 的诊断..."
  
  python3 create_system_network_probe.py latency \
    --src-host "$src_host" \
    --dst-host "$dst_host" \
    --description "定期诊断: $src_host → $dst_host"
  
  sleep 2
done
```

---

## 集成到 CI/CD

### Jenkins Pipeline 示例

```groovy
pipeline {
    agent any
    
    environment {
        API_URL = 'http://localhost:8000'
        API_KEY = credentials('netsherlock-api-key')
    }
    
    stages {
        stage('Create Network Probe') {
            steps {
                sh '''
                    python3 create_system_network_probe.py latency \
                        --api-url $API_URL \
                        --api-key $API_KEY \
                        --src-host 192.168.79.11 \
                        --dst-host 192.168.79.12 \
                        --description "CI/CD automated probe"
                '''
            }
        }
    }
}
```

### GitHub Actions 示例

```yaml
name: Network Probe

on:
  schedule:
    - cron: '0 * * * *'  # 每小时运行一次

jobs:
  probe:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Create System Network Probe
        env:
          API_URL: ${{ secrets.API_URL }}
          API_KEY: ${{ secrets.API_KEY }}
          SRC_HOST: 192.168.79.11
          DST_HOST: 192.168.79.12
        run: |
          python3 -m pip install requests
          python3 create_system_network_probe.py latency
```

---

## 故障排查

### API 连接错误

**问题**: `curl: (7) Failed to connect to localhost port 8000`

**解决方案**:
1. 确认后端服务正在运行
2. 检查 API 地址是否正确
3. 尝试直接访问: `curl http://localhost:8000/health`

### 认证错误

**问题**: `{"detail": "Invalid or missing API key"}`

**解决方案**:
1. 检查 X-API-Key header 是否正确设置
2. 确认 API Key 未过期
3. 使用正确的 API Key 值

### 任务创建失败

**问题**: `{"detail": "Invalid network_type"}`

**解决方案**:
1. 确保 `network_type` 为 `"system"`（不是 `"vm"`）
2. 确保 `src_host` 和 `dst_host` 有效

---

## 参考资源

- 📚 [系统网络探测完整指南](./SYSTEM_NETWORK_PROBE_GUIDE.md)

---

## 许可证

这些示例脚本是 NetSherlock 项目的一部分。

---

**版本**: 1.0  
**最后更新**: 2026-02-06  
**维护者**: NetSherlock 项目团队
