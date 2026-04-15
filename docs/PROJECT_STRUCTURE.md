# 项目结构说明

## 1. 当前仓库根目录

```text
沉香行业情报浏览系统_1.0
├── app/                  程序源码
├── archive/              本地归档与旧材料
├── config/               配置模板与本地配置
├── data/                 数据、证据、数据库、解析快照
├── deploy/               部署说明
├── docs/                 长期维护文档
├── exports/              导出成果与本地报告
├── scripts/              迁移、修复、导出脚本
├── storage/              运行时文件库、缓存、上传、日志
├── tests/                冒烟测试
├── README.md             仓库入口说明
├── requirements.txt      依赖清单
├── run.py                启动入口
├── 启动程序.bat          Windows 启动脚本
└── 安装依赖.bat          Windows 安装脚本
```

## 2. 各目录职责

### `app/`

程序主代码目录。

- `__init__.py`：应用工厂，读取配置，初始化目录和数据库
- `routes.py`：页面和管理路由
- `services.py`：业务服务层，上传、累计视图、文件库、PDF 导出
- `parsers.py`：文档解析、section 切分、结构验证
- `rebuild_engine.py`：历史重建、去重、来源回填、迁移报告
- `rendering.py`：把条目转换成页面渲染结构
- `pdf_export.py`：PDF 输出
- `static/`：CSS / JS
- `templates/`：Jinja 模板

### `config/`

配置目录。

- `local_settings.json`：本地真实配置，不建议进 Git
- `local_settings.example.json`：仓库可提交的配置模板

### `data/`

本地数据和证据目录。

- `database/`：SQLite 数据库
- `processed/archive_parsed/`：当前解析快照
- `raw/briefs/`：原始简报
- `raw/drafts/`：原始底稿
- `raw/linked/`：带链接资料
- `review/`：复查结果
- `verification/`：真实性核验报告

### `storage/`

运行时目录。

- `file_library/`：当前生效文件库
- `cache/`：临时上传缓存
- `uploads/`：原始上传留存
- `logs/`：日志

### `exports/`

导出与生成物目录。

- `pdf/`：页面导出的 PDF
- `reports/`：迁移、证据映射、系统状态报告
- `review_packages/`：代码汇总、项目总说明等外发包文档

### `docs/`

长期维护文档，不是运行产物。

- `PROJECT_STRUCTURE.md`
- `RUN_GUIDE.md`
- `KNOWN_ISSUES.md`
- `GITHUB_REPO_READY.md`
- `review/`：已有外部审查材料
- `specs/`：模板规范

### `archive/`

保留旧材料，不直接删原始资料。

- `legacy_docs/`：旧导出文档
- `duplicates/`：重复历史产物

## 3. 哪些内容建议提交到 Git

建议提交：

- `app/`
- `config/local_settings.example.json`
- `docs/`
- `deploy/`
- `scripts/`
- `tests/`
- `README.md`
- `requirements.txt`
- `run.py`
- `启动程序.bat`
- `安装依赖.bat`
- `docs/specs/TEMPLATE_SPEC_v2.md`

## 4. 哪些内容建议只做本地保存

不建议直接提交：

- `config/local_settings.json`
- `data/database/`
- `data/raw/`
- `data/review/`
- `data/verification/`
- `data/processed/archive_parsed/`
- `storage/`
- `exports/pdf/`
- `exports/reports/`
- `exports/review_packages/`
- `archive/legacy_docs/`
- `archive/duplicates/`

这些边界已经在 `.gitignore` 里补齐。
