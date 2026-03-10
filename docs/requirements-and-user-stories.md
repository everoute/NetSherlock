# 网络运维智能化探索：需求分析与用户故事

## 1. 战略背景与思考

### 1.1 行业现状：网络运维的挑战与机遇

在超融合（Hyper-Converged Infrastructure, HCI）和大规模虚拟化环境中，网络运维正面临前所未有的挑战。传统的物理网络排查经验——抓包、看接口计数器、查路由表——在虚拟化网络栈中已经远远不够。当一个 VM 中的存储 IO 请求发出后，数据包需要经过一条极其复杂的路径：

```
VM 应用层 → Guest 内核网络栈 → virtio-net → vhost-net → TUN/TAP → OVS Kernel Datapath → 物理网卡 → [物理网络] → 物理网卡 → OVS → TUN/TAP → vhost-net → virtio-net → Guest 内核 → 目标 VM
```

这条路径横跨 6 层以上的软件抽象层，每一层都有独立的队列、调度机制和潜在的性能瓶颈。故障可能发生在任何一层，而症状——延迟升高、丢包、吞吐下降——却往往在最上层的应用侧才被感知到，中间的因果链难以用传统手段还原。

这种环境下的网络运维面临三个维度的核心挑战：

| 挑战维度 | 具体表现 | 影响 |
|----------|---------|------|
| **路径复杂度** | VM → virtio → vhost → TUN/TAP → OVS → 物理网卡，跨 6+ 层网络栈 | 故障定位需逐层排查，排列组合爆炸 |
| **工具专业性** | 65+ 个 eBPF 测量工具，各有不同参数、过滤条件和输出格式 | 对使用者的 kernel 知识要求极高 |
| **方法论门槛** | "先定界后详情" 的分层诊断方法论需要深厚的专家经验 | 知道问题在哪一层之后才能选对工具，而知道选哪个工具本身就需要经验 |

**路径复杂度**方面，以一个典型的 VM 间网络延迟问题为例：当用户报告虚拟机之间 ICMP ping 延迟从正常的 0.3ms 飙升到 5ms，运维人员需要判断这额外的 4.7ms 被消耗在了 virtio ring buffer 的排队等待、vhost worker 线程的 CPU 调度延迟、OVS 内核模块的 flow table 查找、还是物理网络的传输中。这些组件分布在不同的内核子系统中，没有统一的观测手段。

**工具专业性**方面，即使我们已经构建了覆盖全路径的 eBPF 测量工具集，每个工具的使用仍然需要理解其 tracepoint 挂载位置、参数含义和输出格式。例如，`vm_network_latency_summary` 需要指定 `--vnet`（虚拟网卡名）、`--phy-nic`（物理网卡名）、`--src-ip`（过滤条件）等参数，而这些参数值需要通过 `ovs-vsctl`、`virsh dumpxml`、`ip link` 等命令从运行环境中提取。

**方法论门槛**方面，有效的网络诊断遵循"先定界后详情"（Boundary First, Then Details）的原则：先用轻量级工具确定问题发生在哪个大的区间（发送端内部、物理网络、接收端内部），再针对定位到的区间部署详细的测量工具。这种分层递进的方法论是多年实战经验的结晶，难以通过文档传递给一线运维人员。

然而，挑战的另一面是机遇。正是因为虚拟化网络栈是完全软件定义的，我们才有可能通过 eBPF 在内核的关键路径上挂载探针，获取微秒级的时间戳和事件信息——这是在传统物理网络中不可能做到的事情。问题不在于数据获取能力的缺失，而在于如何将这些强大但复杂的能力，转化为一线运维人员可以直接使用的智能化工具。

### 1.2 核心优势分析

在探讨 AI 如何融入网络运维之前，有必要先审视我们所处的独特位置。与面向公众市场的 AI 产品不同，我们拥有几个难以复制的结构性优势。

**特定客户群体与稳定规模**。超融合产品服务的是一个明确的企业客户群——他们有真实的运维痛点，有为解决问题付费的意愿和预算，且客户规模相对稳定可预测。这意味着我们不需要在获客成本上与通用 AI 产品竞争，可以将全部精力聚焦于解决领域内的深层问题。

**已有系统渗透与用户习惯**。我们的监控、管理和运维工具已经部署在客户环境中运行。Grafana Dashboard 是运维人员每天查看的界面，Alertmanager 的告警通知是他们工作流的起点，SSH 到节点执行命令是他们的日常操作。这种系统级的渗透意味着 AI 能力的引入不需要改变用户的工作习惯——而是在他们已有的工作流中增强能力。这消除了 AI 产品最大的阻力：冷启动和用户迁移。

**领域数据的天然积累**。每一次告警触发、每一条 OVS 日志、每一个 Grafana 时序指标，都是 AI 模型理解网络行为的训练信号。这些数据不需要额外采集——它们是系统正常运行的副产品。5641 个 Prometheus 指标、78 个 Loki 服务标签、多维度的 pingmesh 探测数据，构成了一个其他竞争者无法轻易获得的领域知识库。

**核心战略判断：服务好现有客户 = 将智能融入每一个触点**。AI 的价值不在于追逐技术热点，而在于将智能能力无缝嵌入客户已有的工作流中。当运维人员收到一条"VM 网络延迟高"的告警时，他不需要知道背后有 Agent 在调度 eBPF 工具——他只需要看到一份清晰的诊断报告，告诉他问题出在 vhost 线程的 CPU 调度延迟上，以及具体的修复建议。这种"润物细无声"的智能化，比任何独立的 AI 产品都更有价值，因为它直接嵌入在解决问题的上下文中。

### 1.3 AI 融入运维的战略思考

这一节是全文的核心论述。我们尝试从第一性原理出发，回答一个根本问题：**AI 在运维场景中到底应该怎样发挥作用？** 答案可以归结为两个关键词的组合：**Context（上下文）** 和 **Action（行动）**。

#### Context 缺失 — 第一层：已有数据的结构化组织缺失

我们并不缺少数据。Grafana 中有 5641 个 Prometheus 指标持续采集；Loki 中聚合了来自 78 个服务的日志；每个节点的 `/var/log/zbs/` 目录下保存着 pingmesh、l2ping、network-high-latency 等专项日志；OVS 有自己的日志和计数器；内核有 `/proc/net/dev`、`netstat -s` 等统计接口。数据是丰富的——但它们对 AI 模型而言，几乎是不可用的。

问题在于：**这些原始数据缺乏结构化的上下文组织，无法直接转化为 AI 模型的有效输入**。

所谓"结构化的上下文组织"，是指围绕原始数据建立的一整套隐性知识体系。一个有经验的网络工程师在看到 `host_network_ping_time_ns > 5000000` 这条告警时，脑中会自动关联一系列上下文信息：

1. **网络类型与拓扑关系**。这是存储网络的 pingmesh 指标，两端是主机节点；数据路径经过 OVS internal port → OVS kernel datapath → 物理网卡 → 物理交换机 → 对端物理网卡 → OVS → internal port。他知道这条路径上有哪些模块，每个模块可能引入怎样的延迟。

2. **每个模块在多端系统中的角色**。OVS 是虚拟交换机，负责 L2/L3 转发和流表匹配；vhost-net 是用户态与内核态之间的桥梁，使用 eventfd 和 ioeventfd 机制进行通知；TUN/TAP 设备是虚拟网络接口的内核实现。这些角色知识决定了当某个模块出现异常时，该如何解读。

3. **日志和指标的解读方式**。`openvswitch_ovs_async_counter` 增长快意味着 upcall 频繁，可能是 flow table miss 导致包被送到 userspace 处理；`elf_vm_network_drop` 非零需要区分是 RX drop（接收端缓冲区满）还是 TX drop（发送端限速）；`node_netstat_Tcp_RetransSegs` 速率突增可能指向网络丢包但也可能是接收端应用消费慢。每个指标都有其特定的异常阈值和解读逻辑。

4. **模块源码级的深层理解**。为什么 vhost worker 线程可能引入毫秒级延迟？因为 vhost_worker 是一个内核线程，它需要被 CPU 调度器唤醒才能处理 virtio ring 中的数据——如果它被调度到了与 vCPU 不同的 NUMA 节点上的 CPU 核，或者被其他高优先级任务抢占，就会产生调度延迟。这种来自内核源码的深层理解，是正确诊断的基础。

5. **通用的问题解决方法论**。"先定界后详情"——先用 path_tracer 类工具确定延迟主要发生在发送端内部、物理网络还是接收端内部，然后再针对具体区间部署详细测量工具。这种方法论避免了在错误的方向上浪费时间。

**这五类隐性知识，就是第一层 Context 缺失的核心内容。** 原始数据本身（指标值、日志行、计数器）只是冰山一角；要让 AI 模型能够像专家一样理解和使用这些数据，必须将上述隐性知识显式地结构化、系统地组织，作为模型的输入上下文。

这不是一个简单的"知识库建设"任务。它要求我们系统性地梳理：网络类型与拓扑的关系模型、每个模块的角色描述和状态解读规则、每个指标和日志字段的语义标注和异常判断逻辑、关键内核路径的处理流程说明、以及分层诊断方法论的形式化表达。

#### Context 缺失 — 第二层：已有监控无法触及的深层信息

第一层 Context 缺失说的是"已有数据缺乏组织"。第二层则更根本：**有些信息根本不存在于现有的监控和日志中——它们必须通过主动部署深度测量/追踪工具才能获得。**

现有监控体系（Grafana/Prometheus/Loki）提供的是宏观层面的统计信息：接口字节数、丢包率、ping 延迟均值。但网络问题的根因往往隐藏在更深的层次：

- **内核网络栈各阶段的微秒级延迟分布**。一个包从 virtio ring 被 vhost worker 取出到通过 TUN 设备送入 OVS，中间经历了多少微秒？这个延迟的 P99 是多少？是否存在长尾？现有监控无法回答这些问题——需要通过 eBPF 在内核函数入口和出口挂载探针来获取。

- **kfree_skb 丢包事件的完整调用栈**。当一个包在内核中被丢弃时，`kfree_skb` 的调用栈记录了丢包的精确位置——是在 netfilter 规则中被 DROP、在 OVS 内核模块中因 flow table miss 被丢弃、还是在 vnet 设备的 TX queue 满时被丢弃。这些信息只能通过 eBPF 追踪 `kfree_skb` tracepoint 获得。

- **vhost-to-TUN 处理路径的时序关系**。vhost worker 线程从 virtio ring 中读取数据到通过 TUN 设备发送出去的时间间隔，反映了虚拟化层的处理效率。如果这个时间间隔异常，需要进一步分析是 CPU 调度延迟还是锁竞争导致的。这种时序信息只能通过专门的 BPF 工具（如 `kvm_vhost_tun_latency_summary`）获得。

- **OVS datapath 内部的 upcall 延迟和 megaflow 匹配效率**。OVS 的转发性能取决于内核态 flow table 的命中率——当发生 cache miss 时，包需要被 upcall 到用户态的 ovs-vswitchd 进行查找，这个过程可能引入数百微秒甚至毫秒级的延迟。upcall 的频率和延迟分布，只能通过追踪 OVS 内核模块的相关函数获得。

我们已经构建了 84 个 eBPF 测量工具来获取这些深层信息。但这引出了一个新的 Context 组织问题：**如何将这 84 个工具的能力、适用场景、参数格式和输出含义，组织为 AI 模型可理解和可操作的上下文？**

每个工具都有自己的"能力描述"——它能测量什么、需要什么输入参数、产出什么格式的输出、适用于什么问题场景。例如：

- `vm_network_latency_summary`：测量 VM 网络栈 8 个阶段的延迟分布，需要 vnet 名、物理网卡名、过滤 IP；适用于 VM 网络延迟诊断的 segment 模式
- `kernel_drop_stack_stats_summary`：统计内核丢包事件的调用栈分布，需要网卡名和 IP 过滤条件；适用于丢包根因定位
- `ovs_upcall_latency_summary`：测量 OVS upcall 延迟分布，需要源 IP 和协议类型；适用于 OVS 慢路径分析

这些工具的能力描述、相互之间的关系（哪些工具可以组合使用、使用顺序是什么）、以及它们的输出如何被下一步分析所消费——构成了第二层 Context 的核心内容。它与第一层 Context 本质上是同一个问题的不同层面：**将领域知识结构化为 AI 可理解的上下文**。区别在于，第一层的数据已经存在只是缺乏组织，而第二层的数据需要主动获取。

#### Context × Action 闭环

到这里，一个关键洞察浮现出来：**Action（行动）并非独立于 Context（上下文）之外——两者形成一个由智能驱动的迭代闭环。**

首先，**两种层次的 Context 获取本身就是 Action**。查询 Grafana 指标是一个 Action；通过 SSH 采集网络拓扑是一个 Action；在远程节点上部署 eBPF 工具进行测量是一个 Action。Context 不会自动出现——它需要 Agent 主动执行 Action 来获取。

其次，**获取到的 Context 经过智能分析后，会产生新的 Action 决策**。Agent 查询 Grafana 发现延迟异常（Context） → 分析判断需要采集网络拓扑（Action 决策） → 拓扑采集结果显示 VM 跨节点通信（新 Context） → 判断需要部署 boundary 模式的 path_tracer（新 Action 决策） → 测量结果显示发送端内部延迟占 85%（新 Context） → 判断需要进一步执行 segment 模式的 8 点位测量（新 Action 决策）。

这个循环可以形式化表达为：

```
Context 组织 → 智能分析 → Action 执行 → 新的 Context 全景 → 重新评估 → 下一个 Action
     ↑                                                                          │
     └──────────────────────────────────────────────────────────────────────────┘
```

**这个多步闭环循环，才是智能化真正产生价值的地方。** 单次的 Context 查询或单次的 Action 执行都不难——难的是在多轮迭代中持续做出正确的决策：选择正确的下一步 Action、从 Action 结果中提取有效信息、将新信息整合到已有 Context 中、基于更全面的 Context 做出更精准的下一步判断。

NetSherlock 的四层架构正是这个闭环的具体实践：

- **L1（基础监控查询）**：获取第一层 Context。Agent 查询 Grafana 指标、Loki 日志、pingmesh 数据，构建问题的初始画像。这是 Action（查询）产生 Context 的第一步。

- **L2（环境采集）+ L3（深度测量）**：获取第二层 Context。L2 通过 SSH 采集网络拓扑（OVS bridge、vnet 设备、物理网卡映射关系），L3 通过部署 eBPF 工具获取微秒级测量数据。这些 Context 是现有监控无法提供的，必须通过主动的 Action（SSH 执行命令、部署 BPF 工具）获取。

- **L4（分析与决策）**：智能分析已获取的全部 Context，生成诊断结论。更重要的是，L4 的分析结果会触发对闭环下一轮的决策——是否需要更深入的测量？应该使用哪个专项工具？问题是否已经定位到足以给出修复建议？

每一轮 L3 + L4 构成闭环的一个迭代。在 Interactive 模式下，这个迭代可以持续多轮：boundary 定界 → segment 分段 → specialized 专项分析，每一轮的输出都成为下一轮决策的输入。

#### 小结

AI 融入运维的核心不是"用 AI 替代人"或"用 AI 写报告"，而是：

1. **系统化地组织两个层次的 Context**——已有数据的结构化（第一层）和深度测量能力的知识化（第二层）
2. **构建 Context × Action 的智能闭环**——让 AI 驱动多步迭代的诊断过程，每一步都基于前一步的结果做出决策
3. **将专家经验编码在闭环的控制逻辑中**——分层诊断方法论不再是个人经验，而是 Agent 的决策框架

### 1.4 战略思想在其他层面的推广与运用

上一节提出的 **Context（两层）× Action 闭环** 框架并非仅适用于网络运维。事实上，它可以作为一个通用的思维模型，推广到产品中其他需要智能化的运维场景。

核心模式可以提炼为：

- **第一层 Context**：已有监控/日志/配置数据的结构化组织——让 AI 能理解已有信息
- **第二层 Context**：通过深度测量/追踪工具主动获取的深层信息——突破已有监控的观测盲区
- **Action 闭环**：基于 Context 分析 → 执行 Action → 获取新 Context → 再次分析 → 下一步 Action

以下是该框架在其他运维场景中的映射：

| 场景 | 第一层 Context（已有数据的结构化） | 第二层 Context（深度测量/追踪） | Action 闭环 |
|------|-----------------------------------|-------------------------------|-------------|
| **存储运维** | SMART 指标、IO 延迟统计、ZBS 日志、磁盘健康度指标、存储池容量与配置 | 块级 IO 追踪（blktrace）、存储路径各阶段延迟拆解、SCSI 命令时序、缓存命中率实时采样 | 指标异常告警 → IO 模式分析 → 部署追踪工具 → 延迟归因 → 定位慢盘/热点/配置问题 → 修复建议 |
| **集群管理** | 集群配置、变更日志、节点状态、服务健康检查、资源利用率、调度历史 | 实时状态探测（进程状态、连接状态、锁状态）、分布式追踪、一致性状态检查 | 状态异常 → 配置审计 → 实时探测 → 根因分析 → 验证修复 → 确认恢复 |
| **用户支持** | 工单历史、知识库文档、FAQ、已知问题库、客户环境配置档案 | 远程诊断数据采集（客户环境日志、配置快照、性能数据）、现场追踪工具输出 | 工单接入 → 历史匹配 → 远程采集 → 智能诊断 → 生成解决方案 → 跟踪确认 |

几个值得强调的要点：

**第二层 Context 是每个场景的差异化关键**。存储场景的 blktrace 块级追踪、集群场景的分布式一致性探测、用户支持场景的远程诊断数据——这些都是超越常规监控的深层信息获取能力。与网络场景中的 eBPF 测量工具类比，每个场景都有自己的"深度工具集"，需要被结构化为 AI 可理解和可操作的上下文。

**闭环的多步迭代在每个场景中都至关重要**。存储诊断可能需要：慢盘识别 → IO 模式分析 → 缓存效率评估 → 队列深度调优建议。集群管理可能需要：节点异常检测 → 服务依赖追踪 → 配置变更审计 → 自动修复 → 状态确认。每一步的输出驱动下一步的决策，这正是 Context × Action 闭环的价值所在。

**已有客户数据和系统渗透是最好的起点**。回到 §1.2 的核心优势分析：我们不需要冷启动——存储指标已经在采集，集群日志已经在记录，工单系统已经在运转。每个场景的第一层 Context 已经存在，需要的是结构化组织；第二层 Context 的获取能力（深度工具集）需要建设，但可以借鉴网络场景中 eBPF 工具集的建设经验。

**框架是通用的，实施是逐步的**。并非所有场景需要同时推进。网络运维场景因为工具集最成熟（84 个 eBPF 工具已就绪）、痛点最尖锐（路径复杂度最高）、闭环最完整（L1-L4 四层已实现），成为最适合率先落地的场景。其他场景可以在网络场景验证成功后，复用架构模式和实施经验，逐步推广。

---

## 2. 网络智能诊断：场景与规划

### 2.1 第一阶段成果回顾：eBPF 测量工具集

在开始规划智能诊断平台之前，有必要回顾我们已有的基础资产——`troubleshooting-tools` 仓库中的 eBPF 测量工具集。这是整个智能化建设的底座。

**工具集规模**：84 个测量工具

| 类型 | 数量 | 说明 |
|------|------|------|
| BCC Python 工具 | 59 | 基于 BCC 框架的 eBPF 工具，功能最丰富 |
| bpftrace 脚本 | 20 | 轻量级追踪脚本，适合快速探测 |
| Shell 脚本 | 5 | 环境采集和辅助工具 |

**覆盖范围**：VM 网络 / 系统（主机间）网络 / 各层单点测量三大领域。

**工具能力矩阵**：

```
                    延迟诊断    丢包检测    性能度量    专项分析
  ┌─────────────┬──────────┬──────────┬──────────┬──────────┐
  │ System 网络  │ ✅ 4工具  │ ✅ 4工具  │ ✅ 4工具  │ ✅ CPU/锁 │
  │ VM 网络     │ ✅ 4工具  │ ✅ 4工具  │ ✅ 4工具  │ ✅ OVS    │
  │ 各层单点    │ ✅ 27工具 │ ✅ 6工具  │          │ ✅ vhost  │
  └─────────────┴──────────┴──────────┴──────────┴──────────┘
```

**三层诊断模型**：工具集在实践中形成了一套成熟的分层诊断方法论：

- **Layer 1 — Summary 工具**：使用内核态 BPF Histogram 聚合，输出统计概览（P50/P95/P99 延迟分布），开销极低可长期运行，用于宏观定位（哪个阶段慢、哪个时段、哪对 IP）
- **Layer 2 — Details 工具**：逐包追踪，记录完整路径上每个阶段的时间戳，支持五元组过滤，用于精确定位瓶颈阶段
- **Layer 3 — Root Cause 工具**：Off-CPU 分析、锁竞争分析、队列/内存分析等专项工具，定位深层根因

**核心矛盾：工具能力越全面，使用复杂度越高**。使用这些工具需要同时掌握：
- 正确的工具组合选择（哪个网络类型？哪种问题？哪种诊断模式？）
- 正确的参数配置（SSH 连接信息、网络设备名称、IP 过滤条件、测量时长、异常阈值）
- 多工具协调执行逻辑（receiver-first 时序约束、双端同步部署、8 点位部署时序）
- 多层测量结果的关联解读（延迟归因计算、丢包位置定位、根因与症状的因果关系）

这正是智能化要解决的核心问题。

### 2.2 从工具集到智能平台的规划路径

工具集的能力是完备的，但交付形式需要根本性的变革。我们规划了一条从手动工具到自主诊断的四阶段演进路径：

```
Stage 0              Stage 1               Stage 2               Stage 3
─────────            ─────────             ─────────             ─────────
65+ eBPF 工具        10 Skills             智能编排               自主诊断
手动操作             自动执行               LLM 辅助               ReAct Agent
专家经验             知识固化               人机协作               自主决策
高认知负担           低使用门槛             交互式引导             零人工干预

troubleshooting      NetSherlock           NetSherlock           NetSherlock
-tools               Phase 1               Phase 2               Phase 3
```

每个阶段对应 Context × Action 框架的不同成熟度：

**Stage 0（当前工具集）— 手动 Context 组织 + 手动 Action 执行**。工程师需要自己理解告警含义、手动 SSH 到节点采集环境信息、手动选择和配置工具、手动解读输出结果。Context 的组织和 Action 的执行完全依赖人的经验和判断。

**Stage 1（确定性编排）— 结构化 Context + 确定性 Action**。将专家经验编码为 Skill：每个 Skill 封装了一组工具的完整使用流程，包括参数映射、协调执行、结果解析。Context 的获取被结构化（L2 环境采集 Skill 自动收集拓扑信息），Action 的执行被确定性编排（WORKFLOW_TABLE 查表决定使用哪个 Skill 组合）。用户只需提供最小输入（目标 IP + SSH 信息），系统自动完成全流程。

**Stage 2（智能编排）— 智能参与 Context 组织 + 人机协作 Action**。引入 LLM 决策引擎：在每轮诊断（L3 + L4）完成后，LLM 综合分析诊断结果、可用 Skill 列表和领域知识，生成下一步建议。人机协作体现在 Checkpoint 机制——系统给出结构化建议（含工具选择、参数配置、预期效果），用户确认后执行。LLM 开始参与 Context 的组织（将多轮诊断结果关联分析）和 Action 的决策（推荐下一步应该用什么工具）。

**Stage 3（自主诊断）— 智能驱动完整闭环**。完全由 ReAct Agent 驱动诊断过程。Agent 自主决定查询什么监控数据、采集什么环境信息、部署什么测量工具、如何解读结果、是否需要更深入的分析。Context 的获取和 Action 的执行完全由智能体自主驱动，实现零人工干预的端到端诊断。

**关键设计原则：底层工具层复用，控制层逐步演进**。从 Stage 0 到 Stage 3，底层的 65+ 个 eBPF 工具保持不变——变化的是它们被组织和调用的方式。Stage 1 将工具封装为 Skill，Stage 2 引入 LLM 进行 Skill 编排决策，Stage 3 由 Agent 自主编排。这种"能力不变，交互革新"的路径，确保了每一步的演进都是增量的、可验证的。

### 2.3 诊断覆盖域：问题类型全景

以下是系统规划覆盖的全部 9 种网络问题类型及其当前状态：

| 问题类型 | 说明 | L1 触发示例 | L3 测量工具 | 状态 |
|----------|------|------------|-------------|------|
| **延迟（Latency）** | VM/系统网络延迟异常 | `host_network_ping_time_ns > 5ms`; VM 间 ping 延迟升高 | `icmp_path_tracer`（boundary）、`vm_network_latency_summary`（segment 8 点位） | ✅ 已实现 |
| **丢包（Packet Drop）** | VM/系统网络丢包 | `host_network_loss_rate > 1%`; `elf_vm_network_drop > 0` | `icmp_drop_detector`（boundary）、`kernel_drop_stack_stats_summary`（详细） | ✅ 已实现 |
| **吞吐/带宽（Throughput）** | 网络吞吐低于预期 | `host_network_transmit_speed_bitps` 低于基线; VM 网络带宽不足 | virtio ring 利用率、vhost worker CPU、NIC queue depth 分析 | 📋 规划中 |
| **TCP 重传（TCP Retransmission）** | TCP 连接质量差 | `node_netstat_Tcp_RetransSegs` 速率突增; `TcpExt_ListenDrops` 增长 | `tcp_connection_analyzer`、拥塞窗口追踪、RTT/inflight 关联分析 | 📋 规划中 |
| **OVS 慢路径（OVS Slow Path）** | OVS 内核态 flow miss 频繁 | `openvswitch_ovs_async_counter` 增长快; ovs-vswitchd CPU 高 | `ovs_upcall_latency_summary`、`ovs_userspace_megaflow`、flow table 分析 | 📋 规划中 |
| **virtio/vhost 争用** | 虚拟化网络栈瓶颈 | VM 网络延迟高但无丢包; vhost worker CPU 饱和 | `vhost_queue_correlation`、virtio ring buffer 占用、NUMA/CPU affinity 分析 | 📋 规划中 |
| **Bond 故障切换（Bond Failover）** | Bond member 状态切换/抖动 | Bond member 状态变化日志; 网络连通性间歇性抖动 | 故障切换时序测量、切换期间丢包统计、LACP 状态追踪 | 💡 远期 |
| **VXLAN/Overlay** | 隧道封装相关问题 | 跨节点 VM 延迟异常高; 分片/MTU 错误 | `skb_frag_list_watcher`、VXLAN 封装/解封时序、MTU 路径发现 | 💡 远期 |
| **CPU/调度争用** | 网络处理相关 CPU 资源不足 | `cpu_cpuset_state_percent{_cpu="cpuset:/zbs/network"}` idle 低; ksoftirqd CPU 高 | `ksoftirqd_sched_latency`、`offcputime-ts`、CPU affinity/NUMA 分析 | 📋 规划中 |

**状态说明**：
- ✅ **已实现**：L3 测量 Skill 和 L4 分析 Skill 均已完成，在 WORKFLOW_TABLE 中注册，可通过 Autonomous/Interactive 模式执行完整诊断流程
- 📋 **规划中**：对应的 eBPF 工具已存在于 troubleshooting-tools 中，需要封装为 NetSherlock Skill 并注册到 WORKFLOW_TABLE
- 💡 **远期**：需要新增测量工具或依赖外部系统集成，列入长期路线图

所有 9 种问题类型都遵循统一的 **L1（告警触发）→ L2（环境采集）→ L3（深度测量）→ L4（分析归因）** 四层架构。已实现的延迟和丢包两种类型验证了这一架构的可行性；后续类型的扩展主要是新增 Skill 实现和 WORKFLOW_TABLE 注册，架构本身无需变更。

---

## 3. 用户与场景分析

### 3.1 用户角色

NetSherlock 面向三类核心用户，他们在诊断流程中的参与深度和关注焦点各有不同：

| 角色 | 使用方式 | 核心诉求 | 与系统的交互模式 |
|------|---------|---------|----------------|
| **一线运维** | 收到告警后触发诊断，查看最终报告 | 降低排查门槛，快速定位问题，无需了解 eBPF/BPF 工具细节 | Autonomous 模式为主；输入是告警，输出是包含根因和修复建议的报告 |
| **网络专家** | Interactive 模式深入分析，在 Checkpoint 处选择下一步 Skill | 工具编排自动化，释放认知负担，专注于分析决策而非工具操作 | Interactive 模式为主；在每轮 L3→L4 后审视建议，决定是否深入、切换方向或终止 |
| **运维管理者** | 查看诊断报告和趋势统计，评估运维效能 | 问题可见性（哪些类型的网络问题最频繁），MTTR 缩短可量化 | 通过前端 Dashboard 或 API 集成查看历史诊断记录和统计 |

三类角色的分层恰好映射到 Context × Action 闭环的不同参与层次：一线运维只消费最终输出（完整闭环的结果），网络专家参与闭环的决策节点（在 Checkpoint 处介入），运维管理者关注闭环的宏观效果（MTTR、诊断覆盖率等指标）。

### 3.2 核心用户场景与 User Stories

#### 3.2.1 告警自动触发（Autonomous）

**场景描述**：Alertmanager 检测到网络指标异常，通过 Webhook 自动触发 NetSherlock 诊断。系统无需人工干预，自动完成 L1（指标查询）→ L2（环境采集）→ L3（深度测量）→ L4（分析归因）全流程，输出诊断报告。

> **US-1**：作为一线运维，当 VM 网络延迟告警触发时（`host_network_ping_time_ns > 5ms`），我希望系统自动完成环境采集、eBPF 测量工具部署、数据分析，输出包含根因定位和修复建议的诊断报告，使我无需了解 BPF 工具细节即可处理告警。
>
> **验收标准**：
> - 告警触发到报告生成全程无人工介入
> - 报告包含：问题分类、测量数据摘要、根因定位、修复建议
> - 报告中的根因描述使用运维人员可理解的语言（如 "vhost 线程 CPU 调度延迟"），而非底层技术细节（如 "kprobe:vhost_net_buf_produce latency P99 = 3.2ms"）

> **US-2**：作为一线运维，当系统网络丢包告警触发时（`host_network_loss_rate > 1%`），我希望系统自动执行 boundary 定界诊断，确定丢包发生在发送端、物理网络还是接收端，并给出具体丢包位置的内核调用栈分析。
>
> **验收标准**：
> - 报告明确指出丢包区间（sender-internal / physical-network / receiver-internal）
> - 如果定位到内核丢包，报告包含 `kfree_skb` 调用栈的可读性解释

#### 3.2.2 手动 CLI 触发（Interactive）

**场景描述**：网络专家在排查复杂问题时，通过 CLI 手动发起诊断。系统以 Interactive 模式运行，在关键决策点（问题分类确认、测量方案确认、是否继续深入）设置 Checkpoint，由专家确认或调整后继续。

> **US-3**：作为网络专家，我希望通过 CLI 指定目标环境后，系统引导我逐步深入诊断——先进行 boundary 定界确认问题在发送端内部，再选择 segment 分段测量精确定位瓶颈在 virtio 层还是 vhost 层——每一步都展示建议供我选择，我可以接受建议或修改参数。
>
> **验收标准**：
> - 系统在问题分类、测量方案选择处暂停等待确认
> - 每个 Checkpoint 展示当前诊断上下文和建议的下一步操作
> - 专家可以修改建议参数（如切换 network_type、调整测量时长）
> - 最终报告包含所有阶段的诊断历史，形成完整的分析链条

#### 3.2.3 API 集成触发

**场景描述**：运维平台通过 REST API 集成 NetSherlock 的诊断能力，将网络诊断嵌入到现有运维工作流中。

> **US-4**：作为运维平台开发者，我希望通过 REST API（`POST /diagnose`）提交诊断请求并通过 `GET /diagnose/{id}` 异步查询结果，将 NetSherlock 的诊断能力集成到现有运维平台中，用户无需离开平台即可获取网络诊断报告。
>
> **验收标准**：
> - API 返回诊断 ID 后可立即通过 GET 查询状态（pending → running → completed）
> - 诊断结果以结构化 JSON 返回，包含分类、测量数据、分析结论
> - API 支持 API Key 认证，防止未授权访问
> - 支持通过 `GET /diagnoses` 批量查询诊断历史

#### 3.2.4 多层递归诊断

**场景描述**：这是 Interactive 模式的高级用法，体现了 Context × Action 闭环的多轮迭代特性。第一轮 boundary 定界完成后，L4 分析结果指出某个区间需要更精细的测量，系统基于 WORKFLOW_TABLE 中的升级路径生成下一轮建议，在专家确认后进入新一轮 L3→L4 诊断。

> **US-5**：作为网络专家，在 boundary 定界发现发送端 unmeasured 区域延迟高后，我希望系统建议执行 segment 分段测量以精确定位瓶颈在 virtio ring、vhost worker、TUN 设备还是 OVS 中的哪个环节，并在我确认后自动进入下一轮 L3→L4 诊断。最终报告包含所有阶段的诊断历史，展示从宏观定界到精确定位的完整推理链。
>
> **验收标准**：
> - 第一轮 L4 分析完成后，系统自动生成下一步建议（基于 WORKFLOW_TABLE 升级路径）
> - 建议包含推荐的 Skill 组合、参数配置和预期效果
> - 多轮诊断结果通过 `stage_history` 完整记录，报告中可追溯每一轮的输入和输出
> - 闭环可以持续多轮：boundary → segment → specialized（未来）

> **US-6**：作为运维管理者，我希望查看每次诊断的完整多阶段历史，理解问题是如何从告警定界逐步深入到根因定位的，以此评估诊断系统的有效性和专家团队的决策质量。

### 3.3 触发方式

NetSherlock 提供三种诊断入口，覆盖从自动化到手动操作的全部场景：

**1. Alertmanager Webhook — 监控告警自动触发**

告警类型到诊断请求的自动映射是系统的核心入口。Alertmanager 在检测到网络指标异常后，通过 Webhook（`POST /webhook/alertmanager`）将告警推送到 NetSherlock。系统解析告警 labels，自动完成以下映射：

- **告警类型 → 诊断参数**：从 `alertname`、`instance`、`job` 等 labels 中提取 network_type（vm/system）、request_type（latency/packet_drop）、目标节点 IP 等信息
- **诊断模式判定**：已知告警类型且配置了 `auto_agent_loop` 时使用 Autonomous 模式；否则使用 Interactive 模式等待人工确认
- **20+ 种告警类型覆盖**：包括 `host_network_ping_time_ns`、`host_network_loss_rate`、`elf_vm_network_drop`、`node_netstat_Tcp_RetransSegs` 等关键网络指标

**2. REST API — 编程式集成**

面向运维平台集成的标准 HTTP API：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/diagnose` | POST | 提交诊断请求，返回 `diagnosis_id` |
| `/diagnose/{id}` | GET | 查询诊断状态和结果 |
| `/diagnoses` | GET | 批量查询诊断历史（支持分页和过滤） |
| `/diagnose/{id}/cancel` | POST | 取消运行中的诊断 |
| `/webhook/alertmanager` | POST | 接收 Alertmanager 告警推送 |

所有 API 端点均要求 API Key 认证（通过 `X-API-Key` Header）。诊断请求提交后异步处理，客户端通过轮询 GET 接口获取进度和结果。诊断任务持久化为 JSON 文件，服务重启后自动恢复。

**3. CLI — 命令行手动触发**

面向网络专家的直接操作入口：

```bash
# 自动模式：指定目标后全自动执行
netsherlock diagnose --target 192.168.77.83 --type vm --problem latency --mode autonomous

# 交互模式：在 Checkpoint 处暂停等待确认
netsherlock diagnose --target 192.168.77.83 --type vm --problem latency --mode interactive

# 使用配置文件（MinimalInputConfig YAML）
netsherlock diagnose --config ./diagnosis-config.yaml
```

CLI 模式支持完整的 MinimalInputConfig YAML 配置，包括 SSH 连接信息、测试 IP 对、网络类型等参数。在 Interactive 模式下，CLI 在终端中展示 Checkpoint 信息并等待用户输入。

---

## 4. 功能需求

### 4.1 L1 基础监控

L1 层是 Context × Action 闭环的起点——Agent 通过查询已有监控数据构建问题的初始画像。这一层的质量直接决定了后续 L2/L3 阶段 Action 决策的准确性。

**现有数据源**

| 数据源 | 类型 | 规模 | 接入方式 |
|--------|------|------|---------|
| Grafana / VictoriaMetrics | Prometheus 时序指标 | 5641 个指标，网络相关 ~130 个 | ✅ MCP Tool: `grafana_query_metrics` |
| Loki | 日志聚合 | 78 services, 123 units | ✅ MCP Tool: `loki_query_logs` |
| 节点本地日志 | 文本日志 (SSH) | `/var/log/zbs/` 下 3 类日志 | ✅ MCP Tool: `read_pingmesh_logs` |

节点本地日志包含三类关键网络数据：
- `network-high-latency`：高延迟事件记录，包含时间戳和延迟值
- `l2ping`：L2 层探测结果，反映二层网络连通性
- `pingmesh`：Mesh 拓扑的 ping 统计，覆盖节点间全连接延迟

**关键网络指标分布**

| 指标类别 | 数量 | 代表性指标 | 覆盖范围 |
|----------|------|-----------|---------|
| `host_network_*` | 29 | `ping_time_ns`, `loss_rate`, `speed`, `transmit/receive_speed_bitps` | 主机间网络质量 |
| `node_network_*` | 36 | `receive_bytes_total`, `transmit_bytes_total`, `receive_errs_total`, `receive_drop_total` | 接口级流量/错误统计 |
| `elf_vm_network_*` | 12 | `speed`, `drop`, `errors`, `receive/transmit_bytes` | VM 网络监控 |
| `openvswitch_*` | 9 | `async_counter`, `vlog_counter` | OVS 内部计数器 |

**覆盖缺口分析**

| 领域 | 覆盖状态 | 具体缺失 | 影响 |
|------|---------|---------|------|
| VM 网络 | ⚠️ 较弱 | 无 virtio/vhost 性能指标，无 VM 粒度延迟（仅有接口级聚合） | 无法在 L1 阶段判断 VM 虚拟化层是否异常，必须依赖 L3 测量 |
| 非存储网络 | ❌ 缺失 | 管理网络、业务网络无持续监控（pingmesh 仅覆盖存储网络） | 非存储网络的问题只能通过手动报告触发，无法自动告警 |
| OVS 性能 | ❌ 缺失 | 无 upcall 率、flow table 命中率、megaflow 细节 | OVS 慢路径问题在 L1 阶段不可见，必须依赖 L3 专项工具 |

**L1 层需求**

- 📋 **自定义监控引入**：开发并部署 `vhost-exporter`（virtio/vhost 性能指标）、`ovs-perf-exporter`（OVS datapath 性能指标）、`multi-net-pingmesh`（多网络平面延迟探测），填补观测盲区
- 📋 **告警规则扩展**：基于新引入的指标，建立 VM 粒度延迟/丢包告警规则，实现更精细的自动触发
- 📋 **短期方案**：将现有 L3 工具（如 `icmp_path_tracer`）以轻量 summary 模式降级为持续监控，在自定义 exporter 就绪前提供过渡覆盖
- 💡 **智能基线**：基于历史指标数据自动学习各指标的正常基线范围，替代硬编码阈值

### 4.2 L2 环境感知

L2 层承担 Context 获取中至关重要的一环——采集目标环境的网络拓扑信息，为 L3 测量工具提供正确的参数配置。没有准确的环境信息（哪个 vnet 设备对应哪个 VM、OVS bridge 的端口映射、物理网卡名称），L3 工具根本无法正确部署。

**已实现功能**

- ✅ **network-env-collector Skill**：通过 SSH 连接到目标节点，执行 `ovs-vsctl`、`virsh dumpxml`、`ip link`、`bridge fdb` 等命令，采集完整的网络拓扑信息（OVS bridge 结构、vnet-to-VM 映射、物理网卡名、Bond 配置）
- ✅ **GlobalInventory 资产管理**：维护集群节点和 VM 的资产清单，支持 VM 名称到 IP 的解析、节点 IP 到 SSH 配置的映射
- ✅ **MinimalInputConfig YAML**：标准化的诊断输入配置格式，包含 SSH 连接信息、测试 IP 对、网络类型等，是 Controller 和 Orchestrator 的统一输入接口

**规划功能**

- 📋 **多网络平面感知**：区分管理网络（mgmt）、存储网络（storage）、业务网络（business）的拓扑结构，每个平面有独立的 IP 段、VLAN 和路由策略
- 📋 **拓扑缓存与增量更新**：首次采集后缓存拓扑快照，后续诊断仅采集变更部分，减少 SSH 命令执行开销
- 💡 **自动拓扑发现**：基于 LLDP/ARP/FDB 表自动发现物理网络拓扑，无需预配置

### 4.3 L3 精确测量

L3 层是整个系统的核心差异化能力——通过 eBPF 工具在内核关键路径上挂载探针，获取第二层 Context（深度测量数据）。这些数据是现有监控体系无法提供的，必须通过主动部署测量工具（Action）才能获取。

**已实现工作流（5 种）**

| 网络类型 | 问题类型 | Boundary 定界 | Segment 分段 | 测量 Skill | 分析 Skill |
|----------|---------|:---:|:---:|------------|-----------|
| System | Latency | ✅ | — | `system-network-path-tracer` | `system-network-latency-analysis` |
| System | Drop | ✅ | — | `system-network-path-tracer` | `system-network-drop-analysis` |
| VM | Latency | ✅ | ✅ | `vm-network-path-tracer` / `vm-latency-measurement` | `vm-network-latency-analysis` / `vm-latency-analysis` |
| VM | Drop | ✅ | — | `vm-network-path-tracer` | `vm-network-drop-analysis` |

每个已实现的工作流都在 `WORKFLOW_TABLE` 中注册为 `(network_type, request_type, mode) → (measurement_skill, analysis_skill, param_builder)` 三元组，由 Controller 查表调度。

**工作流覆盖全景（含规划）**

| 网络类型 | 问题类型 | Boundary | Segment | Event | Specialized |
|----------|---------|:---:|:---:|:---:|:---:|
| System | Latency | ✅ | 📋 | 📋 | 📋 |
| System | Drop | ✅ | 📋 | 🔧 | 📋 |
| VM | Latency | ✅ | ✅ | 📋 | 📋 |
| VM | Drop | ✅ | 📋 | 🔧 | — |

**诊断模式说明**：

- **Boundary（边界定界）**：使用 `icmp_path_tracer` 类工具在发送端和接收端双向部署探针，通过比对两端时间戳确定问题发生在 sender-internal、physical-network 还是 receiver-internal 三个大区间。开销低，定位粗粒度，是诊断的第一步
- **Segment（分段测量）**：以 VM 延迟场景为例，在网络栈的 8 个关键点位（virtio TX → vhost → TUN → OVS egress → physical NIC TX → physical NIC RX → OVS ingress → TUN → vhost → virtio RX）部署探针，精确测量每个阶段的延迟分布。需要 VM SSH 访问权限
- **Event（事件追踪）**：追踪单个事件的完整生命周期。如 `kfree_skb` full tracing 记录每次丢包事件的精确位置和完整调用栈
- **Specialized（专项分析）**：针对特定子系统的深度分析。如 OVS flow table 分析、TCP 重传模式分析、IRQ 亲和性分析、CPU 调度延迟分析

**规划需求**

- 📋 **Event 模式实现**：封装 `kfree_skb` full tracing、`packet-event-tracer`、`virtio-event-tracer` 为 Skill，实现逐事件追踪能力
- 📋 **Specialized 模式实现**：封装 OVS flow 分析、TCP 重传追踪、IRQ/CPU 调度分析为专项 Skill
- 📋 **更广泛的工具→Skill 覆盖**：目前 84 个 eBPF 工具中仅有 ~10 个被封装为 Skill（覆盖率 ~12%），需要逐步将更多工具封装为可被 Controller/Orchestrator 编排的 Skill
- 📋 **多点协调增强**：当前协调执行遵循 receiver-first 时序约束（先部署接收端探针，再部署发送端探针）；需要扩展为支持 N 点协调（多跳路径场景）

### 4.4 L4 诊断分析

L4 层是 Context × Action 闭环中"智能分析"的核心——将 L1/L2/L3 收集到的全部 Context 综合分析，输出诊断结论，并决定闭环是否需要继续迭代。

**已实现分析 Skills（6 个）**

| 分析 Skill | 输入 | 输出 | 对应问题类型 |
|-----------|------|------|-------------|
| `system-network-latency-analysis` | boundary 定界测量数据 | 延迟区间归因（sender/network/receiver） | System Latency |
| `system-network-drop-analysis` | boundary 定界测量数据 | 丢包区间定位 | System Drop |
| `vm-network-latency-analysis` | VM boundary 定界测量数据 | VM 网络延迟区间归因 | VM Latency (boundary) |
| `vm-network-drop-analysis` | VM boundary 定界测量数据 | VM 网络丢包区间定位 | VM Drop |
| `vm-latency-analysis` | 8 点位 segment 测量数据 | 各阶段延迟分布、瓶颈阶段识别 | VM Latency (segment) |
| `kernel-stack-analyzer` | 内核调用栈数据 | 调用栈的可读性解释、根因归类 | 通用 |

每个分析 Skill 由 Claude Agent 执行：接收测量数据作为输入，结合 Skill 定义文件中编码的领域知识（指标解读规则、异常阈值、因果推理逻辑），输出结构化的分析结论。分析 Skill 的输出不仅是最终报告的内容来源，也是 Interactive 模式下生成下一轮建议的决策依据。

**规划需求**

- 📋 **跨域关联分析**：将网络诊断结果与存储 IO 指标、计算资源（CPU/内存）指标关联分析。例如，当网络延迟高与 CPU steal time 高同时出现时，根因可能是宿主机资源超售而非网络问题本身
- 📋 **分析结果结构化增强**：统一分析输出的 schema（问题分类、置信度、根因链、受影响范围、修复建议），便于前端渲染和跨诊断对比
- 💡 **知识积累与学习**：将历史诊断数据（告警特征 → 根因归类）作为 RAG（Retrieval-Augmented Generation）知识库，帮助 LLM 在新诊断中快速匹配历史相似案例
- 💡 **自动修复建议的置信度评分**：为每条修复建议标注置信度（基于历史验证数据），帮助运维人员判断建议的可靠性。高置信度建议可考虑自动执行

### 4.5 交互模式

交互模式是 Context × Action 闭环面向用户的体现——决定了人与 Agent 在闭环中的协作方式。不同交互模式对应不同的自主程度，适配不同角色和场景的需求。

**已实现模式**

- ✅ **Autonomous 单层**：`trigger → L1 → L2 → classify → plan → L3 → L4 → report`。全自动执行，无人工介入。Controller 根据 WORKFLOW_TABLE 确定性编排完整流程。适用于一线运维处理已知类型的告警

- ✅ **Interactive 多层递归**：在 Autonomous 基础上引入 Checkpoint 机制和多轮 L3→L4 迭代。具体流程：
  1. L1 + L2 完成后，在 `PROBLEM_CLASSIFICATION` Checkpoint 暂停，展示分类结果供确认/修改
  2. 确认后选择测量方案，在 `MEASUREMENT_PLAN` Checkpoint 暂停，展示测量方案供确认
  3. 执行 L3 测量 + L4 分析
  4. 分析完成后，在 `STAGE_RESULT` Checkpoint 暂停，展示本轮结果和下一步建议
  5. 如果专家选择继续深入，进入新一轮 L3→L4（回到步骤 2）
  6. 如果专家选择终止，生成包含所有阶段历史的最终报告

- ✅ **阶段建议生成**：当前基于规则驱动——根据 WORKFLOW_TABLE 中的升级路径（boundary → segment → specialized），结合当前诊断结果（哪个区间异常），生成结构化的下一步建议列表

**部分实现**

- 🔧 **LLM 建议引擎**：用 LLM 替代规则驱动的建议生成，实现更灵活、更准确的下一步推荐

  | 维度 | 当前状态（规则驱动） | 目标状态（LLM 驱动） |
  |------|-------------------|-------------------|
  | 输入 | WORKFLOW_TABLE 升级路径 + 当前异常区间 | 完整诊断 Context + 测量数据 + 领域知识库 + Skill Library + LLM 领域知识 |
  | 决策逻辑 | 固定映射（boundary→segment, system→vm） | LLM 综合分析，考虑多因素权衡 |
  | 输出 | 单一建议（下一个 Skill） | 结构化建议列表（多个候选 Skill 组合、参数配置、预期效果、推荐理由） |
  | 跨类型推荐 | ❌ 无法跨越 network_type/request_type 边界 | ✅ 可推荐跨类型诊断（如延迟分析发现丢包特征后，建议切换到丢包诊断） |

**规划需求**

- 📋 **Autonomous 多层自动**：将 Interactive 多层递归中的人工确认环节替换为 LLM 自动判定——LLM 分析 L4 结果后，自主决定是否继续下一轮、选择哪个 Skill、配置什么参数。适用于已知模式的批量告警处理
- 📋 **ReAct 交互**：在 Checkpoint 处支持自然语言对话——用户不仅可以选择预设建议，还可以用自然语言描述自己的判断（如 "我怀疑是 OVS flow table 满了，能不能直接看 upcall 延迟？"），由 LLM 将自然语言转化为具体的 Skill 调用计划

### 4.6 智能编排

智能编排层决定了 Context × Action 闭环中 Action 的选择和执行方式——是由确定性规则查表决定（Controller），还是由 AI 自主推理决定（Orchestrator）。两种引擎代表了不同的成熟度阶段，最终走向混合策略。

**✅ ControllerEngine：确定性编排（生产可用）**

ControllerEngine 是当前的生产引擎，采用 Python 硬编码的确定性流程 `L1 → L2 → classify → plan → L3 → L4`：

- **WORKFLOW_TABLE 查表调度**：`(network_type, request_type, mode)` 三元组映射到 `(measurement_skill, analysis_skill, param_builder)` 三元组，5 种工作流已注册
- **Fallback 机制**：当请求的 mode（如 segment）不可用时，自动降级到 boundary 模式
- **Checkpoint 集成**：在 Interactive 模式下，在关键决策点插入 Checkpoint，支持多轮 L3→L4 递归
- **测试覆盖**：316+ 测试用例，覆盖各种工作流路径、边界条件和错误处理

ControllerEngine 的优势是确定性和可靠性——给定相同输入，总是产生相同的执行路径，便于调试和验证。其局限是扩展需要修改代码（新增工作流 = 修改 WORKFLOW_TABLE + 实现 param_builder）。

**🔧 OrchestratorEngine：ReAct 循环（框架就绪）**

OrchestratorEngine 基于 Claude Agent SDK 的 ReAct 循环，由 LLM 自主决定调用哪些工具：

- ✅ Agent 框架已搭建，17 个 MCP 工具已注册，系统 Prompt 已完善
- ❌ `_synthesize_diagnosis()` 为 placeholder——结果合成逻辑未实现
- ❌ Subagent 结果解析未完成——L3/L4 Subagent 的输出无法正确整合到主 Agent 上下文中
- ❌ 无 MinimalInputConfig 加载——无法从标准配置文件中读取 SSH 和环境信息
- ❌ Alert → 节点配置映射缺失——无法将 Alertmanager 的告警 labels 映射到具体的节点 SSH 配置

**规划需求**

- 📋 **Orchestrator 完善**：实现结果合成逻辑、Subagent 编排协调、配置文件接入，使 OrchestratorEngine 达到可测试状态
- 📋 **混合策略**：简单场景（已知类型的告警、已有工作流覆盖）使用 Controller 的确定性路径，复杂场景（未知类型、需要跨域分析、需要多轮推理）渐进切换到 Orchestrator
- 📋 **Orchestrator 护栏**：为 ReAct 循环设置安全边界——最大迭代次数、Token 预算上限、禁止执行的危险操作列表、结果一致性校验

**演进路径与 Context × Action 框架映射**

| 演进阶段 | Context 获取方式 | Action 决策方式 | 实现状态 |
|----------|----------------|----------------|---------|
| **Phase 1：确定性闭环** | 结构化采集（L2 Skill 固定流程） | 确定性序列（WORKFLOW_TABLE 查表） | ✅ 生产可用 |
| **Phase 2：智能辅助闭环** | Intelligence 辅助 Context 组织（LLM 分析哪些 Context 还需要补充） | 人机协作 Action 选择（LLM 建议 + 人工确认） | 🔧 框架就绪 |
| **Phase 3：自主闭环** | Intelligence 驱动完整 Context 获取（Agent 自主决定查询什么、采集什么） | Intelligence 驱动 Action 执行（Agent 自主选择工具、配置参数、判断终止条件） | 📋 远期目标 |

从 Phase 1 到 Phase 3，变化的是闭环中"智能"的参与深度——底层的 eBPF 工具集、Skill 能力、四层架构保持不变，变化的是编排控制层的决策机制。

### 4.7 前端与可视化

前端为运维人员提供可视化的诊断管理和交互界面，是 NetSherlock 面向终端用户的最后一公里。

**当前状态**

- 🔧 **基础框架已搭建**：React 19 + TypeScript + Tailwind CSS + Vite，基于 mock 数据开发

**规划功能**

- 📋 **诊断任务管理**：创建诊断请求、查看任务列表、按状态/类型/时间过滤、查看详情
- 📋 **实时状态推送**：通过 WebSocket 推送运行中诊断的状态更新（L1 进行中 → L2 完成 → L3 部署中...），替代轮询机制
- 📋 **报告查看器**：渲染诊断报告（Markdown 格式），支持测量数据的可视化展示（延迟分布直方图、丢包位置示意图、网络拓扑图）
- 📋 **Interactive Checkpoint UI**：展示 Checkpoint 处的诊断上下文和建议列表，用户通过 UI 选择/修改后确认继续。支持 ReAct 模式下的自然语言对话输入
- 💡 **诊断趋势 Dashboard**：按时间维度展示诊断频次、问题类型分布、平均诊断耗时、MTTR 趋势等运维效能指标

---

## 5. 非功能需求与约束

### 5.1 性能与成本

- **Token 成本控制**：ControllerEngine 每次诊断涉及 3-4 次 LLM 调用（L2 环境采集解析、L3 测量数据格式化、L4 分析归因、报告生成），单次诊断 Token 消耗约 10-20K tokens。OrchestratorEngine 的 ReAct 循环可能产生 5+ 次 LLM 调用，需要设置 Token 预算上限防止失控
- **诊断耗时**：端到端诊断（Autonomous 模式）目标 < 5 分钟。其中 L3 测量阶段（eBPF 工具采集）通常占 60-120 秒（可配置），是耗时主要来源
- **并发诊断**：支持多个诊断任务并行执行，通过 `asyncio.Queue` 和后台 worker 异步处理。需要注意同一节点上的 eBPF 工具并发冲突

### 5.2 SSH 连接管理

- **连接池复用**：通过 `ssh_manager` 维护 SSH 连接池，避免诊断过程中频繁建立/断开连接
- **超时与重试**：SSH 命令执行设置超时（默认 30s），连接失败自动重试（最多 3 次），超时后记录失败原因并降级处理
- **并发控制**：单节点 SSH 并发连接数限制（默认 5），避免过多并发导致节点 SSH 服务拒绝连接
- **凭据来源**：SSH 凭据从 `credentials.yaml` 配置文件或 MinimalInputConfig 中读取，支持密码和密钥两种认证方式

### 5.3 BPF 部署可靠性

- **Receiver-first 时序约束**：双端协调测量时，必须先在接收端部署探针并确认就绪，再在发送端启动发包。这是因为接收端探针未就绪时发送的数据包无法被捕获，导致测量数据不完整
- **工具清理**：测量完成或失败后，必须确保远程节点上的 BPF 工具进程被正确终止、临时文件被清理。通过 `finally` 块和超时强制 kill 机制保障
- **降级策略**：当 segment 模式的前置条件不满足时（如 VM SSH 不可达），自动 fallback 到 boundary 模式，并在诊断报告中记录降级原因和降级后的诊断范围受限说明

### 5.4 安全性

- **SSH 凭据管理**：凭据文件不入版本控制（`.gitignore`），运行时从配置文件或环境变量加载。禁止在日志输出中包含密码、密钥等敏感信息
- **API 认证**：所有 REST API 端点要求 `X-API-Key` Header 认证。Webhook 端点支持 HMAC 签名校验，确保告警来源可信
- **BPF 工具执行权限**：eBPF 工具需要 root 或 `CAP_BPF` 权限。通过 SSH 以特定用户（如 `smartx`）连接后使用 `sudo` 执行，最小化权限暴露面

### 5.5 可扩展性

- **新工作流接入**：扩展诊断覆盖只需两步——(1) 实现新的测量 Skill 和分析 Skill，(2) 在 WORKFLOW_TABLE 中注册新的三元组映射。不需要修改 Controller 核心逻辑
- **新数据源接入**：通过 MCP Tool 协议接入新的数据源，对 L1 层透明扩展
- **Skill 独立性**：每个 Skill 是自包含的 Claude Agent 任务（SKILL.md 定义 + 参数协议），可独立开发、测试和部署

---

## 6. 优先级与路线图

### 6.1 Phase 演进概览

三个 Phase 对应 Context × Action 闭环的三个成熟度层级——从确定性的专家经验编码，到人机协作的智能辅助，最终到完全自主的智能驱动：

```
Phase 1（当前）            Phase 2（智能编排）          Phase 3（自主诊断）
────────────────          ────────────────           ────────────────
确定性 Context 路径         Intelligence 辅助            Intelligence 驱动
+ 确定性 Action 序列        Context 组织                完整闭环
                          + 人机协作 Action 选择

├─ 5 种工作流              ├─ LLM 建议引擎             ├─ ReAct Orchestrator
├─ WORKFLOW_TABLE 查表      ├─ 更多 Skill 覆盖           ├─ 跨域关联分析
├─ Webhook + CLI           ├─ 多层递归诊断增强            ├─ 知识积累学习
├─ Checkpoint 交互         ├─ Event/Specialized 模式    ├─ 自动修复建议
└─ 316+ 测试用例           └─ Autonomous 多层自动        └─ 零人工干预闭环
```

### 6.2 优先级映射

| 优先级 | 内容 | Phase | 说明 |
|--------|------|-------|------|
| **P0** ✅ | 5 种 boundary/segment 工作流 | Phase 1 (done) | 延迟 + 丢包，VM + System 网络覆盖 |
| **P0** ✅ | ControllerEngine 确定性编排 | Phase 1 (done) | WORKFLOW_TABLE + 完整 L1→L2→L3→L4 流程 |
| **P0** ✅ | Interactive Checkpoint 交互 | Phase 1 (done) | 多层递归 L3→L4，StageResult 记录 |
| **P0** ✅ | Webhook + REST API | Phase 1 (done) | Alertmanager 集成 + 手动诊断 API |
| **P1** 📋 | LLM 建议引擎 | Phase 2 | 替代规则驱动的建议生成，支持跨类型推荐 |
| **P1** 📋 | Event / Specialized 工作流 | Phase 2 | `kfree_skb` full tracing, OVS flow 分析, TCP 重传追踪 |
| **P1** 📋 | 更多工具→Skill 覆盖 | Phase 2 | 从 ~10 Skills 扩展到 25+，覆盖吞吐/重传/OVS/vhost 等问题类型 |
| **P2** 📋 | OrchestratorEngine 完善 | Phase 2 | 结果合成 + Subagent 编排 + MinimalInputConfig 接入 |
| **P2** 📋 | Autonomous 多层自动 | Phase 2 | LLM 自动判定是否继续下一轮，无需人工确认 |
| **P2** 📋 | 前端 MVP | Phase 2 | 诊断管理 + 实时状态 + 报告查看 + Checkpoint UI |
| **P2** 📋 | 自定义监控引入 | Phase 2 | vhost-exporter, ovs-perf-exporter, multi-net-pingmesh |
| **P3** 💡 | 完整 ReAct 自主诊断 | Phase 3 | Orchestrator 接管全流程，零人工干预 |
| **P3** 💡 | 跨域关联分析 | Phase 3 | 网络 + 存储 + 计算指标的联合分析 |
| **P3** 💡 | 知识积累与学习 | Phase 3 | 历史诊断数据 → RAG 知识库 → 模式识别 |
| **P3** 💡 | 自动修复执行 | Phase 3 | 高置信度修复建议的自动化执行（需安全审计机制） |

### 6.3 Phase 间的关键里程碑

**Phase 1 → Phase 2 的前提条件**（当前重点）：
- Phase 1 的 5 种工作流在真实环境中稳定运行，通过端到端验证
- Skill 开发模式成熟，新 Skill 的开发周期可控（< 1 周/Skill）
- Interactive Checkpoint 机制在网络专家的实际使用中验证有效

**Phase 2 → Phase 3 的前提条件**：
- LLM 建议引擎的推荐准确率达到可接受水平（专家评估 > 80% 合理性）
- Orchestrator 在受控场景中验证通过，结果与 Controller 一致性校验
- 足够的历史诊断数据积累（100+ cases），支撑 RAG 知识库建设
- 安全审计机制就绪，为自动修复执行提供护栏

**贯穿所有 Phase 的持续工作**：
- 工具集维护：随内核版本更新适配 BPF tracepoint 变更
- Skill 质量保障：每个 Skill 有对应的集成测试和性能基线
- 文档与知识沉淀：每次诊断实践中发现的新模式反馈到 Skill 定义和领域知识库中
