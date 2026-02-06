# 后端连接问题诊断与修复

## 🔴 问题：Vite 代理连接失败

```
[vite] http proxy error: /diagnoses?limit=50
AggregateError [ECONNREFUSED]:
```

**原因：** 后端未运行或运行在不同端口

---

## ✅ 快速修复（选择一个）

### 方案 1：启动后端（最推荐）

```bash
# 打开新的终端窗口，进入项目目录
cd ~/workspace/netsherlock

# 启动后端服务
python -m netsherlock.api.webhook

# 你应该看到类似输出：
# INFO:     Uvicorn running on http://0.0.0.0:8000
```

然后回到前端，刷新浏览器。

### 方案 2：使用环境变量指定后端地址

```bash
# 如果后端运行在不同端口，使用环境变量
VITE_API_URL=http://localhost:8080 npm run dev
VITE_API_URL=http://localhost:8001 npm run dev
VITE_API_URL=http://localhost:5000 npm run dev
```

### 方案 3：修改默认配置

编辑 `vite.config.ts`，找到你的后端端口，修改默认值：

```typescript
server: {
  port: 3000,
  proxy: {
    '^/health': {
      target: process.env.VITE_API_URL || 'http://localhost:YOUR_PORT',
      changeOrigin: true,
    },
    // ... 其他代理配置
  },
}
```

### 方案 4：使用 Mock 数据（无需后端）

```bash
# 完全不需要后端，使用预置数据
VITE_USE_MOCK_DATA=true npm run dev
```

---

## 🔍 诊断后端状态

### 检查后端是否运行

```bash
# 测试 8000 端口
curl http://localhost:8000/health

# 如果没有响应，尝试其他常见端口
curl http://localhost:8080/health
curl http://localhost:5000/health
curl http://localhost:3001/health
```

### 查找哪个端口在运行

```bash
# 在 Linux/Mac 上
lsof -i :8000
lsof -i :8080
lsof -i :5000

# 在 Windows 上
netstat -ano | findstr :8000
netstat -ano | findstr :8080
netstat -ano | findstr :5000
```

### 检查进程

```bash
# 查找 Python 进程
ps aux | grep python
ps aux | grep netsherlock
ps aux | grep webhook

# 在 Windows 上
tasklist | findstr python
```

---

## 🚀 完整的启动步骤

### 终端 1：启动前端

```bash
cd ~/workspace/netsherlock/web

# 选项 A：使用默认端口
npm run dev

# 选项 B：如果后端在 8080
VITE_API_URL=http://localhost:8080 npm run dev

# 选项 C：使用 Mock 数据（无需后端）
VITE_USE_MOCK_DATA=true npm run dev
```

### 终端 2：启动后端

```bash
cd ~/workspace/netsherlock

# 启动后端
python -m netsherlock.api.webhook

# 或指定端口
python -m uvicorn netsherlock.api.webhook:app --host 0.0.0.0 --port 8000
```

等待两个都启动成功，然后在浏览器打开 `http://localhost:3000`

---

## 📋 后端启动检查清单

启动后端后，检查以下项：

- [ ] 没有 Python 错误
- [ ] 看到 "Uvicorn running on http://0.0.0.0:8000" 或类似信息
- [ ] 可以用 curl 访问：`curl http://localhost:8000/health`
- [ ] 得到 JSON 响应（不是超时或 Connection refused）

启动前端后，检查以下项：

- [ ] 前端运行在 http://localhost:3000
- [ ] 浏览器 DevTools 中没有 CORS 错误
- [ ] API 请求显示相对路径（如 `/diagnoses`）
- [ ] Network 标签中看到 200 状态码

---

## 🆘 常见问题

### Q1: "Port 8000 already in use"

**原因：** 端口被其他进程占用

**解决：**
```bash
# 杀死占用端口的进程（Linux/Mac）
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill -9

# 使用不同端口启动
python -m uvicorn netsherlock.api.webhook:app --port 8001

# 在前端使用该端口
VITE_API_URL=http://localhost:8001 npm run dev
```

### Q2: "ModuleNotFoundError: No module named 'netsherlock'"

**原因：** 虚拟环境未激活或依赖未安装

**解决：**
```bash
# 激活虚拟环境
source ~/workspace/netsherlock/.venv/bin/activate  # Mac/Linux
# 或
~/workspace/netsherlock\.venv\Scripts\activate  # Windows

# 安装依赖
pip install -e .
```

### Q3: "ConnectionRefusedError" or "ECONNREFUSED"

**原因：** 后端未运行

**解决：**
```bash
# 检查后端是否运行
curl http://localhost:8000/health

# 如果没有响应，启动后端
python -m netsherlock.api.webhook
```

### Q4: 怎样确认后端正确的端口？

```bash
# 尝试所有常见端口
for port in 8000 8001 8080 5000 3001; do
  echo "Testing port $port..."
  curl -s http://localhost:$port/health && echo "✓ Found on $port" || echo "✗ Not on $port"
done
```

---

## 📊 配置优先级

Vite 代理使用以下优先级：

1. **环境变量** (最高优先级)
   ```bash
   VITE_API_URL=http://backend.example.com npm run dev
   ```

2. **vite.config.ts 中的 target 值**
   ```typescript
   target: process.env.VITE_API_URL || 'http://localhost:8000'
   ```

3. **fallback 默认值** (最低优先级)
   ```
   http://localhost:8000
   ```

---

## 🔄 运行流程

```
浏览器请求
    ↓
http://localhost:3000 (前端 Vite)
    ↓
Vite 代理拦截
    ↓
识别 /diagnoses 等 API 路径
    ↓
转发到后端
    ↓
http://localhost:8000 (或配置的其他地址)
    ↓
后端处理请求
    ↓
返回响应给前端
```

---

## 💡 提示

### 同时启动前后端的快速脚本

创建文件 `start-all.sh`：

```bash
#!/bin/bash

# 启动后端
echo "🚀 启动后端..."
cd ~/workspace/netsherlock
python -m netsherlock.api.webhook &
BACKEND_PID=$!

# 等待后端启动
sleep 2

# 启动前端
echo "🚀 启动前端..."
cd ~/workspace/netsherlock/web
npm run dev &
FRONTEND_PID=$!

# 显示 PID
echo "Backend PID: $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"

# 等待中断
wait
```

使用：
```bash
bash start-all.sh
```

### 快速重启脚本

```bash
#!/bin/bash
echo "重启 Vite 开发服务器..."
pkill -f "npm run dev"
sleep 1
cd ~/workspace/netsherlock/web
VITE_API_URL=http://localhost:8000 npm run dev
```

---

## 📞 获取帮助

如果还有问题，检查以下日志：

1. **前端日志**（浏览器 DevTools Console）
   - 查看 API 配置信息
   - 查看网络请求错误

2. **后端日志**（终端输出）
   ```
   INFO:     Uvicorn running on http://0.0.0.0:8000
   INFO:     Application startup complete
   ```

3. **网络日志**（浏览器 DevTools Network）
   - 查看请求 URL
   - 查看响应状态
   - 查看 CORS 错误

---

## 🎯 最终检查清单

- [ ] 后端运行在某个端口（8000、8080 等）
- [ ] `curl http://localhost:PORT/health` 返回 JSON
- [ ] 前端配置了正确的后端地址
- [ ] 前端运行在 http://localhost:3000
- [ ] 浏览器访问正常，无网络错误
- [ ] DevTools 中没有 ECONNREFUSED 错误

---

**最后更新：** 2026-02-06
