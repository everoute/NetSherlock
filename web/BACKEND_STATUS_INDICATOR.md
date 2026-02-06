# 后端状态指示器

## 功能描述

在 Sidebar 左下角添加后端 API 连接状态指示器，实时监控后端服务的健康状态。

## 位置

```
┌─────────────────────────┐
│   NETSHERLOCK           │
├─────────────────────────┤
│ Tasks                   │
│ Reports                 │
│                         │
│                         │
├─────────────────────────┤
│ 🟢 Backend Online       │  ← 后端状态指示器（这里）
│ Logged in as: admin     │
│ [Logout]                │
└─────────────────────────┘
```

## 功能特性

### 1. 状态显示

三种后端状态：

| 状态 | 图标 | 颜色 | 说明 |
|------|------|------|------|
| **Online** | 🟢 Wifi | 绿色 | 后端健康且在线 |
| **Degraded** | 🟡 AlertCircle | 黄色 | 后端运行但性能下降 |
| **Offline** | 🔴 WifiOff | 红色 | 后端离线或无法连接 |

### 2. 实时监控

- ✅ **立即检查** - 组件挂载时立即检查后端状态
- ✅ **定期检查** - 每 10 秒检查一次（可配置）
- ✅ **自动清理** - 组件卸载时清除定时器
- ✅ **错误处理** - 连接失败时显示离线状态

### 3. 鼠标悬停提示

```
Online:    "Backend Online | Queue: 5"
Degraded:  "Backend Degraded: <error message>"
Offline:   "Backend Offline: Connection failed"
```

## 实现细节

### 新建文件

**src/lib/useBackendStatus.ts** - 后端状态监控 Hook

```typescript
export function useBackendStatus(): BackendStatus {
  // 每 10 秒调用 api.getHealth()
  // 更新本地状态
  // 返回 { status, timestamp, queueSize, error }
}
```

### 修改文件

**src/components/Sidebar.tsx** - Sidebar 底部新增状态显示

```tsx
<div className="flex items-center gap-2 px-3 py-2 rounded-lg">
  {getStatusIcon()}
  <span>{getStatusLabel()}</span>
</div>
```

## API 依赖

该功能调用 `GET /health` API：

**请求**:
```bash
GET http://localhost:8000/health
```

**响应** (200 OK):
```json
{
  "status": "healthy",
  "timestamp": "2026-02-06T08:00:00Z",
  "queue_size": 5,
  "engine": "diagnosis-engine"
}
```

## 开发用途

### 模拟数据环境

当 `VITE_USE_MOCK_DATA=true` 时：
- api.getHealth() 应该返回模拟的健康检查响应
- 状态指示器仍然会定期更新（每 10 秒）

### 生产环境

当 `VITE_USE_MOCK_DATA=false` 时：
- api.getHealth() 调用真实的后端 API
- 实时显示真实的后端状态

## 用户体验

### 场景 1: 后端正常运行
```
✅ 绿色 "Backend Online | Queue: 2"
```
用户知道后端可用，可以放心使用应用。

### 场景 2: 后端性能下降
```
⚠️ 黄色 "Backend Degraded | Queue: 50"
```
用户被警告后端可能响应缓慢，但仍可使用。

### 场景 3: 后端离线
```
❌ 红色 "Backend Offline: Connection failed"
```
用户知道后端不可用，某些操作可能失败。

## 技术细节

### 状态转换逻辑

```typescript
const checkHealth = async () => {
  try {
    const response = await api.getHealth()

    // 根据响应状态更新
    if (response.status === 'healthy') {
      setBackendStatus('healthy')
    } else {
      setBackendStatus('degraded')
    }
  } catch (error) {
    // 连接失败
    setBackendStatus('offline')
  }
}
```

### 定时器管理

```typescript
useEffect(() => {
  checkHealth()  // 立即检查

  const interval = setInterval(checkHealth, 10000)  // 10 秒检查一次

  return () => clearInterval(interval)  // 组件卸载时清除
}, [])
```

## 性能考虑

- ✅ **轻量级** - 每 10 秒一次 HTTP 请求
- ✅ **非阻塞** - 异步检查，不影响用户界面
- ✅ **自清理** - 组件卸载时自动清理定时器
- ✅ **缓存友好** - 可利用浏览器缓存机制

## 后续改进

- [ ] 可配置的检查间隔
- [ ] 点击刷新按钮立即检查
- [ ] WebSocket 实时状态推送（替代轮询）
- [ ] 状态变化通知提醒
- [ ] 详细的错误日志面板
- [ ] 过去 1 小时的状态历史

## 编译状态

✅ TypeScript: 0 errors
✅ Vite Build: ✓ built
✅ 功能完整可用

## 测试方法

### 手动测试

1. **后端在线**: 后端正常运行时应显示绿色 "Backend Online"
2. **后端离线**: 关闭后端时应显示红色 "Backend Offline"
3. **悬停提示**: 鼠标悬停显示详细信息（队列大小或错误消息）
4. **定期更新**: 状态每 10 秒自动刷新

### 浏览器控制台

```javascript
// 可在浏览器控制台观察
// 每 10 秒应看到 health check 请求
```
