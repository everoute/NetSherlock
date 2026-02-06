# 🌐 NetSherlock 图标预览 - HTTP 服务指南

快速启动本地 HTTP 服务器，在浏览器中预览所有图标设计。

---

## ⚡ 快速启动

### macOS / Linux

```bash
cd web
chmod +x start-icon-preview.sh
./start-icon-preview.sh
```

或直接使用 Python：

```bash
cd web
python3 -m http.server 8000
```

### Windows

```cmd
cd web
start-icon-preview.cmd
```

或使用 PowerShell：

```powershell
cd web
python -m http.server 8000
```

### Node.js (如果已安装)

```bash
cd web
npx http-server -p 8000
```

---

## 📍 访问地址

启动后，在浏览器中打开：

```
http://localhost:8000/ICON_PREVIEW.html
```

---

## 🎨 预览页面功能

| 功能 | 说明 |
|------|------|
| 三设计展示 | 并排显示所有三个设计方案 |
| 多尺寸预览 | 16×16, 32×32, 64×64, 128×128 |
| 深色模式 | 右上角按钮切换深色/浅色主题 |
| 对比表格 | 完整的功能对比矩阵 |
| 响应式设计 | 适配所有屏幕尺寸 |
| 本地存储 | 记忆你的主题偏好 |

---

## 📁 HTTP 服务的文件结构

```
http://localhost:8000/
├── ICON_PREVIEW.html                  ← 主预览页面
├── src/assets/
│   ├── logo-option-1-enhanced-radar.svg
│   ├── logo-option-2-network-lens.svg
│   └── logo-option-3-signal-detective.svg
├── docs/
│   ├── ICON_DESIGN_PROPOSAL.md
│   ├── ICON_INTEGRATION_GUIDE.md
│   ├── ICON_DESIGN_SUMMARY.md
│   └── ICON_DELIVERABLES.md
└── HTTP_PREVIEW_GUIDE.md              ← 本指南
```

---

## 🔗 直接链接

| 资源 | URL |
|------|-----|
| **预览页面** | http://localhost:8000/ICON_PREVIEW.html |
| **方案① SVG** | http://localhost:8000/src/assets/logo-option-1-enhanced-radar.svg |
| **方案② SVG** | http://localhost:8000/src/assets/logo-option-2-network-lens.svg |
| **方案③ SVG** | http://localhost:8000/src/assets/logo-option-3-signal-detective.svg |
| **设计提案** | http://localhost:8000/docs/ICON_DESIGN_PROPOSAL.md |
| **集成指南** | http://localhost:8000/docs/ICON_INTEGRATION_GUIDE.md |

---

## 🎯 使用场景

### 场景 1：快速预览设计

```bash
./start-icon-preview.sh
# 然后在浏览器打开 http://localhost:8000/ICON_PREVIEW.html
```

### 场景 2：直接访问 SVG 文件

```
http://localhost:8000/src/assets/logo-option-1-enhanced-radar.svg
```

可以：
- 在浏览器中查看和缩放
- 右键另存为
- 复制到其他项目
- 使用开发者工具检查

### 场景 3：与团队分享

```bash
# 获取本机 IP 地址
# macOS/Linux
ifconfig | grep "inet " | grep -v 127.0.0.1

# Windows
ipconfig

# 然后分享链接给团队成员
# http://<你的IP>:8000/ICON_PREVIEW.html
```

### 场景 4：深色模式测试

1. 打开 http://localhost:8000/ICON_PREVIEW.html
2. 点击右上角 🌙 按钮切换深色模式
3. 刷新页面，深色模式会被保存

---

## 📊 性能优化

### 启用 Gzip 压缩

对于生产环境，建议使用支持 Gzip 的服务器：

```bash
# 使用 Node.js 的 http-server（自动 Gzip）
npx http-server -p 8000 -g

# 或使用 Python 的第三方库
pip install pyhttp
pyhttp -p 8000
```

### 缓存设置

```bash
# 使用 Node.js 的 http-server，设置缓存头
npx http-server -p 8000 -c-1
```

---

## 🐛 故障排除

### 问题 1：端口已被占用

**错误信息**：
```
Address already in use
```

**解决方案**：
```bash
# 使用不同的端口
python3 -m http.server 8080

# 或杀死占用端口的进程
# macOS/Linux
lsof -ti:8000 | xargs kill -9

# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### 问题 2：SVG 文件加载失败

**原因**：CORS 跨域问题

**解决方案**：
```bash
# 使用启用 CORS 的服务器
npx http-server -p 8000 --cors

# 或在 Python 中添加 CORS 头
# （详见下面的 Python 脚本）
```

### 问题 3：在 macOS 上权限不足

**错误信息**：
```
Permission denied: './start-icon-preview.sh'
```

**解决方案**：
```bash
chmod +x start-icon-preview.sh
./start-icon-preview.sh
```

---

## 🔧 高级用法

### Python 脚本（支持 CORS）

创建 `server.py`：

```python
#!/usr/bin/env python3
import http.server
import socketserver
import os

class CORSRequestHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

PORT = 8000
Handler = CORSRequestHandler
os.chdir('/path/to/web')

with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"🚀 Server running at http://localhost:{PORT}")
    print(f"📍 Preview: http://localhost:{PORT}/ICON_PREVIEW.html")
    httpd.serve_forever()
```

运行：
```bash
python3 server.py
```

### Nginx 配置

```nginx
server {
    listen 8000;
    server_name localhost;
    
    root /path/to/netsherlock/web;
    
    location / {
        try_files $uri $uri/ =404;
        add_header Access-Control-Allow-Origin "*";
    }
    
    location /src/assets/ {
        add_header Content-Type "image/svg+xml";
    }
}
```

---

## 📱 移动设备访问

### 在同一网络的其他设备上预览

1. **获取本机 IP**：
   ```bash
   # macOS/Linux
   ifconfig | grep "inet " | grep -v 127.0.0.1
   
   # Windows
   ipconfig
   ```

2. **启动服务器**：
   ```bash
   ./start-icon-preview.sh
   ```

3. **在移动设备上打开**：
   ```
   http://<你的IP>:8000/ICON_PREVIEW.html
   ```

### 示例

如果你的 IP 是 `192.168.1.100`，则在手机上打开：
```
http://192.168.1.100:8000/ICON_PREVIEW.html
```

---

## 🔒 安全提示

⚠️ **本地开发仅用于内部使用**

- ✅ 适合本地测试和团队演示
- ✅ 可在内部网络分享
- ❌ 不建议在公网暴露
- ❌ 不包含身份验证或加密

如需公开部署，请使用生产级 Web 服务器（Nginx、Apache）。

---

## 📚 相关命令

### 快速参考

```bash
# 启动服务器（端口 8000）
python3 -m http.server 8000

# 启动服务器（自定义端口）
python3 -m http.server 9000

# 启动服务器（自定义目录）
python3 -m http.server -d /path/to/web

# 启动服务器（支持 CORS）
npx http-server -p 8000 --cors

# 停止服务器
Ctrl + C

# 查看本机 IP
ifconfig | grep "inet "

# 监听特定接口
python3 -m http.server 8000 --bind 0.0.0.0
```

---

## 💡 Pro 技巧

### 1. 创建快捷命令

添加到 `.bashrc` 或 `.zshrc`：

```bash
alias preview-icons='cd ~/workspace/netsherlock/web && python3 -m http.server 8000'
```

然后直接运行：
```bash
preview-icons
```

### 2. 自动打开浏览器

```bash
#!/bin/bash
cd web
python3 -m http.server 8000 &
sleep 2
open http://localhost:8000/ICON_PREVIEW.html
```

### 3. 监听文件变化

使用 `watchdog`：

```bash
pip install watchdog
watchmedo shell-command \
    --patterns="*.svg;*.html" \
    --recursive \
    --command='python3 -m http.server 8000'
```

---

## ✅ 验证清单

启动后检查以下项目：

- [ ] 服务器已启动，显示 "Server running at..."
- [ ] 可以访问 http://localhost:8000/ICON_PREVIEW.html
- [ ] 三个 SVG 图标都能正确加载
- [ ] 深色模式按钮可以点击
- [ ] 切换深色模式后刷新仍保持设置
- [ ] 可以在浏览器开发者工具中检查 SVG
- [ ] 文件大小都在 1-2 KB

---

## 📞 常见问题

**Q: 为什么我需要 HTTP 服务器而不是直接打开文件？**

A: 由于 CORS 限制和现代浏览器的安全策略，直接打开 `file://` 协议的 SVG 可能无法加载外部资源。HTTP 服务器避免了这些问题。

**Q: 可以访问来自其他计算机吗？**

A: 可以。启动服务器时使用 `--bind 0.0.0.0` 或获取本机 IP，然后其他计算机可以通过 `http://<IP>:8000` 访问。

**Q: 如何在生产环境中部署？**

A: 请使用生产级 Web 服务器（Nginx、Apache）。参考上面的 Nginx 配置示例。

---

**最后更新**: 2026-02-06  
**推荐端口**: 8000, 8080, 3000  
**所需环境**: Python 3.6+ 或 Node.js
