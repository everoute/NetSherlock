# 🎉 环境变量配置完成

## ✅ 已完成的设置

### 创建的文件

```
web/
├── .env                 # 开发默认配置（提交到 git）
├── .env.production     # 生产配置（提交到 git）
├── .env.local          # 本地个人覆盖（不提交）
├── .env.example        # 配置示例文档
├── ENV_CONFIGURATION.md # 详细配置指南
└── vite.config.ts      # 更新为使用环境变量
```

### 更新的文件

- ✅ `vite.config.ts` - 从 `.env` 读取 `VITE_API_URL`
- ✅ `src/lib/api.ts` - 已使用环境变量（无需修改）
- ✅ `.gitignore` - 已配置忽略本地文件

---

## 🚀 快速开始

### 1️⃣ 默认配置（推荐）

什么都不用做！直接运行：

```bash
npm run dev
```

使用 `.env` 中的配置：
```
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK_DATA=false
```

### 2️⃣ 自定义配置（本地覆盖）

编辑 `.env.local`：

```bash
# .env.local
VITE_API_URL=http://localhost:8001
VITE_USE_MOCK_DATA=true
```

保存后重启：
```bash
npm run dev
```

### 3️⃣ 命令行覆盖

```bash
# 后端在 8001 端口
VITE_API_URL=http://localhost:8001 npm run dev

# 使用 Mock 数据
VITE_USE_MOCK_DATA=true npm run dev

# 组合使用
VITE_API_URL=http://localhost:8001 VITE_USE_MOCK_DATA=true npm run dev
```

---

## 📋 三种配置方式优先级

（从高到低）

```
1. 命令行环境变量
   VITE_API_URL=... npm run dev

2. .env.local （本地个人配置）
   不提交到 git
   用于个人开发覆盖

3. .env （默认配置）
   提交到 git
   所有开发者的默认值
```

---

## 📁 文件说明

### `.env` - 默认开发配置

```bash
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK_DATA=false
VITE_ENVIRONMENT=development
```

- ✅ **提交到 git**
- 🎯 **用途：** 所有开发者的默认值
- 📝 **修改频率：** 很少

### `.env.production` - 生产配置

```bash
VITE_API_URL=https://api.example.com
VITE_USE_MOCK_DATA=false
VITE_ENVIRONMENT=production
```

- ✅ **提交到 git**
- 🎯 **用途：** 生产构建时自动使用
- 📝 **构建方式：** `npm run build`

### `.env.local` - 本地个人覆盖

```bash
# VITE_API_URL=http://localhost:8001
# VITE_USE_MOCK_DATA=true
```

- ❌ **不提交到 git**（在 .gitignore 中）
- 🎯 **用途：** 个人本地设置
- 📝 **示例：** 后端在不同端口、使用 Mock 数据

### `.env.example` - 配置示例

模板文件，展示所有可能的配置选项

---

## 💡 常见使用场景

### 后端在 8080 端口

**编辑 `.env.local`：**
```bash
VITE_API_URL=http://localhost:8080
```

或直接使用命令行：
```bash
VITE_API_URL=http://localhost:8080 npm run dev
```

### 后端未运行，使用 Mock 数据

**编辑 `.env.local`：**
```bash
VITE_USE_MOCK_DATA=true
```

或直接使用命令行：
```bash
VITE_USE_MOCK_DATA=true npm run dev
```

### 连接远程后端

**编辑 `.env.local`：**
```bash
VITE_API_URL=https://api.example.com
```

### 生产环境部署

```bash
npm run build
```

自动使用 `.env.production` 中的配置

---

## 🔍 验证配置

打开浏览器 DevTools (F12) → Console，应该看到：

```javascript
[API Config] {
  baseUrl: "(using Vite proxy)",
  useMockData: false,
  environment: "development"
}
```

这证明环境变量已正确加载。

---

## ⚠️ 重要提示

### 修改后需要重启服务器

```bash
# 1. 停止开发服务器 (Ctrl+C)
# 2. 重启
npm run dev
```

### 环境变量必须以 `VITE_` 开头

Vite 只会暴露 `VITE_` 开头的变量到客户端。

### `.env.local` 不要提交

已在 `.gitignore` 中配置：
```
.env.local
.env.*.local
```

---

## 📚 详细文档

- **ENV_CONFIGURATION.md** - 完整的配置指南
- **.env.example** - 配置示例和场景说明
- **BACKEND_CONNECTION_GUIDE.md** - 后端连接问题诊断

---

## 🎯 总结

| 任务 | 状态 | 说明 |
|------|------|------|
| 创建 `.env` | ✅ | 开发默认配置 |
| 创建 `.env.production` | ✅ | 生产配置 |
| 创建 `.env.local` | ✅ | 本地覆盖模板 |
| 创建 `.env.example` | ✅ | 配置示例 |
| 更新 `vite.config.ts` | ✅ | 读取环境变量 |
| 更新 `.gitignore` | ✅ | 忽略本地文件 |
| 文档编写 | ✅ | 配置和使用说明 |

---

## 🚀 现在就开始

```bash
cd /root/workspace/netsherlock/web

# 方式 1：使用默认配置
npm run dev

# 方式 2：编辑 .env.local 后使用
# 修改 .env.local
npm run dev

# 方式 3：命令行覆盖
VITE_API_URL=http://localhost:8001 npm run dev
```

一切准备就绪！ 🎉

---

**配置日期：** 2026-02-06
**状态：** 完成 ✅
