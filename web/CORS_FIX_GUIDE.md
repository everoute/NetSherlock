# CORS 错误修复指南

## 问题诊断

**错误信息示例：**
```
Access to XMLHttpRequest at 'http://localhost:8000/diagnoses' from origin
'http://localhost:3000' has been blocked by CORS policy:
No 'Access-Control-Allow-Origin' header is present on the requested resource.
```

**原因：**
1. 前端运行在 `http://localhost:3000`（Vite 开发服务器）
2. 后端运行在 `http://localhost:8000`（FastAPI）
3. 浏览器的同源策略（CORS）阻止跨域请求
4. 后端没有配置 CORS 中间件或 Vite 代理没有正确配置

---

## 方案 1：开发环境修复（推荐）

### 第一步：修复 Vite 代理配置

**文件：** `vite.config.ts`

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      // 代理所有 API 请求到后端
      '/health': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/diagnose': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/diagnosis': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/diagnoses': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

**或使用更通用的配置：**

```typescript
export default defineConfig({
  // ... 其他配置
  server: {
    port: 3000,
    proxy: {
      // 匹配所有 API 路由
      '^/.*': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
```

### 第二步：修改 API 客户端配置

**文件：** `src/lib/api.ts`

将 API 调用改为相对路径（利用 Vite 代理）：

```typescript
import type { DiagnosticRequest, DiagnosisResponse, HealthResponse } from '@/types'
import { getMockDiagnosis, getMockDiagnosesList } from './mockData'

const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

// 开发环境使用相对路径（通过 Vite 代理）
// 生产环境使用完整 URL
const API_BASE_URL = import.meta.env.PROD
  ? (import.meta.env.VITE_API_URL || 'http://localhost:8000')
  : ''  // 开发时使用相对路径，Vite 代理会处理

interface ListOptions {
  limit?: number
  offset?: number
  status?: string
}

export const api = {
  async getHealth(): Promise<HealthResponse> {
    const response = await fetch(`${API_BASE_URL}/health`)
    if (!response.ok) {
      throw new Error(`Health check failed: ${response.statusText}`)
    }
    return response.json()
  },

  async createDiagnosis(request: DiagnosticRequest): Promise<DiagnosisResponse> {
    const response = await fetch(`${API_BASE_URL}/diagnose`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request),
    })
    if (!response.ok) {
      throw new Error(`Failed to create diagnosis: ${response.statusText}`)
    }
    return response.json()
  },

  async getDiagnosis(id: string): Promise<DiagnosisResponse> {
    if (USE_MOCK_DATA) {
      const diagnosis = getMockDiagnosis(id)
      if (!diagnosis) {
        throw new Error(`Diagnosis not found: ${id}`)
      }
      await new Promise((resolve) => setTimeout(resolve, 300))
      return diagnosis
    }

    const response = await fetch(`${API_BASE_URL}/diagnosis/${id}`)
    if (!response.ok) {
      throw new Error(`Failed to get diagnosis: ${response.statusText}`)
    }
    return response.json()
  },

  async listDiagnoses(options?: ListOptions): Promise<DiagnosisResponse[]> {
    if (USE_MOCK_DATA) {
      await new Promise((resolve) => setTimeout(resolve, 500))
      return getMockDiagnosesList(options)
    }

    const params = new URLSearchParams()
    if (options?.limit) params.append('limit', options.limit.toString())
    if (options?.offset) params.append('offset', options.offset.toString())
    if (options?.status) params.append('status', options.status)

    const url = `${API_BASE_URL}/diagnoses?${params.toString()}`
    const response = await fetch(url)
    if (!response.ok) {
      throw new Error(`Failed to list diagnoses: ${response.statusText}`)
    }
    return response.json()
  },

  async cancelDiagnosis(id: string): Promise<void> {
    const response = await fetch(`${API_BASE_URL}/diagnosis/${id}/cancel`, {
      method: 'POST',
    })
    if (!response.ok) {
      throw new Error(`Failed to cancel diagnosis: ${response.statusText}`)
    }
  },
}
```

### 第三步：验证代理配置

重启 Vite 开发服务器：

```bash
# 终止当前运行的服务器 (Ctrl+C)
# 重新启动
npm run dev
```

打开浏览器 DevTools → Network 标签，观察：
- 请求 URL 应该是相对路径：`/health`, `/diagnoses` 等
- 不应该看到跨域错误
- 响应状态码应该是 200

---

## 方案 2：后端配置 CORS 中间件（生产环境）

### 在后端添加 CORS 支持

**文件：** `src/netsherlock/api/webhook.py`

在 FastAPI app 初始化后添加 CORS 中间件：

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="NetSherlock",
    description="AI-driven network troubleshooting agent webhook API",
    version="0.1.0",
    lifespan=lifespan,
)

# ============================================================
# CORS Configuration
# ============================================================

# 根据环境配置允许的来源
allowed_origins = [
    "http://localhost:3000",      # Vite 开发服务器
    "http://localhost:5173",      # Vite 默认端口（如果改了）
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
]

# 生产环境：从环境变量读取
import os
if os.getenv('ENVIRONMENT') == 'production':
    allowed_origins = os.getenv('CORS_ALLOWED_ORIGINS', '').split(',')

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Length", "Content-Range"],
)
```

### 更灵活的 CORS 配置（推荐）

```python
from fastapi.middleware.cors import CORSMiddleware
import os
import logging

logger = logging.getLogger(__name__)

def setup_cors(app: FastAPI) -> None:
    """Configure CORS for the FastAPI application.

    Development: Allow localhost on various ports
    Production: Use environment-configured origins
    """

    environment = os.getenv('ENVIRONMENT', 'development')

    if environment == 'development':
        # 开发环境：允许所有 localhost 连接
        allowed_origins = [
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:8080",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:8080",
        ]
        logger.info("CORS configured for development - allowing localhost origins")
    else:
        # 生产环境：从环境变量读取
        cors_origins = os.getenv('CORS_ALLOWED_ORIGINS', '')
        allowed_origins = [o.strip() for o in cors_origins.split(',') if o.strip()]

        if not allowed_origins:
            logger.warning("CORS_ALLOWED_ORIGINS not configured in production!")
            allowed_origins = [""]  # 不允许跨域

        logger.info(f"CORS configured for production - {len(allowed_origins)} origins")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["Content-Length", "Content-Range"],
        max_age=600,  # 预检请求缓存 10 分钟
    )


# 在 app 创建后调用
app = FastAPI(
    title="NetSherlock",
    description="AI-driven network troubleshooting agent webhook API",
    version="0.1.0",
    lifespan=lifespan,
)

setup_cors(app)
```

### 后端 environment 变量配置

**开发环境 (.env)：**
```bash
ENVIRONMENT=development
```

**生产环境 (.env.production)：**
```bash
ENVIRONMENT=production
CORS_ALLOWED_ORIGINS=https://example.com,https://www.example.com,https://api.example.com
```

---

## 方案 3：使用环境特定配置（推荐综合方案）

### 前端配置

**文件：** `vite.config.ts`

```typescript
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: process.env.VITE_USE_PROXY !== 'false' ? {
      '^/(health|diagnose|diagnosis|diagnoses)': {
        target: process.env.VITE_API_URL || 'http://localhost:8000',
        changeOrigin: true,
      },
    } : undefined,
  },
})
```

**文件：** `.env.development`

```bash
VITE_API_URL=http://localhost:8000
VITE_USE_MOCK_DATA=false
VITE_USE_PROXY=true
```

**文件：** `.env.production`

```bash
VITE_API_URL=https://api.example.com
VITE_USE_MOCK_DATA=false
VITE_USE_PROXY=false
```

### API 客户端配置

**文件：** `src/lib/api.ts`

```typescript
const getApiBaseUrl = (): string => {
  // 生产环境或禁用代理时使用完整 URL
  if (import.meta.env.PROD || import.meta.env.VITE_USE_PROXY === 'false') {
    return import.meta.env.VITE_API_URL || 'http://localhost:8000'
  }
  // 开发环境使用相对路径（Vite 代理处理）
  return ''
}

const API_BASE_URL = getApiBaseUrl()
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === 'true'

console.debug('API Configuration:', { API_BASE_URL, USE_MOCK_DATA })
```

---

## 测试 CORS 配置

### 1. 使用浏览器 DevTools

打开浏览器 DevTools (F12)：

```
Console 标签：
- 检查错误信息
- 应该没有 CORS 相关的错误

Network 标签：
- 查看请求 URL
- 检查 Response Headers 中是否有 Access-Control-Allow-Origin
- 状态码应该是 200 或 201
```

### 2. 使用 curl 测试（后端配置）

```bash
# 测试 CORS 预检请求
curl -i -X OPTIONS http://localhost:8000/health \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET" \
  -H "Access-Control-Request-Headers: Content-Type"

# 应该看到：
# Access-Control-Allow-Origin: http://localhost:3000
# Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
```

### 3. 简单的测试页面

创建 `test-cors.html`：

```html
<!DOCTYPE html>
<html>
<head>
    <title>CORS Test</title>
</head>
<body>
    <h1>CORS Test</h1>
    <button onclick="testFetch()">Test Fetch</button>
    <pre id="result"></pre>

    <script>
        async function testFetch() {
            try {
                const response = await fetch('http://localhost:8000/health')
                const data = await response.json()
                document.getElementById('result').textContent = JSON.stringify(data, null, 2)
            } catch (error) {
                document.getElementById('result').textContent = 'Error: ' + error.message
            }
        }
    </script>
</body>
</html>
```

---

## 常见问题排查

### Q1: 修改配置后还是有 CORS 错误

**解决：**
1. 清除浏览器缓存 (Ctrl+Shift+Delete)
2. 硬刷新页面 (Ctrl+F5)
3. 重启 Vite 开发服务器

```bash
# 终止服务器 (Ctrl+C)
npm run dev
```

### Q2: 请求在生产环境失败

**解决：**
1. 检查 `CORS_ALLOWED_ORIGINS` 环境变量配置
2. 确保前端 URL 在允许列表中
3. 检查后端日志：`logger.info("CORS configured...")`

```bash
# 查看配置
echo $CORS_ALLOWED_ORIGINS
```

### Q3: OPTIONS 预检请求返回 405

**解决：**
- 检查后端是否允许 OPTIONS 方法（上面的配置已包含）
- 确保 CORS 中间件在所有其他中间件之前注册

```python
# 正确顺序：CORS 应该是最早的中间件
app.add_middleware(CORSMiddleware, ...)
# 然后是其他中间件
```

### Q4: Credentials/Cookies 不被发送

**解决：**
确保配置了 `allow_credentials=True`：

```python
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,  # 必须配置
    ...
)
```

前端请求也要配置：

```typescript
const response = await fetch(url, {
  credentials: 'include',  // 添加这行
  ...
})
```

---

## 部署检查清单

- [ ] 开发环境使用 Vite 代理或后端 CORS 中间件
- [ ] 生产环境配置了 CORS_ALLOWED_ORIGINS
- [ ] OPTIONS 方法被允许
- [ ] 所有必需的 headers 被允许
- [ ] 测试了跨域请求（浏览器 DevTools 验证）
- [ ] 检查了 Content-Type: application/json 支持
- [ ] 验证了生产环境的实际前端 URL 在允许列表中

---

## 快速切换

### 只用 Mock 数据（无需后端）

```bash
VITE_USE_MOCK_DATA=true npm run dev
```

### 连接真实后端

```bash
VITE_API_URL=http://localhost:8000 npm run dev
```

---

## 更多参考

- [FastAPI CORS 文档](https://fastapi.tiangolo.com/tutorial/cors/)
- [Vite 代理配置](https://vitejs.dev/config/server-options.html#server-proxy)
- [MDN CORS 指南](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS)
