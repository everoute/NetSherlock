# NetSherlock 用户指南

> 版本: 2.1
> 日期: 2026-01-26
> 状态: MVP 完成 (Skill-Driven Architecture)

---

## 目录

1. [概述](#概述)
2. [快速开始](#快速开始)
3. [CLI 与 Webhook 的区别](#cli-与-webhook-的区别)
4. [准备配置文件](#准备配置文件)
5. [CLI 使用](#cli-使用)
6. [Webhook API 使用](#webhook-api-使用)
7. [工作模式](#工作模式)
8. [环境变量配置](#环境变量配置)
9. [故障排除](#故障排除)

---

## 概述

NetSherlock 是一个 AI 驱动的网络故障诊断工具，采用 **Skill 驱动的四层诊断架构**：

| 层级 | 名称 | 实现方式 | 功能 |
|------|------|----------|------|
| L1 | 基础监控 | 直接工具调用 | Grafana/Loki 指标和日志查询 |
| L2 | 环境感知 | `network-env-collector` Skill | SSH 收集 OVS、vhost、NIC 映射 |
| L3 | 精确测量 | `vm-latency-measurement` Skill | BPF 工具部署、8 点协调测量 |
| L4 | 诊断分析 | `vm-latency-analysis` Skill | 日志解析、延迟归因、报告生成 |

### 核心特性

- **Skill 驱动**: L2/L3/L4 通过 Claude Code Skills 执行
- **配置文件必需**: 所有诊断都需要配置文件提供 SSH 和测试参数
- **双入口支持**: CLI 命令行诊断和 Webhook 告警触发

### 支持的诊断类型

| 类型 | 描述 |
|------|------|
| `latency` | 网络延迟诊断（默认） |
| `packet_drop` | 丢包诊断 |
| `connectivity` | 连通性诊断 |

---

## 快速开始

### 快速选择

- **我想快速诊断一个问题** → 使用 [CLI 模式](#cli-使用)
- **我想设置告警自动响应** → 使用 [Webhook 模式](#webhook-api-使用)

### 1. 安装

```bash
uv sync
# 或
pip install -e .
```

### 2. 准备配置文件

**这是必需步骤！** 没有配置文件无法运行诊断。

```bash
# 复制模板
cp config/minimal-input-template.yaml config/my-diagnosis.yaml

# 编辑配置文件，填入实际的 SSH 和测试参数
vim config/my-diagnosis.yaml
```

### 3. 运行诊断

```bash
netsherlock diagnose \
  --config config/my-diagnosis.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency
```

---

## CLI 与 Webhook 的区别

NetSherlock 支持两种使用方式，它们的配置和适用场景不同：

### CLI 模式（命令行）

适用场景：
- 手动诊断单个网络问题
- 开发调试
- 脚本集成

配置方式：
- 使用 `--config` 参数指定 `minimal-input.yaml`
- 在 CLI 命令中指定源和目标节点

```bash
netsherlock diagnose --config config/minimal-input.yaml ...
```

特点：
- 快速启动
- 支持交互模式（检查点确认）
- 配置简洁（仅包含被诊断的节点）

### Webhook 模式（告警驱动）

适用场景：
- 告警自动响应
- 批量资产诊断
- 集成到监控平台

配置方式：
- 启动 Webhook 服务并设置 `GLOBAL_INVENTORY_PATH` 环境变量
- Alertmanager 发送告警到 Webhook
- 系统自动查找节点配置并执行诊断

```bash
export GLOBAL_INVENTORY_PATH=config/global-inventory.yaml
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080
```

特点：
- 自动响应告警
- 支持完整资产清单（所有可能的诊断目标）
- 支持自主模式（无需人工干预）

### 选择指南

| 需求 | 推荐方式 | 配置文件 |
|------|---------|---------|
| 快速诊断单个问题 | CLI + `--config` | `minimal-input.yaml` |
| 调试和开发 | CLI + `--config` | `minimal-input.yaml` |
| 告警自动响应 | Webhook | `global-inventory.yaml` |
| 管理多个生产环境 | Webhook | `global-inventory.yaml` |

---

## 准备配置文件

**重要**: 配置文件是运行诊断的必需输入。它提供 SSH 连接信息和测试参数给 Skills 使用。

### CLI 配置 (`minimal-input.yaml`)

适用于 CLI 单次诊断，完整指定所有节点信息。

```yaml
# config/minimal-input.yaml

nodes:
  # ===== 发送端宿主机 =====
  host-sender:
    ssh: smartx@192.168.75.101     # SSH 连接 (管理网络)
    workdir: /tmp/netsherlock
    role: host

  # ===== 发送端 VM =====
  vm-sender:
    ssh: root@192.168.2.100        # SSH 连接 (管理网络)
    workdir: /tmp/netsherlock
    role: vm
    host_ref: host-sender          # 所属宿主机节点名
    uuid: ae6aa164-604c-4cb0-84b8-2dea034307f1
    test_ip: 10.0.0.1              # ★ 测试流量 IP (见下方说明)

  # ===== 接收端宿主机 =====
  host-receiver:
    ssh: smartx@192.168.75.102
    workdir: /tmp/netsherlock
    role: host

  # ===== 接收端 VM =====
  vm-receiver:
    ssh: root@192.168.2.200
    workdir: /tmp/netsherlock
    role: vm
    host_ref: host-receiver
    uuid: bf7bb275-715d-5dc1-95c9-3feb045418g2
    test_ip: 10.0.0.2              # ★ 测试流量 IP

# ===== 测试对定义 =====
test_pairs:
  vm:
    server: vm-receiver            # 接收端 (先启动)
    client: vm-sender              # 发送端
```

#### 关键字段说明

| 字段 | 类型 | 必需 | 描述 |
|------|------|------|------|
| `nodes.<name>.ssh` | string | 是 | SSH 连接字符串 (user@host[:port]) |
| `nodes.<name>.role` | string | 是 | 节点角色: `host` 或 `vm` |
| `nodes.<name>.workdir` | string | 否 | 远程工作目录，默认 `/tmp/netsherlock` |
| `nodes.<name>.host_ref` | string | VM 必需 | VM 所在宿主机节点名 |
| `nodes.<name>.uuid` | string | VM 必需 | VM UUID |
| `nodes.<name>.test_ip` | string | **关键** | 测试流量 IP (可能与 SSH IP 不同) |
| `test_pairs.<type>.server` | string | 是 | 接收端节点名 |
| `test_pairs.<type>.client` | string | 是 | 发送端节点名 |

### test_ip vs SSH IP 的区别（重要！）

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          VM 网络配置示意                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   ┌─────────────────┐                 ┌─────────────────┐              │
│   │    管理网络      │                 │    测试网络      │              │
│   │  (SSH 访问通道)   │                 │  (数据流量通道)   │              │
│   └────────┬────────┘                 └────────┬────────┘              │
│            │                                   │                        │
│            ▼                                   ▼                        │
│   ssh: root@192.168.2.100            test_ip: 10.0.0.1                 │
│   (用于 SSH 连接管理 VM)              (BPF 工具过滤数据包的 IP)           │
│                                                                         │
│   用途:                               用途:                             │
│   - SSH 登录 VM                       - 发送/接收测试流量                │
│   - 部署 BPF 工具                     - BPF 工具过滤条件                 │
│   - 执行测量命令                      - 延迟测量数据来源                 │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

**常见场景**:

1. **单网络**: 如果 VM 只有一个网络接口，`ssh` 和 `test_ip` 使用相同 IP
2. **多网络**: 如果 VM 有管理网络和数据网络，`ssh` 用管理 IP，`test_ip` 用数据 IP

**错误配置导致的问题**:
- `test_ip` 配置错误 → BPF 工具无法过滤到数据包 → 测量结果为空
- SSH IP 配置错误 → 无法连接 VM → 工具部署失败

### Webhook 配置 (`global-inventory.yaml`)

适用于 Webhook 告警触发的批量诊断，预先配置所有资产。

```yaml
# config/global-inventory.yaml (Webhook 服务使用)

# ===== 宿主机清单 =====
hosts:
  node1:
    mgmt_ip: 192.168.75.101        # 告警中使用的 IP
    ssh:
      user: smartx
      key_file: ~/.ssh/id_rsa
    network_types: ["storage", "management"]

  node2:
    mgmt_ip: 192.168.75.102
    ssh:
      user: smartx
      key_file: ~/.ssh/id_rsa
    network_types: ["storage", "management"]

# ===== VM 清单 =====
vms:
  test-vm-1:
    uuid: ae6aa164-604c-4cb0-84b8-2dea034307f1    # 告警中使用的 UUID
    host_ref: node1                               # 所属宿主机
    ssh:
      user: root
      host: 192.168.2.100                         # SSH 管理 IP
    test_ip: 10.0.0.1                             # 测试流量 IP

  test-vm-2:
    uuid: bf7bb275-715d-5dc1-95c9-3feb045418g2
    host_ref: node2
    ssh:
      user: root
      host: 192.168.2.200
    test_ip: 10.0.0.2
```

---

## CLI 使用

### 诊断命令语法

```bash
netsherlock diagnose \
  --config <CONFIG_FILE> \
  --network-type <TYPE> \
  --src-host <IP> \
  [OPTIONS]
```

### 必需参数

| 参数 | 描述 |
|------|------|
| `--config` | MinimalInputConfig YAML 文件路径 |
| `--network-type` | 网络类型: `vm` 或 `system` |
| `--src-host` | 源主机 IP 地址 |

### VM 网络参数

| 参数 | 描述 | 条件 |
|------|------|------|
| `--src-vm` | 源 VM UUID | `--network-type vm` 时必需 |
| `--dst-host` | 目标主机 IP | VM 间诊断时需要 |
| `--dst-vm` | 目标 VM UUID | 与 `--dst-host` 配合使用 |

### 诊断参数

| 参数 | 短选项 | 描述 | 默认值 |
|------|--------|------|--------|
| `--type` | `-t` | 诊断类型 | `latency` |
| `--duration` | `-d` | 测量时长（秒） | `30` |
| `--mode` | `-m` | 诊断模式 | `interactive` |
| `--autonomous` | | 使用自主模式 | - |
| `--interactive` | | 使用交互模式 | - |
| `--generate-traffic` | | 生成 ICMP 测试流量 | - |

### 流量生成选项

默认情况下，诊断依赖环境中已有的背景流量（如持续的 ping）。如果没有背景流量，使用 `--generate-traffic` 启用自动流量生成：

```bash
# 默认行为：使用背景流量
netsherlock diagnose --config ...

# 启用流量生成（从 sender VM ping receiver VM）
netsherlock diagnose --config ... --generate-traffic
```

**工作原理**：
- 启用此选项时，L3 测量阶段会启动从发送 VM 向接收 VM 的 ICMP ping
- 确保有持续的测试数据包用于 BPF 工具测量
- 适用于 VM 间诊断（当 `--dst-vm` 指定时）

**何时使用**：
- ✓ 环境中没有现有的数据流量
- ✓ 需要可重现的诊断结果
- ✓ 测试网络中的 ICMP 过滤规则

**何时不需要**：
- 应用层已有持续的 TCP/UDP 流量
- 测试网络有高频 ping 或其他 ICMP 流量

### 使用示例

> **注意**: MVP 仅支持跨节点 VM 延迟诊断，必须同时指定 src 和 dst。

#### 示例 1: 跨节点 VM 延迟诊断（交互模式，默认）

```bash
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency
```

#### 示例 2: 跨节点 VM 延迟诊断（自主模式）

```bash
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency \
  --autonomous
```

#### 示例 3: 指定测量时长

```bash
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency \
  --duration 60
```

#### 示例 4: 启用流量生成

```bash
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --generate-traffic
```

#### 示例 5: JSON 输出

```bash
netsherlock --json diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --autonomous
```

### 其他命令

```bash
# 查看帮助
netsherlock --help

# 查看版本
netsherlock --version

# 查看当前配置
netsherlock config

# 查询指标
netsherlock query metrics 'host_network_ping_time_ns{hostname="node1"}'

# 查询日志
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

Webhook 模式用于接收 Alertmanager 告警并自动触发诊断。

### 启动服务

```bash
# 必需：指定资产清单
export GLOBAL_INVENTORY_PATH=config/global-inventory.yaml

# 必需：设置 API Key
export WEBHOOK_API_KEY=your-secret-api-key

# 可选：启用自动诊断
export DIAGNOSIS_AUTONOMOUS_ENABLED=true
export DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true

# 启动 Webhook 服务
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080
```

### API 端点

| Method | Path | Auth | 描述 |
|--------|------|------|------|
| GET | `/health` | 无 | 健康检查 |
| POST | `/webhook/alertmanager` | API Key | 接收 Alertmanager 告警 |
| POST | `/diagnose` | API Key | 手动诊断请求 |
| GET | `/diagnose/{id}` | API Key | 获取诊断状态 |
| GET | `/diagnoses` | API Key | 列出诊断记录 |

### 认证

```bash
# 请求头
X-API-Key: your-api-key-here
```

### 请求示例

#### 手动诊断

```bash
curl -X POST http://localhost:8080/diagnose \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "vm",
    "diagnosis_type": "latency",
    "src_host": "192.168.75.101",
    "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
    "dst_host": "192.168.75.102",
    "dst_vm": "bf7bb275-715d-5dc1-95c9-3feb045418g2"
  }'
```

#### Alertmanager Webhook

```bash
curl -X POST http://localhost:8080/webhook/alertmanager \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "status": "firing",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "VMNetworkLatency",
        "src_host": "192.168.75.101",
        "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1"
      }
    }]
  }'
```

### Webhook 自动诊断数据流

当 Webhook 接收告警时的自动诊断流程：

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           Alertmanager                                       │
│  告警规则触发 (VMNetworkLatency / HostNetworkLatency)                         │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼ POST /webhook/alertmanager
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Webhook Server                                       │
│  1. 认证 (X-API-Key)                                                         │
│  2. 解析告警 labels: alertname, src_host, src_vm, dst_host, dst_vm           │
│  3. 判断诊断模式 (autonomous/interactive)                                     │
│  4. 生成 diagnosis_id                                                        │
│  5. 入队 diagnosis_queue                                                     │
└────────────────────────────────┬────────────────────────────────────────────┘
                                 │
                                 ▼ diagnosis_worker 后台处理
┌─────────────────────────────────────────────────────────────────────────────┐
│                      DiagnosisController                                     │
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ GlobalInventory 查找节点                                             │   │
│  │   find_host_by_ip("192.168.75.101") → node1 配置                    │   │
│  │   find_vm_by_uuid("ae6aa164-...") → test-vm-1 配置                  │   │
│  │   → 自动构建 MinimalInputConfig (包含 SSH、test_ip、test_pairs)       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌───────────┬───────────┬───────────┬───────────┐                        │
│  │    L1     │    L2     │    L3     │    L4     │                        │
│  │  查询监控  │  收集环境  │  执行测量  │  分析报告  │                        │
│  │ (直接调用) │  (Skill)  │  (Skill)  │  (Skill)  │                        │
│  └───────────┴───────────┴───────────┴───────────┘                        │
└─────────────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        DiagnosisResult                                       │
│  - summary: 诊断摘要                                                         │
│  - root_cause: 根因 (category, component, confidence)                        │
│  - recommendations: 改进建议                                                 │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Alertmanager 配置示例

```yaml
# alertmanager.yml
receivers:
  - name: 'netsherlock'
    webhook_configs:
      - url: 'http://netsherlock:8080/webhook/alertmanager'
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
```

### 查询诊断结果

```bash
# 查询特定诊断
curl http://localhost:8080/diagnose/{diagnosis_id} \
  -H "X-API-Key: your-key"

# 列出所有诊断
curl "http://localhost:8080/diagnoses?limit=10" \
  -H "X-API-Key: your-key"
```

---

## 工作模式

### 模式对比

| 模式 | 人工干预 | 典型使用场景 |
|------|----------|--------------|
| **Interactive** | 检查点确认 | CLI 手动诊断、调试 |
| **Autonomous** | 无 | 批量诊断、Webhook 告警触发 |

### Interactive 模式（交互模式）

- 在关键节点暂停，等待用户确认
- CLI 默认使用此模式
- 适合首次诊断和调试

**检查点**:
1. `PROBLEM_CLASSIFICATION` - L2 环境收集后
2. `MEASUREMENT_PLAN` - L3 测量前
3. `FURTHER_DIAGNOSIS` - L4 分析后

### Autonomous 模式（自主模式）

- 全流程自动执行
- 适合告警自动响应
- 使用 `--autonomous` 触发

### CLI 模式选择优先级

```
1. --mode 参数（显式指定）
2. --autonomous / --interactive 标志
3. 配置文件 DIAGNOSIS_DEFAULT_MODE
4. 默认值: interactive
```

### Webhook 模式选择逻辑

```python
def determine_webhook_mode(alert_type, force_mode) -> DiagnosisMode:
    """
    模式选择优先级:
    1. force_mode 显式指定 → 使用指定模式
    2. auto_agent_loop=true 且 alert_type 是已知类型 → autonomous
    3. 其他 → interactive (默认，需要人工确认)
    """
```

---

## 环境变量配置

### 基础配置

```bash
# .env

# Grafana 配置
GRAFANA_BASE_URL=http://192.168.79.79/grafana
GRAFANA_USERNAME=o11y
GRAFANA_PASSWORD=your_password

# SSH 配置
SSH_PRIVATE_KEY_PATH=~/.ssh/id_rsa
```

### CLI 配置

```bash
# SSH 高级配置
SSH_DEFAULT_USER=root
SSH_DEFAULT_PORT=22
SSH_CONNECT_TIMEOUT=10
SSH_COMMAND_TIMEOUT=60

# BPF 工具配置
BPF_LOCAL_TOOLS_PATH=~/workspace/troubleshooting-tools
BPF_REMOTE_TOOLS_PATH=/tmp/netsherlock-tools
BPF_DEPLOY_MODE=auto

# 诊断模式配置
DIAGNOSIS_DEFAULT_MODE=interactive

# 日志配置
LOG_LEVEL=INFO
```

### Webhook 配置

```bash
# Webhook 特定配置
GLOBAL_INVENTORY_PATH=config/global-inventory.yaml    # 必需：资产清单
WEBHOOK_API_KEY=your-secret-api-key                   # 必需：API 认证
DIAGNOSIS_AUTONOMOUS_ENABLED=true                     # 自动诊断启用
DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true             # 自动代理循环
WEBHOOK_ALLOW_INSECURE=false
```

---

## 故障排除

### 常见问题

#### 1. 配置文件未指定

```
Error: --config is required for diagnosis
```

**解决**: 使用 `--config` 提供配置文件
```bash
netsherlock diagnose --config config/minimal-input.yaml ...
```

#### 2. SSH 连接失败

```
Error: SSH connection failed to 192.168.2.100
```

**检查**:
- 配置文件中的 SSH 地址是否正确
- SSH 私钥是否配置
- 网络是否可达

#### 3. BPF 测量结果为空

```
Warning: No packets captured
```

**原因**: `test_ip` 配置错误

**检查**:
- 确认 `test_ip` 是实际数据流量的 IP
- 如果 VM 有多个网卡，确保使用正确的网络接口 IP

#### 4. 检查点超时

```
Error: Checkpoint timed out
```

**解决**:
- 增加超时: `DIAGNOSIS_INTERACTIVE_TIMEOUT_SECONDS=600`
- 或使用自主模式: `--autonomous`

### 调试模式

```bash
# 启用详细日志
LOG_LEVEL=DEBUG netsherlock -v diagnose --config ...
```

---

## 快速参考

```bash
# ========== CLI 诊断 (使用 --config) ==========
# 注意: MVP 仅支持跨节点 VM 延迟诊断

# 跨节点 VM 延迟诊断（交互模式）
netsherlock diagnose \
  --config config/minimal-input.yaml \
  -n vm \
  --src-host <SRC_IP> --src-vm <SRC_UUID> \
  --dst-host <DST_IP> --dst-vm <DST_UUID> \
  -t latency

# 跨节点 VM 延迟诊断（自主模式）
netsherlock diagnose \
  --config config/minimal-input.yaml \
  -n vm \
  --src-host <SRC_IP> --src-vm <SRC_UUID> \
  --dst-host <DST_IP> --dst-vm <DST_UUID> \
  -t latency --autonomous

# 启用流量生成
netsherlock diagnose \
  --config config/minimal-input.yaml \
  -n vm \
  --src-host <SRC_IP> --src-vm <SRC_UUID> \
  --dst-host <DST_IP> --dst-vm <DST_UUID> \
  --generate-traffic

# ========== Webhook 服务 ==========

# 启动服务
export GLOBAL_INVENTORY_PATH=config/global-inventory.yaml
export WEBHOOK_API_KEY=your-secret-key
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080

# ========== 其他命令 ==========

# 查看配置
netsherlock config

# 查询指标
netsherlock query metrics '<PROMQL>'

# JSON 输出
netsherlock --json diagnose --config ... --autonomous
```
