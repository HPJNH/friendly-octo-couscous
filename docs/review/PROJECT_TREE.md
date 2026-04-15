# 目录结构说明

## 1. 说明

以下目录树基于当前项目根目录快照整理。

说明：

- 重点保留了业务目录、运行产物和审查相关文件。
- `__pycache__` 属于 Python 运行缓存，未展开其内部文件。
- 目录树包含当前已有的上传样本、解析样本和 PDF 导出样本，便于外部审查者复核真实运行结果。

## 2. 项目目录树

```text
沉香行业情报浏览系统_1.0/
├─ app/
│  ├─ static/
│  │  ├─ css/
│  │  │  └─ style.css
│  │  └─ js/
│  │     └─ main.js
│  ├─ templates/
│  │  ├─ base.html
│  │  ├─ day.html
│  │  ├─ history.html
│  │  ├─ section_debug.html
│  │  ├─ section_detail.html
│  │  └─ upload.html
│  ├─ __init__.py
│  ├─ constants.py
│  ├─ db.py
│  ├─ parsers.py
│  ├─ pdf_export.py
│  ├─ rendering.py
│  ├─ routes.py
│  ├─ services.py
│  └─ utils.py
├─ archive/
│  └─ parsed/
│     └─ 2026-04-02/
│        ├─ 20260402-215233-986858_draft.json
│        ├─ 20260402-222558-615951_draft.json
│        ├─ 20260402-222558-639084_brief.json
│        ├─ 20260402-222845-955623_draft.json
│        ├─ 20260402-222845-979710_brief.json
│        ├─ 20260402-225824-639563_draft.json
│        ├─ 20260402-225824-669385_brief.json
│        ├─ 20260402-225835-382409_draft.json
│        ├─ 20260402-225835-414007_brief.json
│        ├─ 20260402-231351-126712_draft.json
│        ├─ 20260402-231351-154375_brief.json
│        ├─ 20260402-231548-049566_draft.json
│        ├─ 20260402-231548-078371_brief.json
│        ├─ 20260402-231626-461962_draft.json
│        ├─ 20260402-231626-490029_brief.json
│        ├─ 20260402-231724-768019_draft.json
│        └─ 20260402-231724-795578_brief.json
├─ data/
├─ database/
│  └─ intelligence_browser.db
├─ exports/
│  └─ pdf/
│     └─ 沉香行业情报浏览成果_2026-04-02.pdf
├─ uploads/
│  └─ originals/
│     └─ 2026-04-02/
│        ├─ 20260402-215233-507349_沉香行业情报研究底稿.docx
│        ├─ 20260402-222558-407917_沉香行业情报研究底稿.docx
│        ├─ 20260402-222558-624194_简报(1).docx
│        ├─ 20260402-222845-742155_沉香行业情报研究底稿.docx
│        ├─ 20260402-222845-964298_简报(1).docx
│        ├─ 20260402-225824-511370_沉香行业情报研究底稿.docx
│        ├─ 20260402-225824-653275_简报(1).docx
│        ├─ 20260402-225835-250984_沉香行业情报研究底稿.docx
│        ├─ 20260402-225835-397645_简报(1).docx
│        ├─ 20260402-231350-985154_沉香行业情报研究底稿.docx
│        ├─ 20260402-231351-137927_简报(1).docx
│        ├─ 20260402-231547-915000_沉香行业情报研究底稿.docx
│        ├─ 20260402-231548-062154_简报(1).docx
│        ├─ 20260402-231626-336174_沉香行业情报研究底稿.docx
│        ├─ 20260402-231626-474984_简报(1).docx
│        ├─ 20260402-231724-632696_沉香行业情报研究底稿.docx
│        └─ 20260402-231724-779979_简报(1).docx
├─ KEY_CODE_SUMMARY.md
├─ KNOWN_ISSUES.md
├─ PROJECT_REVIEW_PACKAGE.md
├─ PROJECT_TREE.md
├─ README.md
├─ REVIEW_REQUEST_FOR_GPT.md
├─ RUN_GUIDE.md
├─ requirements.txt
├─ run.py
├─ 项目审查摘要.txt
├─ 启动程序.bat
└─ 安装依赖.bat
```

## 3. 关键文件路径与作用

### 根目录

- `run.py`
  - Flask 启动入口
- `requirements.txt`
  - Python 依赖列表
- `启动程序.bat`
  - Windows 一键启动脚本
- `安装依赖.bat`
  - Windows 一键安装依赖脚本

### 核心应用目录 `app/`

- `app/__init__.py`
  - 创建 Flask 应用
  - 配置数据库、上传目录、导出目录
  - 启动时触发旧文档升级重解析

- `app/constants.py`
  - 10 个正式板块定义
  - section 顺序
  - 状态标签映射
  - 文档类型关键字

- `app/db.py`
  - SQLite 连接
  - 数据表初始化
  - schema 补列

- `app/parsers.py`
  - docx/md/txt/pdf 文本提取
  - docx 段落和表格顺序读取
  - 一级 section 切分
  - 小节标题识别

- `app/rendering.py`
  - 把解析结果转为页面渲染模型
  - 段落、卡片、表格、分组处理
  - 简报 HTML 生成

- `app/services.py`
  - 项目主业务层
  - 上传处理
  - 文档入库
  - section 快照生成
  - 状态判断
  - 首页/详情页/历史页取数
  - PDF 导出载荷组装

- `app/routes.py`
  - Web 路由
  - 首页、历史页、上传页、section 页
  - 调试页
  - PDF 导出与下载

- `app/pdf_export.py`
  - 结构化 PDF 导出
  - 封面、简报、板块、表格生成

- `app/utils.py`
  - 日期识别
  - JSON 读写
  - 文本规范化
  - 哈希计算

### 模板目录 `app/templates/`

- `base.html`
  - 全站框架
  - 左侧导航
  - 顶部操作区
  - 导出提示

- `day.html`
  - 首页
  - 简报展示
  - 今日更新概览
  - 板块总览
  - 历史入口

- `history.html`
  - 历史记录页
  - 每日归档入口
  - PDF 导出入口

- `section_detail.html`
  - 板块详情页
  - 正文、卡片、表格展示

- `section_debug.html`
  - section 解析调试页
  - 展示每个板块的起止边界和预览

- `upload.html`
  - 上传页
  - 上传结果反馈

### 静态资源目录 `app/static/`

- `app/static/css/style.css`
  - 全站样式
  - 导航栏布局
  - 板块阅读页样式
  - 表格、卡片、PDF 提示样式

- `app/static/js/main.js`
  - 上传页拖拽交互

### 数据目录

- `uploads/originals/`
  - 原始上传文件
- `archive/parsed/`
  - 每次解析后的 JSON 归档
- `database/intelligence_browser.db`
  - SQLite 数据库
- `exports/pdf/`
  - 导出的 PDF 成果页

## 4. 审查者最值得先看的文件

如果时间有限，建议先看下面 8 个文件：

1. `app/parsers.py`
2. `app/services.py`
3. `app/rendering.py`
4. `app/pdf_export.py`
5. `app/routes.py`
6. `app/templates/section_detail.html`
7. `app/templates/day.html`
8. `app/static/css/style.css`
