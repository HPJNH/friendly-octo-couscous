from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATE_TAG = datetime.now().strftime("%Y%m%d")
EXPORT_DIR = PROJECT_ROOT / "exports" / "review_packages"
OUTPUT_PATH = EXPORT_DIR / f"CN_闻脉台_当前完整代码审阅包_{DATE_TAG}.md"

TREE_IGNORED_NAMES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
}

TREE_SUMMARY_ONLY_NAMES = {
    "archive",
    "data",
    "exports",
    "storage",
}


def run_git_command(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def get_git_state() -> tuple[str, str, list[str]]:
    branch = run_git_command("branch", "--show-current") or "(unknown)"
    commit = run_git_command("rev-parse", "HEAD") or "(unknown)"
    status_output = run_git_command("status", "--short")
    status_lines = [line for line in status_output.splitlines() if line.strip()]
    return branch, commit, status_lines


def safe_read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def list_files(pattern_root: Path, glob_pattern: str) -> list[str]:
    return sorted(str(path.relative_to(PROJECT_ROOT)) for path in pattern_root.glob(glob_pattern))


def build_tree(root: Path, max_depth: int = 3, prefix: str = "") -> list[str]:
    children = sorted(
        [item for item in root.iterdir() if item.name not in TREE_IGNORED_NAMES],
        key=lambda item: (item.is_file(), item.name.lower()),
    )
    lines: list[str] = []
    for index, child in enumerate(children):
        connector = "└── " if index == len(children) - 1 else "├── "
        lines.append(f"{prefix}{connector}{child.name}")
        if child.is_dir() and max_depth > 0:
            if child.name in TREE_SUMMARY_ONLY_NAMES:
                continue
            extension = "    " if index == len(children) - 1 else "│   "
            lines.extend(build_tree(child, max_depth - 1, prefix + extension))
    return lines


def render_list_block(items: list[str]) -> str:
    return "\n".join(f"- `{item}`" for item in items)


def render_file_section(relative_path: str) -> str:
    path = PROJECT_ROOT / relative_path
    if not path.exists():
        return (
            f"### `{relative_path}`\n"
            f"绝对路径：`{path}`\n\n"
            "```text\n文件不存在\n```\n"
        )

    language = path.suffix.lstrip(".") or "text"
    return (
        f"### `{relative_path}`\n"
        f"绝对路径：`{path}`\n\n"
        f"```{language}\n{safe_read_text(path)}\n```\n"
    )


def build_groups() -> list[tuple[str, list[str]]]:
    docs_dir = PROJECT_ROOT / "docs"
    deploy_dir = PROJECT_ROOT / "deploy"

    docs_files = []
    for relative_path in ["docs/RUN_GUIDE.md"]:
        if (PROJECT_ROOT / relative_path).exists():
            docs_files.append(relative_path)
    docs_files += list_files(docs_dir, "CN_闻脉台*.md")
    docs_files += list_files(docs_dir / "specs", "*.md")

    deploy_files = list_files(deploy_dir, "*.md")

    groups: list[tuple[str, list[str]]] = [
        (
            "关键入口与配置模板",
            [
                "run.py",
                "wsgi.py",
                "requirements.txt",
                "README.md",
                "config/local_settings.example.json",
            ],
        ),
        ("应用主代码（app）", list_files(PROJECT_ROOT / "app", "*.py")),
        ("前台模板（templates）", list_files(PROJECT_ROOT / "app" / "templates", "*.html")),
        (
            "前端样式与脚本（static）",
            list_files(PROJECT_ROOT / "app" / "static" / "css", "*.css")
            + list_files(PROJECT_ROOT / "app" / "static" / "js", "*.js"),
        ),
        ("维护脚本（scripts）", list_files(PROJECT_ROOT / "scripts", "*.py")),
        ("测试文件（tests）", list_files(PROJECT_ROOT / "tests", "*.py")),
        ("部署与说明文档（deploy）", deploy_files),
        ("运行与规范文档（docs）", docs_files),
    ]

    normalized_groups: list[tuple[str, list[str]]] = []
    for title, files in groups:
        deduped: list[str] = []
        for relative_path in files:
            if relative_path not in deduped:
                deduped.append(relative_path)
        normalized_groups.append((title, deduped))
    return normalized_groups


def build_status_summary(branch: str, commit: str, status_lines: list[str]) -> str:
    status_block = render_list_block(status_lines) if status_lines else "- 工作区干净"
    root_tree = "```text\n沉香行业情报浏览系统_1.0\n" + "\n".join(build_tree(PROJECT_ROOT, max_depth=3)) + "\n```"
    sections = [
        "# 闻脉台当前完整代码审阅包",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 给深度审阅的阅读提示",
        "- 当前最值得重点看的是：`app/services.py`、`app/rebuild_engine.py`、`app/routes.py`、`app/security.py`、`app/admin_auth.py`、`app/db.py`。",
        "- 当前项目已经完成恢复运行态和一次受控 rebuild 单独验证，主仓库不再是空壳状态。",
        "- 当前最值得继续质检的是：rebuild 长期稳定性、单实例部署边界、proxy / next / runtime 安全边界、前端局部维护债务。",
        "- 不必重复大规模研究 parser 总路线、八大赛道方案、豆包提示词总框架，这些阶段此前已经收口。",
        "",
        "## 1. 当前项目状态摘要",
        "- 当前阶段：恢复主仓库运行态后，已完成单独 rebuild 验证，处于部署前最后准备阶段。",
        "- 当前主仓库状态：已从空壳状态恢复为可信运行态。",
        "- 当前 rebuild 验证结论：关键计数未归零、未翻倍、首页 / viewer / admin / upload 全部可用。",
        "- 当前不建议立即部署或 push；更适合继续做部署前准备核对。",
        "",
        "## 2. 当前项目目录树",
        root_tree,
        "",
        "## 3. 当前 Git 状态",
        f"- 当前分支：`{branch}`",
        f"- 当前提交：`{commit}`",
        f"- 是否存在未提交改动：`{'是' if status_lines else '否'}`",
        status_block,
        "",
        "## 4. 当前结构说明",
        "- 技术栈：Python、Flask、Jinja 模板、SQLite、WSGI 单实例入口。",
        "- 运行方式：本地入口为 `run.py`，服务器入口为 `wsgi.py`，推荐单实例运行 `wsgi:app`。",
        "- 数据方式：默认仍为 SQLite，当前明确只支持单实例，不支持多实例横向扩展。",
        "- runtime 结构：配置依赖 `APP_RUNTIME_ROOT / DATA_ROOT / STORAGE_ROOT / EXPORTS_ROOT / ARCHIVE_ROOT / LOG_ROOT`。",
        "- 关键模块：`build_safe_next / proxy / runtime` 边界主要落在 `app/routes.py`、`app/security.py`、`app/url_runtime.py`。",
        "- 标记与 rebuild 稳定性主要落在 `app/mark_service.py`、`app/db.py`、`app/rebuild_engine.py`。",
        "",
        "## 5. 当前已知问题与剩余风险",
        "- `style.css / collaboration.css` 仍存在重复覆盖和局部耦合，但不构成当前阻塞。",
        "- `services.py / rebuild_engine.py` 仍偏重，属于结构性维护债，不适合在本轮导出时重构。",
        "- 当前仍是 SQLite + 单实例边界，不能直接视为多实例生产架构。",
        "- scrollspy 和移动端首页还值得继续做真机人工回放，但当前不影响本次代码审阅导出。",
        "",
    ]
    return "\n".join(sections)


def build_review_document() -> str:
    branch, commit, status_lines = get_git_state()
    sections = [build_status_summary(branch, commit, status_lines)]

    for group_title, files in build_groups():
        sections.extend(
            [
                f"## {group_title}",
                render_list_block(files),
                "",
            ]
        )
        for relative_path in files:
            sections.append(render_file_section(relative_path))
            sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_review_document(), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
