# CORS 错误快速修复指南

## 🚀 立即修复（5 分钟）

### 问题
```
Access to XMLHttpRequest at 'http://localhost:8000/diagnoses' from origin
'http://localhost:3000' has been blocked by CORS policy
```

### 快速修复步骤

**1. 停止当前的开发服务器**
```bash
# 在终端中按 Ctrl+C
```

**2. 重启开发服务器**
```bash
npm run dev
```

**完成！** 🎉

Vite 代理已经配置好了，应该可以正常工作。

---

## ✅ 验证修复

打开浏览器 DevTools (F12)：

1. **Console 标签**
   - ❌ 不应该有 CORS 错误
   - ✅ 应该看到日志：`[API Config] baseUrl: (using Vite proxy)`

2. **Network 标签**
   - 点击任意 API 请求（如 `/diagnoses`）
   - ✅ 状态码应该是 200
   - ✅ 不应该有跨域错误

---

## 🔧 如果还是不行

### 方案 A：清除缓存并硬刷新

```bash
# 在浏览器中
Ctrl+Shift+Delete  # 打开清除缓存对话框
```

然后刷新页面：
```
Ctrl+F5 (Windows/Linux)
Cmd+Shift+R (Mac)
```

### 方案 B：检查后端是否运行

```bash
# 检查后端是否在运行
curl http://localhost:8000/health
```

如果返回：
```json
{"status": "healthy"}
```

后端正常运行 ✅

### 方案 C：使用 Mock 数据（无需后端）

```bash
VITE_USE_MOCK_DATA=true npm run dev
```

---

## 📝 改动说明

我为你修改了以下文件：

### 1. `vite.config.ts`
- 配置代理规则：`/health`, `/diagnose`, `/diagnosis`, `/diagnoses`
- 所有这些请求都会被代理到后端

### 2. `src/lib/api.ts`
- 改用相对路径（开发环境）：`/health` 而不是 `http://localhost:8000/health`
- Vite 代理会自动转发到后端
- 生产环境自动使用完整 URL

### 3. `src/netsherlock/api/webhook.py` (后端)
- 添加了 CORS 中间件配置
- 开发环境自动允许 localhost
- 生产环境通过 `CORS_ALLOWED_ORIGINS` 环境变量配置

---

## 🌍 三种运行模式

### 模式 1：Mock 数据（最简单，无需后端）
```bash
VITE_USE_MOCK_DATA=true npm run dev
```
- ✅ 完全独立，无需后端
- ✅ 适合前端开发测试

### 模式 2：连接本地后端（推荐开发）
```bash
npm run dev
```
需要后端也在运行：
```bash
# 在另一个终端
cd ~/workspace/netsherlock
python -m netsherlock.api.webhook
```
- ✅ 开发时使用
- ✅ 自动使用 Vite 代理处理 CORS

### 模式 3：生产环境部署
```bash
npm run build
VITE_API_URL=https://api.example.com npm run build
```
- ✅ 完整 URL 配置
- ✅ 后端配置 CORS 中间件

---

## 🛠️ 调试技巧

### 查看 API 配置日志

打开浏览器控制台，应该看到：
```
[API Config] {
  baseUrl: "(using Vite proxy)",
  useMockData: false,
  environment: "development"
}
```

### 实时查看代理日志

Vite 服务器会显示：
```
  ➜  Local:   http://localhost:3000/
  ➜  press h + enter to show help

  VITE v5.x.x  ready in xxx ms

  ➜  Proxied requests:
      /health → http://localhost:8000
      /diagnose → http://localhost:8000
      /diagnosis → http://localhost:8000
      /diagnoses → http://localhost:8000
```

### 验证请求流程

1. 打开 DevTools Network 标签
2. 访问任何需要 API 的页面
3. 查看请求：
   - ✅ 请求 URL 应该是相对路径：`/diagnoses`
   - ✅ 不应该看到 CORS 错误
   - ✅ 响应应该成功（200）

---

## 📋 故障排除检查清单

- [ ] 已停止并重启 Vite 开发服务器
- [ ] 浏览器缓存已清除
- [ ] 按 F5 或 Ctrl+Shift+Delete 刷新
- [ ] 检查后端是否运行（`curl http://localhost:8000/health`）
- [ ] 查看浏览器 Console 是否有其他错误
- [ ] 确认 Network 标签中的请求 URL 是相对路径

---

## 💡 何时需要配置生产环境 CORS

生产环境需要在后端配置 CORS，如果：
- 前端和后端在不同的域
- 使用 HTTPS
- 需要更严格的跨域控制

详细配置见：[CORS_FIX_GUIDE.md](./CORS_FIX_GUIDE.md)

---

## 📚 相关文档

- **详细修复指南**：`CORS_FIX_GUIDE.md`
- **API 快速参考**：`API_QUICK_REFERENCE.md`
- **前后端集成**：`FRONTEND_BACKEND_INTEGRATION_GUIDE.md`

---

## ❓ 常见问题

**Q: 为什么还是有 CORS 错误？**
A: 确保已经：
1. 重启了 Vite 开发服务器
2. 清除了浏览器缓存
3. 后端正在运行（或使用 VITE_USE_MOCK_DATA=true）

**Q: 如何知道代理是否工作？**
A: 打开浏览器 DevTools → Network 标签，请求 URL 应该是相对路径（如 `/diagnoses`），而不是完整 URL。

**Q: 可以同时使用 Mock 数据和真实后端吗？**
A: 可以，在 api.ts 中已经处理了：如果 `USE_MOCK_DATA=true`，则使用本地 Mock 数据；否则调用后端。

**Q: 生产环境如何部署？**
A:
1. 构建前端：`npm run build`
2. 在后端配置 CORS：设置 `CORS_ALLOWED_ORIGINS` 环境变量
3. 或者在服务器级别配置（nginx/Apache）

---

## 📞 需要帮助？

查看完整的 CORS 指南：`CORS_FIX_GUIDE.md`
