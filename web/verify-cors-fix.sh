#!/bin/bash

# CORS Fix Verification Script
# Usage: bash verify-cors-fix.sh

set -e

echo "🔍 CORS Configuration Verification"
echo "=================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check frontend files
echo "📋 检查前端文件配置..."
echo ""

# Check vite.config.ts
if grep -q "proxy:" web/vite.config.ts; then
    echo -e "${GREEN}✓${NC} vite.config.ts - 代理配置已添加"
else
    echo -e "${RED}✗${NC} vite.config.ts - 代理配置缺失"
fi

if grep -q "/health\|/diagnose\|/diagnoses" web/vite.config.ts; then
    echo -e "${GREEN}✓${NC} vite.config.ts - API 路由已配置"
else
    echo -e "${RED}✗${NC} vite.config.ts - API 路由缺失"
fi

# Check src/lib/api.ts
if grep -q "getApiBaseUrl\|import.meta.env.PROD" web/src/lib/api.ts; then
    echo -e "${GREEN}✓${NC} src/lib/api.ts - API 基础 URL 配置已更新"
else
    echo -e "${RED}✗${NC} src/lib/api.ts - API 基础 URL 配置未更新"
fi

if grep -q "console.debug.*API Config" web/src/lib/api.ts; then
    echo -e "${GREEN}✓${NC} src/lib/api.ts - 调试日志已添加"
else
    echo -e "${YELLOW}⚠${NC} src/lib/api.ts - 调试日志未添加（可选）"
fi

echo ""
echo "📋 检查后端文件配置..."
echo ""

# Check backend CORS
if grep -q "from fastapi.middleware.cors import CORSMiddleware" src/netsherlock/api/webhook.py; then
    echo -e "${GREEN}✓${NC} webhook.py - CORS 中间件已导入"
else
    echo -e "${RED}✗${NC} webhook.py - CORS 中间件未导入"
fi

if grep -q "def setup_cors" src/netsherlock/api/webhook.py; then
    echo -e "${GREEN}✓${NC} webhook.py - setup_cors 函数已添加"
else
    echo -e "${RED}✗${NC} webhook.py - setup_cors 函数未添加"
fi

if grep -q "app.add_middleware.*CORSMiddleware" src/netsherlock/api/webhook.py; then
    echo -e "${GREEN}✓${NC} webhook.py - CORS 中间件已配置"
else
    echo -e "${RED}✗${NC} webhook.py - CORS 中间件未配置"
fi

echo ""
echo "📋 检查测试文件..."
echo ""

if [ -f "web/test-cors.html" ]; then
    echo -e "${GREEN}✓${NC} test-cors.html - 测试页面已创建"
else
    echo -e "${RED}✗${NC} test-cors.html - 测试页面未创建"
fi

echo ""
echo "📋 检查文档文件..."
echo ""

docs=(
    "web/CORS_FIX_GUIDE.md"
    "web/CORS_QUICK_START.md"
    "web/CORS_FIX_SUMMARY.md"
)

for doc in "${docs[@]}"; do
    if [ -f "$doc" ]; then
        echo -e "${GREEN}✓${NC} $doc"
    else
        echo -e "${RED}✗${NC} $doc"
    fi
done

echo ""
echo "🔧 运行时检查..."
echo ""

# Check if backend is running
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} 后端运行正常（http://localhost:8000）"
else
    echo -e "${YELLOW}⚠${NC} 后端未运行（http://localhost:8000）"
    echo "   启动后端：python -m netsherlock.api.webhook"
fi

# Check if frontend dev server is running
if curl -s http://localhost:3000 > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} 前端开发服务器运行正常（http://localhost:3000）"
else
    echo -e "${YELLOW}⚠${NC} 前端开发服务器未运行（http://localhost:3000）"
    echo "   启动前端：npm run dev"
fi

echo ""
echo "=================================="
echo "✅ 验证完成！"
echo ""
echo "下一步："
echo "1. 重启前端开发服务器：npm run dev"
echo "2. 访问 http://localhost:3000"
echo "3. 打开浏览器 DevTools 检查是否有 CORS 错误"
echo "4. 可选：打开 http://localhost:3000/test-cors.html 进行测试"
echo ""
