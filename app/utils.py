import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import markdown


INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
DATE_PATTERNS = [
    re.compile(r"(?P<year>20\d{2})[._-](?P<month>\d{1,2})[._-](?P<day>\d{1,2})"),
    re.compile(r"(?P<year>20\d{2})(?P<month>\d{2})(?P<day>\d{2})"),
    re.compile(r"(?P<year>20\d{2})年(?P<month>\d{1,2})月(?P<day>\d{1,2})日?"),
]
SHORT_DATE_PATTERNS = [
    re.compile(r"(?<!\d)(?P<month>\d{1,2})[._-](?P<day>\d{1,2})(?!\d)"),
    re.compile(r"(?P<month>\d{1,2})月(?P<day>\d{1,2})日?"),
]


def now_local() -> datetime:
    return datetime.now()


def now_string() -> str:
    return now_local().strftime("%Y-%m-%d %H:%M:%S")


def today_string() -> str:
    return now_local().strftime("%Y-%m-%d")


def safe_filename(filename: str) -> str:
    sanitized = INVALID_FILE_CHARS.sub("_", filename).strip().replace(" ", "_")
    return sanitized or "upload_file"


def detect_date_from_filename(filename: str) -> str | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(filename)
        if not match:
            continue
        try:
            parsed = datetime(
                int(match.group("year")),
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            continue
        return parsed.strftime("%Y-%m-%d")
    current_year = now_local().year
    for pattern in SHORT_DATE_PATTERNS:
        match = pattern.search(filename)
        if not match:
            continue
        try:
            parsed = datetime(
                current_year,
                int(match.group("month")),
                int(match.group("day")),
            )
        except ValueError:
            continue
        return parsed.strftime("%Y-%m-%d")
    return None


def sha256_file(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def normalize_heading(text: str) -> str:
    normalized = re.sub(r"^[#>*\-\s]+", "", text.strip())
    normalized = re.sub(r"^第?[（(]?[一二三四五六七八九十0-9]+[）).、．\s-]*", "", normalized)
    normalized = normalized.replace("：", "").replace(":", "")
    normalized = re.sub(r"\s+", "", normalized)
    normalized = re.sub(r"[^\w\u4e00-\u9fff]", "", normalized)
    return normalized.lower()


def normalize_compare_text(text: str) -> str:
    lowered = text.strip().lower()
    lowered = re.sub(r"\s+", "", lowered)
    lowered = re.sub(r"[^\w\u4e00-\u9fff]", "", lowered)
    return lowered


def markdown_to_html(text: str) -> str:
    if not text.strip():
        return ""
    escaped = html.escape(text)
    return markdown.markdown(
        escaped,
        extensions=["extra", "nl2br", "sane_lists"],
        output_format="html5",
    )


def compact_text(text: str) -> str:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def build_excerpt(text: str, limit: int = 88) -> str:
    cleaned = re.sub(r"\s+", " ", text.strip())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def dump_json(data: Any, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def load_json(text: str | None, default: Any) -> Any:
    if not text:
        return default
    try:
        return json.loads(text)
    except (TypeError, json.JSONDecodeError):
        return default
