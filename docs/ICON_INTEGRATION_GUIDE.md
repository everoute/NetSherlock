# NetSherlock 图标集成指南

## 快速对比

### 三个设计方案对比表

| 维度 | 方案一：增强雷达 | 方案二：网络镜头 | 方案三：信号侦测 |
|------|---------|-----------|-----------|
| **设计风格** | 科技感强 | 侦探风格 | 动态感强 |
| **识别度** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **现代感** | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **易于理解** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **适合小尺寸** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **品牌延续性** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **动画潜力** | 中等 | 低 | 高 |
| **B2B 专业性** | 高 | 中 | 中 |
| **用户友好度** | 高 | 高 | 高 |

---

## 集成步骤

### 1️⃣ 选择您的设计

根据品牌战略选择：

- **企业/技术专业** → 方案一（Enhanced Radar）
- **创新/消费品** → 方案二（Network Lens）
- **实时/动态应用** → 方案三（Signal Detective）

### 2️⃣ 更新前端

#### 方案 A：直接替换现有 logo

```bash
# 备份原始 logo
cp web/src/assets/logo.svg web/src/assets/logo.svg.backup

# 复制新设计（选择其中一个）
cp web/src/assets/logo-option-1-enhanced-radar.svg web/src/assets/logo.svg
# 或
cp web/src/assets/logo-option-2-network-lens.svg web/src/assets/logo.svg
# 或
cp web/src/assets/logo-option-3-signal-detective.svg web/src/assets/logo.svg
```

#### 方案 B：保留多个版本

```bash
# 在 Logo 组件中根据上下文选择
export const Logo = ({ variant = 'default' }) => {
  const logoMap = {
    default: '/src/assets/logo-option-1-enhanced-radar.svg',
    detective: '/src/assets/logo-option-2-network-lens.svg',
    signal: '/src/assets/logo-option-3-signal-detective.svg',
  }
  
  return <img src={logoMap[variant]} alt="NetSherlock" />
}
```

### 3️⃣ React 组件集成示例

#### 在 Header 中使用

```tsx
// web/src/components/Header.tsx
import logo from '@/assets/logo.svg'

export function Header() {
  return (
    <header className="border-b">
      <div className="flex items-center gap-4 p-4">
        <img 
          src={logo} 
          alt="NetSherlock" 
          className="w-8 h-8 dark:invert"
        />
        <h1 className="text-xl font-bold">NetSherlock</h1>
      </div>
    </header>
  )
}
```

#### 在导航栏中使用

```tsx
// web/src/components/Navigation.tsx
import logo from '@/assets/logo.svg'

export function Navigation() {
  return (
    <nav className="flex items-center gap-6 px-6 py-4">
      <div className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition">
        <img src={logo} alt="NetSherlock" className="w-6 h-6" />
        <span className="text-sm font-semibold">NetSherlock</span>
      </div>
      {/* 其他导航项 */}
    </nav>
  )
}
```

#### 作为 Favicon 使用

在 `web/index.html` 中：

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  
  <!-- Favicon 配置 -->
  <link rel="icon" type="image/svg+xml" href="/src/assets/logo.svg" />
  <link rel="alternate icon" type="image/png" href="/logo-32.png" />
  
  <title>NetSherlock - Network Diagnostics</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/main.tsx"></script>
</body>
</html>
```

### 4️⃣ Tailwind CSS 样式示例

```tsx
// web/src/components/LogoWithText.tsx
export function LogoWithText() {
  return (
    <div className="flex items-center gap-3">
      <img 
        src={logo} 
        alt="NetSherlock" 
        className="w-10 h-10 rounded-lg bg-gradient-to-br from-blue-50 to-cyan-50 p-1.5 dark:bg-slate-900"
      />
      <div className="flex flex-col">
        <span className="text-sm font-bold text-slate-900 dark:text-white">
          NetSherlock
        </span>
        <span className="text-xs text-slate-500 dark:text-slate-400">
          Network Diagnostics
        </span>
      </div>
    </div>
  )
}
```

---

## 深色模式适配

### 方案 1：CSS 反转

对于深色主题，简单反转颜色：

```tsx
<img 
  src={logo} 
  alt="NetSherlock" 
  className="w-8 h-8 dark:invert"
/>
```

### 方案 2：SVG 变体

为深色模式创建专门的 SVG：

```tsx
import logoDark from '@/assets/logo-dark.svg'
import logoLight from '@/assets/logo.svg'

export function AdaptiveLogo() {
  return (
    <>
      <img src={logoLight} alt="NetSherlock" className="dark:hidden" />
      <img src={logoDark} alt="NetSherlock" className="hidden dark:inline" />
    </>
  )
}
```

### 方案 3：Tailwind 自定义

```tsx
export function DarkModeLogo() {
  const isDark = document.documentElement.classList.contains('dark')
  
  return (
    <img 
      src={logo} 
      alt="NetSherlock" 
      style={{
        filter: isDark ? 'brightness(1.2) saturate(0.8)' : 'none'
      }}
    />
  )
}
```

---

## 导出为其他格式

### SVG → PNG（高质量）

使用在线工具或命令行：

```bash
# 方法 1：使用 ImageMagick
magick convert -background none -density 192 -resize 512x512 \
  logo-option-1-enhanced-radar.svg logo-512.png

# 方法 2：使用 Inkscape
inkscape -l logo-256.png -w 256 -h 256 logo-option-1-enhanced-radar.svg

# 方法 3：在线工具
# https://convertio.co/svg-png/
```

### 为不同尺寸生成

```bash
#!/bin/bash
# 生成多个尺寸的 PNG

for size in 32 64 128 256 512; do
  magick convert -background none logo-option-1-enhanced-radar.svg \
    -resize ${size}x${size} \
    logo-${size}.png
done
```

### 创建 ICO 文件（Favicon）

```bash
# 需要 ImageMagick 的 convert 命令
convert logo-16.png logo-32.png logo-48.png favicon.ico
```

---

## 动画集成（高级）

### 方案：CSS 关键帧

为信号侦测设计添加脉冲效果：

```tsx
// web/src/components/AnimatedLogo.tsx
import { FC } from 'react'
import logo from '@/assets/logo-option-3-signal-detective.svg'

export const AnimatedLogo: FC = () => {
  return (
    <img 
      src={logo} 
      alt="NetSherlock" 
      className="w-8 h-8 animate-pulse"
      style={{
        animation: 'netherlock-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite'
      }}
    />
  )
}
```

在 CSS 中：

```css
/* web/src/index.css */
@keyframes netherlock-pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.7;
  }
}

@keyframes netherlock-rotate {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.animate-netherlock {
  animation: netherlock-rotate 3s linear infinite;
}
```

---

## 品牌应用示例

### 1. 登录页面

```tsx
<div className="flex flex-col items-center justify-center min-h-screen">
  <img 
    src={logo} 
    alt="NetSherlock" 
    className="w-20 h-20 mb-8"
  />
  <h1 className="text-3xl font-bold mb-2">NetSherlock</h1>
  <p className="text-gray-600 mb-8">Network Diagnostics Platform</p>
  {/* 登录表单 */}
</div>
```

### 2. 仪表板顶部

```tsx
<div className="flex items-center justify-between p-4 bg-white border-b">
  <div className="flex items-center gap-4">
    <img src={logo} alt="NetSherlock" className="w-8 h-8" />
    <h2 className="text-lg font-semibold">Dashboard</h2>
  </div>
  {/* 用户菜单等 */}
</div>
```

### 3. 邮件/文档签名

```html
<table cellpadding="0" cellspacing="0" border="0">
  <tr>
    <td>
      <img 
        src="logo-128.png" 
        alt="NetSherlock" 
        width="64" 
        height="64"
      />
    </td>
    <td style="padding-left: 16px;">
      <p style="margin: 0; font-weight: bold;">NetSherlock</p>
      <p style="margin: 4px 0 0 0; font-size: 12px; color: #666;">
        Network Diagnostics
      </p>
    </td>
  </tr>
</table>
```

---

## 故障排除

### Q: 图标在深色主题中看不清

**A**: 使用 `dark:invert` 或创建深色变体：
```tsx
<img src={logo} className="dark:invert" />
```

### Q: SVG 在某些浏览器中不显示

**A**: 确保 MIME 类型正确设置：
```html
<img type="image/svg+xml" src={logo} />
```

或在 CSS 中：
```css
.logo {
  content: url('/src/assets/logo.svg');
}
```

### Q: 性能优化建议

**A**: 对于多次使用，考虑：
1. 内联 SVG（减少 HTTP 请求）
2. 使用 `<picture>` 标签根据屏幕大小选择
3. 启用 SVG 缓存

---

## 下一步

1. ✅ 在团队中讨论三个设计方案
2. ✅ 获得设计批准
3. ✅ 按照上述步骤集成所选设计
4. ✅ 在不同设备和主题中测试
5. ✅ 更新营销材料和文档

---

**最后更新**: 2026-02-06  
**维护者**: Design Team
