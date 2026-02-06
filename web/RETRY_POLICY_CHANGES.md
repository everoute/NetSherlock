# Retry Policy 变更

## 变更摘要

调整任务重试策略，仅允许 cancelled 状态的任务重试，不支持失败任务的重试。

---

## 变更详情

### ✅ 保留功能
**Cancelled 任务可以重试**
```
任务列表中 cancelled 状态 → [RotateCw Retry] 按钮保留
```

- 用户主动取消的任务可以重新执行
- 点击 Retry 按钮重新开始诊断

### ❌ 移除功能
**Failed 任务不再能重试**
```
改进前：error/interrupted 状态 → [Logs] [Retry]
改进后：error/interrupted 状态 → [Logs]（无Retry）
```

---

## 任务状态和 Retry 支持矩阵

| 状态 | Retry 支持 | 显示操作 | 说明 |
|------|-----------|---------|------|
| **pending** | ❌ 不支持 | [Cancel] | 等待中任务 |
| **running** | ❌ 不支持 | [Logs] | 运行中任务 |
| **waiting** | ❌ 不支持 | [Logs] | 等待资源 |
| **completed** | ❌ 不支持 | [Report] | 已完成任务 |
| **error** | ❌ 不支持 | [Logs] | 失败任务（❌ 不能重试） |
| **interrupted** | ❌ 不支持 | [Logs] | 被中断任务（❌ 不能重试） |
| **cancelled** | ✅ 支持 | [Retry] | 取消任务（✅ 可以重试） |

---

## UI 变化对比

### 改进前
```
error        [Logs] [Retry]   ← 失败任务可重试
interrupted  [Logs] [Retry]   ← 中断任务可重试
cancelled    [Retry]          ← 取消任务可重试
```

### 改进后
```
error        [Logs]           ← 失败任务不能重试 ✓
interrupted  [Logs]           ← 中断任务不能重试 ✓
cancelled    [Retry]          ← 取消任务可以重试 ✓
```

---

## 代码变更

### TasksPage.tsx

**删除 error/interrupted 的 Retry 按钮**

```tsx
// 改进前
if (task.status === 'error' || task.status === 'interrupted') {
  actions.push(
    <Link>Logs</Link>
  )
  actions.push(
    <button>Retry</button>  // ❌ 已删除
  )
}

// 改进后
if (task.status === 'error' || task.status === 'interrupted') {
  actions.push(
    <Link>Logs</Link>
  )
}
```

**保留 cancelled 的 Retry**

```tsx
// 保持不变
if (task.status === 'cancelled') {
  actions.push(
    <button>Retry</button>  // ✓ 保留
  )
}
```

---

## 变更原因

### 1. Failed 任务不应自动重试

**问题原因**：
- Error/Interrupted 状态表示任务执行失败
- 直接重试可能重复相同的错误
- 应先检查日志找出根本原因

**解决方案**：
- 用户可查看诊断日志（[Logs] 按钮）
- 了解失败原因后手动调整参数
- 然后创建新的诊断任务

### 2. Cancelled 任务可以重试

**原因**：
- Cancelled 状态 = 用户主动取消
- 不是系统错误，而是用户操作
- 用户可能想修改参数后重试

**应用场景**：
- 用户启动了错误的诊断
- 需要修改参数重新诊断
- 直接点击 [Retry] 重新开始

---

## 工作流对比

### 失败任务处理流程

```
诊断执行
   ↓
Error ❌
   ├─ 旧方案: [Logs] [Retry]
   │           ↓
   │      重复失败 ❌
   │
   └─ 新方案: [Logs]
             ↓
        1. 查看诊断日志
        2. 分析失败原因
        3. 修改参数或配置
        4. 创建新的诊断任务
        5. 执行新诊断 ✓
```

### 取消任务重试流程

```
用户启动诊断
   ↓
用户中途取消 (Cancelled)
   ↓
用户点击 [Retry]
   ↓
重新执行诊断 ✓
```

---

## 后端需求

**无特殊后端需求**
- 后端无需实现 retry 接口
- `POST /diagnosis/{id}/retry` 不需要实现
- 重试是通过创建新的诊断任务完成的

---

## 编译验证

✅ TypeScript: 0 errors
✅ Vite Build: ✓ built
✅ 功能完整: ✓

---

## 文件变更

| 文件 | 变更 |
|------|------|
| src/pages/TasksPage.tsx | ✏️ 移除 error/interrupted 的 Retry 按钮 |

---

## 用户通知

### 失败任务处理

当任务失败时：
1. ✓ 点击 [Logs] 查看详细日志
2. ✓ 分析诊断日志找出原因
3. ✓ 修改诊断参数（如网络配置、超时时间等）
4. ✓ 创建新的诊断任务
5. ✓ 重新执行诊断

**不支持直接点击 [Retry] 重新执行失败任务**

### 取消任务处理

当任务被取消时：
1. ✓ 任务状态变为 "cancelled"
2. ✓ 点击 [Retry] 重新执行
3. ✓ 直接开始新的诊断（使用相同参数）

---

## 后续改进建议

- [ ] 在失败任务详情页显示"创建相似诊断"快捷按钮
- [ ] 提供诊断参数预填充功能
- [ ] 显示诊断失败的原因摘要
- [ ] 记录诊断历史便于用户参考
- [ ] 显示类似失败的诊断统计
