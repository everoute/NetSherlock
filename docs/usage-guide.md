# NetSherlock 使用指南

> 版本: 1.0
> 日期: 2026-01-20

---

## 目录

1. [概述](#概述)
2. [安装与配置](#安装与配置)
3. [工作模式](#工作模式)
4. [CLI 使用](#cli-使用)
5. [Webhook API 使用](#webhook-api-使用)
6. [配置参考](#配置参考)
7. [故障排除](#故障排除)

---

## 概述

NetSherlock 是一个 AI 驱动的网络故障诊断工具，采用四层诊断架构：

| 层级 | 名称 | 功能 |
|------|------|------|
| L1 | 基础监控 | 查询 Grafana/Loki 指标和日志 |
| L2 | 环境感知 | 收集网络拓扑（VM/系统网络环境） |
| L3 | 精确测量 | 执行 BPF 工具进行分段延迟测量 |
| L4 | 诊断分析 | 分析数据、定位根因、生成报告 |

### 支持的诊断类型

| 类型 | 描述 |
|------|------|
| `latency` | 网络延迟诊断 |
| `packet_drop` | 丢包诊断 |
| `connectivity` | 连通性诊断 |

---

## 安装与配置

### 1. 安装

```bash
# 使用 uv 安装
uv sync

# 或使用 pip
pip install -e .
```

### 2. 配置环境变量

复制示例配置文件并修改：

```bash
cp .env.example .env
```

### 3. 必需配置

| 配置项 | 描述 | 示例 |
|--------|------|------|
| `LLM_API_KEY` | Anthropic API 密钥 | `sk-ant-xxx` |
| `GRAFANA_BASE_URL` | Grafana 地址 | `http://192.168.79.79/grafana` |
| `GRAFANA_USERNAME` | Grafana 用户名 | `admin` |
| `GRAFANA_PASSWORD` | Grafana 密码 | `password` |
| `SSH_PRIVATE_KEY_PATH` | SSH 私钥路径 | `~/.ssh/id_rsa` |

### 4. 可选配置

| 配置项 | 描述 | 默认值 |
|--------|------|--------|
| `LLM_MODEL` | Claude 模型 | `claude-sonnet-4-20250514` |
| `DIAGNOSIS_DEFAULT_MODE` | 默认诊断模式 | `interactive` |
| `WEBHOOK_API_KEY` | Webhook 认证密钥 | 无 |

---

## 工作模式

NetSherlock 支持两种核心工作模式：

### 模式 1: Interactive（人机协作模式）

**特点**：
- 在关键节点暂停，等待用户确认
- 用户可以修改诊断方向或取消操作
- CLI 默认使用此模式

**检查点**：
1. **问题分类确认** - L2 环境收集后，确认问题类型
2. **测量计划确认** - L3 测量前，确认测量方案
3. **深入诊断确认** - L4 分析后，是否继续深入

**适用场景**：
- 首次诊断未知问题
- 需要人工判断的复杂场景
- 希望了解诊断过程的用户

### 模式 2: Autonomous（全自主模式）

**特点**：
- 全流程自动执行，无需人工干预
- 快速完成诊断并输出报告
- 支持中途中断

**适用场景**：
- 已知问题类型的快速诊断
- 告警自动响应
- 批量诊断任务

### 模式选择逻辑

```
优先级（从高到低）：
1. 命令行 --mode 参数
2. 命令行 --autonomous / --interactive 标志
3. 配置文件 DIAGNOSIS_DEFAULT_MODE
4. 默认值：interactive
```

---

## CLI 使用

### 基本命令

```bash
# 查看帮助
netsherlock --help

# 查看版本
netsherlock --version

# 查看当前配置
netsherlock config
```

### 诊断命令

#### 基本语法

```bash
netsherlock diagnose --network-type <TYPE> --src-host <IP> [OPTIONS]
```

#### 必需参数

| 参数 | 短选项 | 描述 |
|------|--------|------|
| `--network-type` | `-n` | 网络类型: `vm` (VM 网络) 或 `system` (系统网络) |
| `--src-host` | | 源主机 IP 地址（执行诊断的宿主机） |

#### VM 网络参数

| 参数 | 描述 | 条件 |
|------|------|------|
| `--src-vm` | 源 VM UUID | `--network-type vm` 时必需 |
| `--dst-host` | 目标主机 IP | VM 间诊断时需要 |
| `--dst-vm` | 目标 VM UUID | 与 `--dst-host` 配合使用 |

#### 诊断参数

| 参数 | 短选项 | 描述 | 默认值 |
|------|--------|------|--------|
| `--type` | `-t` | 诊断类型 (`latency`, `packet_drop`, `connectivity`) | `latency` |
| `--duration` | `-d` | 测量持续时间（秒） | `30` |
| `--mode` | `-m` | 诊断模式 (`autonomous`, `interactive`) | `interactive` |
| `--autonomous` | | 快捷方式：使用自主模式 | - |
| `--interactive` | | 快捷方式：使用交互模式 | - |

#### 全局选项

| 选项 | 描述 |
|------|------|
| `-v, --verbose` | 启用详细输出 |
| `--json` | 输出 JSON 格式 |

#### 参数验证规则

**VM 网络诊断** (`--network-type vm`):
- `--src-vm` 必需
- 如果指定 `--dst-host`，则 `--dst-vm` 也必需
- 如果指定 `--dst-vm`，则 `--dst-host` 也必需

### 使用示例

#### 示例 1: 单 VM 网络诊断（交互模式）

```bash
netsherlock diagnose \
  --network-type vm \
  --src-host 192.168.1.10 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --type latency
```

输出示例：
```
Diagnosis Request: a1b2c3d4
  Network Type: vm
  Source Host: 192.168.1.10
  Source VM: ae6aa164-604c-4cb0-84b8-2dea034307f1
  Type: latency
  Mode: interactive
  Duration: 30s

Starting diagnosis...

============================================================
CHECKPOINT: problem_classification
============================================================

Summary: Detected VM network latency issue

Details:
  problem_type: vm_network_latency
  confidence: 85%
  indicators:
    - vhost CPU usage: 78%
    - OVS tx_errors: 234

Recommendation: Proceed with VM latency breakdown measurement

Options:
  1. Confirm and continue
  2. Modify classification
  3. Cancel diagnosis

Enter choice (1=Confirm, 2=Modify, 3=Cancel) [1]: 1
Confirmed. Continuing...
```

#### 示例 2: VM 间网络诊断（自主模式）

```bash
netsherlock diagnose \
  --network-type vm \
  --src-host 192.168.1.10 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.1.20 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency \
  --autonomous
```

输出示例：
```
Diagnosis Request: e5f6g7h8
  Network Type: vm
  Source Host: 192.168.1.10
  Source VM: ae6aa164-604c-4cb0-84b8-2dea034307f1
  Destination Host: 192.168.1.20
  Destination VM: bf7bb275-715d-5dc1-95c9-3feb045418g2
  Type: latency
  Mode: autonomous
  Duration: 30s

Starting diagnosis...

============================================================
DIAGNOSIS RESULT
============================================================

Diagnosis ID: e5f6g7h8
Status: completed
Mode: autonomous
Summary: VM-to-VM network latency bottleneck identified in vhost processing

Root Cause:
  category: vhost_processing
  component: vhost-net worker thread
  confidence: 85

Recommendations:
  1. Check vhost worker CPU affinity (priority: high)
  2. Review VM vCPU scheduling (priority: medium)

Duration: 45.3s
```

#### 示例 3: 指定测量时长

```bash
netsherlock diagnose \
  --network-type vm \
  --src-host 192.168.1.10 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --type latency \
  --duration 60
```

#### 示例 4: JSON 输出

```bash
netsherlock --json diagnose \
  --network-type vm \
  --src-host 192.168.1.10 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --autonomous
```

输出示例：
```json
{
  "diagnosis_id": "i9j0k1l2",
  "status": "completed",
  "mode": "autonomous",
  "summary": "Network latency within normal range",
  "root_cause": {
    "category": "none",
    "confidence": 90
  },
  "recommendations": [],
  "started_at": "2026-01-20T10:30:00",
  "completed_at": "2026-01-20T10:30:45",
  "error": null
}
```

### 环境收集命令

#### 系统网络环境

```bash
netsherlock env system --host <IP> [--port-type <TYPE>]
```

参数：
| 参数 | 描述 | 可选值 |
|------|------|--------|
| `--host` | 目标主机 IP | |
| `--port-type` | 过滤端口类型 | `mgt`, `storage`, `access`, `vpc` |

示例：
```bash
# 收集所有系统网络信息
netsherlock env system --host 192.168.1.10

# 只收集存储网络
netsherlock env system --host 192.168.1.10 --port-type storage
```

#### VM 网络环境

```bash
netsherlock env vm --host <IP> --vm-id <UUID>
```

参数：
| 参数 | 描述 |
|------|------|
| `--host` | 宿主机 IP |
| `--vm-id` | VM UUID |

示例：
```bash
netsherlock env vm --host 192.168.1.10 --vm-id ae6aa164-604c-4cb0-84b8-2dea034307f1
```

### 监控查询命令

#### 查询指标

```bash
netsherlock query metrics '<PROMQL>' [OPTIONS]
```

参数：
| 参数 | 描述 | 默认值 |
|------|------|--------|
| `PROMQL` | PromQL 查询表达式 | - |
| `--start` | 开始时间 | `-1h` |
| `--end` | 结束时间 | `now` |
| `--step` | 查询步长 | `1m` |

示例：
```bash
# 查询主机网络延迟
netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}'

# 指定时间范围
netsherlock query metrics 'up' --start "-30m" --end "now"
```

#### 查询日志

```bash
netsherlock query logs '<LOGQL>' [OPTIONS]
```

参数：
| 参数 | 描述 | 默认值 |
|------|------|--------|
| `LOGQL` | LogQL 查询表达式 | - |
| `--start` | 开始时间 | `-1h` |
| `--end` | 结束时间 | `now` |
| `--limit` | 最大返回条数 | `100` |

示例：
```bash
# 查询服务日志
netsherlock query logs '{service="nginx"} |= "error"' --limit 50
```

### 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 诊断成功完成 |
| 1 | 诊断失败（错误） |
| 2 | 用户取消诊断 |
| 3 | 诊断被中断 |
| 130 | Ctrl+C 中断 |

---

## Webhook API 使用

### 启动服务

```bash
# 使用 uvicorn 启动
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8000

# 或使用脚本
python -m netsherlock.api.webhook
```

### 认证

所有 API 端点（除 `/health`）需要 API Key 认证：

```bash
# 请求头
X-API-Key: your-api-key-here
```

配置 API Key：
```bash
# .env
WEBHOOK_API_KEY=your-secret-api-key
```

### API 端点

#### 健康检查

```
GET /health
```

响应：
```json
{"status": "healthy", "version": "0.1.0"}
```

#### Alertmanager Webhook

```
POST /webhook/alertmanager
```

用于接收 Alertmanager 告警并自动触发诊断。

请求体示例：
```json
{
  "status": "firing",
  "alerts": [
    {
      "status": "firing",
      "labels": {
        "alertname": "VMNetworkLatency",
        "instance": "192.168.1.10:9100",
        "severity": "warning",
        "vm_name": "test-vm-01"
      },
      "annotations": {
        "summary": "VM network latency > 5ms",
        "description": "High latency detected on VM network"
      }
    }
  ]
}
```

响应：
```json
{
  "status": "accepted",
  "diagnosis_id": "diag-a1b2c3d4",
  "mode": "autonomous",
  "message": "Diagnosis started in autonomous mode"
}
```

#### 手动诊断

```
POST /diagnose
```

请求体：
```json
{
  "network_type": "vm",
  "problem_type": "latency",
  "src_host": "192.168.1.10",
  "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
  "dst_host": "192.168.1.20",
  "dst_vm": "bf7bb275-715d-5dc1-95c9-3feb045418g2",
  "mode": "interactive",
  "description": "High latency observed between VMs"
}
```

参数说明：
| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `network_type` | string | 是 | 网络类型 (`vm`, `system`) |
| `problem_type` | string | 是 | 诊断类型 (`latency`, `packet_drop`, `connectivity`) |
| `src_host` | string | 是 | 源主机 IP |
| `src_vm` | string | 条件 | 源 VM UUID (`network_type=vm` 时必需) |
| `dst_host` | string | 否 | 目标主机 IP (VM 间诊断时需要) |
| `dst_vm` | string | 条件 | 目标 VM UUID (与 `dst_host` 配合使用) |
| `mode` | string | 否 | 诊断模式 (`autonomous`, `interactive`) |
| `description` | string | 否 | 问题描述 |

响应：
```json
{
  "status": "accepted",
  "diagnosis_id": "diag-e5f6g7h8",
  "mode": "interactive",
  "message": "Diagnosis started in interactive mode"
}
```

#### 查询诊断状态

```
GET /diagnose/{diagnosis_id}
```

响应：
```json
{
  "diagnosis_id": "diag-e5f6g7h8",
  "status": "completed",
  "mode": "autonomous",
  "result": {
    "summary": "...",
    "root_cause": {...},
    "recommendations": [...]
  }
}
```

#### 列出诊断

```
GET /diagnoses
```

查询参数：
| 参数 | 描述 | 默认值 |
|------|------|--------|
| `limit` | 返回数量 | 10 |
| `status` | 过滤状态 | 无 |

响应：
```json
{
  "diagnoses": [
    {"diagnosis_id": "diag-xxx", "status": "completed", ...},
    {"diagnosis_id": "diag-yyy", "status": "running", ...}
  ],
  "total": 2
}
```

### Alertmanager 配置示例

```yaml
# alertmanager.yml
receivers:
  - name: 'netsherlock'
    webhook_configs:
      - url: 'http://netsherlock:8000/webhook/alertmanager'
        http_config:
          headers:
            X-API-Key: 'your-api-key'
        send_resolved: false

route:
  receiver: 'netsherlock'
  routes:
    - match:
        alertname: 'VMNetworkLatency'
      receiver: 'netsherlock'
    - match:
        alertname: 'HostNetworkLatency'
      receiver: 'netsherlock'
```

---

## 配置参考

### 完整配置示例

```bash
# .env

# ===== 基础设施 =====
DEBUG=false

# SSH 配置
SSH_DEFAULT_USER=root
SSH_DEFAULT_PORT=22
SSH_PRIVATE_KEY_PATH=~/.ssh/id_rsa
SSH_CONNECT_TIMEOUT=10
SSH_COMMAND_TIMEOUT=60
SSH_MAX_CONNECTIONS=10

# Grafana 配置
GRAFANA_BASE_URL=http://192.168.79.79/grafana
GRAFANA_USERNAME=o11y
GRAFANA_PASSWORD=your_password

# BPF 工具配置
BPF_LOCAL_TOOLS_PATH=~/workspace/troubleshooting-tools/measurement-tools
BPF_REMOTE_TOOLS_PATH=/tmp/netsherlock-tools
BPF_DEPLOY_MODE=auto

# ===== LLM 配置 =====
LLM_API_KEY=sk-ant-xxx
LLM_MODEL=claude-sonnet-4-20250514
LLM_MAX_TOKENS=4096
LLM_TEMPERATURE=0.0
LLM_COMPACT_PROMPTS=false

# ===== 诊断模式配置 =====
DIAGNOSIS_DEFAULT_MODE=interactive
DIAGNOSIS_AUTONOMOUS_ENABLED=true
DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=false
DIAGNOSIS_INTERACTIVE_TIMEOUT_SECONDS=300

# ===== Webhook 配置 =====
WEBHOOK_API_KEY=your-secret-api-key
WEBHOOK_ALLOW_INSECURE=false

# ===== 日志配置 =====
LOG_LEVEL=INFO
LOG_FORMAT=console
```

### 配置项详解

#### LLM 配置

| 配置项 | 环境变量 | 描述 | 默认值 |
|--------|----------|------|--------|
| API Key | `LLM_API_KEY` 或 `ANTHROPIC_API_KEY` | Claude API 密钥 | 无 |
| 模型 | `LLM_MODEL` | 使用的 Claude 模型 | `claude-sonnet-4-20250514` |
| 最大 Token | `LLM_MAX_TOKENS` | 响应最大 token 数 | `4096` |
| 温度 | `LLM_TEMPERATURE` | 生成温度 (0.0-1.0) | `0.0` |
| 紧凑提示 | `LLM_COMPACT_PROMPTS` | 使用紧凑提示词减少 token | `false` |

#### 诊断模式配置

| 配置项 | 环境变量 | 描述 | 默认值 |
|--------|----------|------|--------|
| 默认模式 | `DIAGNOSIS_DEFAULT_MODE` | 默认诊断模式 | `interactive` |
| 启用自主模式 | `DIAGNOSIS_AUTONOMOUS_ENABLED` | 是否允许自主模式 | `false` |
| 自动 Agent 循环 | `DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP` | Webhook 触发时自动执行 | `false` |
| 交互超时 | `DIAGNOSIS_INTERACTIVE_TIMEOUT_SECONDS` | 检查点等待超时（秒） | `300` |

#### 已知告警类型

以下告警类型可触发自主模式（当 `DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true`）：

- `VMNetworkLatency`
- `HostNetworkLatency`

---

## 故障排除

### 常见问题

#### 1. API Key 未配置

错误：
```
Error: LLM API key not configured
```

解决：
```bash
# 设置环境变量
export LLM_API_KEY=sk-ant-xxx

# 或在 .env 文件中配置
LLM_API_KEY=sk-ant-xxx
```

#### 2. SSH 连接失败

错误：
```
Error: SSH connection failed to 192.168.1.10
```

检查：
- SSH 私钥路径是否正确
- 目标主机是否可达
- SSH 用户是否有权限

#### 3. Grafana 查询失败

错误：
```
Error: Grafana query failed: 401 Unauthorized
```

检查：
- Grafana URL 是否正确
- 用户名密码是否正确
- 用户是否有查询权限

#### 4. 检查点超时

错误：
```
Error: Checkpoint timed out waiting for user input
```

解决：
- 增加超时时间：`DIAGNOSIS_INTERACTIVE_TIMEOUT_SECONDS=600`
- 或使用自主模式：`--autonomous`

### 调试模式

启用详细日志：
```bash
# 命令行
netsherlock -v diagnose --host 192.168.1.10

# 环境变量
export LOG_LEVEL=DEBUG
export DEBUG=true
```

### 日志位置

```bash
# 配置日志文件
LOG_FILE_PATH=/var/log/netsherlock/netsherlock.log
```

---

## 快速参考卡

```
# 单 VM 网络诊断（交互模式）
netsherlock diagnose -n vm --src-host <IP> --src-vm <UUID> -t latency

# 单 VM 网络诊断（自主模式）
netsherlock diagnose -n vm --src-host <IP> --src-vm <UUID> -t latency --autonomous

# VM 间网络诊断
netsherlock diagnose -n vm \
  --src-host <SRC_IP> --src-vm <SRC_UUID> \
  --dst-host <DST_IP> --dst-vm <DST_UUID> \
  -t latency

# JSON 输出
netsherlock --json diagnose -n vm --src-host <IP> --src-vm <UUID> --autonomous

# 收集系统环境
netsherlock env system -h <IP>

# 收集 VM 环境
netsherlock env vm -h <IP> --vm-id <UUID>

# 查询指标
netsherlock query metrics '<PROMQL>'

# 查询日志
netsherlock query logs '<LOGQL>'

# 查看配置
netsherlock config
```
