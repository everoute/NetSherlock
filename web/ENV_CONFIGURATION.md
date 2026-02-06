# 环境变量配置指南

## 📋 概览

前端使用 `.env` 文件管理配置，包括：
- 后端 API 地址
- 特性开关（Mock 数据）
- 环境类型

Vite 会自动从以下文件加载环境变量（优先级从高到低）：

1. `.env.local` - 本地覆盖（**不提交到 git**）
2. `.env.{MODE}.local` - 模式特定本地文件
3. `.env.{MODE}` - 模式特定文件
4. `.env` - 默认文件

---

## 📁 文件说明

### `.env` - 默认开发配置

```bash
# Backend API Configuration
VITE_API_URL=http://localhost:8000

# Features
VITE_USE_MOCK_DATA=false

# Environment
VITE_ENVIRONMENT=development
```

**何时提交：** ✅ 提交到 git（开发默认配置）

**用途：** 所有开发者的默认配置

---

### `.env.production` - 生产环境配置

```bash
# Production API Configuration
VITE_API_URL=https://api.example.com

# Features
VITE_USE_MOCK_DATA=false

# Environment
VITE_ENVIRONMENT=production
```

**何时提交：** ✅ 提交到 git（生产默认配置）

**用途：** 构建生产版本时自动使用

**构建方式：**
```bash
npm run build
```

---

### `.env.local` - 本地个人覆盖

```bash
# Local overrides (not committed to git)
# Uncomment the line below to change the backend address for your local environment

# VITE_API_URL=http://localhost:8001
# VITE_USE_MOCK_DATA=true
```

**何时提交：** ❌ **不提交到 git**（在 .gitignore 中）

**用途：** 个人本地设置，不影响其他开发者

**示例场景：**
- 后端运行在非标准端口
- 需要使用 Mock 数据进行调试
- 连接到不同的远程后端

---

### `.env.development` - 开发环境特定配置

如果需要，可以创建 `.env.development` 覆盖默认 `.env`

```bash
# Development environment specific settings
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK_DATA=false
VITE_ENVIRONMENT=development
```

**何时使用：** 很少需要，通常用 `.env.local` 就够了

---

## 🔧 常见使用场景

### 场景 1：使用默认配置（推荐）

**需要做的事：** 什么都不用做

```bash
npm run dev
```

使用 `.env` 中的配置：
- API: `http://localhost:8000`
- Mock: `false`

---

### 场景 2：后端在不同端口

**修改 `.env.local`：**

```bash
# .env.local
VITE_API_URL=http://localhost:8001
```

```bash
npm run dev
```

**或使用环境变量（无需修改文件）：**

```bash
VITE_API_URL=http://localhost:8001 npm run dev
```

---

### 场景 3：使用 Mock 数据（无需后端）

**修改 `.env.local`：**

```bash
# .env.local
VITE_USE_MOCK_DATA=true
```

```bash
npm run dev
```

**或使用环境变量：**

```bash
VITE_USE_MOCK_DATA=true npm run dev
```

---

### 场景 4：连接远程后端

**修改 `.env.local`：**

```bash
# .env.local
VITE_API_URL=https://api.example.com
```

```bash
npm run dev
```

---

### 场景 5：生产环境构建

```bash
npm run build
```

自动使用 `.env.production` 中的配置：
- API: `https://api.example.com`
- Mock: `false`

---

## 📝 环境变量列表

| 变量名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `VITE_API_URL` | string | `http://localhost:8000` | 后端 API 地址 |
| `VITE_USE_MOCK_DATA` | boolean | `false` | 是否使用 Mock 数据 |
| `VITE_ENVIRONMENT` | string | `development` | 环境类型 |

---

## 🔍 验证环境变量加载

打开浏览器 DevTools，在 Console 中应该看到：

```javascript
[API Config] {
  baseUrl: "(using Vite proxy)",
  useMockData: false,
  environment: "development"
}
```

或在生产环境：

```javascript
[API Config] {
  baseUrl: "https://api.example.com",
  useMockData: false,
  environment: "production"
}
```

---

## ⚠️ 注意事项

### 环境变量必须以 `VITE_` 开头

Vite 只会暴露以 `VITE_` 开头的变量到客户端代码。

```javascript
// ✅ 可以访问
console.log(import.meta.env.VITE_API_URL)

// ❌ 无法访问（会是 undefined）
console.log(import.meta.env.API_URL)
console.log(import.meta.env.SECRET_KEY)
```

### `.env.local` 不要提交

```bash
# 在 .gitignore 中已经配置
.env
.env.local
.env.*.local
```

### 修改后需要重启开发服务器

如果修改 `.env` 文件：

```bash
# 1. 停止开发服务器 (Ctrl+C)
# 2. 重启
npm run dev
```

### 布尔值必须是字符串

```bash
# ✓ 正确
VITE_USE_MOCK_DATA=true
VITE_USE_MOCK_DATA=false

# ✓ 也可以
VITE_USE_MOCK_DATA="true"
VITE_USE_MOCK_DATA="false"
```

在代码中检查时使用字符串比较：

```javascript
import.meta.env.VITE_USE_MOCK_DATA === 'true'
```

---

## 🚀 快速命令参考

```bash
# 开发环境 - 使用 .env
npm run dev

# 开发环境 - 覆盖后端地址
VITE_API_URL=http://localhost:8001 npm run dev

# 开发环境 - 使用 Mock 数据
VITE_USE_MOCK_DATA=true npm run dev

# 生产环境 - 构建（使用 .env.production）
npm run build

# 预览生产构建
npm run preview
```

---

## 📊 环境变量优先级

```
命令行环境变量（最高）
    ↓
.env.{MODE}.local
    ↓
.env.local
    ↓
.env.{MODE}
    ↓
.env
    ↓
代码中的默认值（最低）
```

**示例：**

```bash
# 使用命令行传入的值（最高优先级）
VITE_API_URL=http://custom-backend:9000 npm run dev
```

---

## 🔐 安全建议

### ✅ 可以提交到 git

- `.env` - 开发默认值
- `.env.production` - 生产默认值

### ❌ 不要提交到 git

- `.env.local` - 个人本地配置
- `.env.*.local` - 模式特定的本地配置
- 任何包含敏感信息的 `.env` 文件

### 🔒 处理敏感信息

如果需要在环境变量中存储敏感信息（如 API tokens）：

1. **本地开发：** 存储在 `.env.local`（不提交）
2. **生产环境：** 使用服务器的真实环境变量或密钥管理服务

```bash
# .env.local（不提交到 git）
VITE_API_TOKEN=secret-token-here
```

```javascript
// 代码中使用
const token = import.meta.env.VITE_API_TOKEN
```

---

## 📚 完整示例

### 示例 1：全部使用默认值

```bash
# 文件内容
# .env
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK_DATA=false

# 启动
npm run dev

# 结果：使用本地后端，无 Mock 数据
```

### 示例 2：使用 Mock 数据进行开发

```bash
# 文件内容
# .env
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK_DATA=false

# .env.local
VITE_USE_MOCK_DATA=true

# 启动
npm run dev

# 结果：使用 Mock 数据，无需后端
```

### 示例 3：多个后端环境

```bash
# .env - 默认
VITE_API_URL=http://localhost:8000

# .env.local - 使用远程后端
VITE_API_URL=https://dev-api.example.com

# 启动
npm run dev

# 结果：使用远程开发后端
```

---

## ✨ 最佳实践

1. **提交 `.env` 到 git** - 包含所有开发者的默认值
2. **不提交 `.env.local`** - 已在 .gitignore 中
3. **注释敏感值** - 在 `.env` 中用注释说明
4. **提供示例** - 在 `.env.local` 中提供注释示例
5. **记录文档** - 在此文件中记录所有变量

---

## 🔗 相关文件

- `vite.config.ts` - Vite 配置，读取环境变量
- `src/lib/api.ts` - API 客户端，使用环境变量
- `.gitignore` - 配置了 `.env.local` 不提交

---

**最后更新：** 2026-02-06
**Vite 版本：** 5.x+
