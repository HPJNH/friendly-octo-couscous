from __future__ import annotations

import html
import re
from typing import Any

from .constants import STATUS_CLASS_MAP
from .utils import normalize_compare_text


FIELD_ALIASES = {
    "title": ["标题", "事项", "主题", "名称", "对象名称", "账号", "账号/对象名称"],
    "time": ["时间", "日期", "发布时间", "监测时间"],
    "source": ["来源", "出处", "信息来源", "渠道"],
    "info_type": ["信息类型", "类型", "类别"],
    "content_type": ["内容类型"],
    "direction": ["观察方向", "方向"],
    "core_content": ["核心内容", "内容", "关键信息", "核心信息", "核心事实", "要点"],
    "why": ["为什么值得纳入", "为什么重要", "纳入原因", "观察价值", "为什么值得关注"],
    "value": ["观察价值", "对我方意义", "价值", "研判价值"],
    "object_name": ["对象名称", "对象", "账号名称", "主体"],
    "keywords": ["高频词", "关键词", "标签"],
    "activity_mechanism": ["活动机制", "机制"],
    "price_clues": ["价格线索", "价格", "价格带"],
}

DATE_HINT_PATTERN = re.compile(
    r"(20\d{2}[.\-年/]\d{1,2}[.\-月/]\d{1,2}日?)|(\d{1,2}月\d{1,2}日)"
)


def build_section_render_payload(section_key: str, section_title: str, blocks: list[dict], status: str) -> dict[str, Any]:
    template_name = choose_section_template(section_key)
    groups = group_blocks(section_key, blocks, status)
    outline = [group["title"] for group in groups if group.get("title")]
    card_count = len(extract_cards_from_render_payload({"groups": groups}))
    table_count = sum(
        1 for group in groups for block in group["blocks"] if block["type"] == "table"
    )
    return {
        "section_key": section_key,
        "section_title": section_title,
        "template_name": template_name,
        "template_label": template_label(template_name),
        "groups": groups,
        "outline": outline,
        "card_count": card_count,
        "table_count": table_count,
        "status_counts": {"新增": 0, "更新": 0, "历史保留": 0, "无内容": 0},
    }


def build_brief_html(blocks: list[dict]) -> str:
    html_parts: list[str] = []
    has_title = False

    for block in blocks:
        if block["type"] == "heading":
            level = min(max(block.get("level", 2), 2), 4)
            html_parts.append(f"<h{level}>{format_inline(block['text'])}</h{level}>")
            continue

        if block["type"] == "table":
            headers, rows = split_table_rows(block["rows"])
            if not headers:
                continue
            html_parts.append("<div class=\"table-scroll\"><table class=\"detail-table\">")
            html_parts.append("<thead><tr>")
            html_parts.extend(f"<th>{format_inline(cell)}</th>" for cell in headers)
            html_parts.append("</tr></thead><tbody>")
            for row in rows:
                html_parts.append("<tr>")
                html_parts.extend(f"<td>{format_inline(cell)}</td>" for cell in row)
                html_parts.append("</tr>")
            html_parts.append("</tbody></table></div>")
            continue

        text = block["text"]
        if not has_title and len(text) <= 40:
            html_parts.append(f"<h2>{format_inline(text)}</h2>")
            has_title = True
            continue

        if re.match(r"^\s*\d+\.\s*", text):
            html_parts.append(f"<h3>{format_inline(text)}</h3>")
            continue

        if re.match(r"^\s*信号[一二三四五六七八九十0-9]+[：:]", text):
            html_parts.append(f"<h4>{format_inline(text)}</h4>")
            continue

        html_parts.append(f"<p>{format_inline(text)}</p>")

    return "".join(html_parts)


def choose_section_template(section_key: str) -> str:
    if section_key == "report_note":
        return "rules"
    if section_key == "policy_env":
        return "policy"
    if section_key == "douyin_monitoring":
        return "monitoring"
    return "intelligence"


def template_label(template_name: str) -> str:
    labels = {
        "rules": "说明型版式",
        "policy": "政策分层版式",
        "monitoring": "监测卡片版式",
        "intelligence": "情报卡片版式",
    }
    return labels.get(template_name, "内容版式")


def group_blocks(section_key: str, blocks: list[dict], status: str) -> list[dict]:
    groups: list[dict] = []
    current_group = new_group()
    groups.append(current_group)

    for block in blocks:
        if block["type"] == "heading":
            current_group = new_group(
                title=block["text"],
                level=block.get("level", 2),
                category=detect_group_category(section_key, block["text"]),
            )
            groups.append(current_group)
            continue

        rendered_block = transform_block(section_key, block, status)
        if rendered_block:
            current_group["blocks"].append(rendered_block)

    return [group for group in groups if group["blocks"] or group.get("title")]


def new_group(title: str | None = None, level: int = 1, category: str | None = None) -> dict[str, Any]:
    return {"title": title, "level": level, "category": category, "blocks": []}


def detect_group_category(section_key: str, heading_text: str) -> str | None:
    if section_key == "policy_env":
        if "国家层" in heading_text:
            return "国家层"
        if "海南省层" in heading_text:
            return "海南省层"
        if "儋州" in heading_text or "洋浦" in heading_text:
            return "儋州 / 洋浦层"
    if section_key == "douyin_monitoring":
        if "A层" in heading_text:
            return "A层优先监测"
        if "B层" in heading_text:
            return "B层补充监测"
        if "C层" in heading_text:
            return "C层关键词监测"
        if "复核" in heading_text:
            return "重点复核线索"
    return None


def transform_block(section_key: str, block: dict, status: str) -> dict[str, Any] | None:
    if block["type"] == "paragraph":
        card = extract_paragraph_card(section_key, block["text"], status)
        if card:
            return {"type": "card", "card": card}
        return {"type": "paragraph", "text": block["text"]}

    if block["type"] == "table":
        headers, rows = split_table_rows(block["rows"])
        cards = extract_cards_from_table(headers, rows, status)
        return {
            "type": "table",
            "headers": headers,
            "rows": rows,
            "cards": cards,
            "summary": f"{len(rows)} 行 × {len(headers)} 列" if headers else f"{len(rows)} 行表格",
        }

    return None


def split_table_rows(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    cleaned_rows = [trim_row(row) for row in rows if any(cell.strip() for cell in row)]
    if not cleaned_rows:
        return [], []
    if len(cleaned_rows) == 1:
        return cleaned_rows[0], []
    return cleaned_rows[0], cleaned_rows[1:]


def trim_row(row: list[str]) -> list[str]:
    last_non_empty = 0
    for index, value in enumerate(row, start=1):
        if value.strip():
            last_non_empty = index
    clipped = row[:last_non_empty] if last_non_empty else row
    return [cell.strip() for cell in clipped]


def extract_cards_from_table(headers: list[str], rows: list[list[str]], status: str) -> list[dict[str, Any]]:
    if not headers or not rows:
        return []

    mapping = map_table_headers(headers)
    mapped_count = len([key for key in mapping.values() if key])
    cards = []
    for index, row in enumerate(rows, start=1):
        row_map = {}
        for column_index, header in enumerate(headers):
            value = row[column_index].strip() if column_index < len(row) else ""
            canonical_key = mapping.get(column_index)
            if canonical_key and value:
                row_map[canonical_key] = value

        if mapped_count >= 3:
            title = row_map.get("title") or row_map.get("object_name") or f"情报项 {index}"
            core_content = row_map.get("core_content", "")
            if not title and not core_content:
                continue

            tags = build_card_tags(row_map)
            cards.append(
                build_card(
                    title=title,
                    status=status,
                    time=row_map.get("time"),
                    source=row_map.get("source"),
                    core_content=core_content,
                    why=row_map.get("why") or row_map.get("value"),
                    tags=tags,
                    compare_meta={
                        "title": title,
                        "time": row_map.get("time", ""),
                        "source": row_map.get("source", ""),
                        "object_name": row_map.get("object_name", ""),
                        "core_content": core_content,
                        "why": row_map.get("why") or row_map.get("value", ""),
                        "tags": tags,
                    },
                )
            )
            continue

        generic_card = build_generic_table_card(headers, row, index, status)
        if generic_card:
            cards.append(generic_card)

    return cards


def map_table_headers(headers: list[str]) -> dict[int, str | None]:
    mapping: dict[int, str | None] = {}
    for index, header in enumerate(headers):
        normalized = normalize_compare_text(header)
        matched_key = None
        for key, aliases in FIELD_ALIASES.items():
            if any(normalize_compare_text(alias) in normalized or normalized in normalize_compare_text(alias) for alias in aliases):
                matched_key = key
                break
        mapping[index] = matched_key
    return mapping


def extract_paragraph_card(section_key: str, text: str, status: str) -> dict[str, Any] | None:
    stripped = text.strip()
    if not stripped:
        return None

    if section_key == "report_note":
        label, body = split_label_value(stripped, max_label_length=24)
        if label and body:
            return build_card(
                title=label,
                status=status,
                core_content=body,
                style="rule",
                compare_meta={"title": label, "core_content": body, "object_name": label},
            )
        return build_card(
            title="说明",
            status=status,
            core_content=stripped,
            style="rule",
            compare_meta={"title": "说明", "core_content": stripped, "object_name": "说明"},
        )

    label, body = split_label_value(stripped, max_label_length=34)
    if not label or not body:
        return None

    tags = []
    time_hint = extract_date_hint(label) or extract_date_hint(body)

    if section_key == "douyin_monitoring":
        if any(keyword in label for keyword in ("直播", "视频", "评论区", "话题")):
            tags.append(label)
        return build_card(
            title=label,
            status=status,
            time=time_hint,
            core_content=body,
            tags=tags,
            style="monitor",
            compare_meta={"title": label, "time": time_hint or "", "core_content": body, "tags": tags, "object_name": label},
        )

    return build_card(
        title=label,
        status=status,
        time=time_hint,
        core_content=body,
        compare_meta={"title": label, "time": time_hint or "", "core_content": body, "object_name": label},
    )


def split_label_value(text: str, max_label_length: int) -> tuple[str | None, str | None]:
    for separator in ("：", ":"):
        if separator not in text:
            continue
        label, body = text.split(separator, 1)
        label = label.strip(" *\u3000")
        body = body.strip()
        if label and body and len(label) <= max_label_length:
            return label, body
    return None, None


def extract_date_hint(text: str) -> str | None:
    match = DATE_HINT_PATTERN.search(text)
    return match.group(0) if match else None


def build_card_tags(row_map: dict[str, str]) -> list[str]:
    tags = []
    for key in ("info_type", "content_type", "direction", "object_name", "keywords", "activity_mechanism", "price_clues"):
        value = row_map.get(key)
        if not value:
            continue
        for piece in split_tag_values(value):
            if piece not in tags:
                tags.append(piece)
    return tags[:8]


def split_tag_values(value: str) -> list[str]:
    parts = re.split(r"[、,，/｜|；;]\s*", value)
    return [part.strip() for part in parts if part.strip()]


def build_card(
    title: str,
    status: str,
    core_content: str,
    time: str | None = None,
    source: str | None = None,
    why: str | None = None,
    tags: list[str] | None = None,
    style: str = "intelligence",
    source_url: str | None = None,
    source_title: str | None = None,
    supporting_sources: list[dict[str, Any]] | None = None,
    first_seen: str | None = None,
    last_seen: str | None = None,
    confidence_level: str | None = None,
    needs_review: bool = False,
    compare_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "title": title.strip(),
        "time": time,
        "source": source,
        "source_url": source_url,
        "source_title": source_title or title.strip(),
        "supporting_sources": supporting_sources or [],
        "first_seen": first_seen,
        "last_seen": last_seen,
        "confidence_level": confidence_level,
        "needs_review": needs_review,
        "core_content": core_content.strip(),
        "why": why.strip() if why else "",
        "tags": tags or [],
        "style": style,
        "status": status,
        "status_class": STATUS_CLASS_MAP.get(status, ""),
        "compare_meta": compare_meta or {},
    }


def format_inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped.replace("\n", "<br>")


def build_generic_table_card(headers: list[str], row: list[str], index: int, status: str) -> dict[str, Any] | None:
    pairs = []
    for column_index, header in enumerate(headers):
        value = row[column_index].strip() if column_index < len(row) else ""
        if header.strip() and value:
            pairs.append((header.strip(), value))
    if not pairs:
        return None

    title = pairs[0][1]
    time_value = ""
    source_value = ""
    why_value = ""
    content_lines = []
    tags = []
    for header, value in pairs[1:]:
        normalized_header = normalize_compare_text(header)
        if not time_value and "时间" in normalized_header:
            time_value = value
            continue
        if not source_value and ("来源" in normalized_header or "出处" in normalized_header):
            source_value = value
            continue
        if not why_value and ("价值" in normalized_header or "原因" in normalized_header):
            why_value = value
            continue
        content_lines.append(f"{header}：{value}")
        if len(tags) < 5:
            tags.append(header)

    core_content = "\n".join(content_lines) if content_lines else title
    return build_card(
        title=title or f"情报项 {index}",
        status=status,
        time=time_value or None,
        source=source_value or None,
        core_content=core_content,
        why=why_value or None,
        tags=tags,
        compare_meta={
            "title": title,
            "time": time_value,
            "source": source_value,
            "core_content": core_content,
            "why": why_value,
            "tags": tags,
            "object_name": title,
        },
    )


def extract_cards_from_render_payload(render_payload: dict[str, Any]) -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    for group in render_payload.get("groups", []):
        group_title = group.get("title") or ""
        for block in group.get("blocks", []):
            if block.get("type") == "card":
                card = block["card"]
                card.setdefault("group_title", group_title)
                card.setdefault("compare_meta", {})
                card["compare_meta"].setdefault("group_title", group_title)
                cards.append(card)
            elif block.get("type") == "table":
                for card in block.get("cards", []):
                    card.setdefault("group_title", group_title)
                    card.setdefault("compare_meta", {})
                    card["compare_meta"].setdefault("group_title", group_title)
                    cards.append(card)
    return cards
