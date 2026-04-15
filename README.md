# 沉香行业情报浏览系统 1.0

## 项目是什么

这是一个本地运行的行业情报浏览系统，用来接收研究底稿和每日简报，解析内容，保留历史版本，并以网页方式展示“截至当前最新版本的累计有效内容”。

它更像一个“行业记忆系统”，而不是一次性日报播放器。项目重点不在抓网，而在以下几件事：

- 接收和归档底稿、简报、证据资料
- 解析并展示结构化情报内容
- 保留历史版本和证据链
- 支持本地 / 局域网访问和后续接手维护

## 当前仓库定位

这份目录现在按 GitHub 仓库的思路做了整理：

- `app/` 放程序源码
- `config/` 放配置模板和本地配置
- `scripts/` 放迁移、清洗、导出脚本
- `docs/` 放长期维护文档
- `data/` 放本地证据与运行数据
- `storage/` 放上传、缓存、文件库、日志
- `exports/` 放导出产物和本地报告
- `archive/` 放旧导出、旧规范、重复历史产物

其中需要特别注意：

- **适合进入 Git 的内容**：源码、脚本、模板、样式、文档、配置模板
- **不建议直接进入 Git 的内容**：数据库、上传文件、原始底稿、核验报告、导出 PDF、本地报告、本地配置

`.gitignore` 已经按这个边界补齐。

## 当前目录结构

```text
沉香行业情报浏览系统_1.0
├── app/
├── archive/
├── config/
├── data/
├── deploy/
├── docs/
├── exports/
├── scripts/
├── storage/
├── tests/
├── README.md
├── requirements.txt
├── run.py
├── 启动程序.bat
└── 安装依赖.bat
```

更详细的结构说明请看：

- `docs/PROJECT_STRUCTURE.md`
- `docs/GITHUB_REPO_READY.md`

## 运行环境

- Python 3.11+
- Windows 本地运行为主
- 浏览器访问
- SQLite 本地数据库

## 第一次启动前要做什么

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 复制配置模板

把下面这个文件复制一份：

- `config/local_settings.example.json`

复制后的目标文件名为：

- `config/local_settings.json`

3. 按本机情况修改配置

至少建议修改这些字段：

- `SECRET_KEY`
- `ADMIN_PASSWORD`
- `INITIAL_ADMIN_ACCESS_CODE`
- `INITIAL_VIEWER_ACCESS_CODE`
- `LAN_ACCESS_HOST`

## 如何启动

```bash
python run.py
```

Windows 下也可以直接双击：

- `启动程序.bat`

默认访问地址：

- 本机：`http://127.0.0.1:5050`
- 局域网：`http://192.168.1.2:5050`

## 当前权限控制

系统现在是轻量访问控制模型，不是正式员工账号体系。

- `viewer`：只读浏览
- `admin`：可上传、撤回、激活、删除、管理访问资格

本地配置由 `config/local_settings.json` 控制。

## 当前主要功能

- 上传研究底稿、每日简报
- 自动识别文档类型
- docx / md / txt / pdf 文本提取
- 固定 section 解析与展示
- 历史累计有效内容视图
- 文件库管理
- 访问码权限控制
- 来源链接与证据链展示
- PDF 导出
- 迁移 / 重建 / 去重脚本

## 当前最需要维护者知道的边界

### 1. 真实本地数据不要直接提交到 Git

以下目录默认只做本地保存：

- `data/raw/`
- `data/review/`
- `data/verification/`
- `data/database/`
- `data/processed/archive_parsed/`
- `storage/`
- `exports/pdf/`
- `exports/reports/`
- `exports/review_packages/`

### 2. 当前最乱的地方已经不是源码，而是“运行产物”

现在最容易让项目重新变乱的，不是 `app/`，而是这些地方：

- 本地数据库持续累积
- 文件库中的活跃文件和历史文件
- 导出 PDF 和导出报告
- 外发代码汇总和项目说明大文件

### 3. 接公网前不要误判为“已经生产可用”

当前版本适合：

- 本机运行
- 局域网试用
- 内部继续开发

当前版本还不适合直接裸奔上公网，后续仍建议补：

- 正式账号体系
- HTTPS
- 服务器级访问控制
- 操作审计日志
- 环境变量密钥管理

## 文档入口

### 仓库维护文档

- `docs/PROJECT_STRUCTURE.md`
- `docs/RUN_GUIDE.md`
- `docs/KNOWN_ISSUES.md`
- `docs/GITHUB_REPO_READY.md`

### 现有审查材料

- `docs/review/PROJECT_TREE.md`
- `docs/review/RUN_GUIDE.md`
- `docs/review/KNOWN_ISSUES.md`
- `docs/review/PROJECT_REVIEW_PACKAGE.md`

### 模板规范

- `docs/specs/TEMPLATE_SPEC_v2.md`

## 常用脚本

```bash
python scripts/migration_rebuild_entries.py
python scripts/normalize_entry_states.py
python scripts/dedupe_events.py
python scripts/export_review_bundle.py
python tests/smoke_test.py
```

## 如果要交给别人继续接手

建议按这个顺序看：

1. `README.md`
2. `docs/GITHUB_REPO_READY.md`
3. `docs/PROJECT_STRUCTURE.md`
4. `docs/RUN_GUIDE.md`
5. `docs/KNOWN_ISSUES.md`
6. `docs/specs/TEMPLATE_SPEC_v2.md`
7. `app/routes.py`
8. `app/services.py`
9. `app/rebuild_engine.py`
