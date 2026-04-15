from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATE_TAG = datetime.now().strftime("%Y%m%d")
EXPORT_DIR = PROJECT_ROOT / "exports" / "review_packages"

KEY_FILES = [
    "run.py",
    "README.md",
    "requirements.txt",
    "config/local_settings.example.json",
    "docs/PROJECT_STRUCTURE.md",
    "docs/RUN_GUIDE.md",
    "docs/KNOWN_ISSUES.md",
    "docs/GITHUB_REPO_READY.md",
    "docs/specs/TEMPLATE_SPEC_v2.md",
    "app/__init__.py",
    "app/admin_auth.py",
    "app/constants.py",
    "app/db.py",
    "app/parsers.py",
    "app/pdf_export.py",
    "app/rebuild_engine.py",
    "app/rendering.py",
    "app/routes.py",
    "app/services.py",
    "app/utils.py",
    "app/templates/base.html",
    "app/templates/access_login.html",
    "app/templates/admin_verify.html",
    "app/templates/access_manage.html",
    "app/templates/day.html",
    "app/templates/history.html",
    "app/templates/library.html",
    "app/templates/library_detail.html",
    "app/templates/section_detail.html",
    "app/templates/section_debug.html",
    "app/templates/upload.html",
    "app/static/css/style.css",
    "app/static/js/main.js",
    "scripts/migration_rebuild_entries.py",
    "scripts/normalize_entry_states.py",
    "scripts/dedupe_events.py",
]

KEY_FILE_DESCRIPTIONS = {
    "run.py": "项目启动入口。",
    "README.md": "仓库主说明文档。",
    "requirements.txt": "Python 依赖清单。",
    "config/local_settings.example.json": "可提交的配置模板，供接手者复制成本地配置。",
    "docs/PROJECT_STRUCTURE.md": "项目结构说明。",
    "docs/RUN_GUIDE.md": "运行说明。",
    "docs/KNOWN_ISSUES.md": "当前已知问题。",
    "docs/GITHUB_REPO_READY.md": "仓库整理说明与接手建议。",
    "docs/specs/TEMPLATE_SPEC_v2.md": "底稿模板规范。",
    "app/__init__.py": "应用工厂，负责配置和初始化。",
    "app/admin_auth.py": "访问控制与权限管理。",
    "app/constants.py": "常量和映射定义。",
    "app/db.py": "数据库结构与初始化。",
    "app/parsers.py": "文档解析与结构识别。",
    "app/pdf_export.py": "PDF 导出逻辑。",
    "app/rebuild_engine.py": "历史重建、来源回填、重建报告。",
    "app/rendering.py": "渲染模型构建。",
    "app/routes.py": "Flask 路由。",
    "app/services.py": "业务服务层。",
    "app/utils.py": "工具函数。",
    "app/templates/base.html": "全局页面框架。",
    "app/templates/access_login.html": "访问码登录页。",
    "app/templates/admin_verify.html": "管理验证页。",
    "app/templates/access_manage.html": "访问资格管理页。",
    "app/templates/day.html": "首页模板。",
    "app/templates/history.html": "历史页模板。",
    "app/templates/library.html": "文件库模板。",
    "app/templates/library_detail.html": "文件详情模板。",
    "app/templates/section_detail.html": "板块详情模板。",
    "app/templates/section_debug.html": "section 调试模板。",
    "app/templates/upload.html": "上传页模板。",
    "app/static/css/style.css": "主样式文件。",
    "app/static/js/main.js": "主前端脚本。",
    "scripts/migration_rebuild_entries.py": "迁移与重建脚本入口。",
    "scripts/normalize_entry_states.py": "状态归一化脚本入口。",
    "scripts/dedupe_events.py": "事件去重脚本入口。",
}


def build_tree(root: Path, max_depth: int = 3, prefix: str = "") -> list[str]:
    ignored = {"__pycache__", ".git"}
    children = sorted(
        [item for item in root.iterdir() if item.name not in ignored],
        key=lambda item: (item.is_file(), item.name.lower()),
    )
    lines: list[str] = []
    for index, child in enumerate(children):
        connector = "└── " if index == len(children) - 1 else "├── "
        lines.append(f"{prefix}{connector}{child.name}")
        if child.is_dir() and max_depth > 0:
            extension = "    " if index == len(children) - 1 else "│   "
            lines.extend(build_tree(child, max_depth - 1, prefix + extension))
    return lines


def safe_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if path.name == "local_settings.example.json":
        payload = json.loads(text)
        for key in ("SECRET_KEY", "ADMIN_PASSWORD", "INITIAL_ADMIN_ACCESS_CODE", "INITIAL_VIEWER_ACCESS_CODE"):
            if key in payload:
                payload[key] = "***masked***"
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return text


def render_file_section(relative_path: str) -> str:
    path = PROJECT_ROOT / relative_path
    description = KEY_FILE_DESCRIPTIONS.get(relative_path, "关键文件。")
    if not path.exists():
        return (
            f"## 文件：{path.name}\n"
            f"路径：{path}\n"
            f"作用：{description}\n\n"
            "```text\n文件不存在\n```\n"
        )
    language = path.suffix.lstrip(".") or "text"
    return (
        f"## 文件：{path.name}\n"
        f"路径：{path}\n"
        f"作用：{description}\n\n"
        f"```{language}\n{safe_text(path)}\n```\n"
    )


def write_project_summary(tree_block: str) -> Path:
    output_path = EXPORT_DIR / f"CN_情报浏览系统_项目总说明_{DATE_TAG}.md"
    output_path.write_text(
        "\n".join(
            [
                "# 情报浏览系统 项目总说明",
                "",
                "## 项目目录树",
                tree_block,
                "",
                "## 项目目标",
                "- 把研究底稿、每日简报、历史资料和证据链组织成可长期维护的本地情报浏览系统。",
                "- 支持本地运行、局域网浏览、历史累计展示、文件库管理和 PDF 导出。",
                "",
                "## 当前仓库状态",
                "- 当前已经完成目录分层：源码、配置、数据、存储、导出、文档、脚本、归档已分开。",
                "- 当前已经补齐仓库基础文件：README、.gitignore、结构说明、运行说明、已知问题说明。",
                "- 当前尚未执行 git init 和首次提交，这一步建议等目录方案确认后再做。",
                "",
                "## 当前目录最乱的地方",
                "- 运行产物容易堆积：数据库、文件库、PDF、解析快照会持续增长。",
                "- 外发导出文档与长期维护文档容易混层。",
                "- 上级工作目录还有一份完整复制包，容易误当主工程。",
                "",
                "## 本次整理动作",
                "- 将生成型审查文档统一移动到 `exports/review_packages/`。",
                "- 为本地配置补充可提交模板 `config/local_settings.example.json`。",
                "- 用 `.gitignore` 明确排除数据库、原始资料、导出物、文件库和本地配置。",
                "- 新增维护文档，明确保留、归档、删除建议。",
                "",
                "## 建议保留",
                "- `app/`、`scripts/`、`docs/`、`tests/`、`deploy/`、`run.py`、`requirements.txt`。",
                "- `config/local_settings.example.json` 作为配置模板保留进仓库。",
                "",
                "## 建议归档",
                "- `archive/legacy_docs/`",
                "- `archive/duplicates/`",
                "- `docs/review/` 中的历史审查材料",
                "- `exports/review_packages/` 中的导出审查包",
                "",
                "## 建议本地保留但不要提交 Git",
                "- `data/` 下的数据库、原始底稿、核验报告、解析快照",
                "- `storage/` 下的文件库、缓存、上传、日志",
                "- `exports/pdf/` 和 `exports/reports/`",
                "",
                "## 下一步建议",
                "1. 先确认这轮仓库化整理方案。",
                "2. 再执行 `git init`。",
                "3. 再做第一次干净提交。",
                "4. 然后进入下一轮功能开发。",
            ]
        ),
        encoding="utf-8",
    )
    return output_path


def write_change_log(tree_block: str) -> Path:
    output_path = EXPORT_DIR / f"CN_情报浏览系统_修改说明_{DATE_TAG}.md"
    output_path.write_text(
        "\n".join(
            [
                "# 情报浏览系统 修改说明",
                "",
                "## 项目目录树",
                tree_block,
                "",
                "## 本次仓库层修改",
                "- 补充 `.gitignore`，建立 Git 提交边界。",
                "- 新增 `config/local_settings.example.json`，替代真实本地配置直接进仓库。",
                "- 新增维护文档：结构说明、运行说明、已知问题、仓库整理说明。",
                "- 将导出型审查文档统一移到 `exports/review_packages/`。",
                "- 重写 `README.md` 为 GitHub 接手友好的主入口文档。",
                "",
                "## 这次没有做的事",
                "- 没有引入外部 GitHub repo 代码。",
                "- 没有做云部署。",
                "- 没有改业务逻辑主链路。",
                "- 没有粗暴删除原始资料。",
            ]
        ),
        encoding="utf-8",
    )
    return output_path


def write_migration_digest(tree_block: str) -> Path:
    output_path = EXPORT_DIR / f"CN_情报浏览系统_迁移与重建报告_{DATE_TAG}.md"
    output_path.write_text(
        "\n".join(
            [
                "# 情报浏览系统 迁移与重建报告",
                "",
                "## 项目目录树",
                tree_block,
                "",
                "## 说明",
                "- 这份文档是迁移 / 重建材料的中文入口。",
                "- 详细报告继续看 `exports/reports/` 下的文件。",
                "",
                "## 推荐继续查看",
                "- `exports/reports/MIGRATION_REPORT.md`",
                "- `exports/reports/SOURCE_INDEX.md`",
                "- `exports/reports/EVIDENCE_MAP.md`",
                "- `exports/reports/REBUILD_DECISIONS.md`",
                "- `exports/reports/SYSTEM_STATUS_CHECK.md`",
            ]
        ),
        encoding="utf-8",
    )
    return output_path


def write_code_bundle(tree_block: str) -> Path:
    output_path = EXPORT_DIR / f"CN_情报浏览系统_代码汇总_{DATE_TAG}.md"
    sections = [
        "# 情报浏览系统 代码汇总",
        "",
        "## 项目目录树",
        tree_block,
        "",
        "## 关键文件清单",
        *[f"- `{path}`" for path in KEY_FILES],
        "",
    ]
    for relative_path in KEY_FILES:
        sections.append(render_file_section(relative_path))
        sections.append("")
    output_path.write_text("\n".join(sections), encoding="utf-8")
    return output_path


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    tree_block = "```text\n沉香行业情报浏览系统_1.0\n" + "\n".join(build_tree(PROJECT_ROOT, max_depth=3)) + "\n```"
    outputs = [
        write_project_summary(tree_block),
        write_change_log(tree_block),
        write_migration_digest(tree_block),
        write_code_bundle(tree_block),
    ]
    for item in outputs:
        print(item)


if __name__ == "__main__":
    main()
