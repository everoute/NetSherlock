# 登录认证功能

## 功能描述

为 NetSherlock 应用添加了完整的登录认证系统。用户必须先登录才能访问任务诊断相关的功能。

## 默认凭证

- **用户名**: `admin`
- **密码**: `admin`

## 实现细节

### 1. 认证 Context (`src/lib/auth.tsx`)

```typescript
interface AuthContextType {
  isAuthenticated: boolean
  username: string | null
  login: (username: string, password: string) => boolean
  logout: () => void
}
```

**功能**:
- 管理全局认证状态
- 提供 `useAuth()` hook 供组件使用
- 使用 localStorage 持久化登录状态
- 用户刷新页面后保持登录状态

### 2. 登录页面 (`src/pages/LoginPage.tsx`)

**UI 特性**:
- 📱 响应式设计，居中显示
- 🎨 蓝色渐变背景，白色卡片界面
- 📝 表单包含用户名和密码输入
- ⚠️ 错误消息显示（如凭证错误）
- 🔄 加载状态，防止重复提交
- 📋 展示默认凭证提示

**表单验证**:
- 用户名和密码都必须填写
- 提交按钮在表单未完成时禁用

### 3. 受保护路由 (`src/components/ProtectedRoute.tsx`)

- 检查用户是否已认证
- 未认证用户自动重定向到登录页面
- 保护所有需要认证的路由

### 4. 应用路由修改 (`src/App.tsx`)

```
/login          → 登录页面（公开）
/               → 受保护的主布局
  /tasks        → 任务列表
  /tasks/new    → 新建任务
  /tasks/:id    → 任务详情
  /reports      → 报告列表
  /reports/:id  → 报告详情
```

### 5. Header 增强 (`src/components/Header.tsx`)

**认证后显示**:
- 欢迎信息：`Welcome, admin`
- 登出按钮（红色 LogOut 图标）
- "New Task" 按钮

**点击登出**:
- 清除认证状态
- 删除 localStorage 中的用户名
- 重定向到登录页面

## 用户流程

1. **首次访问** → 自动重定向到 `/login`
2. **输入凭证** → 用户名: `admin`, 密码: `admin`
3. **点击登录** → 验证成功，重定向到 `/tasks`
4. **使用应用** → 访问任务和报告功能
5. **点击登出** → 返回登录页面

## 技术栈

- **状态管理**: React Context API
- **路由保护**: React Router 自定义组件
- **持久化**: localStorage
- **UI 组件**: Lucide React 图标
- **样式**: Tailwind CSS

## 文件清单

| 文件 | 类型 | 描述 |
|------|------|------|
| `src/lib/auth.tsx` | 新增 | 认证 Context 和 Provider |
| `src/pages/LoginPage.tsx` | 新增 | 登录页面组件 |
| `src/components/ProtectedRoute.tsx` | 新增 | 路由保护组件 |
| `src/App.tsx` | 修改 | 添加登录路由和认证 Provider |
| `src/components/Header.tsx` | 修改 | 添加登出功能和用户信息显示 |

## 安全说明

⚠️ **注意**: 这是演示实现，使用硬编码凭证。生产环境应该：
- 使用真实的后端认证 API
- 实现安全的令牌管理（JWT）
- 使用 HTTPS
- 不在前端存储敏感信息
- 实现会话超时机制

## 验证清单

✅ TypeScript 编译通过（0 errors）
✅ 登录功能正常工作
✅ 凭证验证正确
✅ 路由保护有效
✅ 登出功能完整
✅ localStorage 持久化正常
✅ 页面刷新保持登录状态
✅ UI 响应式设计
