from __future__ import annotations

import subprocess
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATE_TAG = datetime.now().strftime("%Y%m%d")
EXPORT_DIR = PROJECT_ROOT / "exports" / "review_packages"
OUTPUT_PATH = EXPORT_DIR / f"CN_闻脉台_最新完整代码审阅文稿_{DATE_TAG}.md"

IGNORED_TREE_NAMES = {".git", "__pycache__", ".pytest_cache"}
GROUPS: list[tuple[str, list[str]]] = [
    ("项目入口与配置", ["run.py", "requirements.txt", "README.md", "config/local_settings.example.json"]),
    ("核心 Python 代码", sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "app").glob("*.py"))),
    ("模板文件", sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "app" / "templates").glob("*.html"))),
    (
        "样式与脚本文件",
        sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "app" / "static" / "css").glob("*.css"))
        + sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "app" / "static" / "js").glob("*.js")),
    ),
    ("维护脚本", sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "scripts").glob("*.py"))),
    ("测试文件", sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "tests").glob("*.py"))),
    (
        "说明文档",
        ["docs/RUN_GUIDE.md"]
        + sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "docs").glob("CN_闻脉台_*.md"))
        + sorted(str(path.relative_to(PROJECT_ROOT)) for path in (PROJECT_ROOT / "docs" / "specs").glob("*.md")),
    ),
]


def build_tree(root: Path, max_depth: int = 3, prefix: str = "") -> list[str]:
    children = sorted(
        [item for item in root.iterdir() if item.name not in IGNORED_TREE_NAMES],
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


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


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
        f"```{language}\n{read_text(path)}\n```\n"
    )


def build_review_document() -> str:
    branch, commit, status_lines = get_git_state()
    root_tree = "```text\n沉香行业情报浏览系统_1.0\n" + "\n".join(build_tree(PROJECT_ROOT, max_depth=3)) + "\n```"

    sections: list[str] = [
        "# 闻脉台 最新完整代码审阅文稿",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 项目目录树",
        root_tree,
        "",
        "## 当前状态说明",
        f"- 当前分支：`{branch}`",
        f"- 当前提交：`{commit}`",
        f"- 是否存在未提交改动：`{'是' if status_lines else '否'}`",
        "- 当前主程序目录保持为 `app/`、`config/`、`docs/`、`deploy/`、`scripts/`、`tests/`、`data/`、`storage/`、`exports/` 等长期维护结构。",
        "- 当前首页已进入前台收尾阶段，本轮聚焦欢迎 Hero 排版、主内容区冗余品牌条删除、主副标题层级修正、左侧导航滚动同步、局部布局收口。",
        "",
        "## 本轮改动摘要",
        "- 欢迎 Hero 主标题拆成“欢迎回来”与 `display_name` 两个语义块，姓名整体不再被拆散换行。",
        "- 副标题提升为第二视觉层，字号、颜色、行高和与主标题间距按收尾要求收紧。",
        "- 首页主内容区顶部品牌条不再渲染，品牌感保留在侧栏品牌区和页面整体标题体系。",
        "- 首页主入口增加滚动同步 scrollspy，覆盖 `今日重点 / 今日新增 / 近期变化 / 历史归档` 四个主区块。",
        "- 首页布局改为条件式收口：`今日重点` 保持双栏，`今日新增 / 近期变化 / 历史归档` 使用单栏或紧凑单栏。",
        "",
        "## Git 工作区改动",
        render_list_block(status_lines) if status_lines else "- 工作区干净",
        "",
    ]

    for group_title, files in GROUPS:
        existing_files = []
        for relative_path in files:
            if relative_path not in existing_files:
                existing_files.append(relative_path)

        sections.extend(
            [
                f"## {group_title}",
                render_list_block(existing_files),
                "",
            ]
        )
        for relative_path in existing_files:
            sections.append(render_file_section(relative_path))
            sections.append("")

    return "\n".join(sections).rstrip() + "\n"


def main() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_review_document(), encoding="utf-8")
    print(OUTPUT_PATH)


if __name__ == "__main__":
    main()
