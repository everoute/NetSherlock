@echo off
REM NetSherlock Icon Design - HTTP Preview Server (Windows)
REM 启动本地 HTTP 服务器以预览图标设计

setlocal enabledelayedexpansion

echo 🚀 启动 NetSherlock 图标预览服务器...
echo.

REM 获取当前目录
cd /d "%~dp0"

REM 检测 Python
for /f "tokens=*" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i

if "%PYTHON_VERSION%"=="" (
    echo ❌ 错误: 未找到 Python
    echo 请安装 Python 3.6+ 来运行此脚本
    pause
    exit /b 1
)

echo ✅ 使用: %PYTHON_VERSION%
echo.

REM 获取端口（默认 8000）
if "%1"=="" (
    set PORT=8000
) else (
    set PORT=%1
)

echo 📍 预览地址:
echo    http://localhost:%PORT%/ICON_PREVIEW.html
echo.
echo 💡 快捷链接:
echo    http://localhost:%PORT%/ICON_PREVIEW.html#增强雷达
echo    http://localhost:%PORT%/ICON_PREVIEW.html#网络镜头
echo    http://localhost:%PORT%/ICON_PREVIEW.html#信号侦测
echo.
echo 📁 资源位置:
echo    SVG 图标: http://localhost:%PORT%/src/assets/logo-option-*.svg
echo.
echo ⌨️  按 Ctrl+C 停止服务器
echo.

REM 启动服务器
python -m http.server %PORT%
