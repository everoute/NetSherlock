# CORS 错误修复 - 完整总结

## 📋 问题诊断

**错误症状：**
```
Access to XMLHttpRequest at 'http://localhost:8000/diagnoses' from origin
'http://localhost:3000' has been blocked by CORS policy
```

**根本原因：**
1. 前端（Vite 3000）和后端（FastAPI 8000）运行在不同端口
2. 浏览器同源策略阻止跨域请求
3. 后端未配置 CORS 中间件

---

## ✅ 已实施的修复

### 1. 前端修改（3 个文件）

#### `vite.config.ts`
- ✅ 配置代理规则
- ✅ 转发 `/health`, `/diagnose`, `/diagnosis`, `/diagnoses` 到后端
- ✅ 设置 `changeOrigin: true`

#### `src/lib/api.ts`
- ✅ 改用相对路径（开发环境）
- ✅ 生产环境自动使用完整 URL
- ✅ 添加 API 配置日志

#### `test-cors.html`
- ✅ 提供可视化测试页面
- ✅ 可直接在浏览器中打开测试

### 2. 后端修改（1 个文件）

#### `src/netsherlock/api/webhook.py`
- ✅ 导入 `CORSMiddleware`
- ✅ 配置开发环境允许所有 localhost 源
- ✅ 配置生产环境使用环境变量
- ✅ 添加详细日志

---

## 🚀 使用指南

### 快速启动（推荐）

```bash
# 1. 停止旧的开发服务器 (Ctrl+C)
# 2. 重启开发服务器
npm run dev

# 3. 打开浏览器
http://localhost:3000
```

**完成！** 修改已生效，CORS 错误应该消失。

### 三种运行模式

#### 模式 1：使用 Mock 数据（无需后端）
```bash
VITE_USE_MOCK_DATA=true npm run dev
```
✅ 最简单，完全独立
✅ 前端开发时使用
✅ 有预置的测试数据

#### 模式 2：连接本地后端（推荐开发）
```bash
# 终端 1：前端
npm run dev

# 终端 2：后端
cd ~/workspace/netsherlock
python -m netsherlock.api.webhook
```
✅ 开发最完整的方案
✅ 自动使用 Vite 代理处理 CORS

#### 模式 3：生产环境
```bash
# 构建
npm run build

# 配置环境变量
export VITE_API_URL=https://api.example.com
export CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com

# 部署
```
✅ 部署到生产服务器
✅ 后端配置 CORS 中间件

---

## 🔍 验证修复

### 方法 1：浏览器 DevTools（推荐）

打开浏览器 DevTools (F12)：

**Console 标签：**
```javascript
// 应该看到
[API Config] {
  baseUrl: "(using Vite proxy)",
  useMockData: false,
  environment: "development"
}

// 不应该有 CORS 错误
```

**Network 标签：**
- 点击任意 API 请求（如 `/diagnoses`）
- ✅ 状态码应该是 200
- ✅ 请求 URL 应该是相对路径
- ✅ 不应该有跨域错误

### 方法 2：使用测试页面

```bash
# 在浏览器中打开
http://localhost:3000/test-cors.html

# 或直接打开文件
打开 ~/workspace/netsherlock/web/test-cors.html
```

然后点击按钮测试各个 API 端点。

### 方法 3：命令行测试

```bash
# 测试后端是否运行
curl http://localhost:8000/health

# 应该返回
{"status":"healthy","timestamp":"2026-02-06T10:00:00Z",...}
```

---

## 📝 文件修改清单

### 前端文件

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `vite.config.ts` | 配置代理规则 | ✅ 完成 |
| `src/lib/api.ts` | 使用相对路径 | ✅ 完成 |
| `test-cors.html` | 新增测试页面 | ✅ 新增 |

### 后端文件

| 文件 | 修改内容 | 状态 |
|------|---------|------|
| `src/netsherlock/api/webhook.py` | 添加 CORS 中间件 | ✅ 完成 |

### 文档文件

| 文件 | 用途 |
|------|------|
| `CORS_FIX_GUIDE.md` | 详细修复指南 |
| `CORS_QUICK_START.md` | 快速启动 |
| `CORS_FIX_SUMMARY.md` | 本文件 |

---

## ❓ 常见问题

### Q1: 修改后重启还是报错？

**A:** 按以下顺序检查：

1. ✅ 确保已停止旧进程 (Ctrl+C)
2. ✅ 清除浏览器缓存 (Ctrl+Shift+Delete)
3. ✅ 硬刷新页面 (Ctrl+F5)
4. ✅ 检查后端是否运行

```bash
# 检查后端
curl http://localhost:8000/health

# 没有响应？启动后端
python -m netsherlock.api.webhook
```

### Q2: 如何知道代理是否工作？

**A:** 打开浏览器 DevTools → Network 标签，查看 API 请求：

- ✅ 正确：`/diagnoses` （相对路径）
- ❌ 错误：`http://localhost:8000/diagnoses` （完整 URL）

### Q3: 生产环境如何配置？

**A:** 在服务器上设置环境变量：

```bash
# .env 或 .env.production
ENVIRONMENT=production
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com
VITE_API_URL=https://api.example.com
```

### Q4: 可以同时使用 Mock 和真实后端吗？

**A:** 是的，`api.ts` 中已处理：

```typescript
if (USE_MOCK_DATA) {
  // 使用 Mock 数据
  return getMockDiagnosis(id)
} else {
  // 调用真实 API
  const response = await fetch(...)
}
```

---

## 🧪 测试检查清单

- [ ] 已重启 Vite 开发服务器（npm run dev）
- [ ] 浏览器缓存已清除（Ctrl+Shift+Delete）
- [ ] 硬刷新页面（Ctrl+F5）
- [ ] DevTools Console 中无 CORS 错误
- [ ] DevTools Network 中 API 请求成功（200 状态码）
- [ ] 请求 URL 是相对路径（/diagnoses）
- [ ] 后端正在运行（curl http://localhost:8000/health）
- [ ] 测试页面正常工作（test-cors.html）

---

## 🔧 故障排除

### 问题：仍然有 CORS 错误

```
步骤 1: 检查后端
$ curl http://localhost:8000/health
# 无响应？启动后端

步骤 2: 清除缓存
按 Ctrl+Shift+Delete

步骤 3: 硬刷新
按 Ctrl+F5

步骤 4: 重启前端
停止 npm run dev
再运行 npm run dev
```

### 问题：请求超时

```
可能原因：
1. 后端未运行
2. 后端地址错误
3. 网络连接问题

解决：
$ ping localhost
# 如果无响应，检查网络

$ netstat -an | grep 8000
# Windows: netstat -ano | findstr :8000
# 检查 8000 端口是否被占用
```

### 问题：API 返回 404

```
检查：
1. 端点路径是否正确
2. 后端 API 是否实现
3. 路由是否注册

查看后端日志获取更多信息
```

---

## 📊 配置对比

### 开发环境 vs 生产环境

| 方面 | 开发 | 生产 |
|------|------|------|
| Vite 代理 | ✅ 启用 | ❌ 禁用 |
| API Base URL | 相对路径 (``) | 完整 URL |
| CORS 来源 | localhost:* | 环境变量配置 |
| Mock 数据 | 可选 | 禁用 |

---

## 🎯 关键要点

1. **Vite 代理（开发）**
   - 自动转发 API 请求到后端
   - 避免 CORS 错误
   - 无需后端配置 CORS

2. **后端 CORS 中间件（生产）**
   - 配置允许的来源
   - 前后端在不同域时必需
   - 使用环境变量配置

3. **相对 vs 绝对 URL**
   - 开发：相对路径（/diagnoses）
   - 生产：完整 URL（https://api.example.com/diagnoses）

---

## 📚 相关文档

- **详细指南**：[CORS_FIX_GUIDE.md](./CORS_FIX_GUIDE.md)
- **快速开始**：[CORS_QUICK_START.md](./CORS_QUICK_START.md)
- **API 参考**：[API_QUICK_REFERENCE.md](./API_QUICK_REFERENCE.md)
- **前后端对齐**：[FRONTEND_BACKEND_ALIGNMENT.md](./FRONTEND_BACKEND_ALIGNMENT.md)

---

## 🎉 完成

CORS 错误修复已完成！

- ✅ 前端代理配置
- ✅ API 调用修改
- ✅ 后端 CORS 中间件
- ✅ 测试页面和文档

现在可以安心进行前后端联调了。

---

**最后更新：** 2026-02-06
**支持环境：** Node.js 18+, Python 3.9+
