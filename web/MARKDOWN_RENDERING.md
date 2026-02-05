# Markdown Report Rendering

本项目实现了完整的Markdown诊断报告渲染功能。诊断报告可以在任务详情页和报告详情页中以格式化的Markdown形式显示。

## 功能特性

### 支持的Markdown元素

✅ **标题**: H1, H2, H3 (带下划线)
✅ **段落**: 正确的间距和排版
✅ **列表**: 无序列表和有序列表
✅ **表格**: 完整的GitHub风格表格，带hover效果
✅ **代码**: 行内代码和代码块（语法高亮背景）
✅ **链接**: 可点击的超链接
✅ **引用**: 左边框引用块
✅ **分割线**: 水平分割线
✅ **GitHub风格Markdown**: 删除线、表格、任务列表等

## 文件结构

### 1. 页面组件

#### TaskDetailPage.tsx
- 显示诊断任务的详细信息
- 包含执行日志和完整报告段落
- 当`markdown_report`存在时显示完整报告

```tsx
{task.markdown_report && (
  <div className="bg-white border border-gray-200 rounded-lg p-6 mt-6">
    <h2 className="text-lg font-semibold text-gray-900 mb-4">
      Full Report
    </h2>
    <div className="prose prose-sm max-w-none">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>
        {task.markdown_report}
      </ReactMarkdown>
    </div>
  </div>
)}
```

#### ReportDetailPage.tsx
- 显示已完成诊断的详细报告
- 包含根因分析、建议和完整Markdown报告
- 同样渲染完整的Markdown报告

### 2. 样式定义

#### index.css
完整的CSS样式定义，包括：
- 标题样式（H1, H2, H3）
- 表格样式（包括hover效果）
- 代码块和行内代码
- 链接样式
- 列表样式
- 引用块样式
- 响应式排版

### 3. 依赖包

已在`package.json`中配置：
```json
{
  "react-markdown": "^9.0.1",
  "remark-gfm": "^4.0.0"
}
```

- **react-markdown**: React中的Markdown渲染库
- **remark-gfm**: GitHub风格Markdown支持（表格、删除线等）

## 样式定义

### 基础样式

| 元素 | 样式 |
|------|------|
| 正文 | 灰色(#1f2937), 行高1.75 |
| H1 | 1.875rem, 粗体700, 深灰色 |
| H2 | 1.5rem, 粗体600, 带下边框 |
| H3 | 1.25rem, 粗体600, 浅灰色 |
| 代码 | 灰色背景, 等宽字体, 带圆角 |
| 代码块 | 深色背景, 浅色文字 |
| 表格 | 完整边框, 灰色表头, hover效果 |
| 链接 | 蓝色(#2563eb), 带下划线, hover变深 |

### prose-sm 变体

针对较小屏幕的压缩样式：
- 字体大小: 0.875rem
- 行高: 1.6
- 标题大小相应缩小

## 示例

### 报告结构

```markdown
# VM Network Latency Analysis Report

**Measurement Directory**: `measurement-20260204-175008`

## Summary

| Metric | Value |
|--------|-------|
| Sender Total RTT | 353.80 us |
| Receiver Total RTT | 229.00 us |

## Layer Attribution

| Layer | Latency (us) | Percentage |
|-------|-------------|------------|
| Receiver Host OVS | 118.00 | 33.4% |

## Key Findings

- **Primary Bottleneck**: Receiver Host OVS (118.0us, 33.4%)
- **Physical Network**: 23.0us - within normal range
```

### 渲染效果

✅ 标题带有适当的字体大小和间距
✅ 表格使用网格布局，清晰易读
✅ 数据行hover时有背景色变化
✅ 链接可点击且带有适当的颜色
✅ 代码块具有可读性强的样式

## 使用方法

### 在组件中使用

```typescript
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

// 在JSX中
<div className="prose prose-sm max-w-none">
  <ReactMarkdown remarkPlugins={[remarkGfm]}>
    {markdown_content}
  </ReactMarkdown>
</div>
```

### 在mock数据中

所有mock诊断都包含完整的`markdown_report`字段：

```typescript
{
  diagnosis_id: 'diag-20260204-175008-vm-latency',
  status: 'completed',
  markdown_report: `# VM Network Latency Analysis Report\n\n...`,
  // ... 其他字段
}
```

## 自定义样式

要修改Markdown样式，编辑`src/index.css`中的`.prose`相关类：

```css
/* 示例：修改表头颜色 */
.prose th {
  background-color: #your-color;
}

/* 示例：修改代码块颜色 */
.prose pre {
  background-color: #your-color;
}
```

## 浏览器兼容性

✅ 现代浏览器完全支持
✅ Chrome/Firefox/Safari/Edge
✅ 响应式设计，支持移动设备

## 性能考虑

- Markdown渲染在客户端进行（无服务器处理）
- React-markdown高效处理大型报告
- CSS样式使用原生CSS（无额外依赖）

## 已知限制

- 不支持自定义Markdown扩展（仅限GitHub风格）
- 不支持嵌入式多媒体
- 代码块未进行语法高亮（但有视觉区分）

## 下一步改进

可选的增强功能：
- 添加Highlight.js进行代码语法高亮
- 支持主题切换（亮/暗模式）
- 添加目录导航（Table of Contents）
- 支持PDF导出
