# NetSherlock 用户指南

> 版本: 2.0
> 日期: 2026-01-22
> 状态: MVP 完成 (Skill-Driven Architecture)

---

## 目录

1. [概述](#概述)
2. [快速开始](#快速开始)
3. [准备配置文件（必需）](#准备配置文件必需)
4. [CLI 使用](#cli-使用)
5. [Webhook API 使用](#webhook-api-使用)
6. [自动模式数据流原理](#自动模式数据流原理)
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

- **Skill 驱动**: L2/L3/L4 通过 Claude Code Skills 执行，保证 receiver-first 时序
- **配置文件必需**: 所有诊断都需要配置文件提供 SSH 和测试参数
- **双模式支持**: 手动模式 (`--config`) 和自动模式 (`--inventory`)

### 支持的诊断类型

| 类型 | 描述 |
|------|------|
| `latency` | 网络延迟诊断（默认） |
| `packet_drop` | 丢包诊断 |
| `connectivity` | 连通性诊断 |

---

## 快速开始

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

## 准备配置文件（必需）

**重要**: 配置文件是运行诊断的必需输入。它提供 SSH 连接信息和测试参数给 Skills 使用。

### 配置模式选择

| 模式 | 配置文件 | CLI 参数 | 使用场景 |
|------|----------|----------|----------|
| **手动模式** | `minimal-input.yaml` | `--config` | 开发调试、单次诊断 |
| **自动模式** | `global-inventory.yaml` | `--inventory` | 告警触发、批量诊断 |

### 手动模式配置 (`minimal-input.yaml`)

适用于单次诊断，完整指定所有节点信息。

```yaml
# config/minimal-input.yaml (手动模式)

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

### 自动模式配置 (`global-inventory.yaml`)

适用于告警触发的批量诊断，预先配置所有资产。

```yaml
# config/global-inventory.yaml (自动模式)

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

**工作原理**:

```
告警触发
    │
    ▼
接收告警参数: src_host=192.168.75.101, src_vm=ae6aa164-...
    │
    ▼
查询 GlobalInventory
    │
    ├── find_host_by_ip("192.168.75.101") → node1
    └── find_vm_by_uuid("ae6aa164-...") → test-vm-1
    │
    ▼
自动构建 MinimalInputConfig
    │
    ▼
执行诊断 (L2→L3→L4 Skills)
```

---

## CLI 使用

### 诊断命令语法

```bash
netsherlock diagnose \
  [--config <CONFIG_FILE>] \
  --network-type <TYPE> \
  --src-host <IP> \
  [OPTIONS]
```

### 必需参数

| 参数 | 描述 |
|------|------|
| `--network-type` | 网络类型: `vm` 或 `system` |
| `--src-host` | 源主机 IP 地址 |

### 配置参数

| 参数 | 短选项 | 描述 |
|------|--------|------|
| `--config` | `-c` | MinimalInputConfig YAML 文件路径 (**推荐**) |
| `--inventory` | | GlobalInventory YAML 文件路径 (自动模式) |

> **注意**: 虽然 `--config` 不是必需的，但强烈推荐提供配置文件，以确保 SSH 连接信息和 `test_ip` 正确配置。

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

### 使用示例

#### 示例 1: 单 VM 延迟诊断（手动模式 + 交互）

```bash
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --type latency
```

#### 示例 2: VM 间延迟诊断（手动模式 + 自主）

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

#### 示例 3: 使用资产清单（自动模式）

```bash
netsherlock diagnose \
  --inventory config/global-inventory.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2 \
  --type latency \
  --autonomous
```

#### 示例 4: 指定测量时长

```bash
netsherlock diagnose \
  --config config/minimal-input.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --type latency \
  --duration 60
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

### 启动服务

```bash
# 指定资产清单（自动模式必需）
export GLOBAL_INVENTORY_PATH=config/global-inventory.yaml

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

# 配置 API Key
export WEBHOOK_API_KEY=your-secret-api-key
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

---

## 自动模式数据流原理

本节详细说明 Webhook 触发的自动诊断模式的数据流和工作原理。

### 整体数据流

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
│  │ _load_minimal_input(request)                                         │   │
│  │   如果 --inventory 指定:                                              │   │
│  │     GlobalInventory.load(inventory_path)                            │   │
│  │       .build_minimal_input(src_host, src_vm, dst_host, dst_vm)     │   │
│  │   → MinimalInputConfig (包含 SSH、test_ip、test_pairs)               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌───────────┬───────────┬───────────┬───────────┐                        │
│  │    L1     │    L2     │    L3     │    L4     │                        │
│  │  查询监控  │  收集环境  │  执行测量  │  分析报告  │                        │
│  │ (直接调用) │  (Skill)  │  (Skill)  │  (Skill)  │                        │
│  └───────────┴───────────┴───────────┴───────────┘                        │
│                           │                                                │
│                           ▼                                                │
│                    SkillExecutor                                           │
│                           │                                                │
│         ┌─────────────────┼─────────────────┐                              │
│         ▼                 ▼                 ▼                              │
│  network-env-     vm-latency-       vm-latency-                           │
│  collector        measurement       analysis                               │
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

### 关键步骤详解

#### 1. Alertmanager 告警触发

Alertmanager 检测到网络延迟告警后，向 NetSherlock 发送 webhook 请求：

```json
{
  "status": "firing",
  "alerts": [{
    "status": "firing",
    "labels": {
      "alertname": "VMNetworkLatency",
      "src_host": "192.168.75.101",
      "src_vm": "ae6aa164-604c-4cb0-84b8-2dea034307f1",
      "dst_host": "192.168.75.102",
      "dst_vm": "bf7bb275-715d-5dc1-95c9-3feb045418g2",
      "severity": "warning"
    },
    "annotations": {
      "summary": "VM 网络延迟超过 5ms"
    }
  }]
}
```

#### 2. Webhook 服务器处理

```python
# webhook.py - receive_alertmanager_webhook()

# 1. 解析告警 labels
alert_type = alert.labels.get("alertname")  # "VMNetworkLatency"
src_host = alert.labels.get("src_host")      # "192.168.75.101"
src_vm = alert.labels.get("src_vm")          # VM UUID

# 2. 判断诊断模式
effective_mode = determine_webhook_mode(alert_type=alert_type)
# 如果 alert_type 是已知类型 (VMNetworkLatency/HostNetworkLatency)
# 且 auto_agent_loop=true，则使用 autonomous 模式

# 3. 入队异步处理
await diagnosis_queue.put(("alert", diagnosis_id, alert_data))
```

#### 3. GlobalInventory 查找节点

当使用 `--inventory` 参数启动 webhook 服务时，系统会使用 GlobalInventory 将告警中的 IP/UUID 映射到具体的 SSH 配置：

```python
# GlobalInventory.build_minimal_input()

# 根据 src_host IP 查找宿主机配置
src_host_result = inventory.find_host_by_ip("192.168.75.101")
# → ("node1", HostConfig(mgmt_ip=..., ssh_user="smartx", ...))

# 根据 src_vm UUID 查找 VM 配置
src_vm_result = inventory.find_vm_by_uuid("ae6aa164-...")
# → ("test-vm-1", VMConfig(uuid=..., ssh_host="192.168.2.100", test_ip="10.0.0.1", ...))

# 构建 MinimalInputConfig
nodes = {
    "host-sender": NodeConfig(ssh=SSHConfig(user="smartx", host="192.168.75.101"), ...),
    "vm-sender": NodeConfig(ssh=SSHConfig(...), test_ip="10.0.0.1", uuid="ae6aa164-..."),
    "host-receiver": ...,
    "vm-receiver": ...,
}
```

#### 4. Skill 执行诊断

DiagnosisController 使用 MinimalInputConfig 中的信息调用 Skills：

```python
# _collect_environment() - L2
src_vm_node = self._minimal_input.get_node("vm-sender")
await skill_executor.invoke(
    skill_name="network-env-collector",
    parameters={
        "mode": "vm",
        "uuid": src_vm_node.uuid,
        "host_ip": self._minimal_input.get_node("host-sender").ssh.host,
        "vm_host": src_vm_node.ssh.host,
        ...
    }
)

# _execute_measurement() - L3
await skill_executor.invoke(
    skill_name="vm-latency-measurement",
    parameters={
        "sender_vm_ip": src_vm_node.test_ip,    # 关键: 测试流量 IP
        "receiver_vm_ip": dst_vm_node.test_ip,
        ...
    }
)
```

### 自动模式配置要点

#### 1. 启动 Webhook 服务时指定资产清单

```bash
# 设置环境变量
export GLOBAL_INVENTORY_PATH=config/global-inventory.yaml
export WEBHOOK_API_KEY=your-secret-key
export DIAGNOSIS_AUTONOMOUS_ENABLED=true
export DIAGNOSIS_AUTONOMOUS_AUTO_AGENT_LOOP=true

# 启动服务
uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8080
```

#### 2. GlobalInventory 必须包含所有可能的告警目标

```yaml
# config/global-inventory.yaml

hosts:
  node1:
    mgmt_ip: 192.168.75.101    # 告警中 src_host/dst_host 的值
    ssh:
      user: smartx
      key_file: ~/.ssh/id_rsa

  node2:
    mgmt_ip: 192.168.75.102
    ssh:
      user: smartx

vms:
  test-vm-1:
    uuid: ae6aa164-604c-4cb0-84b8-2dea034307f1  # 告警中 src_vm/dst_vm 的值
    host_ref: node1
    ssh:
      user: root
      host: 192.168.2.100      # SSH 管理 IP
    test_ip: 10.0.0.1          # 测试流量 IP (BPF 过滤)

  test-vm-2:
    uuid: bf7bb275-715d-5dc1-95c9-3feb045418g2
    host_ref: node2
    ssh:
      user: root
      host: 192.168.2.200
    test_ip: 10.0.0.2
```

#### 3. Alertmanager 告警规则配置

告警规则需要在 labels 中包含必要的节点信息：

```yaml
# prometheus/rules/network.yaml
groups:
  - name: network
    rules:
      - alert: VMNetworkLatency
        expr: vm_network_latency_ms > 5
        for: 1m
        labels:
          severity: warning
          src_host: "{{ $labels.host_ip }}"
          src_vm: "{{ $labels.vm_uuid }}"
          # 如果是 VM 间延迟，还需要:
          # dst_host: "{{ $labels.dst_host_ip }}"
          # dst_vm: "{{ $labels.dst_vm_uuid }}"
        annotations:
          summary: "VM {{ $labels.vm_name }} 网络延迟 {{ $value }}ms"
```

### 模式判断逻辑

```python
def determine_webhook_mode(alert_type, force_mode) -> DiagnosisMode:
    """
    模式选择优先级:
    1. force_mode 显式指定 → 使用指定模式
    2. auto_agent_loop=true 且 alert_type 是已知类型 → autonomous
    3. 其他 → interactive (默认，需要人工确认)
    """
    if force_mode:
        return force_mode

    config = settings.get_diagnosis_config()

    # 已知告警类型列表
    KNOWN_ALERT_TYPES = ["VMNetworkLatency", "HostNetworkLatency"]

    if config.autonomous.auto_agent_loop and alert_type in KNOWN_ALERT_TYPES:
        return DiagnosisMode.AUTONOMOUS

    return DiagnosisMode.INTERACTIVE
```

### 查询诊断结果

告警触发后，可以通过 API 查询诊断状态和结果：

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

| 模式 | 配置来源 | 人工干预 | 典型使用场景 |
|------|----------|----------|--------------|
| **Interactive** | `--config` | 检查点确认 | CLI 手动诊断、调试 |
| **Autonomous** | `--inventory` | 无 | Webhook 告警触发 |

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
- 使用 `--autonomous` 或 `--inventory` 触发

### 模式选择优先级

```
1. --mode 参数（显式指定）
2. --autonomous / --interactive 标志
3. 配置文件 DIAGNOSIS_DEFAULT_MODE
4. 默认值: interactive
```

---

## 环境变量配置

### 必需配置

```bash
# .env

# Grafana 配置
GRAFANA_BASE_URL=http://192.168.79.79/grafana
GRAFANA_USERNAME=o11y
GRAFANA_PASSWORD=your_password

# SSH 配置
SSH_PRIVATE_KEY_PATH=~/.ssh/id_rsa
```

### 可选配置

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
DIAGNOSIS_AUTONOMOUS_ENABLED=true

# Webhook 配置
WEBHOOK_API_KEY=your-secret-api-key
WEBHOOK_ALLOW_INSECURE=false

# 日志配置
LOG_LEVEL=INFO
```

---

## 故障排除

### 常见问题

#### 1. SSH 连接信息不正确

```
Error: SSH connection failed - invalid host or user
```

**解决**: 使用 `--config` 提供正确的 SSH 配置
```bash
netsherlock diagnose --config config/minimal-input.yaml ...
```

**提示**: 虽然 `--config` 不是必需的，但强烈推荐使用配置文件以确保 SSH 和 test_ip 正确配置。

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
# ========== 手动模式 (--config) ==========

# 单 VM 诊断
netsherlock diagnose \
  --config config/minimal-input.yaml \
  -n vm --src-host <IP> --src-vm <UUID> \
  -t latency

# VM 间诊断
netsherlock diagnose \
  --config config/minimal-input.yaml \
  -n vm \
  --src-host <SRC_IP> --src-vm <SRC_UUID> \
  --dst-host <DST_IP> --dst-vm <DST_UUID> \
  -t latency --autonomous

# ========== 自动模式 (--inventory) ==========

# 使用资产清单
netsherlock diagnose \
  --inventory config/global-inventory.yaml \
  -n vm \
  --src-host <IP> --src-vm <UUID> \
  -t latency --autonomous

# ========== 其他命令 ==========

# 查看配置
netsherlock config

# 查询指标
netsherlock query metrics '<PROMQL>'

# JSON 输出
netsherlock --json diagnose --config ... --autonomous
```
