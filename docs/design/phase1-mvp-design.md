# Phase 1 MVP 详细设计

> 版本: 4.0
> 日期: 2026-01-22
> 状态: **MVP 功能完成** - Skill 驱动架构
> 变更: 根据实际实现重写，修正 L2/L3/L4 为 Skill 驱动模式

---

## 一、MVP 范围定义

### 1.1 功能边界

| 维度 | MVP 范围 | 后续扩展 |
|------|----------|----------|
| **入口** | CLI + Alertmanager Webhook | Grafana 面板集成 |
| **问题类型** | VM 网络延迟诊断 | 丢包、吞吐、OVS、vhost 等 9 类 |
| **网络范围** | VM 网络 (virtio → vhost → OVS → 物理) | 系统网络 (OVS internal port) |
| **执行方式** | Skill 驱动 (Claude Code Skills) | 直接工具调用 |
| **运行模式** | 手动模式 + 自动模式 | 更多模式 |
| **配置方式** | YAML 配置文件 (MinimalInputConfig) | API 配置 |

### 1.2 核心输入要求

**关键变化**: 诊断执行需要配置文件作为输入，提供 SSH 连接信息和测试参数。

| 模式 | 配置文件 | 说明 |
|------|----------|------|
| **手动模式** | `minimal-input.yaml` | 用户手动定义节点 SSH、test_ip、测试配对 |
| **自动模式** | `global-inventory.yaml` | 预配置资产清单，从告警参数自动构建配置 |

### 1.3 双模式控制循环

#### 模式 1: 手动模式 (Manual Mode) - 默认

```
用户准备配置文件 (minimal-input.yaml)
        │
        ▼
┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
│ CLI 触发 │ → │ L2 环境  │ → │ L3 测量  │ → │ L4 分析  │ → │ 诊断报告 │
│ --config │    │  Skill   │    │  Skill   │    │  Skill   │    │          │
└──────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
                     ↑               ↑               ↑
                     └───── MinimalInputConfig ──────┘
```

**配置文件作用**:
- 提供 SSH 连接信息给 Skills
- 定义 `test_ip`（测试流量 IP，可能与 SSH IP 不同）
- 定义测试配对 (server/client)

#### 模式 2: 自动模式 (Auto Mode)

```
告警触发 (Alertmanager Webhook)
        │
        ▼
┌──────────────┐    ┌──────────────────┐    ┌──────────────┐
│ 接收告警参数  │ → │ GlobalInventory  │ → │ 构建          │
│ src_host_ip  │    │ 资产清单查询      │    │ MinimalInput │
│ src_vm_uuid  │    │                  │    │ Config       │
└──────────────┘    └──────────────────┘    └──────────────┘
                                                    │
                                                    ▼
                                            (同手动模式流程)
```

### 1.4 核心用户场景

**场景 A - 手动模式 CLI**:
```bash
# 1. 准备配置文件
cp config/minimal-input-template.yaml my-diagnosis.yaml
# 编辑 my-diagnosis.yaml，填入实际 SSH 和 test_ip

# 2. 执行诊断
netsherlock diagnose \
  --config my-diagnosis.yaml \
  --network-type vm \
  --src-host 192.168.75.101 \
  --src-vm ae6aa164-604c-4cb0-84b8-2dea034307f1 \
  --dst-host 192.168.75.102 \
  --dst-vm bf7bb275-715d-5dc1-95c9-3feb045418g2
```

**场景 B - 自动模式 Webhook**:
```bash
# 预先配置 global-inventory.yaml
netsherlock server --inventory config/global-inventory.yaml

# Alertmanager 发送告警，自动触发诊断
```

---

## 二、系统架构

### 2.1 Skill 驱动架构 (核心设计)

```
                                    ┌─────────────────────────────────┐
                                    │         Entry Points            │
                                    ├────────────────┬────────────────┤
                                    │ Alertmanager   │     CLI        │
                                    │   Webhook      │   (diagnose)   │
                                    └───────┬────────┴───────┬────────┘
                                            │                │
                                            ▼                ▼
                                    ┌───────────────────────────────┐
                                    │       配置文件加载            │
                                    ├───────────────┬───────────────┤
                                    │ --config      │ --inventory   │
                                    │ (手动模式)    │ (自动模式)    │
                                    └───────┬───────┴───────┬───────┘
                                            │               │
                                            ▼               ▼
                                    ┌───────────────────────────────┐
                                    │      MinimalInputConfig       │
                                    │  • nodes (SSH 连接)           │
                                    │  • test_ip (测试流量 IP)      │
                                    │  • test_pairs (配对关系)      │
                                    └───────────────┬───────────────┘
                                                    │
                                                    ▼
                            ┌───────────────────────────────────────────┐
                            │           DiagnosisController             │
                            │  ┌─────────────────────────────────────┐  │
                            │  │         Mode Selection              │  │
                            │  │  ┌─────────────┐  ┌──────────────┐  │  │
                            │  │  │ Autonomous  │  │ Interactive  │  │  │
                            │  │  │   Loop      │  │    Loop      │  │  │
                            │  │  └─────────────┘  └──────────────┘  │  │
                            │  └─────────────────────────────────────┘  │
                            └───────────────────────────────────────────┘
                                            │
                                            ▼
                            ┌───────────────────────────────────────────┐
                            │              SkillExecutor                │
                            │     (Claude Code Skills 调用器)           │
                            └───────────────────────────────────────────┘
                                            │
            ┌───────────────────────────────┼───────────────────────────┐
            ▼                               ▼                           ▼
┌───────────────────────┐   ┌───────────────────────┐   ┌───────────────────────┐
│  network-env-collector│   │ vm-latency-measurement│   │  vm-latency-analysis  │
│       (L2 Skill)      │   │       (L3 Skill)      │   │       (L4 Skill)      │
├───────────────────────┤   ├───────────────────────┤   ├───────────────────────┤
│ • SSH 收集网络拓扑    │   │ • 部署 BPF 工具       │   │ • 解析测量日志        │
│ • virsh/OVS/proc 查询 │   │ • receiver-first 保证 │   │ • 计算分段延迟        │
│ • 输出 VMNetworkEnv   │   │ • 8 点协调测量        │   │ • 根因归因分析        │
└───────────────────────┘   └───────────────────────┘   └───────────────────────┘
```

### 2.2 DiagnosisController 核心流程

```python
class DiagnosisController:
    def __init__(
        self,
        config: DiagnosisConfig,
        checkpoint_callback: CheckpointCallback | None = None,
        skill_executor: SkillExecutorProtocol | None = None,
        global_inventory_path: str | Path | None = None,  # 自动模式
        minimal_input_path: str | Path | None = None,     # 手动模式
    ):
        pass

    async def run(self, request: DiagnosisRequest) -> DiagnosisResult:
        # 1. 加载配置
        self._minimal_input = self._load_minimal_input(request)

        # 2. 根据模式执行
        if mode == DiagnosisMode.AUTONOMOUS:
            return await self._run_autonomous(request)
        else:
            return await self._run_interactive(request)

    def _load_minimal_input(self, request) -> MinimalInputConfig:
        """配置加载逻辑"""
        if self._minimal_input_path:
            # 手动模式: 从 YAML 加载
            return MinimalInputConfig.load(self._minimal_input_path)

        if self._global_inventory_path:
            # 自动模式: 从 inventory + request 构建
            inventory = GlobalInventory.load(self._global_inventory_path)
            return inventory.build_minimal_input(
                src_host_ip=request.src_host,
                src_vm_uuid=request.src_vm,
                dst_host_ip=request.dst_host,
                dst_vm_uuid=request.dst_vm,
            )

        # 回退: 从 request 创建简化配置 (功能有限)
        return self._create_minimal_from_request(request)
```

### 2.3 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 执行方式 | Skill 驱动 | 复用 Claude Code Skills，避免重复实现 |
| 配置输入 | MinimalInputConfig YAML | 明确 SSH 和 test_ip，避免歧义 |
| 自动模式 | GlobalInventory | 预配置资产，告警自动匹配 |
| receiver-first | Skill 内部保证 | `vm-latency-measurement` Skill 内置时序 |
| 默认模式 | Interactive (人机协作) | 保守策略，避免自动执行意外操作 |

### 2.4 外部系统集成架构

NetSherlock 需要与外部监控系统集成。以下明确各组件的归属和集成方式。

#### 2.4.1 组件归属

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     外部监控系统 (用户已有/自行管理)                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐      ┌─────────────────┐      ┌─────────────────┐        │
│  │ Prometheus  │ ───► │  Alertmanager   │      │     Grafana     │        │
│  │ (指标采集)   │      │  (告警路由)     │      │  (可视化/告警)   │        │
│  └─────────────┘      └────────┬────────┘      └────────┬────────┘        │
│                                │                        │                  │
│                                │ Webhook                │ Webhook          │
└────────────────────────────────┼────────────────────────┼──────────────────┘
                                 │                        │
                                 │   两种告警源均可触发    │
                                 ▼                        ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        NetSherlock (本项目)                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │               Webhook Server (api/webhook.py) 内置组件               │   │
│  │                                                                      │   │
│  │  POST /webhook/alertmanager  ← Alertmanager 标准格式                 │   │
│  │  POST /diagnose              ← 通用诊断请求 (Grafana/手动)            │   │
│  │  GET  /diagnose/{id}         ← 查询诊断结果                          │   │
│  └──────────────────────────────────┬──────────────────────────────────┘   │
│                                     │                                       │
│                                     ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    DiagnosisController                               │   │
│  │                    (L1 → L2 → L3 → L4 Skills)                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 2.4.2 组件说明

| 组件 | 归属 | 说明 |
|------|------|------|
| **Prometheus** | 外部系统 | 指标采集，用户自行部署和管理 |
| **Alertmanager** | 外部系统 | Prometheus 告警路由组件，可选 |
| **Grafana** | 外部系统 | 可视化和告警，可作为告警源替代 Alertmanager |
| **Webhook Server** | **NetSherlock 内置** | `netsherlock.api.webhook` 模块 |
| **DiagnosisController** | **NetSherlock 内置** | 诊断执行核心 |

#### 2.4.3 告警源选择

**方式 A: Alertmanager (推荐)**

Alertmanager 是 Prometheus 生态的标准告警管理组件，支持告警去重、分组、静默。

```yaml
# alertmanager.yml
receivers:
  - name: 'netsherlock'
    webhook_configs:
      - url: 'http://<netsherlock-host>:8080/webhook/alertmanager'
        http_config:
          headers:
            X-API-Key: 'your-secret-key'

route:
  routes:
    - match:
        alertname: 'VMNetworkLatency'
      receiver: 'netsherlock'
```

**方式 B: Grafana 告警**

Grafana 自带告警功能，可直接配置 Webhook 通知。

```yaml
# Grafana Contact Point 配置
contact_points:
  - name: netsherlock
    type: webhook
    settings:
      url: http://<netsherlock-host>:8080/diagnose
      httpMethod: POST
      httpHeader:
        X-API-Key: 'your-secret-key'
```

**方式 C: 手动 API 调用**

直接调用 API 触发诊断，适用于集成到其他系统。

```bash
curl -X POST http://localhost:8080/diagnose \
  -H "X-API-Key: your-key" \
  -H "Content-Type: application/json" \
  -d '{
    "network_type": "vm",
    "src_host": "192.168.75.101",
    "src_vm": "ae6aa164-...",
    "dst_host": "192.168.75.102",
    "dst_vm": "bf7bb275-..."
  }'
```

#### 2.4.4 集成数据流

```
┌─────────────┐
│ 监控系统    │  (Prometheus/Grafana 检测到网络延迟)
└──────┬──────┘
       │
       ▼ 触发告警
┌─────────────┐
│ 告警源      │  Alertmanager 或 Grafana Alerting
└──────┬──────┘
       │
       ▼ HTTP POST (Webhook)
┌─────────────────────────────────────────────────────────────────┐
│                    NetSherlock Webhook Server                    │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 1. 认证: 验证 X-API-Key                                  │    │
│  │ 2. 解析: 提取 labels (src_host, src_vm, dst_host, ...)  │    │
│  │ 3. 模式判断: auto_agent_loop + 已知告警类型 → autonomous │    │
│  │ 4. 入队: diagnosis_queue.put(request)                   │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ▼ diagnosis_worker 异步处理
┌─────────────────────────────────────────────────────────────────┐
│                    DiagnosisController                           │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 1. GlobalInventory 查找:                                 │    │
│  │    find_host_by_ip(src_host) → HostConfig               │    │
│  │    find_vm_by_uuid(src_vm)   → VMConfig (含 test_ip)    │    │
│  │                                                          │    │
│  │ 2. 构建 MinimalInputConfig:                              │    │
│  │    nodes: host-sender, vm-sender, host-receiver, ...    │    │
│  │    test_pairs: {vm: {server: vm-receiver, client: ...}} │    │
│  │                                                          │    │
│  │ 3. 执行诊断:                                             │    │
│  │    L1 查询 → L2 Skill → L3 Skill → L4 Skill            │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────┬──────────────────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐
│ 诊断报告    │  DiagnosisResult (summary, root_cause, recommendations)
└─────────────┘
```

#### 2.4.5 告警 Labels 要求

为了让 GlobalInventory 能正确查找节点，告警规则必须包含以下 labels：

| Label | 必需 | 说明 |
|-------|------|------|
| `alertname` | 是 | 告警名称，用于模式判断 |
| `src_host` | 是 | 源宿主机管理 IP |
| `src_vm` | VM 诊断必需 | 源 VM UUID |
| `dst_host` | 跨节点诊断必需 | 目标宿主机管理 IP |
| `dst_vm` | 跨 VM 诊断必需 | 目标 VM UUID |

**Prometheus 告警规则示例**:

```yaml
groups:
  - name: network
    rules:
      - alert: VMNetworkLatency
        expr: vm_network_latency_ms{quantile="0.99"} > 5
        for: 2m
        labels:
          severity: warning
          src_host: "{{ $labels.host_ip }}"
          src_vm: "{{ $labels.vm_uuid }}"
          dst_host: "{{ $labels.peer_host_ip }}"
          dst_vm: "{{ $labels.peer_vm_uuid }}"
        annotations:
          summary: "VM {{ $labels.vm_name }} 到 {{ $labels.peer_vm_name }} 延迟 {{ $value | printf \"%.2f\" }}ms"
```

### 2.5 VM 网络告警规则设计

NetSherlock 自动模式依赖告警触发。现有 Grafana/Prometheus 告警可能不足以支持 VM 网络诊断场景，需要专门添加。

#### 2.5.1 现有指标分析

| 指标族 | 数量 | 示例 | 局限性 |
|--------|------|------|--------|
| `elf_vm_network_*` | 12 | `transmit_speed_bitps`, `drop`, `errors` | 仅基础流量/丢包，无延迟 |
| `host_network_ping_time_ns` | 1 | 主机间 ping 延迟 | 主机级别，非 VM 粒度 |
| `openvswitch_*` | 9 | `port_tx_bytes`, `flow_count` | OVS 聚合数据，无 VM 关联 |

**核心缺口**: 缺乏 **VM 粒度的网络延迟指标**，无法自动触发 VM 延迟诊断。

#### 2.5.2 需新增的指标采集

需要在现有监控基础设施中添加 VM 网络延迟指标导出。

**方案 A: 基于 Pingmesh 扩展 (推荐)**

利用现有 pingmesh 探测机制，添加 VM 粒度的延迟采集。

```yaml
# prometheus-exporter 新增采集项
vm_network_latency_ms:
  type: histogram
  help: "VM to VM network latency in milliseconds"
  labels:
    - src_vm_uuid
    - src_host
    - dst_vm_uuid
    - dst_host
    - network_type    # mgt/storage/access
  buckets: [0.5, 1, 2, 5, 10, 20, 50, 100]

vm_network_ping_loss_ratio:
  type: gauge
  help: "VM to VM ping packet loss ratio"
  labels:
    - src_vm_uuid
    - dst_vm_uuid
```

**方案 B: 基于 eBPF 实时采集**

部署轻量级 eBPF 探测，直接在内核层面采集延迟。

```python
# bpf_vm_latency_exporter.py 概念
# 挂载点: tcp_rcv_established, tcp_sendmsg
# 输出: vm_tcp_latency_us{vm_uuid, direction, quantile}
```

**推荐**: MVP 阶段采用方案 A (扩展 Pingmesh)，后续可增加方案 B。

#### 2.5.3 Prometheus Recording Rules

为了提高告警计算效率，预计算常用聚合：

```yaml
# recording_rules.yml
groups:
  - name: vm_network_aggregations
    interval: 30s
    rules:
      # VM 延迟 P99
      - record: vm_network_latency:p99_5m
        expr: |
          histogram_quantile(0.99,
            sum by (src_vm_uuid, dst_vm_uuid, le) (
              rate(vm_network_latency_ms_bucket[5m])
            )
          )

      # VM 丢包率
      - record: vm_network_loss:rate_5m
        expr: |
          avg_over_time(vm_network_ping_loss_ratio[5m])

      # 按主机聚合的 VM 延迟
      - record: vm_network_latency:by_host_p99_5m
        expr: |
          max by (src_host, dst_host) (
            vm_network_latency:p99_5m
          )
```

#### 2.5.4 Alert Rules 定义

**核心告警规则** (触发 NetSherlock 诊断):

```yaml
# alerts/vm_network_alerts.yml
groups:
  - name: vm_network_diagnosis_triggers
    rules:
      # 告警 1: VM 网络延迟 - 单 VM 对
      - alert: VMNetworkLatencyHigh
        expr: vm_network_latency:p99_5m > 5  # 阈值 5ms
        for: 2m
        labels:
          severity: warning
          diagnosis_type: latency
          # NetSherlock 所需 labels
          src_host: "{{ $labels.src_host }}"
          src_vm: "{{ $labels.src_vm_uuid }}"
          dst_host: "{{ $labels.dst_host }}"
          dst_vm: "{{ $labels.dst_vm_uuid }}"
        annotations:
          summary: "VM {{ $labels.src_vm_uuid }} → {{ $labels.dst_vm_uuid }} 延迟 {{ $value | printf \"%.2f\" }}ms"
          runbook_url: "https://wiki/runbook/vm-network-latency"

      # 告警 2: VM 网络延迟 - 主机级别
      - alert: VMNetworkLatencyByHost
        expr: vm_network_latency:by_host_p99_5m > 10  # 主机对聚合阈值
        for: 3m
        labels:
          severity: critical
          diagnosis_type: latency
          src_host: "{{ $labels.src_host }}"
          dst_host: "{{ $labels.dst_host }}"
        annotations:
          summary: "主机 {{ $labels.src_host }} → {{ $labels.dst_host }} 多个 VM 延迟异常"

      # 告警 3: VM 网络丢包
      - alert: VMNetworkPacketLoss
        expr: vm_network_loss:rate_5m > 0.01  # 丢包率 > 1%
        for: 2m
        labels:
          severity: warning
          diagnosis_type: drop
          src_host: "{{ $labels.src_host }}"
          src_vm: "{{ $labels.src_vm_uuid }}"
          dst_host: "{{ $labels.dst_host }}"
          dst_vm: "{{ $labels.dst_vm_uuid }}"
        annotations:
          summary: "VM {{ $labels.src_vm_uuid }} 丢包率 {{ $value | printf \"%.2f%%\" }}"

      # 告警 4: OVS CPU 高负载 (关联 VM)
      - alert: OVSCPUHighWithVMTraffic
        expr: |
          host_service_cpu_usage_percent{_service="ovs_vswitchd_svc"} > 80
          and on(hostname)
          sum by (hostname) (rate(elf_vm_network_transmit_speed_bitps[5m])) > 1e9
        for: 5m
        labels:
          severity: warning
          diagnosis_type: latency
          src_host: "{{ $labels.hostname }}"
        annotations:
          summary: "{{ $labels.hostname }} OVS CPU {{ $value | printf \"%.1f\" }}%，VM 流量高"
```

#### 2.5.5 告警路由配置

配置 Alertmanager 将 VM 网络告警路由到 NetSherlock:

```yaml
# alertmanager.yml
route:
  receiver: 'default'
  routes:
    # VM 网络告警 → NetSherlock
    - match_re:
        alertname: 'VMNetwork.*'
      receiver: 'netsherlock-vm-network'
      group_by: ['alertname', 'src_host', 'src_vm']
      group_wait: 30s
      group_interval: 5m
      repeat_interval: 4h

receivers:
  - name: 'netsherlock-vm-network'
    webhook_configs:
      - url: 'http://netsherlock:8080/webhook/alertmanager'
        send_resolved: false  # 仅发送 firing
        http_config:
          headers:
            X-API-Key: '${WEBHOOK_API_KEY}'
```

#### 2.5.6 Grafana Alert 配置 (替代方案)

如果使用 Grafana Alerting 替代 Alertmanager:

```yaml
# Grafana Alert Rule (UI 配置对应的 JSON)
{
  "title": "VM Network Latency High",
  "condition": "C",
  "data": [
    {
      "refId": "A",
      "datasourceUid": "prometheus",
      "model": {
        "expr": "vm_network_latency:p99_5m{} > 5",
        "intervalMs": 30000
      }
    }
  ],
  "for": "2m",
  "labels": {
    "diagnosis_type": "latency"
  },
  "annotations": {
    "summary": "VM {{ $labels.src_vm_uuid }} 延迟异常"
  },
  "notification_settings": {
    "receiver": "netsherlock-webhook"
  }
}
```

#### 2.5.7 集成检查清单

部署 VM 网络告警需要完成以下步骤:

| 步骤 | 组件 | 操作 | 负责方 |
|------|------|------|--------|
| 1 | Exporter | 添加 `vm_network_latency_ms` 指标采集 | 监控团队 |
| 2 | Prometheus | 添加 Recording Rules | 监控团队 |
| 3 | Prometheus | 添加 Alert Rules | 监控团队 |
| 4 | Alertmanager/Grafana | 配置 Webhook 路由 | 监控团队 |
| 5 | NetSherlock | 启动 Webhook Server | 运维/用户 |
| 6 | GlobalInventory | 配置资产清单 | 运维/用户 |

**验证命令**:

```bash
# 1. 检查指标是否可用
curl -s "http://prometheus:9090/api/v1/query?query=vm_network_latency:p99_5m" | jq .

# 2. 检查告警规则是否加载
curl -s "http://prometheus:9090/api/v1/rules" | jq '.data.groups[].rules[] | select(.name | startswith("VMNetwork"))'

# 3. 测试 NetSherlock Webhook
curl -X POST http://netsherlock:8080/webhook/alertmanager \
  -H "X-API-Key: test-key" \
  -H "Content-Type: application/json" \
  -d '{"alerts":[{"labels":{"alertname":"VMNetworkLatencyHigh","src_host":"192.168.75.101","src_vm":"test-uuid"}}]}'
```

---

## 三、层级职责与接口定义

### 3.1 L1: 基础监控层 (直接实现)

**职责**: 查询现有监控数据，建立问题上下文

**实现方式**: DiagnosisController 直接调用 Grafana/Loki API

| 方法 | 输入 | 输出 | 数据源 |
|------|------|------|--------|
| `_query_monitoring()` | DiagnosisRequest | dict (L1Context) | Grafana/Loki |

**关键指标 (MVP)**:
- `host_network_ping_time_ns` - 主机网络延迟
- `elf_vm_network_*` - VM 网络流量/丢包
- `host_service_cpu_usage_percent{_service="ovs_vswitchd_svc"}` - OVS CPU

### 3.2 L2: 环境感知层 (Skill 驱动)

**职责**: 收集网络拓扑和环境信息

**实现方式**: 调用 `network-env-collector` Skill

```python
async def _collect_environment(self, request, l1_context) -> dict:
    """通过 Skill 收集环境"""
    executor = self._get_skill_executor()

    # 从 MinimalInputConfig 获取 SSH 信息
    src_vm_node = self._minimal_input.get_node("vm-sender")
    src_host_node = self._minimal_input.get_node("host-sender")

    # 调用 Skill
    result = await executor.invoke(
        skill_name="network-env-collector",
        parameters={
            "mode": "vm",
            "uuid": request.src_vm,
            "host_ip": src_host_node.ssh.host,
            "host_user": src_host_node.ssh.user,
            "vm_host": src_vm_node.ssh.host,
            "vm_user": src_vm_node.ssh.user,
        },
    )
    return result.data
```

**Skill 输出 (VMNetworkEnv)**:
```json
{
  "vm_uuid": "ae6aa164-...",
  "host": "192.168.75.101",
  "qemu_pid": 12345,
  "nics": [
    {
      "mac": "fa:16:3e:xx:xx:xx",
      "host_vnet": "vnet0",
      "ovs_bridge": "br-int",
      "vhost_pids": [12346, 12347]
    }
  ]
}
```

### 3.3 L3: 精确测量层 (Skill 驱动)

**职责**: 执行 BPF 工具，收集分段延迟数据

**实现方式**: 调用 `vm-latency-measurement` Skill

**核心约束**: **receiver-first 时序** - Skill 内部保证接收端先于发送端启动

```python
async def _execute_measurement(self, plan, environment) -> dict:
    """通过 Skill 执行测量"""
    executor = self._get_skill_executor()

    result = await executor.invoke(
        skill_name="vm-latency-measurement",
        parameters=plan.get("parameters", {}),
    )

    return {
        "status": "success" if result.is_success else "error",
        "data": result.data,
        "segments": result.data.get("segments", {}),
    }
```

**Skill 执行的 8 个测量点**:

| 位置 | 工具 | 测量内容 |
|------|------|----------|
| Sender VM | `kernel_icmp_rtt.py` | Segments A, M |
| Sender Host | `icmp_drop_detector.py` | Segments B, K |
| Sender Host | `kvm_vhost_tun_latency_details.py` | Segment B_1 |
| Sender Host | `tun_tx_to_kvm_irq.py` | Segment L |
| Receiver VM | `kernel_icmp_rtt.py` | Segments F, G, H |
| Receiver Host | `icmp_drop_detector.py` | Segments D, I |
| Receiver Host | `tun_tx_to_kvm_irq.py` | Segment E |
| Receiver Host | `kvm_vhost_tun_latency_details.py` | Segment I_1 |

### 3.4 L4: 诊断分析层 (Skill 驱动)

**职责**: 分析测量数据，识别根因，生成报告

**实现方式**: 调用 `vm-latency-analysis` Skill

```python
async def _analyze_and_report(self, measurements, environment) -> dict:
    """两阶段分析"""
    # Phase 1: 数据计算 (确定性)
    breakdown = self._calculate_breakdown(measurements)

    # Phase 2: LLM 推理 (via Skill)
    executor = self._get_skill_executor()
    result = await executor.invoke(
        skill_name="vm-latency-analysis",
        parameters={
            "breakdown": breakdown.to_dict(),
            "environment": environment,
        },
    )

    return {
        "root_cause": result.data.get("primary_contributor"),
        "confidence": result.data.get("confidence"),
        "recommendations": result.data.get("recommendations", []),
    }
```

**根因分类 (LayerType)**:
```python
class LayerType(str, Enum):
    SENDER_VM = "sender_vm"           # 发送端 VM 内部
    SENDER_HOST = "sender_host"       # 发送端宿主机
    NETWORK = "network"               # 物理网络
    RECEIVER_HOST = "receiver_host"   # 接收端宿主机
    RECEIVER_VM = "receiver_vm"       # 接收端 VM 内部
```

---

## 四、配置文件设计

### 4.1 MinimalInputConfig (手动模式)

**用途**: 定义诊断所需的节点 SSH 信息和测试参数

```yaml
# config/minimal-input.yaml
nodes:
  vm-sender:
    ssh: "root@192.168.2.100"        # SSH 连接 (管理网络)
    workdir: "/tmp/netsherlock"
    role: "vm"
    host_ref: "host-sender"          # 关联宿主机
    uuid: "ae6aa164-604c-4cb0-84b8-2dea034307f1"
    test_ip: "10.0.0.1"              # 关键: 测试流量 IP!

  vm-receiver:
    ssh: "root@192.168.2.101"
    workdir: "/tmp/netsherlock"
    role: "vm"
    host_ref: "host-receiver"
    uuid: "bf7bb275-715d-5dc1-95c9-3feb045418g2"
    test_ip: "10.0.0.2"

  host-sender:
    ssh: "smartx@192.168.75.101"     # 宿主机 SSH
    workdir: "/tmp/netsherlock"
    role: "host"

  host-receiver:
    ssh: "smartx@192.168.75.102"
    workdir: "/tmp/netsherlock"
    role: "host"

test_pairs:
  vm:
    server: "vm-receiver"            # 接收端 (先启动)
    client: "vm-sender"              # 发送端
```

**关键字段说明**:

| 字段 | 说明 | 重要性 |
|------|------|--------|
| `ssh` | SSH 连接字符串 (user@host) | 必需 |
| `test_ip` | 测试流量 IP，可能与 SSH IP 不同! | **关键** |
| `host_ref` | VM 关联的宿主机节点名 | VM 必需 |
| `uuid` | VM UUID | VM 必需 |
| `test_pairs` | 定义 server/client 配对 | 跨节点诊断必需 |

### 4.2 GlobalInventory (自动模式)

**用途**: 预配置资产清单，从告警参数自动构建 MinimalInputConfig

```yaml
# config/global-inventory.yaml
hosts:
  host-192-168-75-101:
    mgmt_ip: "192.168.75.101"
    ssh:
      user: "smartx"
      key_file: "/root/.ssh/host_key"
    network_types: ["mgt", "storage", "access"]

vms:
  vm-ae6aa164:
    uuid: "ae6aa164-604c-4cb0-84b8-2dea034307f1"
    host_ref: "host-192-168-75-101"
    ssh:
      user: "root"
      host: "192.168.2.100"
    test_ip: "10.0.0.1"
```

**自动模式工作流**:
```
1. 告警包含: src_host_ip=192.168.75.101, src_vm_uuid=ae6aa164-...
2. GlobalInventory.find_host_by_ip() 查找主机
3. GlobalInventory.find_vm_by_uuid() 查找 VM
4. GlobalInventory.build_minimal_input() 构建配置
5. 执行诊断流程
```

### 4.3 test_ip vs SSH IP

**重要**: `test_ip` 可能与 SSH 管理 IP 不同!

| 场景 | SSH IP | test_ip | 说明 |
|------|--------|---------|------|
| 管理网 vs 业务网 | 192.168.2.100 | 10.0.0.1 | 延迟问题在业务网 |
| 多网卡 VM | 192.168.2.100 (eth0) | 172.16.0.1 (eth1) | 测试存储网络 |

BPF 工具使用 `test_ip` 过滤数据包，必须是实际测试流量的 IP!

---

## 五、数据流设计

### 5.1 手动模式数据流

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 用户准备配置文件                                                         │
│ ────────────────                                                        │
│ config/minimal-input.yaml                                               │
│   • nodes: SSH 连接信息                                                  │
│   • test_ip: 测试流量 IP                                                │
│   • test_pairs: server/client 配对                                      │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ CLI 触发诊断                                                             │
│ ────────────                                                            │
│ netsherlock diagnose \                                                  │
│   --config minimal-input.yaml \                                         │
│   --network-type vm \                                                   │
│   --src-host 192.168.75.101 --src-vm <UUID> \                          │
│   --dst-host 192.168.75.102 --dst-vm <UUID>                            │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   DiagnosisController         │
                    │   _load_minimal_input()       │
                    │   → MinimalInputConfig        │
                    └───────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ L1: 监控数据查询 (直接实现)                                              │
│ ─────────────────────────                                               │
│ • GrafanaClient.query_metrics()                                         │
│ • LokiClient.query_logs()                                               │
│ → L1Context                                                             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ L2: 环境收集 (via network-env-collector Skill)                          │
│ ──────────────────────────────────────────────                          │
│ SkillExecutor.invoke("network-env-collector", {                         │
│   "mode": "vm",                                                         │
│   "uuid": request.src_vm,                                               │
│   "host_ip": MinimalInput.host-sender.ssh.host,                        │
│   "host_user": MinimalInput.host-sender.ssh.user,                      │
│   "vm_host": MinimalInput.vm-sender.ssh.host,                          │
│   "vm_user": MinimalInput.vm-sender.ssh.user,                          │
│ })                                                                      │
│ → VMNetworkEnv                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ L3: 精确测量 (via vm-latency-measurement Skill)                         │
│ ──────────────────────────────────────────────                          │
│ SkillExecutor.invoke("vm-latency-measurement", {                        │
│   "sender_vm_ssh": MinimalInput.vm-sender.ssh,                         │
│   "sender_vm_test_ip": MinimalInput.vm-sender.test_ip,                 │
│   "receiver_vm_ssh": MinimalInput.vm-receiver.ssh,                     │
│   "receiver_vm_test_ip": MinimalInput.vm-receiver.test_ip,             │
│   ...                                                                   │
│ })                                                                      │
│ → MeasurementResult (segments, total_rtt)                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ L4: 分析报告 (via vm-latency-analysis Skill)                            │
│ ────────────────────────────────────────────                            │
│ 1. 数据计算: _calculate_breakdown(measurements)                         │
│ 2. LLM 推理: SkillExecutor.invoke("vm-latency-analysis", {...})        │
│ → AnalysisResult (root_cause, confidence, recommendations)             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ 输出: DiagnosisResult                                                    │
│ ───────────────────                                                     │
│ {                                                                       │
│   "diagnosis_id": "diag-abc12345",                                     │
│   "status": "completed",                                                │
│   "summary": "VM 网络延迟异常，瓶颈在 sender_host 层",                  │
│   "root_cause": {"category": "sender_host", "confidence": 0.85},       │
│   "recommendations": [                                                  │
│     {"action": "检查 vhost worker CPU 亲和性", "priority": "high"}      │
│   ]                                                                     │
│ }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 六、Checkpoint 设计 (Interactive Mode)

### 6.1 检查点类型

| Checkpoint | 触发时机 | 用户操作 |
|------------|----------|----------|
| `PROBLEM_CLASSIFICATION` | L2 完成后 | 确认/修改问题分类 |
| `MEASUREMENT_PLAN` | L3 执行前 | 确认/取消测量计划 |
| `FURTHER_DIAGNOSIS` | L4 完成后 | 是否深入诊断 |

### 6.2 交互流程

```
Phase 1: L1 + L2 (自动执行)
        │
        ▼
╔═══════════════════════════════════════╗
║   Checkpoint 1: PROBLEM_CLASSIFICATION ║
║   ─────────────────────────────────── ║
║   检测到 VM 网络延迟问题               ║
║   置信度: 90%                          ║
║                                       ║
║   [1] 确认  [2] 修改  [3] 取消        ║
╚═══════════════════════════════════════╝
        │
        ▼ (用户确认)
Phase 2: 测量计划
        │
        ▼
╔═══════════════════════════════════════╗
║   Checkpoint 2: MEASUREMENT_PLAN       ║
║   ─────────────────────────────────── ║
║   计划: vm-latency-measurement        ║
║   时长: 30 秒                          ║
║   影响: CPU < 5%                       ║
║                                       ║
║   [1] 执行  [2] 修改  [3] 取消        ║
╚═══════════════════════════════════════╝
        │
        ▼ (用户确认)
Phase 3: L3 执行
Phase 4: L4 分析
        │
        ▼
输出诊断报告
```

---

## 七、Skills 定义

### 7.1 network-env-collector

**位置**: `.claude/skills/network-env-collector/`

**功能**: 收集 KVM 虚拟化主机的网络环境信息

**输入参数**:
```yaml
mode: "vm" | "system"
uuid: "VM UUID"           # mode=vm 时
host_ip: "宿主机 IP"
host_user: "SSH 用户"
vm_host: "VM SSH IP"      # 可选
vm_user: "VM SSH 用户"    # 可选
```

**输出**: VMNetworkEnv (JSON)

### 7.2 vm-latency-measurement

**位置**: `.claude/skills/vm-latency-measurement/`

**功能**: 协调 8 点延迟测量，保证 receiver-first 时序

**输入参数**:
```yaml
sender:
  vm:
    ssh: "root@10.0.0.1"
    ip: "10.0.0.1"
  host:
    ssh: "root@192.168.1.10"
    vnet_interface: "vnet0"
receiver:
  vm:
    ssh: "root@10.0.0.2"
    ip: "10.0.0.2"
  host:
    ssh: "root@192.168.1.20"
    vnet_interface: "vnet0"
measurement:
  duration: 30
```

**输出**: MeasurementResult (segments, total_rtt, log_files)

### 7.3 vm-latency-analysis

**位置**: `.claude/skills/vm-latency-analysis/`

**功能**: 分析测量数据，识别根因，生成报告

**输入参数**:
```yaml
breakdown:
  total_rtt_us: 5000
  segments:
    A: {p50: 100, p95: 200}
    B: {p50: 500, p95: 1000}
    ...
environment:
  src_env: {...}
  dst_env: {...}
```

**输出**: AnalysisResult (primary_contributor, confidence, recommendations)

---

## 八、测试覆盖

### 8.1 测试统计

| 类别 | 测试文件 | 测试数 |
|------|----------|--------|
| MinimalInputConfig | `test_minimal_input.py` | 45 |
| GlobalInventory | `test_global_inventory.py` | 40 |
| SkillExecutor | `test_skill_executor.py` | 35 |
| DiagnosisController | `test_controller_skills.py` | 60 |
| 集成测试 | `test_integration_workflow.py` | 50 |
| **总计** | | **642** |

### 8.2 关键测试场景

1. **MinimalInputConfig 加载**: YAML 解析、节点查找、验证
2. **GlobalInventory 构建**: IP/UUID 查找、MinimalInput 生成
3. **Skill 调用**: 参数构建、结果解析、错误处理
4. **端到端流程**: 手动模式、自动模式、Checkpoint 交互

---

## 九、版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| 4.0 | 2026-01-22 | 根据实际实现重写，Skill 驱动架构 |
| 3.2 | 2026-01-22 | 功能 review，添加架构演进说明 |
| 3.1 | 2026-01-20 | CLI 参数重构 |
| 3.0 | 2026-01-19 | MVP 实现完成 |
