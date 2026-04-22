from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import zipfile
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path

from flask import current_app

from .cache_service import get_or_build_cached_read_view
from .constants import (
    BRIEF_EXPORT_ENABLED,
    BRIEF_UI_ENABLED,
    DOCUMENT_TYPE_LABELS,
    DRAFT_TAIL_PATTERNS,
    FEATURED_SECTION_KEYS,
    FILE_STATUS_CLASS_MAP,
    FILE_STATUS_LABELS,
    FRONTEND_READING_CATEGORIES,
    FRONTEND_SECONDARY_LABELS,
    FRONTEND_SECTION_DISPLAY,
    FRONTEND_STATUS_CLASS_MAP,
    FRONTEND_STATUS_LABELS,
    FRONTEND_STATUS_ORDER,
    PARSER_VERSION,
    READING_TRACKS_V1,
    REPORT_NOTE_DISPLAY_LABELS,
    SECTION_DEFINITIONS,
    SECTION_KEY_ALIASES,
    SECTION_MAP,
    SECTION_ORDER,
    SECTION_SUBCATEGORY_RULES,
    SOFT_HIDDEN_SECTION_KEYS,
    STATUS_CLASS_MAP,
    TRACK_DISPLAY_MAP,
    TRACK_SUBTRACK_RULES,
    VISIBLE_SECTION_DEFINITIONS,
    VISIBLE_SECTION_MAP,
    VISIBLE_SECTION_ORDER,
    WORKBENCH_SHORTCUT_DEFINITIONS,
)
from .db import get_connection
from .mark_service import apply_mark_summaries_to_cards, fetch_entry_mark_summaries
from .parsers import (
    UnsupportedFileError,
    build_draft_metadata,
    build_sections_from_blocks,
    detect_document_type,
    extract_brief_title,
    extract_text,
    parse_brief_file,
    parse_draft_file,
    text_to_blocks,
    validate_draft_contract,
)
from .pdf_export import export_pdf
from .rebuild_engine import (
    build_repaired_section_history,
    build_repaired_section_views,
    rebuild_repaired_entries,
)
from .rendering import (
    build_brief_html,
    build_section_render_payload,
    extract_cards_from_render_payload,
    normalize_render_payload,
)
from .security import ensure_path_within_roots
from .utils import (
    build_excerpt,
    compact_text,
    detect_date_from_filename,
    dump_json,
    load_json,
    normalize_compare_text,
    now_local,
    now_string,
    safe_filename,
    sha256_file,
    today_string,
)


FILE_LIBRARY_FOLDER_MAP = {
    "draft": "drafts",
    "brief": "briefs",
    "export": "exports",
}

ITEM_STATUS_ORDER = ["新增", "更新", "背景补充", "历史保留", "占位项", "无内容"]


HEADING_PREFIX_PATTERN = re.compile(r"^\s*(\d+)\.(\d+)\s*[、.\-]?\s*")
NUMBER_PREFIX_PATTERN = re.compile(r"^\s*[\dA-Za-z一二三四五六七八九十]+(?:\.[\dA-Za-z]+)*\s*[、.．)\-]?\s*")


@dataclass
class ProcessingResult:
    success: bool
    original_name: str
    saved_name: str | None = None
    report_date: str | None = None
    document_type: str = "unknown"
    document_type_label: str = "未识别"
    recognition_note: str = ""
    message: str = ""
    is_new_day: bool = False
    wrote_history: bool = False
    updated_current_version: bool = False
    stored_path: str | None = None
    parsed_path: str | None = None
    day_url: str | None = None
    validation_errors: list[str] = field(default_factory=list)
    validation_warnings: list[str] = field(default_factory=list)
    parse_report_lines: list[str] = field(default_factory=list)


def get_visible_section_rows(section_map: dict[str, dict]) -> list[dict]:
    return [section_map[key] for key in VISIBLE_SECTION_ORDER if key in section_map]


def get_reading_track_meta(track_key: str) -> dict:
    if track_key == "reading_note":
        return {
            "key": "reading_note",
            "title": "阅读说明",
            "description": "用于理解当前版本的阅读边界、口径与说明。",
            "section_keys": ["report_note"],
        }
    for track in READING_TRACKS_V1:
        if track["key"] == track_key:
            return track
    return {
        "key": track_key,
        "title": track_key,
        "description": "",
        "section_keys": [],
    }


def get_frontend_section_meta(section_key: str) -> dict:
    if section_key in FRONTEND_SECTION_DISPLAY:
        meta = FRONTEND_SECTION_DISPLAY[section_key]
        return {
            **meta,
            "track_key": meta["category_key"],
            "track_title": meta["category_title"],
        }
    title = SECTION_MAP.get(section_key, {}).get("title", section_key)
    return {
        "category_key": section_key,
        "category_title": title,
        "section_title": title,
        "view_label": "",
        "nav_title": title,
        "track_key": section_key,
        "track_title": title,
    }


def get_display_status_payload(status: str, *, needs_review: bool = False) -> dict:
    if needs_review:
        return {
            "label": "待复核",
            "class": FRONTEND_STATUS_CLASS_MAP["待复核"],
            "filter_value": "待复核",
        }
    label = FRONTEND_STATUS_LABELS.get(status, status)
    return {
        "label": label,
        "class": FRONTEND_STATUS_CLASS_MAP.get(label, STATUS_CLASS_MAP.get(status, "")),
        "filter_value": label,
    }


def translate_status_counts(status_counts: dict[str, int] | None, review_count: int = 0) -> dict[str, int]:
    translated = {label: 0 for label in FRONTEND_STATUS_ORDER}
    for status, count in (status_counts or {}).items():
        label = FRONTEND_STATUS_LABELS.get(status)
        if not label or not count:
            continue
        translated[label] += count
    if review_count:
        translated["待复核"] += review_count
    return translated


def build_status_pills(status_counts: dict[str, int]) -> list[dict]:
    pills = []
    for label in FRONTEND_STATUS_ORDER:
        count = status_counts.get(label, 0)
        if not count:
            continue
        pills.append({"label": label, "count": count, "class": FRONTEND_STATUS_CLASS_MAP.get(label, "")})
    return pills


def strip_display_prefix(text: str) -> str:
    return NUMBER_PREFIX_PATTERN.sub("", (text or "").strip()).strip()


def _normalize_track_tokens(values) -> list[str]:
    if not values:
        return []
    if isinstance(values, str):
        values = re.split(r"[、,，/｜|；;\n\r]+", values)
    normalized = []
    for value in values:
        text = normalize_compare_text(str(value))
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def resolve_track_subcategory(track_key: str, title: str = "", tags=None) -> dict[str, str]:
    rules = TRACK_SUBTRACK_RULES.get(track_key, [])
    if not rules:
        return {"key": "", "label": ""}

    normalized_tags = set(_normalize_track_tokens(tags))
    if normalized_tags:
        for rule in rules:
            rule_tokens = set(_normalize_track_tokens(rule.get("tag_keys", [])))
            if rule_tokens & normalized_tags:
                return {"key": rule["key"], "label": rule["display_label"]}

    normalized_title = normalize_compare_text(title or "")
    if normalized_title:
        for rule in rules:
            keywords = _normalize_track_tokens(rule.get("keywords", []))
            if any(keyword and keyword in normalized_title for keyword in keywords):
                return {"key": rule["key"], "label": rule["display_label"]}

    return {"key": "", "label": ""}


def resolve_section_subcategory(section_key: str, title: str, tags=None) -> str:
    track_key = get_frontend_section_meta(section_key)["track_key"]
    return resolve_track_subcategory(track_key, title=title, tags=tags)["label"]


def extract_card_business_tags(card: dict) -> list[str]:
    compare_meta = card.get("compare_meta") or {}
    raw_values = []
    for key in ("business_tags", "track_tags"):
        value = card.get(key)
        if value:
            raw_values.extend(value if isinstance(value, list) else [value])
        compare_value = compare_meta.get(key)
        if compare_value:
            raw_values.extend(compare_value if isinstance(compare_value, list) else [compare_value])
    return _normalize_track_tokens(raw_values)


def extract_group_business_tags(group: dict) -> list[str]:
    raw_values = []
    for block in group.get("blocks", []):
        if block.get("type") == "card" and block.get("card"):
            raw_values.extend(extract_card_business_tags(block["card"]))
        elif block.get("type") == "table":
            for card in block.get("cards", []):
                raw_values.extend(extract_card_business_tags(card))
    return _normalize_track_tokens(raw_values)


def translate_group_heading(section_key: str, title: str | None) -> str:
    if not title:
        return ""
    stripped = (title or "").strip()
    if not stripped:
        return ""
    if section_key == "report_note":
        for prefix, display in REPORT_NOTE_DISPLAY_LABELS.items():
            if stripped.startswith(prefix):
                return display
        return strip_display_prefix(stripped)

    match = HEADING_PREFIX_PATTERN.match(stripped)
    if match:
        subsection_label = FRONTEND_SECONDARY_LABELS.get(match.group(2))
        if subsection_label:
            return subsection_label

    subcategory_label = resolve_section_subcategory(section_key, stripped)
    if subcategory_label:
        return subcategory_label

    if get_frontend_section_meta(section_key)["track_key"] in TRACK_SUBTRACK_RULES:
        return ""

    return strip_display_prefix(stripped)


def build_sidebar_primary_links(nav_date: str | None) -> list[dict]:
    dashboard_link = f"/day/{nav_date}" if nav_date else "/"
    return [
        {"key": "today_focus", "title": "今日重点", "href": f"{dashboard_link}#today-focus"},
        {"key": "today_new", "title": "今日新增", "href": f"{dashboard_link}#today-new"},
        {"key": "recent_changes", "title": "近期变化", "href": f"{dashboard_link}#recent-versions"},
        {"key": "history_archive", "title": "历史归档", "href": "/history"},
    ]


def build_sidebar_reading_links(nav_date: str | None) -> list[dict]:
    dashboard_link = f"/day/{nav_date}" if nav_date else "/"
    links = []
    for category in READING_TRACKS_V1:
        links.append(
            {
                "key": category["key"],
                "title": category["title"],
                "description": category["description"],
                "href": f"{dashboard_link}#reading-category-{category['key']}",
            }
        )
    return links


def translate_frontend_copy(text: str | None) -> str:
    if not text:
        return ""
    translated = str(text)
    replacements = (
        ("补采窗口", "本期新增"),
        ("背景补充", "延伸背景"),
        ("历史保留", "历史延续"),
        ("占位项", "本期无新增"),
        ("无内容", "本期无新增"),
        ("待人工复核", "待复核"),
        ("当前状态说明", "板块判断"),
        ("报告说明", "阅读说明"),
        ("方法说明", "阅读说明"),
        ("采集说明", "阅读说明"),
    )
    for source, target in replacements:
        translated = translated.replace(source, target)
    return translated


def build_workbench_shortcuts(report_date: str) -> list[dict]:
    shortcuts = []
    base_href = f"/day/{report_date}"
    for item in WORKBENCH_SHORTCUT_DEFINITIONS:
        if item["key"] == "history_archive":
            url = "/history"
        else:
            url = f"{base_href}#{item['anchor']}"
        shortcuts.append(
            {
                "key": item["key"],
                "title": item["title"],
                "description": item["description"],
                "href": url,
            }
        )
    return shortcuts


def _section_priority_tuple(section: dict) -> tuple:
    return (
        1 if section.get("manual_mark_count") else 0,
        section.get("manual_mark_count", 0),
        1 if section.get("display_content") else 0,
        1 if section.get("review_count") else 0,
        1 if section.get("new_count") else 0,
        1 if section.get("updated_count") else 0,
        1 if section.get("key") in FEATURED_SECTION_KEYS else 0,
        section.get("new_count", 0),
        section.get("updated_count", 0),
        -section.get("number", 99),
    )


def build_today_focus_sections(sections: list[dict]) -> list[dict]:
    candidates = [
        section
        for section in sections
        if section.get("display_content")
        and (
            section.get("manual_mark_count")
            or section.get("latest_mark_at")
            or section.get("new_count")
            or section.get("updated_count")
            or section.get("review_count")
            or section.get("key") in FEATURED_SECTION_KEYS
        )
    ]
    if not candidates:
        candidates = [section for section in sections if section.get("display_content")]
    if not candidates:
        candidates = list(sections)
    return sorted(candidates, key=_section_priority_tuple, reverse=True)[:4]


def build_today_new_sections(sections: list[dict]) -> list[dict]:
    candidates = [
        section
        for section in sections
        if section.get("display_content")
        and (
            section.get("new_count")
            or section.get("updated_count")
            or section.get("review_count")
        )
    ]
    return sorted(candidates, key=_section_priority_tuple, reverse=True)


def build_filter_options(display_status_counts: dict[str, int]) -> list[dict]:
    return [
        {"label": label, "count": display_status_counts.get(label, 0)}
        for label in FRONTEND_STATUS_ORDER
    ]


def collect_render_model_cards(render_model: dict) -> list[dict]:
    cards: list[dict] = []
    for group in render_model.get("groups", []):
        for block in group.get("blocks", []):
            if block.get("type") == "card" and block.get("card"):
                cards.append(block["card"])
            elif block.get("type") == "table" and block.get("cards"):
                cards.extend([card for card in block.get("cards", []) if card])
    return cards


def apply_section_preview_marks(
    sections: list[dict],
    *,
    viewer_identity_id: int | None = None,
    viewer_role: str = "guest",
) -> dict[int, dict]:
    entry_ids = []
    for section in sections:
        entry_ids.extend(section.get("entry_ids") or [])

    summaries = fetch_entry_mark_summaries(
        entry_ids,
        viewer_identity_id=viewer_identity_id,
        viewer_role=viewer_role,
    )
    empty_summary = {
        "has_marks": False,
        "count": 0,
        "items": [],
        "highlight_note": "",
        "latest_mark_at": "",
        "latest_marker_label": "",
        "viewer_can_mark": bool(viewer_identity_id),
        "viewer_mark": None,
    }

    for section in sections:
        preview_summaries = []
        for preview in section.get("preview_cards", []):
            summary = summaries.get(preview.get("entry_id")) or dict(empty_summary)
            preview["mark_summary"] = summary
            preview["has_manual_marks"] = summary["has_marks"]
            if summary["has_marks"]:
                preview_summaries.append(summary)

        preview_summaries.sort(
            key=lambda item: (
                item.get("latest_mark_at") or "",
                item.get("count", 0),
            ),
            reverse=True,
        )
        top_summary = preview_summaries[0] if preview_summaries else None
        section["manual_mark_count"] = sum(item.get("count", 0) for item in preview_summaries)
        section["has_manual_marks"] = bool(top_summary)
        section["manual_mark_note"] = top_summary.get("highlight_note", "") if top_summary else ""
        section["latest_mark_at"] = top_summary.get("latest_mark_at", "") if top_summary else ""
        section["latest_marker_label"] = top_summary.get("latest_marker_label", "") if top_summary else ""
    return summaries


def apply_detail_marks(
    render_model: dict,
    *,
    viewer_identity_id: int | None = None,
    viewer_role: str = "guest",
) -> dict[int, dict]:
    cards = collect_render_model_cards(render_model)
    return apply_mark_summaries_to_cards(
        cards,
        viewer_identity_id=viewer_identity_id,
        viewer_role=viewer_role,
    )


def translate_card_for_frontend(section_key: str, card: dict, fallback_status: str) -> dict:
    translated = deepcopy(card)
    section_meta = get_frontend_section_meta(section_key)
    internal_status = translated.get("status") or fallback_status
    status_payload = get_display_status_payload(
        internal_status,
        needs_review=bool(translated.get("needs_review")),
    )
    subcategory_payload = resolve_track_subcategory(
        section_meta["track_key"],
        title=translated.get("title") or translated.get("source_title") or "",
        tags=extract_card_business_tags(translated),
    )
    translated["internal_status"] = internal_status
    translated["status"] = status_payload["label"]
    translated["status_class"] = status_payload["class"]
    translated["filter_value"] = status_payload["filter_value"]
    translated["source_title"] = translated.get("source_title") or translated.get("title") or "未命名来源"
    translated["track_key"] = section_meta["track_key"]
    translated["track_title"] = section_meta["track_title"]
    translated["subcategory_key"] = subcategory_payload["key"]
    translated["display_category"] = subcategory_payload["label"]
    translated["group_title_display"] = translate_group_heading(section_key, translated.get("group_title"))
    translated["why"] = translate_frontend_copy(translated.get("why"))
    return translated


def build_frontend_render_model(section_key: str, render_model: dict, section_status: str) -> dict:
    frontend_model = deepcopy(render_model)
    groups = frontend_model.get("groups", [])
    review_count = 0

    for group in groups:
        raw_title = group.get("title") or ""
        raw_category = group.get("category") or ""
        group_tags = extract_group_business_tags(group)
        display_title = translate_group_heading(section_key, raw_title)
        display_category = resolve_section_subcategory(
            section_key,
            raw_category or raw_title,
            tags=group_tags,
        )
        if not display_category and raw_category and section_key not in SECTION_SUBCATEGORY_RULES:
            display_category = strip_display_prefix(raw_category)
        group["display_title"] = display_title
        group["display_category"] = display_category

        translated_blocks = []
        for block in group.get("blocks", []):
            translated_block = deepcopy(block)
            if translated_block.get("type") == "card" and translated_block.get("card"):
                translated_card = translate_card_for_frontend(section_key, translated_block["card"], section_status)
                translated_block["card"] = translated_card
                review_count += 1 if translated_card.get("needs_review") else 0
            elif translated_block.get("type") == "table" and translated_block.get("cards"):
                translated_cards = []
                for card in translated_block.get("cards", []):
                    translated_card = translate_card_for_frontend(section_key, card, section_status)
                    translated_cards.append(translated_card)
                    review_count += 1 if translated_card.get("needs_review") else 0
                translated_block["cards"] = translated_cards
            translated_blocks.append(translated_block)
        group["blocks"] = translated_blocks

    display_status_counts = translate_status_counts(frontend_model.get("status_counts"), review_count)
    frontend_model["display_status_counts"] = display_status_counts
    frontend_model["filter_options"] = build_filter_options(display_status_counts)
    return frontend_model


def group_sections_for_ui(section_map: dict[str, dict]) -> list[dict]:
    groups = []
    for group in READING_TRACKS_V1:
        items = [section_map[key] for key in group["section_keys"] if key in section_map]
        groups.append(
            {
                "key": group["key"],
                "title": group["title"],
                "description": group["description"],
                "anchor_id": f"reading-category-{group['key']}",
                "sections": items,
            }
        )
    return groups


def get_section_group_meta(section_key: str) -> dict:
    section_meta = get_frontend_section_meta(section_key)
    if section_meta["category_key"] == "reading_note":
        return get_reading_track_meta("reading_note")
    for group in READING_TRACKS_V1:
        if group["key"] == section_meta["category_key"]:
            return group
    return {"key": "hidden", "title": section_meta["category_title"], "description": "该板块当前仅保留历史回退能力。"}


def _looks_like_text(sample: bytes) -> bool:
    if not sample:
        return True
    if sample.startswith((b"\xff\xfe", b"\xfe\xff", b"\xef\xbb\xbf")):
        return True
    if b"\x00" in sample:
        return False
    for encoding in ("utf-8", "utf-8-sig", "gb18030"):
        try:
            sample.decode(encoding)
            return True
        except UnicodeDecodeError:
            continue
    return False


def validate_uploaded_file_signature(file_path: Path, extension: str) -> tuple[bool, str]:
    sample = file_path.read_bytes()[:4096]
    if extension == ".pdf":
        if sample.startswith(b"%PDF-"):
            return True, "application/pdf"
        return False, "该文件扩展名为 .pdf，但文件头不是有效的 PDF 签名。"

    if extension == ".docx":
        if not zipfile.is_zipfile(file_path):
            return False, "该文件扩展名为 .docx，但实际内容不是有效的 Office 文档压缩包。"
        try:
            with zipfile.ZipFile(file_path) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return False, "该文件扩展名为 .docx，但压缩结构已损坏，无法作为有效底稿读取。"
        if "[Content_Types].xml" in names and any(name.startswith("word/") for name in names):
            return True, "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        return False, "该文件扩展名为 .docx，但内部结构不符合 Word 文档格式。"

    if extension in {".md", ".txt"}:
        if _looks_like_text(sample):
            return True, "text/plain"
        return False, f"该文件扩展名为 {extension}，但内容更像二进制文件，无法按文本处理。"

    return False, "不支持的文件类型。"


def get_layout_context(selected_date: str | None = None) -> dict:
    latest_date = get_latest_report_date()
    nav_date = selected_date or latest_date
    debug_link = f"/debug/sections/{nav_date}" if nav_date else None
    export_link = f"/export/pdf/{nav_date}" if nav_date else None
    return {
        "latest_date": latest_date,
        "dashboard_link": f"/day/{nav_date}" if nav_date else "/",
        "sidebar_primary_links": build_sidebar_primary_links(nav_date),
        "sidebar_reading_links": build_sidebar_reading_links(nav_date),
        "reading_note_link": f"/section/{nav_date}/report_note" if nav_date else "/",
        "sidebar_section_groups": [],
        "nav_date": nav_date,
        "debug_link": debug_link,
        "export_link": export_link,
        "library_link": "/library",
    }


def build_read_content_version(
    connection: sqlite3.Connection,
    *,
    report_date: str | None = None,
    include_exports: bool = False,
) -> str:
    if report_date:
        document_params = (report_date,)
        entry_params = (report_date,)
        document_query = """
            SELECT GROUP_CONCAT(signature, '|') AS value
            FROM (
                SELECT id || ':' || report_date || ':' || doc_type || ':' || lifecycle_status || ':' || is_current || ':' || COALESCE(withdrawn_at, '') || ':' || uploaded_at AS signature
                FROM documents
                WHERE lifecycle_status != 'deleted'
                  AND report_date <= ?
                ORDER BY id
            )
        """
        entry_query = """
            SELECT COUNT(*) || ':' || COALESCE(MAX(updated_at), '0') AS value
            FROM entries
            WHERE is_current_chain = 1
              AND is_deleted = 0
              AND report_date <= ?
        """
    else:
        document_params = ()
        entry_params = ()
        document_query = """
            SELECT GROUP_CONCAT(signature, '|') AS value
            FROM (
                SELECT id || ':' || report_date || ':' || doc_type || ':' || lifecycle_status || ':' || is_current || ':' || COALESCE(withdrawn_at, '') || ':' || uploaded_at AS signature
                FROM documents
                WHERE lifecycle_status != 'deleted'
                ORDER BY id
            )
        """
        entry_query = """
            SELECT COUNT(*) || ':' || COALESCE(MAX(updated_at), '0') AS value
            FROM entries
            WHERE is_current_chain = 1
              AND is_deleted = 0
        """

    document_signature = _fetch_cache_signature(connection, document_query, document_params)
    entry_signature = _fetch_cache_signature(connection, entry_query, entry_params)
    rebuild_signature = _fetch_cache_signature(
        connection,
        """
        SELECT COUNT(*) || ':' || COALESCE(MAX(COALESCE(completed_at, started_at)), '0') AS value
        FROM rebuild_runs
        """,
    )
    export_signature = "exports:skip"
    if include_exports:
        export_signature = _fetch_cache_signature(
            connection,
            """
            SELECT GROUP_CONCAT(signature, '|') AS value
            FROM (
                SELECT id || ':' || report_date || ':' || status || ':' || file_name || ':' || created_at AS signature
                FROM export_files
                WHERE status != 'deleted'
                ORDER BY id
            )
            """,
        )

    raw_version = "|".join(
        [
            f"docs:{document_signature}",
            f"entries:{entry_signature}",
            f"rebuild:{rebuild_signature}",
            f"exports:{export_signature}",
        ]
    )
    return hashlib.sha1(raw_version.encode("utf-8")).hexdigest()[:20]


def _fetch_cache_signature(connection: sqlite3.Connection, query: str, params: tuple = ()) -> str:
    row = connection.execute(query, params).fetchone()
    if not row:
        return "0"
    value = row["value"]
    return value if value else "0"


def get_latest_report_date() -> str | None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            """
            SELECT MAX(report_date) AS report_date
            FROM documents
            WHERE is_current = 1
              AND lifecycle_status = 'active'
            """
        ).fetchone()
    return row["report_date"] if row and row["report_date"] else None


def get_latest_effective_date_by_type(doc_type: str) -> str | None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            """
            SELECT MAX(report_date) AS report_date
            FROM documents
            WHERE doc_type = ?
              AND is_current = 1
              AND lifecycle_status = 'active'
            """,
            (doc_type,),
        ).fetchone()
    return row["report_date"] if row and row["report_date"] else None


def process_uploaded_files(file_storages) -> list[ProcessingResult]:
    results = []
    for file_storage in file_storages:
        if not file_storage or not file_storage.filename:
            continue
        results.append(process_single_file(file_storage))
    return results


def process_single_file(file_storage) -> ProcessingResult:
    original_name = file_storage.filename or ""
    extension = Path(original_name).suffix.lower()
    if not extension:
        return ProcessingResult(success=False, original_name=original_name, message="文件缺少扩展名，系统无法处理。")
    if extension not in current_app.config["SUPPORTED_EXTENSIONS"]:
        return ProcessingResult(
            success=False,
            original_name=original_name,
            message=f"暂不支持 {extension} 文件，请改为 .docx / .md / .txt / .pdf 后重新上传。",
        )

    report_date = detect_date_from_filename(original_name) or today_string()
    timestamp = now_local().strftime("%Y%m%d-%H%M%S-%f")
    saved_name = f"{timestamp}_{safe_filename(original_name)}"

    temp_dir = current_app.config["TEMP_UPLOAD_ROOT"] / report_date
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_path = temp_dir / saved_name
    file_storage.save(temp_path)

    valid_signature, signature_result = validate_uploaded_file_signature(temp_path, extension)
    if not valid_signature:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return ProcessingResult(
            success=False,
            original_name=original_name,
            saved_name=saved_name,
            report_date=report_date,
            message=signature_result,
        )
    detected_mime = signature_result

    try:
        fallback_content = extract_text(temp_path)
    except UnsupportedFileError as error:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return ProcessingResult(
            success=False,
            original_name=original_name,
            saved_name=saved_name,
            report_date=report_date,
            message=str(error),
        )

    doc_type, recognition_note = detect_document_type(original_name, fallback_content)
    if doc_type == "unknown":
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        return ProcessingResult(
            success=False,
            original_name=original_name,
            saved_name=saved_name,
            report_date=report_date,
            document_type=doc_type,
            document_type_label=DOCUMENT_TYPE_LABELS[doc_type],
            recognition_note=recognition_note,
            message="系统未能识别文件属于研究底稿还是每日分析简报，请调整文件名后重新上传。",
        )

    validation_result = None
    parse_report_lines: list[str] = []
    validation_warnings: list[str] = []
    if doc_type == "draft":
        validation_result = validate_draft_contract(temp_path, fallback_content)
        validation_warnings = list(validation_result["warnings"])
        parse_report_lines = build_draft_parse_report_lines(validation_result["report"])
        if not validation_result["success"]:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
            return ProcessingResult(
                success=False,
                original_name=original_name,
                saved_name=saved_name,
                report_date=report_date,
                document_type=doc_type,
                document_type_label=DOCUMENT_TYPE_LABELS[doc_type],
                recognition_note=recognition_note,
                message="上传前结构验证未通过，请按底稿模板修正后重新上传。",
                stored_path=str(temp_path),
                validation_errors=validation_result["errors"],
                validation_warnings=validation_warnings,
                parse_report_lines=parse_report_lines + validation_result["details"],
            )

    final_path = build_library_path("active", doc_type, report_date, saved_name)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path.replace(final_path)

    parsed_document = parse_document(final_path, doc_type, fallback_content, report_date)
    parsed_document["document_metadata"]["detected_mime"] = detected_mime
    if validation_result:
        parsed_document["document_metadata"]["validation_report"] = validation_result["report"]
        parsed_document["document_metadata"]["validation_warnings"] = validation_warnings
    file_hash = sha256_file(final_path)
    uploaded_at = now_string()

    document_id = 0
    existing_rows = []
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        existing_rows = connection.execute(
            """
            SELECT *
            FROM documents
            WHERE report_date = ?
              AND doc_type = ?
              AND lifecycle_status = 'active'
              AND is_current = 1
            ORDER BY uploaded_at DESC
            """,
            (report_date, doc_type),
        ).fetchall()
        is_new_day = (
            connection.execute(
                """
                SELECT COUNT(1) AS count
                FROM documents
                WHERE report_date = ?
                  AND lifecycle_status = 'active'
                  AND is_current = 1
                """,
                (report_date,),
            ).fetchone()["count"]
            == 0
        )

        for row in existing_rows:
            set_document_status(connection, row, "archived", is_current=False)

        cursor = connection.execute(
            """
            INSERT INTO documents (
                report_date, doc_type, original_name, stored_name, stored_path, parsed_path,
                file_ext, uploaded_at, title, content, html_content, file_hash, metadata_json,
                lifecycle_status, withdrawn_at, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL, 1)
            """,
            (
                report_date,
                doc_type,
                original_name,
                saved_name,
                str(final_path),
                "",
                extension,
                uploaded_at,
                parsed_document["title"],
                parsed_document["content"],
                parsed_document["html_content"],
                file_hash,
                json.dumps(
                    {
                        **parsed_document["document_metadata"],
                        "recognition_note": recognition_note,
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        document_id = cursor.lastrowid

        section_records: list[dict] = []
        if doc_type == "draft":
            section_records = create_section_snapshots(connection, document_id, report_date, parsed_document["sections"])

        parsed_path = write_document_archive(
            connection,
            document_id=document_id,
            report_date=report_date,
            doc_type=doc_type,
            original_name=original_name,
            stored_path=final_path,
            title=parsed_document["title"],
            content=parsed_document["content"],
            recognition_note=recognition_note,
            sections=section_records,
            uploaded_at=uploaded_at,
            document_metadata=parsed_document["document_metadata"],
        )
        connection.commit()

    if doc_type == "draft":
        try:
            rebuild_effective_chain_from(report_date)
        except Exception as error:
            with get_connection(current_app.config["DATABASE_PATH"]) as connection:
                inserted_row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
                if inserted_row:
                    set_document_status(connection, inserted_row, "withdrawn", is_current=False)

                if existing_rows:
                    restore_row = connection.execute("SELECT * FROM documents WHERE id = ?", (existing_rows[0]["id"],)).fetchone()
                    if restore_row and restore_row["lifecycle_status"] != "deleted":
                        activate_document_row(connection, restore_row)
                        archive_same_day_siblings(connection, restore_row)
                connection.commit()

            return ProcessingResult(
                success=False,
                original_name=original_name,
                saved_name=saved_name,
                report_date=report_date,
                document_type=doc_type,
                document_type_label=DOCUMENT_TYPE_LABELS[doc_type],
                recognition_note=recognition_note,
                message=f"上传后重建失败，系统已回滚到上一个稳定版本：{error}",
                stored_path=str(final_path),
                parsed_path=str(parsed_path),
                validation_warnings=validation_warnings,
                parse_report_lines=parse_report_lines,
            )

    return ProcessingResult(
        success=True,
        original_name=original_name,
        saved_name=saved_name,
        report_date=report_date,
        document_type=doc_type,
        document_type_label=DOCUMENT_TYPE_LABELS[doc_type],
        recognition_note=recognition_note,
        message="上传成功，系统已写入文件库并刷新当前有效版本。",
        is_new_day=is_new_day,
        wrote_history=True,
        updated_current_version=bool(existing_rows),
        stored_path=str(final_path),
        parsed_path=str(parsed_path),
        day_url=f"/day/{report_date}",
        validation_warnings=validation_warnings,
        parse_report_lines=parse_report_lines,
    )


def parse_document(file_path: Path, doc_type: str, fallback_content: str, report_date: str) -> dict:
    if doc_type == "brief":
        brief_payload = parse_brief_from_source(file_path, fallback_content)
        title = extract_brief_title(brief_payload["content"], f"{report_date} 每日分析简报")
        return {
            "title": title,
            "content": brief_payload["content"],
            "html_content": build_brief_html(brief_payload["blocks"]),
            "sections": {},
            "document_metadata": {
                "parser_version": PARSER_VERSION,
                "doc_type": doc_type,
                "block_count": len(brief_payload["blocks"]),
                "tail_hits": brief_payload.get("tail_hits", []),
            },
        }

    draft_payload = parse_draft_from_source(file_path, fallback_content)
    draft_metadata = draft_payload.get("metadata") or {}
    return {
        "title": f"{report_date} 沉香行业情报研究底稿",
        "content": draft_payload["content"],
        "html_content": "",
        "sections": draft_payload["sections"],
        "document_metadata": {
            "parser_version": PARSER_VERSION,
            "doc_type": doc_type,
            "section_count": len(draft_payload["sections"]),
            "tail_hits": draft_payload.get("tail_hits", []),
            "contract_version": draft_metadata.get("contract_version", "unknown"),
            "window_metadata": draft_metadata.get("window_metadata", {}),
            "draft_metadata": draft_metadata,
        },
    }


def parse_draft_from_source(file_path: Path | None, fallback_content: str) -> dict:
    if file_path and file_path.exists():
        return parse_draft_file(file_path, fallback_content)
    blocks = text_to_blocks(fallback_content)
    sections = build_sections_from_blocks(blocks)
    return {
        "content": fallback_content,
        "sections": sections,
        "tail_hits": [],
        "metadata": build_draft_metadata(sections),
    }


def parse_brief_from_source(file_path: Path | None, fallback_content: str) -> dict:
    if file_path and file_path.exists():
        return parse_brief_file(file_path, fallback_content)
    blocks = text_to_blocks(fallback_content)
    return {"content": fallback_content, "blocks": blocks, "tail_hits": []}


def build_draft_parse_report_lines(report: dict) -> list[str]:
    lines = [
        f"识别到 {report.get('module_count', 0)} 个正式模块。",
        f"识别到 {report.get('table_count', 0)} 张表格。",
        f"识别到 {report.get('structured_item_count', 0)} 条结构化条目。",
    ]
    empty_sections = report.get("empty_sections") or []
    note_only_sections = report.get("note_only_sections") or []
    if empty_sections:
        lines.append(f"空模块：{' / '.join(empty_sections)}")
    if note_only_sections:
        lines.append(f"纯说明模块：{' / '.join(note_only_sections)}")
    if report.get("tail_detected"):
        lines.append("检测到尾部冗余内容，已在解析阶段自动截断。")
    return lines


def create_section_snapshots(
    connection: sqlite3.Connection,
    document_id: int,
    report_date: str,
    parsed_sections: dict[str, dict],
) -> list[dict]:
    created_at = now_string()
    connection.execute("DELETE FROM sections WHERE document_id = ?", (document_id,))

    records: list[dict] = []
    for section_key in SECTION_ORDER:
        definition = SECTION_MAP[section_key]
        section_model = parsed_sections.get(
            section_key,
            {
                "section_key": section_key,
                "section_number": definition["number"],
                "section_title": definition["title"],
                "blocks": [],
                "plain_text": "",
            },
        )
        raw_content = compact_text(section_model.get("plain_text", ""))
        parser_meta = build_section_parser_meta(section_model)
        previous = find_previous_section(connection, section_key, report_date)

        raw_render = build_section_render_payload(
            section_key,
            definition["title"],
            section_model.get("blocks", []),
            "历史保留",
        )
        comparison = compare_section_content(raw_content=raw_content, current_render=raw_render, previous_row=previous)
        display_render = comparison["render_payload"]

        metadata_payload = {
            "parser_version": PARSER_VERSION,
            "parser_meta": parser_meta,
            "raw_render": raw_render,
            "display_render": display_render,
            "compare_summary": {
                "status_counts": comparison["status_counts"],
                "matched_cards": comparison["matched_cards"],
            },
        }

        cursor = connection.execute(
            """
            INSERT INTO sections (
                document_id, report_date, section_key, section_title, raw_content, raw_html,
                display_content, display_html, status, note, similarity, previous_section_id,
                source_document_id, source_date, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                report_date,
                section_key,
                definition["title"],
                raw_content,
                "",
                raw_content,
                "",
                comparison["status"],
                comparison["note"],
                comparison["similarity"],
                comparison["previous_section_id"],
                comparison["source_document_id"],
                comparison["source_date"],
                json.dumps(metadata_payload, ensure_ascii=False),
                created_at,
            ),
        )

        records.append(
            {
                "id": cursor.lastrowid,
                "section_key": section_key,
                "section_title": definition["title"],
                "status": comparison["status"],
                "note": comparison["note"],
                "raw_content": raw_content,
                "display_content": raw_content,
                "source_date": comparison["source_date"],
                "similarity": comparison["similarity"],
                "render_payload": display_render,
                "parser_meta": parser_meta,
            }
        )

    return records


def compare_section_content(raw_content: str, current_render: dict, previous_row) -> dict:
    has_current_text = bool(normalize_compare_text(raw_content))
    previous_render = load_row_render_payload(previous_row) if previous_row else fallback_render_payload("", "", "无内容")
    previous_cards = extract_cards_from_render_payload(previous_render) if previous_row else []
    current_cards = extract_cards_from_render_payload(current_render)

    if current_cards:
        status_counts, matched_cards, average_score = compare_cards_against_previous(current_cards, previous_cards)
        current_render["status_counts"] = status_counts
        status = section_status_from_item_counts(status_counts, has_current_text)
        note = build_section_note(previous_row, status_counts, status)
        return {
            "status": status,
            "note": note,
            "similarity": average_score,
            "previous_section_id": previous_row["id"] if previous_row else None,
            "source_document_id": previous_row["document_id"] if previous_row else None,
            "source_date": previous_row["report_date"] if previous_row else None,
            "render_payload": current_render,
            "status_counts": status_counts,
            "matched_cards": matched_cards,
        }

    fallback = compare_text_only_section(raw_content, previous_row)
    current_render["status_counts"] = fallback["status_counts"]
    return {
        "status": fallback["status"],
        "note": fallback["note"],
        "similarity": fallback["similarity"],
        "previous_section_id": fallback["previous_section_id"],
        "source_document_id": fallback["source_document_id"],
        "source_date": fallback["source_date"],
        "render_payload": current_render,
        "status_counts": fallback["status_counts"],
        "matched_cards": 0,
    }


def compare_cards_against_previous(current_cards: list[dict], previous_cards: list[dict]) -> tuple[dict, int, float]:
    current_profiles = [build_card_compare_profile(card) for card in current_cards]
    previous_profiles = [build_card_compare_profile(card) for card in previous_cards]

    candidates: list[tuple[float, int, int]] = []
    for current_index, current_profile in enumerate(current_profiles):
        for previous_index, previous_profile in enumerate(previous_profiles):
            score = card_match_score(current_profile, previous_profile)
            if score >= 0.44:
                candidates.append((score, current_index, previous_index))

    candidates.sort(key=lambda item: item[0], reverse=True)
    matched_current: dict[int, tuple[int, float]] = {}
    used_previous: set[int] = set()
    for score, current_index, previous_index in candidates:
        if current_index in matched_current or previous_index in used_previous:
            continue
        matched_current[current_index] = (previous_index, score)
        used_previous.add(previous_index)

    status_counts = {label: 0 for label in ITEM_STATUS_ORDER}
    score_values: list[float] = []
    matched_cards = 0

    for current_index, card in enumerate(current_cards):
        if current_index not in matched_current:
            card["status"] = "新增"
            card["status_class"] = STATUS_CLASS_MAP["新增"]
            card["match_score"] = 0.0
            card["match_basis"] = "未在上一有效版本中找到相近内容"
            status_counts["新增"] += 1
            continue

        previous_index, score = matched_current[current_index]
        previous_profile = previous_profiles[previous_index]
        current_profile = current_profiles[current_index]
        status = determine_card_status(current_profile, previous_profile, score)
        card["status"] = status
        card["status_class"] = STATUS_CLASS_MAP[status]
        card["match_score"] = round(score, 4)
        card["match_basis"] = previous_profile["summary"]
        status_counts[status] += 1
        score_values.append(score)
        matched_cards += 1

    if sum(status_counts.values()) == 0:
        status_counts["无内容"] = 1

    average_score = round(sum(score_values) / len(score_values), 4) if score_values else 0.0
    return status_counts, matched_cards, average_score


def build_card_compare_profile(card: dict) -> dict:
    compare_meta = card.get("compare_meta", {}) or {}
    title = compare_meta.get("title") or card.get("title") or ""
    object_name = compare_meta.get("object_name") or title
    core_content = compare_meta.get("core_content") or card.get("core_content") or ""
    why = compare_meta.get("why") or card.get("why") or ""
    source = compare_meta.get("source") or card.get("source") or ""
    time_value = compare_meta.get("time") or card.get("time") or ""
    group_title = compare_meta.get("group_title") or card.get("group_title") or ""
    tags = compare_meta.get("tags") or card.get("tags") or []
    merged_text = " ".join(part for part in [title, object_name, core_content, why, source, group_title] if part)
    return {
        "title": title,
        "object_name": object_name,
        "core_content": core_content,
        "why": why,
        "source": source,
        "time": time_value,
        "group_title": group_title,
        "tags": [normalize_compare_text(tag) for tag in tags if normalize_compare_text(tag)],
        "title_norm": normalize_compare_text(title),
        "object_norm": normalize_compare_text(object_name),
        "core_norm": normalize_compare_text(core_content),
        "why_norm": normalize_compare_text(why),
        "source_norm": normalize_compare_text(source),
        "time_norm": normalize_compare_text(time_value),
        "group_norm": normalize_compare_text(group_title),
        "summary": title or object_name or core_content[:24] or "上一版本卡片",
        "merged_norm": normalize_compare_text(merged_text),
    }


def card_match_score(current_profile: dict, previous_profile: dict) -> float:
    title_ratio = similarity_ratio(current_profile["title_norm"], previous_profile["title_norm"])
    object_ratio = similarity_ratio(current_profile["object_norm"], previous_profile["object_norm"])
    core_ratio = similarity_ratio(current_profile["core_norm"], previous_profile["core_norm"])
    why_ratio = similarity_ratio(current_profile["why_norm"], previous_profile["why_norm"])
    source_ratio = similarity_ratio(current_profile["source_norm"], previous_profile["source_norm"])
    group_ratio = similarity_ratio(current_profile["group_norm"], previous_profile["group_norm"])
    merged_ratio = similarity_ratio(current_profile["merged_norm"], previous_profile["merged_norm"])
    time_ratio = time_match_score(current_profile["time_norm"], previous_profile["time_norm"])
    tag_ratio = tag_overlap_score(current_profile["tags"], previous_profile["tags"])

    score = (
        title_ratio * 0.22
        + object_ratio * 0.18
        + core_ratio * 0.28
        + why_ratio * 0.07
        + source_ratio * 0.06
        + time_ratio * 0.09
        + group_ratio * 0.05
        + tag_ratio * 0.05
        + merged_ratio * 0.14
    )
    if current_profile["object_norm"] and current_profile["object_norm"] == previous_profile["object_norm"]:
        score += 0.08
    if current_profile["time_norm"] and current_profile["time_norm"] == previous_profile["time_norm"]:
        score += 0.05
    if current_profile["title_norm"] and current_profile["title_norm"] == previous_profile["title_norm"]:
        score += 0.06
    return min(round(score, 4), 1.0)


def determine_card_status(current_profile: dict, previous_profile: dict, score: float) -> str:
    title_ratio = similarity_ratio(current_profile["title_norm"], previous_profile["title_norm"])
    object_ratio = similarity_ratio(current_profile["object_norm"], previous_profile["object_norm"])
    core_ratio = similarity_ratio(current_profile["core_norm"], previous_profile["core_norm"])
    merged_ratio = similarity_ratio(current_profile["merged_norm"], previous_profile["merged_norm"])
    source_ratio = similarity_ratio(current_profile["source_norm"], previous_profile["source_norm"])
    time_ratio = time_match_score(current_profile["time_norm"], previous_profile["time_norm"])
    same_time = bool(current_profile["time_norm"] and current_profile["time_norm"] == previous_profile["time_norm"])
    current_len = len(current_profile["core_norm"])
    previous_len = len(previous_profile["core_norm"])

    if (
        score >= 0.9
        or (title_ratio >= 0.88 and core_ratio >= 0.8)
        or (object_ratio >= 0.9 and core_ratio >= 0.78 and same_time)
        or (merged_ratio >= 0.9 and abs(current_len - previous_len) <= max(10, int(previous_len * 0.08)))
    ):
        return "历史保留"

    if (
        score >= 0.62
        or (object_ratio >= 0.86 and core_ratio >= 0.45)
        or (title_ratio >= 0.78 and core_ratio >= 0.45)
        or (same_time and core_ratio >= 0.45)
        or (source_ratio >= 0.5 and core_ratio >= 0.5)
        or (source_ratio >= 0.5 and title_ratio >= 0.38)
        or (time_ratio >= 0.75 and core_ratio >= 0.42 and source_ratio >= 0.35)
        or (merged_ratio >= 0.68 and score >= 0.56)
    ):
        return "更新"

    return "新增"


def similarity_ratio(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        shorter = min(len(left), len(right))
        longer = max(len(left), len(right))
        return min(1.0, 0.72 + shorter / max(longer, 1) * 0.25)
    return SequenceMatcher(None, left, right).ratio()


def time_match_score(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    if left in right or right in left:
        return 0.82
    return SequenceMatcher(None, left, right).ratio() * 0.75


def tag_overlap_score(left: list[str], right: list[str]) -> float:
    if not left or not right:
        return 0.0
    left_set = set(left)
    right_set = set(right)
    intersection = len(left_set & right_set)
    union = len(left_set | right_set)
    return intersection / union if union else 0.0


def section_status_from_item_counts(status_counts: dict, has_content: bool) -> str:
    if status_counts.get("新增", 0):
        return "新增"
    if status_counts.get("更新", 0):
        return "更新"
    if status_counts.get("历史保留", 0):
        return "历史保留"
    if has_content:
        return "历史保留"
    return "无内容"


def build_section_note(previous_row, status_counts: dict, status: str) -> str:
    previous_date = previous_row["report_date"] if previous_row else None
    if not previous_row:
        if status_counts.get("新增", 0):
            return f"相对于当前有效版本链，这是首次出现的有效内容，共识别 {status_counts['新增']} 条情报。"
        if status == "无内容":
            return "本板块本日未解析出有效正文，请检查原始文档结构或解析结果。"
        return "本板块已生成展示内容。"

    if status == "无内容":
        return f"本板块本日未解析出有效正文，且在 {previous_date} 之后没有可延续的有效内容。"

    parts = []
    for label in ["新增", "更新", "历史保留"]:
        count = status_counts.get(label, 0)
        if count:
            parts.append(f"{label} {count} 条")
    if not parts:
        parts.append("未识别出卡片级变化")
    return f"相对于上一有效版本 {previous_date}：{'，'.join(parts)}。"


def compare_text_only_section(raw_content: str, previous_row) -> dict:
    previous_content = previous_row["display_content"] if previous_row else ""
    normalized_current = normalize_compare_text(raw_content)
    normalized_previous = normalize_compare_text(previous_content)

    if not normalized_current:
        if normalized_previous:
            return {
                "status": "历史保留",
                "note": f"本板块本日未解析出有效正文，最近有效版本可追溯至 {previous_row['report_date']}。",
                "similarity": 1.0,
                "previous_section_id": previous_row["id"],
                "source_document_id": previous_row["document_id"],
                "source_date": previous_row["report_date"],
                "status_counts": {"新增": 0, "更新": 0, "历史保留": 1, "无内容": 0},
            }
        return {
            "status": "无内容",
            "note": "本板块本日未解析出有效正文，请检查原始文档结构或解析结果。",
            "similarity": 0.0,
            "previous_section_id": previous_row["id"] if previous_row else None,
            "source_document_id": previous_row["document_id"] if previous_row else None,
            "source_date": previous_row["report_date"] if previous_row else None,
            "status_counts": {"新增": 0, "更新": 0, "历史保留": 0, "无内容": 1},
        }

    if not normalized_previous:
        return {
            "status": "新增",
            "note": "相对于上一有效版本链，本板块首次出现有效内容。",
            "similarity": 0.0,
            "previous_section_id": previous_row["id"] if previous_row else None,
            "source_document_id": previous_row["document_id"] if previous_row else None,
            "source_date": previous_row["report_date"] if previous_row else None,
            "status_counts": {"新增": 1, "更新": 0, "历史保留": 0, "无内容": 0},
        }

    similarity = SequenceMatcher(None, normalized_previous, normalized_current).ratio()
    if normalized_current == normalized_previous or similarity >= 0.93:
        status = "历史保留"
        note = f"与上一有效版本 {previous_row['report_date']} 高度一致，判定为历史保留。"
    elif normalized_previous in normalized_current or normalized_current in normalized_previous or similarity >= 0.58:
        status = "更新"
        note = f"与上一有效版本 {previous_row['report_date']} 存在延续关系，且出现补充或改写，判定为更新。"
    else:
        status = "新增"
        note = f"与上一有效版本 {previous_row['report_date']} 差异较大，判定为新增。"

    return {
        "status": status,
        "note": note,
        "similarity": round(similarity, 4),
        "previous_section_id": previous_row["id"] if previous_row else None,
        "source_document_id": previous_row["document_id"] if previous_row else None,
        "source_date": previous_row["report_date"] if previous_row else None,
        "status_counts": {
            "新增": 1 if status == "新增" else 0,
            "更新": 1 if status == "更新" else 0,
            "历史保留": 1 if status == "历史保留" else 0,
            "无内容": 0,
        },
    }


def find_previous_section(connection: sqlite3.Connection, section_key: str, report_date: str):
    return connection.execute(
        """
        SELECT s.*, d.original_name
        FROM sections s
        JOIN documents d ON d.id = s.document_id
        WHERE s.section_key = ?
          AND s.report_date < ?
          AND d.doc_type = 'draft'
          AND d.is_current = 1
          AND d.lifecycle_status = 'active'
        ORDER BY s.report_date DESC, d.uploaded_at DESC
        LIMIT 1
        """,
        (section_key, report_date),
    ).fetchone()


def write_document_archive(
    connection: sqlite3.Connection,
    document_id: int,
    report_date: str,
    doc_type: str,
    original_name: str,
    stored_path: Path,
    title: str,
    content: str,
    recognition_note: str,
    sections: list[dict],
    uploaded_at: str,
    document_metadata: dict,
) -> Path:
    payload = build_archive_payload(
        document_id=document_id,
        report_date=report_date,
        original_name=original_name,
        saved_path=stored_path,
        doc_type=doc_type,
        title=title,
        content=content,
        recognition_note=recognition_note,
        sections=sections,
        uploaded_at=uploaded_at,
        document_metadata=document_metadata,
    )
    parsed_path = write_archive_json(report_date, doc_type, payload)
    metadata_json = load_json(
        connection.execute("SELECT metadata_json FROM documents WHERE id = ?", (document_id,)).fetchone()["metadata_json"],
        {},
    )
    metadata_json.update(document_metadata)
    metadata_json["recognition_note"] = recognition_note
    metadata_json["parsed_path"] = str(parsed_path)
    connection.execute(
        """
        UPDATE documents
        SET parsed_path = ?, metadata_json = ?
        WHERE id = ?
        """,
        (str(parsed_path), json.dumps(metadata_json, ensure_ascii=False), document_id),
    )
    return parsed_path


def build_archive_payload(
    document_id: int,
    report_date: str,
    original_name: str,
    saved_path: Path,
    doc_type: str,
    title: str,
    content: str,
    recognition_note: str,
    sections: list[dict],
    uploaded_at: str,
    document_metadata: dict,
) -> dict:
    payload = {
        "document_id": document_id,
        "report_date": report_date,
        "doc_type": doc_type,
        "title": title,
        "original_name": original_name,
        "stored_path": str(saved_path),
        "uploaded_at": uploaded_at,
        "recognition_note": recognition_note,
        "content": content,
        "document_metadata": document_metadata,
    }
    if sections:
        payload["sections"] = sections
    return payload


def write_archive_json(report_date: str, doc_type: str, payload: dict) -> Path:
    filename = f"{now_local().strftime('%Y%m%d-%H%M%S-%f')}_{doc_type}.json"
    archive_path = current_app.config["ARCHIVE_ROOT"] / report_date / filename
    dump_json(payload, archive_path)
    return archive_path


def get_day_snapshot(
    report_date: str,
    *,
    viewer_identity_id: int | None = None,
    viewer_role: str = "guest",
) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        content_version = build_read_content_version(connection, report_date=report_date)

    cache_key = f"day_snapshot_base:{report_date}:{content_version}"
    snapshot, _from_cache = get_or_build_cached_read_view(
        cache_key,
        lambda: _build_day_snapshot_base(report_date),
    )
    apply_section_preview_marks(
        snapshot["sections"],
        viewer_identity_id=viewer_identity_id,
        viewer_role=viewer_role,
    )
    snapshot["section_groups"] = group_sections_for_ui({section["key"]: section for section in snapshot["sections"]})
    snapshot["today_focus_sections"] = build_today_focus_sections(snapshot["sections"])
    snapshot["today_new_sections"] = build_today_new_sections(snapshot["sections"])
    snapshot["featured_sections"] = snapshot["today_focus_sections"]
    snapshot["overview"]["featured_sections"] = len(snapshot["today_focus_sections"])
    snapshot["overview"]["today_focus_sections"] = len(snapshot["today_focus_sections"])
    snapshot["overview"]["today_new_sections"] = len(snapshot["today_new_sections"])
    return snapshot


def _build_day_snapshot_base(report_date: str) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        brief = get_current_document(connection, report_date, "brief")
        draft = get_current_document(connection, report_date, "draft")
        _draft_chain, cumulative_views = build_cumulative_section_views(connection, report_date)
        if cumulative_views:
            section_map = {
                section_key: build_section_card(connection, cumulative_views.get(section_key))
                for section_key in VISIBLE_SECTION_ORDER
            }
        else:
            section_map = {definition["key"]: empty_section_card(definition["key"]) for definition in VISIBLE_SECTION_DEFINITIONS}

    sections = get_visible_section_rows(section_map)
    section_groups = group_sections_for_ui(section_map)
    today_focus_sections = build_today_focus_sections(sections)
    today_new_sections = build_today_new_sections(sections)
    featured_sections = today_focus_sections

    section_status_counts = defaultdict(int)
    item_status_counts = defaultdict(int)
    review_items = 0
    for section in sections:
        section_status_counts[section["status"]] += 1
        for label, count in section.get("internal_item_status_counts", {}).items():
            item_status_counts[label] += count
        review_items += section.get("needs_review_count", 0)

    sections_with_content = sum(1 for section in sections if section["display_content"])
    display_status_counts = translate_status_counts(item_status_counts, review_items)
    overview = {
        "date": report_date,
        "sections_with_content": sections_with_content,
        "draft_uploaded": bool(draft),
        "current_draft_date": draft["report_date"] if draft else get_latest_effective_date_by_type("draft"),
        "visible_sections": len(sections),
        "featured_sections": len(today_focus_sections),
        "today_focus_sections": len(today_focus_sections),
        "today_new_sections": len(today_new_sections),
        "new_items": item_status_counts.get("新增", 0),
        "updated_items": item_status_counts.get("更新", 0),
        "background_items": item_status_counts.get("背景补充", 0),
        "retained_items": item_status_counts.get("历史保留", 0),
        "placeholder_items": item_status_counts.get("占位项", 0),
        "review_items": review_items,
    }

    return {
        "report_date": report_date,
        "brief": build_brief_card(brief),
        "draft": build_draft_card(draft),
        "sections": sections,
        "today_focus_sections": today_focus_sections,
        "today_new_sections": today_new_sections,
        "featured_sections": featured_sections,
        "section_groups": section_groups,
        "workbench_shortcuts": build_workbench_shortcuts(report_date),
        "status_counts": display_status_counts,
        "status_pills": build_status_pills(display_status_counts),
        "section_status_counts": dict(section_status_counts),
        "item_status_counts": dict(item_status_counts),
        "overview": overview,
        "retained_assets": {
            "brief_available": bool(brief),
            "brief_title": brief["title"] if brief else "",
            "brief_visible": BRIEF_UI_ENABLED,
        },
        "has_any_content": bool(sections_with_content or draft),
    }


def build_brief_card(row) -> dict:
    if not row:
        return {
            "available": False,
            "title": "今日尚未上传每日分析简报",
            "html_content": "",
            "uploaded_at": "",
            "original_name": "",
            "stored_path": "",
            "report_date": "",
        }
    return {
        "available": True,
        "title": row["title"],
        "html_content": row["html_content"],
        "uploaded_at": row["uploaded_at"],
        "original_name": row["original_name"],
        "stored_path": row["stored_path"],
        "parsed_path": row["parsed_path"],
        "report_date": row["report_date"],
    }


def build_draft_card(row) -> dict:
    if not row:
        return {"available": False}
    return {
        "available": True,
        "original_name": row["original_name"],
        "uploaded_at": row["uploaded_at"],
        "stored_path": row["stored_path"],
        "parsed_path": row["parsed_path"],
        "report_date": row["report_date"],
    }


def empty_section_card(section_key: str) -> dict:
    section_meta = get_frontend_section_meta(section_key)
    display_status = get_display_status_payload("无内容")
    display_status_counts = translate_status_counts({"无内容": 1})
    return {
        "key": section_key,
        "number": SECTION_MAP[section_key]["number"],
        "title": section_meta["section_title"],
        "display_title": section_meta["section_title"],
        "display_kicker": section_meta["category_title"],
        "category_key": section_meta["category_key"],
        "category_title": section_meta["category_title"],
        "view_label": section_meta["view_label"],
        "internal_title": SECTION_MAP[section_key]["title"],
        "track_key": section_meta["track_key"],
        "track_title": section_meta["track_title"],
        "internal_status": "无内容",
        "status": display_status["label"],
        "status_class": display_status["class"],
        "excerpt": "本日未提供该板块内容。",
        "note": translate_frontend_copy("请上传包含该板块内容的研究底稿。"),
        "detail_url": None,
        "display_content": "",
        "raw_content": "",
        "source_file_name": "",
        "source_date": None,
        "similarity": None,
        "item_status_counts": display_status_counts,
        "status_pills": build_status_pills(display_status_counts),
        "internal_item_status_counts": {"新增": 0, "更新": 0, "背景补充": 0, "历史保留": 0, "占位项": 0, "无内容": 1},
        "preview_mode": "text",
        "preview_cards": [],
        "needs_review_count": 0,
        "new_count": 0,
        "updated_count": 0,
        "review_count": 0,
    }
    definition = SECTION_MAP[section_key]
    return {
        "key": section_key,
        "number": definition["number"],
        "title": definition["title"],
        "status": "无内容",
        "status_class": STATUS_CLASS_MAP["无内容"],
        "excerpt": "本日未提供该板块内容。",
        "note": "请上传包含该板块的研究底稿。",
        "detail_url": None,
        "display_content": "",
        "raw_content": "",
        "source_file_name": "",
        "source_date": None,
        "similarity": None,
        "item_status_counts": {"新增": 0, "更新": 0, "背景补充": 0, "历史保留": 0, "占位项": 0, "无内容": 1},
        "needs_review_count": 0,
    }


def build_section_card(connection: sqlite3.Connection, row) -> dict:
    section_key = row["section_key"]
    section_meta = get_frontend_section_meta(section_key)
    source_file_name = row["current_file_name"]
    render_payload = load_row_render_payload(row)
    cards = extract_cards_from_render_payload(render_payload)
    preview_payload = build_section_preview_payload(render_payload, row["display_content"] or row["raw_content"] or "")
    status_counts = render_payload.get("status_counts") or {
        "新增": 1 if row["status"] == "新增" else 0,
        "更新": 1 if row["status"] == "更新" else 0,
        "背景补充": 1 if row["status"] == "背景补充" else 0,
        "历史保留": 1 if row["status"] == "历史保留" else 0,
        "占位项": 1 if row["status"] == "占位项" else 0,
        "无内容": 1 if row["status"] == "无内容" else 0,
    }
    if row["source_document_id"]:
        source_file = connection.execute("SELECT original_name FROM documents WHERE id = ?", (row["source_document_id"],)).fetchone()
        if source_file:
            source_file_name = source_file["original_name"]

    display_content = row["display_content"]
    needs_review_count = sum(1 for card in cards if card.get("needs_review"))
    display_status = get_display_status_payload(row["status"])
    display_status_counts = translate_status_counts(status_counts, needs_review_count)
    preview_cards = preview_payload["cards"]
    for preview_card, source_card in zip(preview_cards, cards[: len(preview_cards)]):
        subcategory_payload = resolve_track_subcategory(
            section_meta["track_key"],
            title=source_card.get("title") or source_card.get("source_title") or "",
            tags=extract_card_business_tags(source_card),
        )
        preview_card["track_title"] = section_meta["track_title"]
        preview_card["subcategory_label"] = subcategory_payload["label"]
        preview_tags = []
        if subcategory_payload["label"]:
            preview_tags.append(subcategory_payload["label"])
        for tag in preview_card.get("tags") or []:
            if tag and tag not in preview_tags:
                preview_tags.append(tag)
        preview_card["tags"] = preview_tags[:3]
    return {
        "key": section_key,
        "number": SECTION_MAP[section_key]["number"],
        "title": section_meta["section_title"],
        "display_title": section_meta["section_title"],
        "display_kicker": section_meta["category_title"],
        "category_key": section_meta["category_key"],
        "category_title": section_meta["category_title"],
        "view_label": section_meta["view_label"],
        "track_key": section_meta["track_key"],
        "track_title": section_meta["track_title"],
        "internal_title": row["section_title"],
        "internal_status": row["status"],
        "status": display_status["label"],
        "status_class": display_status["class"],
        "excerpt": preview_payload["excerpt"],
        "note": translate_frontend_copy(row["note"]),
        "detail_url": f"/section/{row['report_date']}/{section_key}",
        "display_content": display_content,
        "raw_content": row["raw_content"],
        "source_file_name": source_file_name,
        "source_date": row["source_date"],
        "similarity": row["similarity"],
        "item_status_counts": display_status_counts,
        "status_pills": build_status_pills(display_status_counts),
        "internal_item_status_counts": status_counts,
        "preview_mode": preview_payload["mode"],
        "preview_cards": preview_cards,
        "needs_review_count": needs_review_count,
        "new_count": status_counts.get("新增", 0),
        "updated_count": status_counts.get("更新", 0),
        "review_count": needs_review_count,
        "entry_ids": [preview["entry_id"] for preview in preview_cards if preview.get("entry_id")],
        "manual_mark_count": 0,
        "has_manual_marks": False,
        "manual_mark_note": "",
        "latest_mark_at": "",
        "latest_marker_label": "",
    }
    return {
        "key": row["section_key"],
        "number": SECTION_MAP[row["section_key"]]["number"],
        "title": row["section_title"],
        "status": row["status"],
        "status_class": STATUS_CLASS_MAP[row["status"]],
        "excerpt": preview_payload["excerpt"],
        "note": row["note"],
        "detail_url": f"/section/{row['report_date']}/{row['section_key']}",
        "display_content": display_content,
        "raw_content": row["raw_content"],
        "source_file_name": source_file_name,
        "source_date": row["source_date"],
        "similarity": row["similarity"],
        "item_status_counts": status_counts,
        "preview_mode": preview_payload["mode"],
        "preview_cards": preview_payload["cards"],
        "needs_review_count": sum(1 for card in cards if card.get("needs_review")),
    }


def build_section_preview_payload(render_payload: dict, fallback_text: str) -> dict:
    cards = extract_cards_from_render_payload(render_payload)
    if cards:
        preview_cards = [build_preview_card(card) for card in cards[:2]]
        for preview_card, source_card in zip(preview_cards, cards[:2]):
            preview_card["entry_id"] = source_card.get("entry_id")
            preview_card.setdefault(
                "mark_summary",
                {
                    "has_marks": False,
                    "count": 0,
                    "items": [],
                    "highlight_note": "",
                    "latest_mark_at": "",
                    "latest_marker_label": "",
                    "viewer_can_mark": False,
                    "viewer_mark": None,
                },
            )
            preview_card.setdefault("has_manual_marks", False)
        preview_excerpt = preview_cards[0]["body"] if preview_cards and preview_cards[0]["body"] else fallback_text
        return {
            "mode": "cards",
            "cards": preview_cards,
            "excerpt": build_excerpt(preview_excerpt or "本日未提供该板块内容。"),
        }
    return {
        "mode": "text",
        "cards": [],
        "excerpt": build_excerpt(fallback_text or "本日未提供该板块内容。"),
    }


def build_preview_card(card: dict) -> dict:
    body = build_excerpt(card.get("core_content") or "", limit=72)
    why = build_excerpt(card.get("why") or "", limit=56) if card.get("why") else ""
    display_status = get_display_status_payload(card.get("status") or "历史保留", needs_review=bool(card.get("needs_review")))
    meta = [value for value in [card.get("time"), card.get("source")] if value]
    if card.get("first_seen"):
        meta.append(f"首次 {card['first_seen']}")
    if card.get("last_seen") and card.get("last_seen") != card.get("first_seen"):
        meta.append(f"最近 {card['last_seen']}")
    return {
        "title": card.get("title") or "情报预览",
        "body": body,
        "why": translate_frontend_copy(why),
        "meta": meta,
        "tags": (card.get("tags") or [])[:3],
        "status": display_status["label"],
        "status_class": display_status["class"],
    }


def get_effective_draft_chain(connection: sqlite3.Connection, report_date: str) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT *
        FROM documents
        WHERE doc_type = 'draft'
          AND is_current = 1
          AND lifecycle_status = 'active'
          AND report_date <= ?
        ORDER BY report_date ASC, uploaded_at ASC
        """,
        (report_date,),
    ).fetchall()


def load_effective_section_rows(connection: sqlite3.Connection, report_date: str) -> tuple[list[sqlite3.Row], dict[str, list[dict]]]:
    draft_rows = get_effective_draft_chain(connection, report_date)
    if not draft_rows:
        return [], {key: [] for key in SECTION_ORDER}

    document_ids = [row["id"] for row in draft_rows]
    placeholders = ",".join("?" for _ in document_ids)
    section_rows = connection.execute(
        f"""
        SELECT s.*, d.original_name AS current_file_name, d.stored_path AS current_file_path, d.uploaded_at AS document_uploaded_at
        FROM sections s
        JOIN documents d ON d.id = s.document_id
        WHERE s.document_id IN ({placeholders})
        ORDER BY s.report_date ASC, d.uploaded_at ASC, s.id ASC
        """,
        document_ids,
    ).fetchall()

    rows_by_doc_and_key: dict[tuple[int, str], dict] = {}
    for raw_row in section_rows:
        row = dict(raw_row)
        resolved_key = resolve_section_key(row["section_key"])
        row["resolved_section_key"] = resolved_key
        bucket_key = (row["document_id"], resolved_key)
        existing = rows_by_doc_and_key.get(bucket_key)
        if not existing:
            rows_by_doc_and_key[bucket_key] = row
            continue
        if row["section_key"] == resolved_key and existing["section_key"] != resolved_key:
            rows_by_doc_and_key[bucket_key] = row

    grouped_rows = {key: [] for key in SECTION_ORDER}
    for draft_row in draft_rows:
        for section_key in SECTION_ORDER:
            row = rows_by_doc_and_key.get((draft_row["id"], section_key))
            if row:
                grouped_rows[section_key].append(row)

    return draft_rows, grouped_rows


def build_cumulative_section_views(connection: sqlite3.Connection, report_date: str) -> tuple[list[sqlite3.Row], dict[str, dict]]:
    draft_rows, grouped_rows = load_effective_section_rows(connection, report_date)
    latest_draft = draft_rows[-1] if draft_rows else None
    repaired_views = build_repaired_section_views(connection, report_date, latest_draft)
    section_views = {}
    for definition in SECTION_DEFINITIONS:
        if definition["key"] == "report_note":
            section_views[definition["key"]] = build_cumulative_section_row(
                definition,
                grouped_rows.get(definition["key"], []),
                report_date,
                latest_draft,
            )
            continue

        rebuilt_row = repaired_views.get(definition["key"])
        if rebuilt_row:
            section_views[definition["key"]] = rebuilt_row
        else:
            section_views[definition["key"]] = build_cumulative_section_row(
                definition,
                grouped_rows.get(definition["key"], []),
                report_date,
                latest_draft,
            )
    return draft_rows, section_views


def build_cumulative_section_row(definition: dict, rows: list[dict], report_date: str, latest_draft) -> dict:
    if not rows:
        return build_empty_rollup(definition, report_date, latest_draft)

    if definition["key"] == "report_note":
        return build_report_note_rollup(definition, rows, report_date, latest_draft)

    aggregate_cards: list[dict] = []
    latest_note_groups: list[dict] = []
    latest_note_row: dict | None = None
    latest_row = rows[-1]
    latest_content_row = next((row for row in reversed(rows) if (row["raw_content"] or "").strip()), latest_row)

    for row in rows:
        render_payload = load_row_render_payload(row)
        incoming_cards = [deepcopy(card) for card in extract_cards_from_render_payload(render_payload)]
        note_groups = extract_persistent_note_groups(definition["key"], render_payload)

        if note_groups:
            latest_note_groups = note_groups
            latest_note_row = row

        aggregate_cards = merge_cumulative_cards(aggregate_cards, incoming_cards, row["report_date"])

    if not aggregate_cards and latest_content_row:
        base_render = load_row_render_payload(latest_content_row)
        status = latest_row["status"] if latest_row["report_date"] == report_date else "历史保留"
        return build_rollup_from_render(
            definition=definition,
            report_date=report_date,
            status=status,
            note=build_cumulative_rollup_note(latest_row, latest_content_row, status, {}),
            render_payload=base_render,
            source_row=latest_content_row,
            current_row=latest_row,
        )

    render_payload = build_cumulative_render_payload(definition, aggregate_cards, latest_note_groups, latest_note_row or latest_content_row)
    status_counts = count_card_statuses(aggregate_cards)
    status = section_status_from_item_counts(status_counts, bool(aggregate_cards))
    note = build_cumulative_rollup_note(latest_row, latest_content_row, status, status_counts)
    return build_rollup_from_render(
        definition=definition,
        report_date=report_date,
        status=status,
        note=note,
        render_payload=render_payload,
        source_row=latest_note_row or latest_content_row,
        current_row=latest_row,
    )


def build_report_note_rollup(definition: dict, rows: list[dict], report_date: str, latest_draft) -> dict:
    latest_row = rows[-1]
    source_row = next((row for row in reversed(rows) if (row["raw_content"] or "").strip()), latest_row)
    if not source_row:
        return build_empty_rollup(definition, report_date, latest_draft)

    render_payload = normalize_report_note_render(load_row_render_payload(source_row))
    status = latest_row["status"] if latest_row["report_date"] == report_date else "历史保留"
    note = build_cumulative_rollup_note(latest_row, source_row, status, render_payload.get("status_counts") or {})
    return build_rollup_from_render(
        definition=definition,
        report_date=report_date,
        status=status,
        note=note,
        render_payload=render_payload,
        source_row=source_row,
        current_row=latest_row,
    )


def build_empty_rollup(definition: dict, report_date: str, latest_draft) -> dict:
    return {
        "section_key": definition["key"],
        "section_title": definition["title"],
        "report_date": report_date,
        "status": "无内容",
        "note": "本板块当前没有可累计展示的有效内容。",
        "similarity": 0.0,
        "raw_content": "",
        "display_content": "",
        "metadata_json": json.dumps({"display_render": fallback_render_payload(definition["title"], "", "无内容")}, ensure_ascii=False),
        "source_document_id": latest_draft["id"] if latest_draft else None,
        "source_date": None,
        "current_file_name": latest_draft["original_name"] if latest_draft else "",
        "current_file_path": latest_draft["stored_path"] if latest_draft else "",
        "document_id": latest_draft["id"] if latest_draft else None,
        "current_document_id": latest_draft["id"] if latest_draft else None,
    }


def build_rollup_from_render(
    definition: dict,
    report_date: str,
    status: str,
    note: str,
    render_payload: dict,
    source_row,
    current_row,
) -> dict:
    render_payload.setdefault("status_counts", infer_render_status_counts(status, render_payload, blocks_to_text_from_render(render_payload)))
    metadata = {
        "display_render": render_payload,
        "raw_render": render_payload,
        "rollup": {"mode": "cumulative", "report_date": report_date},
    }
    raw_content = blocks_to_text_from_render(render_payload)
    return {
        "section_key": definition["key"],
        "section_title": definition["title"],
        "report_date": report_date,
        "status": status,
        "note": note,
        "similarity": current_row.get("similarity") if current_row else 0.0,
        "raw_content": raw_content,
        "display_content": raw_content,
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "source_document_id": source_row["document_id"] if source_row else None,
        "source_date": source_row["report_date"] if source_row else None,
        "current_file_name": current_row["current_file_name"] if current_row else "",
        "current_file_path": current_row["current_file_path"] if current_row else "",
        "document_id": source_row["document_id"] if source_row else (current_row["document_id"] if current_row else None),
        "current_document_id": current_row["document_id"] if current_row else None,
    }


def merge_cumulative_cards(existing_cards: list[dict], incoming_cards: list[dict], report_date: str) -> list[dict]:
    if not existing_cards:
        seeded = [stamp_card_dates(card, report_date) for card in incoming_cards]
        return seeded

    retained_cards = [mark_card_retained(card) for card in existing_cards]
    if not incoming_cards:
        return retained_cards

    current_profiles = [build_card_compare_profile(card) for card in incoming_cards]
    previous_profiles = [build_card_compare_profile(card) for card in retained_cards]
    candidates: list[tuple[float, int, int]] = []
    for current_index, current_profile in enumerate(current_profiles):
        for previous_index, previous_profile in enumerate(previous_profiles):
            score = card_match_score(current_profile, previous_profile)
            if score >= 0.44:
                candidates.append((score, current_index, previous_index))

    candidates.sort(key=lambda item: item[0], reverse=True)
    matched_current: dict[int, int] = {}
    used_previous: set[int] = set()
    for _score, current_index, previous_index in candidates:
        if current_index in matched_current or previous_index in used_previous:
            continue
        matched_current[current_index] = previous_index
        used_previous.add(previous_index)

    merged_cards = list(retained_cards)
    for current_index, card in enumerate(incoming_cards):
        stamped = stamp_card_dates(card, report_date)
        if current_index in matched_current:
            previous_card = merged_cards[matched_current[current_index]]
            stamped["effective_since"] = previous_card.get("effective_since") or previous_card.get("last_seen_date") or report_date
            merged_cards[matched_current[current_index]] = stamped
        else:
            merged_cards.append(stamped)
    return merged_cards


def stamp_card_dates(card: dict, report_date: str) -> dict:
    stamped = deepcopy(card)
    stamped["effective_since"] = stamped.get("effective_since") or report_date
    stamped["last_seen_date"] = report_date
    return stamped


def mark_card_retained(card: dict) -> dict:
    retained = deepcopy(card)
    retained["status"] = "历史保留"
    retained["status_class"] = STATUS_CLASS_MAP["历史保留"]
    return retained


def count_card_statuses(cards: list[dict]) -> dict:
    counts = {label: 0 for label in ITEM_STATUS_ORDER}
    if not cards:
        counts["无内容"] = 1
        return counts
    for card in cards:
        counts[card.get("status") or "历史保留"] += 1
    return counts


def build_cumulative_render_payload(definition: dict, cards: list[dict], note_groups: list[dict], source_row) -> dict:
    base_render = load_row_render_payload(source_row) if source_row else fallback_render_payload(definition["title"], "", "无内容")
    groups: list[dict] = []
    grouped_cards: dict[str | None, list[dict]] = {}
    for card in cards:
        grouped_cards.setdefault(card.get("group_title") or None, []).append(card)

    for group_title, group_cards in grouped_cards.items():
        groups.append(
            {
                "title": group_title,
                "level": 2 if group_title else 1,
                "category": None,
                "blocks": [{"type": "card", "card": deepcopy(card)} for card in group_cards],
            }
        )

    if note_groups:
        groups.extend(deepcopy(note_groups))
    if not groups:
        groups = deepcopy(base_render.get("groups") or [])

    outline = [group["title"] for group in groups if group.get("title")]
    return {
        "section_key": definition["key"],
        "section_title": definition["title"],
        "template_name": base_render.get("template_name", "intelligence"),
        "template_label": base_render.get("template_label", "内容版式"),
        "groups": groups,
        "outline": outline,
        "card_count": len(cards),
        "table_count": 0,
        "status_counts": count_card_statuses(cards),
    }


def extract_persistent_note_groups(section_key: str, render_payload: dict) -> list[dict]:
    if section_key == "report_note":
        return normalize_report_note_render(render_payload).get("groups", [])

    note_groups: list[dict] = []
    for group in render_payload.get("groups", []):
        group_title = group.get("title") or ""
        if "当前状态说明" not in group_title and "背景补充" not in group_title:
            continue
        blocks: list[dict] = []
        for block in group.get("blocks", []):
            if block.get("type") == "paragraph":
                blocks.append(deepcopy(block))
            elif block.get("type") == "card":
                card = block["card"]
                blocks.append({"type": "paragraph", "text": build_note_text_from_card(card)})
        if blocks:
            note_groups.append(
                {
                    "title": group_title,
                    "level": group.get("level", 2),
                    "category": group.get("category"),
                    "blocks": blocks,
                }
            )
    return note_groups


def normalize_report_note_render(render_payload: dict) -> dict:
    groups: list[dict] = []
    for group in render_payload.get("groups", []):
        blocks: list[dict] = []
        for block in group.get("blocks", []):
            if block.get("type") == "paragraph":
                if not is_non_body_tail_text(block.get("text", "")):
                    blocks.append(deepcopy(block))
            elif block.get("type") == "card":
                note_text = build_note_text_from_card(block["card"])
                if not is_non_body_tail_text(note_text):
                    blocks.append({"type": "paragraph", "text": note_text})
        if blocks or group.get("title"):
            groups.append(
                {
                    "title": group.get("title"),
                    "level": group.get("level", 1),
                    "category": group.get("category"),
                    "blocks": blocks,
                }
            )

    normalized = deepcopy(render_payload)
    normalized["groups"] = groups
    normalized["card_count"] = 0
    normalized["table_count"] = 0
    has_text = bool(blocks_to_text_from_render({"groups": groups}))
    normalized["status_counts"] = {"新增": 0, "更新": 0, "历史保留": 1 if has_text else 0, "无内容": 0 if has_text else 1}
    return normalized


def build_note_text_from_card(card: dict) -> str:
    title = (card.get("title") or "说明").strip()
    core = (card.get("core_content") or "").strip()
    why = (card.get("why") or "").strip()
    if why:
        return f"{title}：{core}\n补充说明：{why}"
    return f"{title}：{core}" if core else title


def blocks_to_text_from_render(render_payload: dict) -> str:
    parts: list[str] = []
    for group in render_payload.get("groups", []):
        if group.get("title"):
            parts.append(group["title"])
        for block in group.get("blocks", []):
            if block.get("type") == "paragraph":
                parts.append(block.get("text", ""))
            elif block.get("type") == "card":
                card = block["card"]
                parts.append(card.get("title") or "")
                parts.append(card.get("core_content") or "")
                if card.get("why"):
                    parts.append(card["why"])
            elif block.get("type") == "table":
                for card in block.get("cards", []):
                    parts.append(card.get("title") or "")
                    parts.append(card.get("core_content") or "")
                    if card.get("why"):
                        parts.append(card["why"])
    return compact_text("\n\n".join(part for part in parts if part))


def build_cumulative_rollup_note(current_row, source_row, status: str, status_counts: dict) -> str:
    if not source_row:
        return "本板块当前没有可累计展示的有效内容。"
    if source_row["report_date"] == current_row["report_date"]:
        if status_counts:
            parts = [f"{label} {count} 条" for label, count in status_counts.items() if label != "无内容" and count]
            if parts:
                return f"当前累计视图已更新至 {current_row['report_date']}：{'，'.join(parts)}。"
        return f"当前累计视图已更新至 {current_row['report_date']}。"
    return f"本板块在 {current_row['report_date']} 未出现新的有效条目，当前继续沿用 {source_row['report_date']} 的有效内容并保留历史累计结果。"


def normalize_pdf_render_payload(section_key: str, render_payload: dict) -> dict:
    if section_key == "report_note":
        return normalize_report_note_render(render_payload)

    normalized = deepcopy(render_payload)
    cleaned_groups: list[dict] = []
    for group in normalized.get("groups", []):
        cleaned_blocks: list[dict] = []
        for block in group.get("blocks", []):
            if block.get("type") == "paragraph":
                if is_non_body_tail_text(block.get("text", "")):
                    continue
                cleaned_blocks.append(block)
                continue
            if block.get("type") == "heading":
                if is_non_body_tail_text(group.get("title") or ""):
                    continue
                cleaned_blocks.append(block)
                continue
            if block.get("type") == "card":
                card_text = "\n".join(
                    value for value in [block["card"].get("title", ""), block["card"].get("core_content", ""), block["card"].get("why", "")]
                    if value
                )
                if is_non_body_tail_text(card_text):
                    continue
                cleaned_blocks.append(block)
                continue
            if block.get("type") == "table" and block.get("cards"):
                cleaned_blocks.append(block)
        if cleaned_blocks or group.get("title"):
            cleaned_groups.append(
                {
                    "title": group.get("title"),
                    "level": group.get("level", 1),
                    "category": group.get("category"),
                    "blocks": cleaned_blocks,
                }
            )
    normalized["groups"] = cleaned_groups
    return normalized


def is_non_body_tail_text(text: str) -> bool:
    normalized = compact_text(text or "").lower()
    if not normalized:
        return False
    return any(fragment.lower() in normalized for fragment in DRAFT_TAIL_PATTERNS if fragment)


def get_history_overview(limit: int = 30) -> list[dict]:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        content_version = build_read_content_version(connection)

    cache_key = f"history_overview:{limit}:{content_version}"
    history, _from_cache = get_or_build_cached_read_view(
        cache_key,
        lambda: _build_history_overview_base(limit),
    )
    return history


def _build_history_overview_base(limit: int = 30) -> list[dict]:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        doc_rows = connection.execute(
            """
            SELECT *
            FROM documents
            WHERE lifecycle_status != 'deleted'
            ORDER BY report_date DESC, uploaded_at DESC
            """
        ).fetchall()
    days: dict[str, dict] = {}
    for row in doc_rows:
        day = days.setdefault(
            row["report_date"],
            {
                "report_date": row["report_date"],
                "has_brief": False,
                "has_draft": False,
                "brief_name": "",
                "draft_name": "",
                "status_counts": defaultdict(int),
                "can_export": False,
                "draft_versions": defaultdict(int),
                "brief_versions": defaultdict(int),
            },
        )
        if row["doc_type"] == "brief":
            day["brief_versions"][row["lifecycle_status"]] += 1
            if row["is_current"] and row["lifecycle_status"] == "active" and not day["has_brief"]:
                day["has_brief"] = True
                day["brief_name"] = row["original_name"]
        elif row["doc_type"] == "draft":
            day["draft_versions"][row["lifecycle_status"]] += 1
            if row["is_current"] and row["lifecycle_status"] == "active" and not day["has_draft"]:
                day["has_draft"] = True
                day["draft_name"] = row["original_name"]

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        for report_date, day in days.items():
            if not day["has_draft"]:
                continue
            _draft_chain, cumulative_views = build_cumulative_section_views(connection, report_date)
            for section_key in VISIBLE_SECTION_ORDER:
                section_row = cumulative_views.get(section_key)
                if section_row:
                    day["status_counts"][section_row["status"]] += 1

    ordered = sorted(days.values(), key=lambda item: item["report_date"], reverse=True)
    for day in ordered:
        day["can_export"] = bool(day["has_draft"])
        display_status_counts = translate_status_counts(day["status_counts"])
        day["display_status_counts"] = display_status_counts
        day["display_status_pills"] = build_status_pills(display_status_counts)
        day["status_counts"] = dict(day["status_counts"])
        day["draft_versions"] = dict(day["draft_versions"])
        day["brief_versions"] = dict(day["brief_versions"])
    return ordered[:limit]


def get_recent_days(limit: int = 8) -> list[dict]:
    return get_history_overview(limit=limit)


def get_section_detail(
    report_date: str,
    section_key: str,
    *,
    viewer_identity_id: int | None = None,
    viewer_role: str = "guest",
) -> dict | None:
    resolved_section_key = resolve_section_key(section_key)
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        content_version = build_read_content_version(connection, report_date=report_date)

    cache_key = f"section_detail_base:{report_date}:{resolved_section_key}:{content_version}"
    detail, _from_cache = get_or_build_cached_read_view(
        cache_key,
        lambda: _build_section_detail_base(report_date, resolved_section_key),
    )
    if not detail:
        return None

    mark_summaries = apply_detail_marks(
        detail["render_model"],
        viewer_identity_id=viewer_identity_id,
        viewer_role=viewer_role,
    )
    detail["manual_mark_count"] = sum(1 for summary in mark_summaries.values() if summary.get("has_marks"))
    return detail


def _build_section_detail_base(report_date: str, section_key: str) -> dict | None:
    section_key = resolve_section_key(section_key)
    if section_key not in SECTION_MAP:
        return None

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        draft = get_current_document(connection, report_date, "draft")
        if not draft:
            return None

        _draft_chain, cumulative_views = build_cumulative_section_views(connection, report_date)
        row = cumulative_views.get(section_key)
        if not row:
            return None

        history_rows = build_repaired_section_history(connection, report_date, section_key, limit=8)

    metadata = load_json(row["metadata_json"], {})
    render_model = normalize_render_payload(
        metadata.get("display_render") or metadata.get("raw_render") or fallback_render_payload(row["section_title"], row["raw_content"], row["status"])
    )
    render_model.setdefault("status_counts", infer_render_status_counts(row["status"], render_model, row["display_content"] or row["raw_content"] or ""))
    render_model = build_frontend_render_model(section_key, render_model, row["status"])
    raw_content = row["raw_content"] or ""
    has_effective_content = bool(raw_content.strip())
    parse_warning = ""
    if not has_effective_content:
        parse_warning = "本板块本日未解析出有效正文，请检查原始文档结构或解析结果。"
    group_meta = get_section_group_meta(section_key)
    is_soft_hidden = section_key in SOFT_HIDDEN_SECTION_KEYS
    section_meta = get_frontend_section_meta(section_key)
    display_status = get_display_status_payload(row["status"])

    return {
        "report_date": report_date,
        "section_key": section_key,
        "title": section_meta["section_title"],
        "category_key": section_meta["category_key"],
        "category_title": section_meta["category_title"],
        "track_key": section_meta["track_key"],
        "track_title": section_meta["track_title"],
        "source_section_title": row["section_title"],
        "view_label": section_meta["view_label"],
        "display_title": section_meta["track_title"],
        "display_kicker": "阅读赛道",
        "status": display_status["label"],
        "status_class": display_status["class"],
        "internal_title": row["section_title"],
        "internal_status": row["status"],
        "raw_content": raw_content,
        "display_content": row["display_content"],
        "note": translate_frontend_copy(row["note"]),
        "source_file_name": row["current_file_name"],
        "source_file_path": row["current_file_path"],
        "source_date": row["source_date"] or report_date,
        "current_file_name": row["current_file_name"],
        "current_file_path": row["current_file_path"],
        "current_file_id": row.get("current_document_id") or row["document_id"],
        "render_model": render_model,
        "manual_mark_count": 0,
        "has_effective_content": has_effective_content,
        "parse_warning": parse_warning,
        "debug_url": f"/debug/sections/{report_date}",
        "day_url": f"/day/{report_date}",
        "export_url": f"/export/pdf/{report_date}",
        "filter_counts": render_model["display_status_counts"],
        "filter_options": render_model["filter_options"],
        "group_title": group_meta["title"],
        "group_description": translate_frontend_copy(group_meta["description"]),
        "is_soft_hidden": is_soft_hidden,
        "visibility_note": "该板块已从主导航与导出结构中软移除，当前页面仅保留历史回退访问能力。" if is_soft_hidden else "",
        "history_rows": [
            {
                "report_date": history_row["report_date"],
                "status": get_display_status_payload(history_row["status"]).get("label"),
                "status_class": get_display_status_payload(history_row["status"]).get("class"),
                "note": translate_frontend_copy(history_row["note"]),
                "excerpt": build_excerpt(translate_frontend_copy(history_row.get("excerpt") or "本日无有效结构化条目")),
            }
            for history_row in history_rows
        ],
    }


def get_section_debug_view(report_date: str) -> dict | None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        draft = get_current_document(connection, report_date, "draft")
        if not draft:
            return None
        rows = connection.execute("SELECT s.* FROM sections s WHERE s.document_id = ? ORDER BY s.id ASC", (draft["id"],)).fetchall()

    row_map = {row["section_key"]: row for row in rows}
    section_items = []
    for definition in SECTION_DEFINITIONS:
        row = row_map.get(definition["key"])
        metadata = load_json(row["metadata_json"], {}) if row else {}
        parser_meta = metadata.get("parser_meta", {})
        raw_content = (row["raw_content"] if row else "") or ""
        section_items.append(
            {
                "number": definition["number"],
                "title": definition["title"],
                "slug": definition["key"],
                "status": row["status"] if row else "无内容",
                "status_class": STATUS_CLASS_MAP[row["status"]] if row else STATUS_CLASS_MAP["无内容"],
                "start_paragraph_index": parser_meta.get("start_paragraph_index"),
                "end_paragraph_index": parser_meta.get("end_paragraph_index"),
                "start_block_index": parser_meta.get("start_block_index"),
                "end_block_index": parser_meta.get("end_block_index"),
                "matched_heading": parser_meta.get("matched_heading") or definition["title"],
                "content_length": len(raw_content),
                "preview_head": raw_content[:300],
                "preview_tail": raw_content[-300:] if raw_content else "",
                "has_effective_content": bool(raw_content.strip()),
                "detail_url": f"/section/{report_date}/{definition['key']}",
            }
        )

    return {
        "report_date": report_date,
        "document_title": draft["title"],
        "original_name": draft["original_name"],
        "stored_path": draft["stored_path"],
        "parsed_path": draft["parsed_path"],
        "sections": section_items,
    }


def create_day_pdf_export(report_date: str) -> dict:
    payload = build_day_pdf_payload(report_date)
    if not payload["summary"]["draft_uploaded"] and not payload["summary"]["available_sections"]:
        raise ValueError("当前日期还没有可导出的有效底稿内容。")

    filename = f"沉香行业情报浏览成果_{report_date}.pdf"
    export_path = current_app.config["EXPORT_ROOT"] / filename
    export_pdf(payload, export_path)
    export_id = register_export_file(report_date, filename, export_path, payload)
    return {
        "report_date": report_date,
        "filename": filename,
        "saved_path": str(export_path),
        "download_path": export_path,
        "export_id": export_id,
    }


def register_export_file(report_date: str, filename: str, export_path: Path, payload: dict) -> int:
    metadata = {
        "report_date": report_date,
        "generated_at": now_string(),
        "summary": payload.get("summary", {}),
    }
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        existing = connection.execute(
            "SELECT id FROM export_files WHERE file_name = ? AND report_date = ? LIMIT 1",
            (filename, report_date),
        ).fetchone()
        if existing:
            connection.execute(
                """
                UPDATE export_files
                SET stored_path = ?, file_ext = ?, created_at = ?, status = 'active', metadata_json = ?
                WHERE id = ?
                """,
                (
                    str(export_path),
                    export_path.suffix.lower(),
                    now_string(),
                    json.dumps(metadata, ensure_ascii=False),
                    existing["id"],
                ),
            )
            connection.commit()
            return existing["id"]

        cursor = connection.execute(
            """
            INSERT INTO export_files (
                report_date, file_name, stored_path, file_ext, created_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                report_date,
                filename,
                str(export_path),
                export_path.suffix.lower(),
                now_string(),
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        connection.commit()
        return cursor.lastrowid


def build_day_pdf_payload(report_date: str) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        brief_row = get_current_document(connection, report_date, "brief")
        draft_row = get_current_document(connection, report_date, "draft")
        _draft_chain, cumulative_views = build_cumulative_section_views(connection, report_date)

    section_payloads = []
    for definition in VISIBLE_SECTION_DEFINITIONS:
        row = cumulative_views.get(definition["key"]) if cumulative_views else None
        metadata = load_json(row["metadata_json"], {}) if row else {}
        render_model = normalize_render_payload(
            metadata.get("display_render") if row else fallback_render_payload(definition["title"], "", "无内容")
        )
        raw_content = (row["raw_content"] if row else "") or ""
        section_payloads.append(
            {
                "number": definition["number"],
                "key": definition["key"],
                "title": definition["title"],
                "report_date": report_date,
                "status": row["status"] if row else "无内容",
                "note": row["note"] if row else "本日未提供该板块内容。",
                "has_effective_content": bool(raw_content.strip()),
                "empty_message": "本日未解析出有效内容，请在系统中检查该板块的原始文档结构。",
                "render_model": normalize_pdf_render_payload(definition["key"], render_model),
            }
        )

    summary = {
        "draft_uploaded": bool(draft_row),
        "available_sections": sum(1 for item in section_payloads if item["has_effective_content"]),
        "new_sections": sum(1 for item in section_payloads if item["status"] == "新增"),
        "updated_sections": sum(1 for item in section_payloads if item["status"] == "更新"),
    }
    return {
        "report_date": report_date,
        "export_time": now_string(),
        "files": {
            "draft_name": draft_row["original_name"] if draft_row else "",
        },
        "summary": summary,
        "sections": section_payloads,
        "retained_assets": {
            "brief_available": bool(brief_row) and not BRIEF_EXPORT_ENABLED,
        },
    }


def build_pdf_brief_payload(brief_row) -> dict:
    if not brief_row:
        return {"available": False, "title": "当日未上传每日分析简报", "original_name": "", "blocks": []}

    stored_path = Path(brief_row["stored_path"]) if brief_row["stored_path"] else None
    brief_source = parse_brief_from_source(stored_path, brief_row["content"] or "")
    return {
        "available": True,
        "title": brief_row["title"],
        "original_name": brief_row["original_name"],
        "blocks": brief_source["blocks"],
    }


def fallback_render_payload(section_title: str, text: str, status: str) -> dict:
    if not text:
        groups = [{"title": None, "level": 1, "category": None, "blocks": []}]
    else:
        groups = [{"title": None, "level": 1, "category": None, "blocks": [{"type": "paragraph", "text": text}]}]
    return {
        "section_title": section_title,
        "template_name": "intelligence",
        "template_label": "内容版式",
        "groups": groups,
        "outline": [],
        "card_count": 0,
        "table_count": 0,
        "status_counts": infer_render_status_counts(status, {"groups": groups}, text),
    }


def infer_render_status_counts(status: str, render_payload: dict, raw_content: str) -> dict:
    cards = extract_cards_from_render_payload(render_payload)
    if cards:
        counts = {label: 0 for label in ITEM_STATUS_ORDER}
        for card in cards:
            card_status = card.get("status", status)
            if card_status == "待人工复核":
                card_status = "更新"
            if card_status not in counts:
                counts[card_status] = 0
            counts[card_status] += 1
        return counts
    return {
        "新增": 1 if status == "新增" and raw_content.strip() else 0,
        "更新": 1 if status == "更新" and raw_content.strip() else 0,
        "背景补充": 1 if status == "背景补充" and raw_content.strip() else 0,
        "历史保留": 1 if status == "历史保留" else 0,
        "占位项": 1 if status == "占位项" and raw_content.strip() else 0,
        "无内容": 1 if status == "无内容" else 0,
    }


def load_row_render_payload(row) -> dict:
    if not row:
        return fallback_render_payload("", "", "无内容")
    metadata = load_json(row["metadata_json"], {})
    render_payload = metadata.get("display_render") or metadata.get("raw_render")
    if render_payload:
        render_payload = normalize_render_payload(render_payload)
        render_payload.setdefault("status_counts", infer_render_status_counts(row["status"], render_payload, row["display_content"] or row["raw_content"] or ""))
        return render_payload
    section_title = row["section_title"] if "section_title" in row.keys() else row["section_key"]
    return fallback_render_payload(section_title, row["display_content"] or row["raw_content"], row["status"])


def build_section_parser_meta(section_model: dict) -> dict:
    return {
        "section_number": section_model.get("section_number"),
        "matched_heading": section_model.get("matched_heading"),
        "start_block_index": section_model.get("start_block_index"),
        "end_block_index": section_model.get("end_block_index"),
        "start_paragraph_index": section_model.get("start_paragraph_index"),
        "end_paragraph_index": section_model.get("end_paragraph_index"),
        "content_block_count": section_model.get("content_block_count", 0),
        "content_length": len(section_model.get("plain_text", "") or ""),
        "preview_head": (section_model.get("plain_text", "") or "")[:300],
        "preview_tail": (section_model.get("plain_text", "") or "")[-300:] if section_model.get("plain_text") else "",
    }


def resolve_section_key(section_key: str) -> str:
    return SECTION_KEY_ALIASES.get(section_key, section_key)


def get_file_library_view() -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        content_version = build_read_content_version(connection, include_exports=True)

    cache_key = f"library_overview:{content_version}"
    library_view, _from_cache = get_or_build_cached_read_view(
        cache_key,
        _build_file_library_view_base,
    )
    return library_view


def _build_file_library_view_base() -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        document_rows = connection.execute(
            """
            SELECT *
            FROM documents
            WHERE lifecycle_status != 'deleted'
            ORDER BY report_date DESC, uploaded_at DESC
            """
        ).fetchall()
        export_rows = connection.execute(
            """
            SELECT *
            FROM export_files
            WHERE status != 'deleted'
            ORDER BY report_date DESC, created_at DESC
            """
        ).fetchall()

    drafts = []
    briefs = []
    archived_drafts = []
    exports = []
    summary = defaultdict(int)

    for row in document_rows:
        item = build_library_document_row(row)
        summary["documents"] += 1
        summary[row["lifecycle_status"]] += 1
        if row["is_current"] and row["lifecycle_status"] == "active":
            summary["current_effective"] += 1
        if row["doc_type"] == "draft":
            drafts.append(item)
            if row["is_current"] and row["lifecycle_status"] == "active":
                summary["current_effective_drafts"] += 1
            if row["lifecycle_status"] != "active":
                archived_drafts.append(item)
        elif row["doc_type"] == "brief":
            briefs.append(item)
            summary["retained_assets"] += 1

    for row in export_rows:
        exports.append(build_library_export_row(row))
        summary["exports"] += 1

    return {
        "summary": dict(summary),
        "drafts": drafts,
        "briefs": briefs,
        "exports": exports,
        "archived_files": archived_drafts,
        "current_draft": next((item for item in drafts if item["is_current"]), None),
    }


def build_library_document_row(row) -> dict:
    status = row["lifecycle_status"]
    return {
        "id": row["id"],
        "kind": "document",
        "doc_type": row["doc_type"],
        "doc_type_label": DOCUMENT_TYPE_LABELS.get(row["doc_type"], row["doc_type"]),
        "name": row["original_name"],
        "file_ext": row["file_ext"],
        "uploaded_at": row["uploaded_at"],
        "report_date": row["report_date"],
        "status": status,
        "status_label": FILE_STATUS_LABELS[status],
        "status_class": FILE_STATUS_CLASS_MAP[status],
        "is_current": bool(row["is_current"] and status == "active"),
        "stored_path": row["stored_path"],
        "detail_url": f"/library/document/{row['id']}",
        "download_url": f"/library/document/{row['id']}/download",
        "can_withdraw": status == "active",
        "can_activate": status in {"archived", "withdrawn"},
        "can_delete": status != "deleted",
    }


def build_library_export_row(row) -> dict:
    status = row["status"] or "active"
    return {
        "id": row["id"],
        "kind": "export",
        "doc_type": "export",
        "doc_type_label": DOCUMENT_TYPE_LABELS["export"],
        "name": row["file_name"],
        "file_ext": row["file_ext"],
        "uploaded_at": row["created_at"],
        "report_date": row["report_date"],
        "status": status,
        "status_label": "可下载" if status == "active" else FILE_STATUS_LABELS.get(status, status),
        "status_class": "tag-active" if status == "active" else FILE_STATUS_CLASS_MAP.get(status, "tag-empty"),
        "is_current": False,
        "stored_path": row["stored_path"],
        "detail_url": f"/library/export/{row['id']}",
        "download_url": f"/library/export/{row['id']}/download",
        "can_withdraw": False,
        "can_activate": False,
        "can_delete": status != "deleted",
    }


def get_document_library_detail(document_id: int) -> dict | None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            return None
        same_day_rows = connection.execute(
            """
            SELECT *
            FROM documents
            WHERE report_date = ?
              AND doc_type = ?
            ORDER BY uploaded_at DESC
            """,
            (row["report_date"], row["doc_type"]),
        ).fetchall()
        section_rows = []
        if row["doc_type"] == "draft":
            section_rows = connection.execute(
                "SELECT section_key, section_title, status, note FROM sections WHERE document_id = ? ORDER BY id ASC",
                (document_id,),
            ).fetchall()

    metadata = load_json(row["metadata_json"], {})
    return {
        "kind": "document",
        "id": row["id"],
        "name": row["original_name"],
        "doc_type": row["doc_type"],
        "doc_type_label": DOCUMENT_TYPE_LABELS.get(row["doc_type"], row["doc_type"]),
        "report_date": row["report_date"],
        "uploaded_at": row["uploaded_at"],
        "status": row["lifecycle_status"],
        "status_label": FILE_STATUS_LABELS[row["lifecycle_status"]],
        "status_class": FILE_STATUS_CLASS_MAP[row["lifecycle_status"]],
        "is_current": bool(row["is_current"] and row["lifecycle_status"] == "active"),
        "stored_path": row["stored_path"],
        "parsed_path": row["parsed_path"],
        "title": row["title"],
        "file_ext": row["file_ext"],
        "metadata": metadata,
        "same_day_versions": [build_library_document_row(item) for item in same_day_rows],
        "can_delete": row["lifecycle_status"] != "deleted",
        "sections": [
            {
                "section_key": section["section_key"],
                "section_title": section["section_title"],
                "status": section["status"],
                "status_class": STATUS_CLASS_MAP[section["status"]],
                "note": section["note"],
            }
            for section in section_rows
        ],
    }


def get_export_library_detail(export_id: int) -> dict | None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM export_files WHERE id = ?", (export_id,)).fetchone()
    if not row:
        return None
    return {
        "kind": "export",
        "id": row["id"],
        "name": row["file_name"],
        "doc_type": "export",
        "doc_type_label": DOCUMENT_TYPE_LABELS["export"],
        "report_date": row["report_date"],
        "uploaded_at": row["created_at"],
        "status": row["status"],
        "status_label": "可下载" if row["status"] == "active" else FILE_STATUS_LABELS.get(row["status"], row["status"]),
        "status_class": "tag-active" if row["status"] == "active" else FILE_STATUS_CLASS_MAP.get(row["status"], "tag-empty"),
        "is_current": False,
        "stored_path": row["stored_path"],
        "parsed_path": "",
        "title": row["file_name"],
        "file_ext": row["file_ext"],
        "metadata": load_json(row["metadata_json"], {}),
        "same_day_versions": [],
        "sections": [],
        "can_delete": row["status"] != "deleted",
    }


def withdraw_document(document_id: int) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise ValueError("未找到要撤回的文件。")
        if row["lifecycle_status"] == "withdrawn":
            return {"report_date": row["report_date"], "doc_type": row["doc_type"], "name": row["original_name"]}

        was_current = bool(row["is_current"] and row["lifecycle_status"] == "active")
        set_document_status(connection, row, "withdrawn", is_current=False)

        if was_current:
            replacement = select_replacement_document(connection, row["report_date"], row["doc_type"], exclude_id=row["id"])
            if replacement:
                activate_document_row(connection, replacement)
                archive_same_day_siblings(connection, replacement)

        connection.commit()

    if row["doc_type"] == "draft":
        rebuild_effective_chain_from(row["report_date"])

    return {"report_date": row["report_date"], "doc_type": row["doc_type"], "name": row["original_name"]}


def activate_document(document_id: int) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise ValueError("未找到要启用的文件。")

        activate_document_row(connection, row)
        archive_same_day_siblings(connection, row)
        connection.commit()

    if row["doc_type"] == "draft":
        rebuild_effective_chain_from(row["report_date"])

    return {"report_date": row["report_date"], "doc_type": row["doc_type"], "name": row["original_name"]}


def delete_document(document_id: int) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM documents WHERE id = ?", (document_id,)).fetchone()
        if not row:
            raise ValueError("未找到要删除的文件。")
        if row["lifecycle_status"] == "deleted":
            return {"report_date": row["report_date"], "doc_type": row["doc_type"], "name": row["original_name"]}

        was_current = bool(row["is_current"] and row["lifecycle_status"] == "active")
        set_document_status(connection, row, "deleted", is_current=False)

        if was_current:
            replacement = select_replacement_document(connection, row["report_date"], row["doc_type"], exclude_id=row["id"])
            if replacement:
                activate_document_row(connection, replacement)
                archive_same_day_siblings(connection, replacement)

        connection.commit()

    if row["doc_type"] == "draft":
        rebuild_effective_chain_from(row["report_date"])

    return {"report_date": row["report_date"], "doc_type": row["doc_type"], "name": row["original_name"]}


def activate_document_row(connection: sqlite3.Connection, row) -> None:
    target_path = move_document_to_status(row, "active")
    connection.execute(
        """
        UPDATE documents
        SET lifecycle_status = 'active',
            withdrawn_at = NULL,
            is_current = 1,
            stored_path = ?
        WHERE id = ?
        """,
        (str(target_path), row["id"]),
    )


def archive_same_day_siblings(connection: sqlite3.Connection, active_row) -> None:
    sibling_rows = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE report_date = ?
          AND doc_type = ?
          AND id != ?
          AND lifecycle_status NOT IN ('withdrawn', 'deleted')
        ORDER BY uploaded_at DESC
        """,
        (active_row["report_date"], active_row["doc_type"], active_row["id"]),
    ).fetchall()
    for sibling in sibling_rows:
        set_document_status(connection, sibling, "archived", is_current=False)


def select_replacement_document(connection: sqlite3.Connection, report_date: str, doc_type: str, exclude_id: int):
    return connection.execute(
        """
        SELECT *
        FROM documents
        WHERE report_date = ?
          AND doc_type = ?
          AND id != ?
          AND lifecycle_status NOT IN ('withdrawn', 'deleted')
        ORDER BY uploaded_at DESC
        LIMIT 1
        """,
        (report_date, doc_type, exclude_id),
    ).fetchone()


def set_document_status(connection: sqlite3.Connection, row, status: str, is_current: bool) -> None:
    target_path = move_document_to_status(row, status)
    connection.execute(
        """
        UPDATE documents
        SET lifecycle_status = ?,
            withdrawn_at = ?,
            is_current = ?,
            stored_path = ?
        WHERE id = ?
        """,
        (
            status,
            now_string() if status == "withdrawn" else None,
            1 if is_current else 0,
            str(target_path),
            row["id"],
        ),
    )


def build_library_path(status: str, doc_type: str, report_date: str, stored_name: str) -> Path:
    folder_name = FILE_LIBRARY_FOLDER_MAP.get(doc_type, "files")
    return current_app.config["FILE_LIBRARY_ROOT"] / status / folder_name / report_date / stored_name


def build_export_path(status: str, report_date: str, file_name: str) -> Path:
    if status == "active":
        return current_app.config["EXPORT_ROOT"] / file_name
    return current_app.config["EXPORT_ROOT"] / f"_{status}" / report_date / file_name


def move_document_to_status(row, status: str) -> Path:
    current_path = Path(row["stored_path"]) if row["stored_path"] else None
    target_path = build_library_path(status, row["doc_type"], row["report_date"], row["stored_name"])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if current_path and current_path.exists() and current_path.resolve() != target_path.resolve():
        if target_path.exists() and target_path.resolve() != current_path.resolve():
            target_path = ensure_unique_path(target_path)
        current_path.replace(target_path)
    return target_path


def move_export_to_status(row, status: str) -> Path:
    current_path = Path(row["stored_path"]) if row["stored_path"] else None
    target_path = build_export_path(status, row["report_date"], row["file_name"])
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if current_path and current_path.exists() and current_path.resolve() != target_path.resolve():
        if target_path.exists() and target_path.resolve() != current_path.resolve():
            target_path = ensure_unique_path(target_path)
        current_path.replace(target_path)
    return target_path


def ensure_unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}_{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def get_document_download_path(document_id: int) -> Path:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            "SELECT stored_path, lifecycle_status FROM documents WHERE id = ?",
            (document_id,),
        ).fetchone()
    if not row:
        raise ValueError("未找到文件。")
    if row["lifecycle_status"] == "deleted":
        raise ValueError("该文件已删除。")
    return ensure_path_within_roots(
        row["stored_path"],
        [current_app.config["FILE_LIBRARY_ROOT"]],
        label="文件下载",
    )


def get_export_download_path(export_id: int) -> Path:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            "SELECT stored_path, status FROM export_files WHERE id = ?",
            (export_id,),
        ).fetchone()
    if not row:
        raise ValueError("未找到导出文件。")
    if row["status"] == "deleted":
        raise ValueError("该导出文件已删除。")
    return ensure_path_within_roots(
        row["stored_path"],
        [current_app.config["EXPORTS_ROOT"]],
        label="导出文件",
    )


def delete_export_file(export_id: int) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM export_files WHERE id = ?", (export_id,)).fetchone()
        if not row:
            raise ValueError("未找到要删除的导出文件。")
        if row["status"] == "deleted":
            return {"report_date": row["report_date"], "name": row["file_name"]}

        target_path = move_export_to_status(row, "deleted")
        connection.execute(
            """
            UPDATE export_files
            SET status = 'deleted',
                stored_path = ?
            WHERE id = ?
            """,
            (str(target_path), row["id"]),
        )
        connection.commit()

    return {"report_date": row["report_date"], "name": row["file_name"]}


def get_current_document(connection: sqlite3.Connection, report_date: str, doc_type: str):
    return connection.execute(
        """
        SELECT *
        FROM documents
        WHERE report_date = ?
          AND doc_type = ?
          AND is_current = 1
          AND lifecycle_status = 'active'
        ORDER BY uploaded_at DESC
        LIMIT 1
        """,
        (report_date, doc_type),
    ).fetchone()


def upgrade_existing_documents() -> None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        normalize_existing_document_statuses(connection)
        sync_document_storage(connection)
        sync_existing_exports(connection)

        current_rows = connection.execute(
            """
            SELECT *
            FROM documents
            WHERE is_current = 1
              AND lifecycle_status = 'active'
            ORDER BY report_date ASC, uploaded_at ASC
            """
        ).fetchall()

        draft_rows = [row for row in current_rows if row["doc_type"] == "draft"]
        brief_rows = [row for row in current_rows if row["doc_type"] == "brief"]
        current_entry_count = connection.execute(
            """
            SELECT COUNT(1) AS count
            FROM entries
            WHERE is_current_chain = 1
              AND is_deleted = 0
            """
        ).fetchone()["count"]
        total_entry_count = connection.execute(
            """
            SELECT COUNT(1) AS count
            FROM entries
            """
        ).fetchone()["count"]
        section_count = connection.execute(
            """
            SELECT COUNT(1) AS count
            FROM sections
            """
        ).fetchone()["count"]
        preserve_existing_content = total_entry_count > 0 or section_count > 0
        start_date = None
        if not preserve_existing_content and draft_rows and any(
            needs_upgrade(row) or missing_sections(connection, row["id"]) for row in draft_rows
        ):
            start_date = draft_rows[0]["report_date"]
        needs_full_rebuild = bool(draft_rows) and current_entry_count == 0 and total_entry_count == 0 and section_count == 0

        if not preserve_existing_content and brief_rows and any(needs_upgrade(row) for row in brief_rows):
            reparse_current_briefs(connection, brief_rows)

        connection.commit()

    if start_date:
        rebuild_effective_chain_from(start_date)
        return

    if needs_full_rebuild:
        rebuild_repaired_entries(write_reports=False)


def normalize_existing_document_statuses(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT * FROM documents ORDER BY id ASC").fetchall()
    for row in rows:
        lifecycle_status = row["lifecycle_status"] or "active"
        if lifecycle_status == "active" and not row["is_current"]:
            lifecycle_status = "archived"
        if lifecycle_status == "withdrawn" and row["is_current"]:
            connection.execute("UPDATE documents SET is_current = 0 WHERE id = ?", (row["id"],))
        if lifecycle_status != row["lifecycle_status"]:
            connection.execute("UPDATE documents SET lifecycle_status = ? WHERE id = ?", (lifecycle_status, row["id"]))


def sync_document_storage(connection: sqlite3.Connection) -> None:
    rows = connection.execute("SELECT * FROM documents ORDER BY id ASC").fetchall()
    for row in rows:
        current_status = row["lifecycle_status"] or ("active" if row["is_current"] else "archived")
        target_path = build_library_path(current_status, row["doc_type"], row["report_date"], row["stored_name"])
        target_path.parent.mkdir(parents=True, exist_ok=True)
        current_path = Path(row["stored_path"]) if row["stored_path"] else None
        final_path = target_path
        if current_path and current_path.exists() and current_path.resolve() != target_path.resolve():
            if target_path.exists() and target_path.resolve() != current_path.resolve():
                final_path = ensure_unique_path(target_path)
            current_path.replace(final_path)
        connection.execute("UPDATE documents SET stored_path = ? WHERE id = ?", (str(final_path), row["id"]))


def sync_existing_exports(connection: sqlite3.Connection) -> None:
    known_paths = {
        row["stored_path"]
        for row in connection.execute("SELECT stored_path FROM export_files WHERE status != 'deleted'").fetchall()
    }
    for export_path in current_app.config["EXPORT_ROOT"].glob("*.pdf"):
        if str(export_path) in known_paths:
            continue
        report_date = detect_date_from_filename(export_path.name) or today_string()
        connection.execute(
            """
            INSERT INTO export_files (
                report_date, file_name, stored_path, file_ext, created_at, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, 'active', ?)
            """,
            (
                report_date,
                export_path.name,
                str(export_path),
                export_path.suffix.lower(),
                now_string(),
                json.dumps({"synced_from_disk": True}, ensure_ascii=False),
            ),
        )


def needs_upgrade(row) -> bool:
    metadata = load_json(row["metadata_json"], {})
    return metadata.get("parser_version") != PARSER_VERSION


def missing_sections(connection: sqlite3.Connection, document_id: int) -> bool:
    count = connection.execute("SELECT COUNT(1) AS count FROM sections WHERE document_id = ?", (document_id,)).fetchone()["count"]
    return count == 0


def reparse_current_briefs(connection: sqlite3.Connection, brief_rows: list) -> None:
    for row in brief_rows:
        stored_path = Path(row["stored_path"]) if row["stored_path"] else None
        parsed_document = parse_document(stored_path, "brief", row["content"] or "", row["report_date"])
        metadata = load_json(row["metadata_json"], {})
        metadata.update(parsed_document["document_metadata"])
        metadata["recognition_note"] = metadata.get("recognition_note", "")
        connection.execute(
            "UPDATE documents SET title = ?, content = ?, html_content = ?, metadata_json = ? WHERE id = ?",
            (
                parsed_document["title"],
                parsed_document["content"],
                parsed_document["html_content"],
                json.dumps(metadata, ensure_ascii=False),
                row["id"],
            ),
        )


def rebuild_effective_chain_from(start_date: str) -> None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM documents
            WHERE doc_type = 'draft'
              AND is_current = 1
              AND lifecycle_status = 'active'
              AND report_date >= ?
            ORDER BY report_date ASC, uploaded_at ASC
            """,
            (start_date,),
        ).fetchall()
        if not rows:
            return

        document_ids = [row["id"] for row in rows]
        if document_ids:
            placeholders = ",".join("?" for _ in document_ids)
            connection.execute(
                f"UPDATE sections SET previous_section_id = NULL WHERE previous_section_id IN (SELECT id FROM sections WHERE document_id IN ({placeholders}))",
                document_ids,
            )
            connection.execute(
                f"DELETE FROM sections WHERE document_id IN ({placeholders})",
                document_ids,
            )

        for row in rows:
            stored_path = Path(row["stored_path"]) if row["stored_path"] else None
            parsed_document = parse_document(stored_path, "draft", row["content"] or "", row["report_date"])
            metadata = load_json(row["metadata_json"], {})
            recognition_note = metadata.get("recognition_note", "")
            metadata.update(parsed_document["document_metadata"])

            connection.execute(
                "UPDATE documents SET title = ?, content = ?, html_content = ?, metadata_json = ? WHERE id = ?",
                (
                    parsed_document["title"],
                    parsed_document["content"],
                    parsed_document["html_content"],
                    json.dumps(metadata, ensure_ascii=False),
                    row["id"],
                ),
            )

            section_records = create_section_snapshots(connection, row["id"], row["report_date"], parsed_document["sections"])
            write_document_archive(
                connection,
                document_id=row["id"],
                report_date=row["report_date"],
                doc_type="draft",
                original_name=row["original_name"],
                stored_path=stored_path or Path(row["stored_path"]),
                title=parsed_document["title"],
                content=parsed_document["content"],
                recognition_note=recognition_note,
                sections=section_records,
                uploaded_at=row["uploaded_at"],
                document_metadata=parsed_document["document_metadata"],
            )

        connection.commit()

    rebuild_repaired_entries(write_reports=False)
