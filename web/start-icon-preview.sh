#!/bin/bash

# NetSherlock Icon Design - HTTP Preview Server
# 启动本地 HTTP 服务器以预览图标设计

set -e

echo "🚀 启动 NetSherlock 图标预览服务器..."
echo ""

# 获取当前脚本的目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 检测可用的 Python 版本
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    PYTHON_VERSION=$(python3 --version 2>&1)
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
    PYTHON_VERSION=$(python --version 2>&1)
else
    echo "❌ 错误: 未找到 Python"
    echo "请安装 Python 3.6+ 来运行此脚本"
    exit 1
fi

echo "✅ 使用: $PYTHON_VERSION"
echo ""

# 启动 HTTP 服务器
PORT=${1:-8000}

echo "📍 预览地址:"
echo "   http://localhost:$PORT/ICON_PREVIEW.html"
echo ""
echo "💡 快捷链接:"
echo "   http://localhost:$PORT/ICON_PREVIEW.html#增强雷达"
echo "   http://localhost:$PORT/ICON_PREVIEW.html#网络镜头"
echo "   http://localhost:$PORT/ICON_PREVIEW.html#信号侦测"
echo ""
echo "📁 资源位置:"
echo "   SVG 图标: http://localhost:$PORT/src/assets/logo-option-*.svg"
echo ""
echo "⌨️  按 Ctrl+C 停止服务器"
echo ""

# 启动服务器
$PYTHON_CMD -m http.server $PORT --directory .
