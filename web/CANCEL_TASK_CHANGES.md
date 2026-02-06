# Cancel Task 功能调整

## 变更摘要

调整 Cancel Task 功能，仅保留 pending 任务的取消操作，移除 running 任务的取消操作。

---

## 变更详情

### ✅ 保留的功能

**Pending 任务可以取消**
```
任务列表中 pending 状态 → [XCircle Cancel] 按钮保留
```

- 位置：TasksPage.tsx 的 action 列
- 触发：用户点击 Cancel 按钮
- 效果：调用 `api.cancelDiagnosis(id)`
- API：POST `/diagnosis/{id}/cancel`

---

### ❌ 移除的功能

#### 1. Running 任务不再能取消
```
改进前：Running/Waiting 状态 → [Cancel] 按钮
改进后：Running/Waiting 状态 → 仅显示 [Logs] 按钮
```

**TasksPage.tsx 变更**
```tsx
// 改进前
if (task.status === 'running' || task.status === 'waiting') {
  actions.push(<Link>Logs</Link>)
  actions.push(<button>Cancel</button>)  // ❌ 已移除
}

// 改进后
if (task.status === 'running' || task.status === 'waiting') {
  actions.push(<Link>Logs</Link>)
}
```

#### 2. TaskDetailPage 的 Cancel 按钮移除
```
改进前：Running 任务详情页 → [XCircle Cancel] 按钮
改进后：Running 任务详情页 → 无 Cancel 按钮
```

**TaskDetailPage.tsx 变更**
```tsx
// 改进前
<div className="mt-6 flex gap-3">
  {isRunning && (
    <button>Cancel</button>  // ❌ 已移除
  )}
  {task.status === 'completed' && (
    <Link>View Report</Link>
  )}
</div>

// 改进后
{task.status === 'completed' && (
  <div className="mt-6">
    <Link>View Report</Link>
  </div>
)}
```

#### 3. 移除 isRunning 变量
```tsx
// ❌ 已删除
const isRunning = task.status === 'running' || task.status === 'waiting'

// 原因：不再需要此变量
```

---

## 文件变更清单

| 文件 | 变更 | 说明 |
|------|------|------|
| src/pages/TasksPage.tsx | ✏️ 修改 | 移除 running 任务的 cancel 按钮，保留 pending |
| src/pages/TaskDetailPage.tsx | ✏️ 修改 | 移除所有 cancel 按钮和 isRunning 变量 |
| src/lib/api.ts | ✏️ 修改 | 恢复 cancelDiagnosis 函数 |

---

## 任务状态和 Cancel 支持矩阵

| 状态 | 支持 Cancel | 显示操作 | 说明 |
|------|-----------|---------|------|
| **pending** | ✅ 支持 | [Cancel] | 等待中的任务可以取消 |
| **running** | ❌ 不支持 | [Logs] | 运行中的任务不能取消 |
| **waiting** | ❌ 不支持 | [Logs] | 等待中的任务不能取消 |
| **completed** | ❌ 不支持 | [Report] | 已完成的任务 |
| **error** | ❌ 不支持 | [Logs, Retry] | 错误的任务 |
| **interrupted** | ❌ 不支持 | [Logs, Retry] | 中断的任务 |
| **cancelled** | ❌ 不支持 | [Retry] | 已取消的任务 |

---

## 用户界面变化

### TasksPage - 任务列表

```
状态         操作列显示
────────────────────────
pending    [Cancel]        ← 可以取消
running    [Logs]          ← 不能取消
waiting    [Logs]          ← 不能取消
completed  [Report]        ← 不能取消
error      [Logs] [Retry]  ← 不能取消
```

### TaskDetailPage - 任务详情

```
状态         底部按钮显示
────────────────────────
pending    (无按钮)        ← 无详情页或无按钮
running    (无按钮)        ← 无 Cancel 按钮
waiting    (无按钮)        ← 无 Cancel 按钮
completed  [View Report]   ← 查看报告
```

---

## API 端点状态

| 端点 | 状态 | 用途 |
|------|------|------|
| POST `/diagnosis/{id}/cancel` | ✅ 保留 | 取消 pending 任务 |

**调用时机**：用户在任务列表中点击 pending 任务的 Cancel 按钮

---

## 后端支持需求

后端需要支持：
```
POST /diagnosis/{id}/cancel

适用于 pending 状态的任务
立即取消任务，状态变为 cancelled
```

---

## 编译验证

✅ TypeScript: 0 errors
✅ Vite Build: ✓ built
✅ 功能完整: ✓

---

## 变更原因

1. **Running 任务不可中断** - 运行中的任务应该继续完成，不应中途取消
2. **Pending 任务可取消** - 等待中的任务可以在开始前取消
3. **简化 UI** - 减少用户困惑，明确哪些任务可以取消

---

## 后续建议

- [ ] 确认后端 `/diagnosis/{id}/cancel` API 仅接受 pending 状态
- [ ] 添加确认对话框防止误操作
- [ ] 记录 cancel 操作的审计日志
- [ ] 显示用户谁取消了哪个任务
