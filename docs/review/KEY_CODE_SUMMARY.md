# 关键代码汇总

## 1. 最关键的代码文件

下面这些文件是当前项目最值得审查的代码文件。

| 文件 | 作用 | 当前缺陷 / 风险 |
| --- | --- | --- |
| `app/parsers.py` | 文档解析主入口，负责 docx/md/txt/pdf 文本提取、docx 段落和表格顺序遍历、section 切分、小节识别 | 标题匹配仍依赖固定写法；复杂表格和异常标题格式仍有风险 |
| `app/services.py` | 主业务层，负责上传、入库、section 快照、状态判断、页面取数、PDF 数据载荷组装 | 文件过大、职责过多，后续维护成本高 |
| `app/rendering.py` | 把解析结果转成页面可渲染的数据结构，负责卡片、表格、分组、简报 HTML | 启发式结构化较多，字段识别不是严格语义解析 |
| `app/pdf_export.py` | 结构化 PDF 导出，不是直接打印网页 | PDF 样式是简化版，不是网页像素级还原 |
| `app/routes.py` | 路由层，负责首页、历史页、上传页、板块页、调试页、PDF 导出下载 | 当前仍把调试入口暴露在主界面，产品体验偏内部工具 |
| `app/db.py` | SQLite schema 和连接 | 没有正式迁移体系，只做了轻量补列 |
| `app/constants.py` | section 定义、状态映射、文档类型关键字 | 所有板块识别依赖这里的固定配置 |
| `app/templates/section_detail.html` | 板块详情页模板 | 页面结构较复杂，后续易和渲染模型耦合过深 |
| `app/templates/day.html` | 首页模板，包含简报、概览、板块总览、历史入口 | 首页信息量仍然偏大，继续产品化还有空间 |
| `app/static/css/style.css` | 全站布局和主要阅读样式 | 单文件较大，后续可拆分为多个样式模块 |

## 2. 问题定位对照表

### section 切分逻辑在哪

主要在：

- `app/parsers.py`

重点函数：

- `extract_docx_blocks()`
- `iter_docx_block_items()`
- `build_sections_from_blocks()`
- `match_section_heading()`
- `strip_top_level_numbering()`

### docx 解析逻辑在哪

主要在：

- `app/parsers.py`

重点函数：

- `extract_docx_text()`
- `extract_docx_blocks()`
- `build_paragraph_block()`
- `build_table_block()`

### 表格解析逻辑在哪

表格提取在：

- `app/parsers.py`

表格渲染数据整理在：

- `app/rendering.py`

重点函数：

- `build_table_block()`
- `split_table_rows()`
- `extract_cards_from_table()`

### 页面渲染逻辑在哪

后端数据整理在：

- `app/services.py`
- `app/rendering.py`

前端模板在：

- `app/templates/base.html`
- `app/templates/day.html`
- `app/templates/history.html`
- `app/templates/section_detail.html`
- `app/templates/section_debug.html`
- `app/templates/upload.html`

### 导航栏布局逻辑在哪

主要在：

- `app/templates/base.html`
- `app/static/css/style.css`

与“左侧导航可滚动”直接相关的样式也在 `style.css`。

### PDF 导出逻辑在哪

主要在：

- `app/pdf_export.py`

触发与数据准备在：

- `app/routes.py`
- `app/services.py`

## 3. 各模块简要说明

### `app/parsers.py`

这是解析器核心。

它做了三件重要事情：

1. 读取 docx 中的段落和表格，并保持顺序
2. 只允许 10 个正式一级标题切换 section
3. 把 `2.1 / 3.1.1` 这类识别为板块内部小节，而不是一级板块

当前缺陷：

- 标题识别比较“保守”，优点是降低串栏，缺点是遇到标题变体时更容易漏识别
- 不能读取图片、文本框、批注等复杂 Word 元素

### `app/services.py`

这是项目最重的业务文件。

它负责：

- 上传处理
- 文档解析调用
- 入库
- section 状态计算
- 首页/详情页/历史页取数
- PDF 导出数据拼装
- 启动时旧数据升级

当前缺陷：

- 单文件职责太多
- 后续继续加功能会越来越难维护

### `app/rendering.py`

它的职责不是“解析原始 docx”，而是把解析后的 blocks 变成：

- 卡片
- 表格
- 正文段落
- 小节分组

当前缺陷：

- 对“标题 / 时间 / 来源 / 核心内容”的识别是启发式规则
- 不同样本的稳定性还需要更多真实文档验证

### `app/pdf_export.py`

它不是把网页截图成 PDF，也不是浏览器打印网页。

它做的是：

- 根据系统中的展示结果重新组织内容
- 用 ReportLab 生成结构化 PDF
- 输出封面、简报、各板块、表格

当前缺陷：

- 样式比网页简化
- 复杂表格的分页与换行仍可能不够优雅

### 模板与样式

- `base.html` 控制全局导航和顶部操作
- `day.html` 控制首页
- `section_detail.html` 控制板块详情页
- `style.css` 控制全站阅读样式

当前缺陷：

- 模板层和渲染模型耦合较深
- 样式文件已经比较长，后续适合拆分

## 4. 最值得外部审查者重点看的问题

建议外部审查者重点判断以下几点：

1. `app/parsers.py` 的一级标题识别是否足够稳
2. `app/services.py` 是否应该拆层
3. `app/rendering.py` 的卡片识别规则是否过于脆弱
4. `app/pdf_export.py` 是否已经足够满足“对外展示成果”这个目标
5. 数据库存绝对路径的做法是否适合迁移
6. “历史保留”状态和实际正文展示是否需要重新定义
