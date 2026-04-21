from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
import re

from docx import Document
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.table import Table
from docx.text.paragraph import Paragraph
from pypdf import PdfReader

from .constants import (
    BRIEF_KEYWORDS,
    DRAFT_KEYWORDS,
    DRAFT_MAIN_TITLE,
    DRAFT_REPORT_NOTE_SUBSECTIONS,
    DRAFT_STANDARD_SUBSECTION_ALIASES,
    DRAFT_STANDARD_SUBSECTIONS,
    DRAFT_STRUCTURED_TABLE_COLUMNS,
    DRAFT_STRUCTURED_TABLE_COLUMNS_V2,
    DRAFT_TAIL_PATTERNS,
    DRAFT_WINDOW_METADATA_LABELS,
    SECTION_DEFINITIONS,
)
from .utils import compact_text, normalize_heading


CHINESE_NUMBERS = ["十", "九", "八", "七", "六", "五", "四", "三", "二", "一"]
ARABIC_NUMBERS = [str(number) for number in range(10, 0, -1)]
SUBHEADING_PATTERN = re.compile(r"^\s*(?P<path>\d+(?:\.\d+)+)\s*(?P<title>.+?)\s*$")
TRAILING_HEADING_SUFFIX_PATTERN = re.compile(r"\s*[（(【\[].{0,18}[)）】\]]\s*$")
NON_BODY_TAIL_PATTERN = re.compile("|".join(re.escape(item) for item in DRAFT_TAIL_PATTERNS if item))
DATE_PATTERN = re.compile(r"(20\d{2})[.\-/年](\d{1,2})[.\-/月](\d{1,2})")
CHINESE_DATE_PATTERN = re.compile(r"(20\d{2})年(\d{1,2})月(\d{1,2})日")


class UnsupportedFileError(Exception):
    pass


def extract_text(file_path: Path) -> str:
    extension = file_path.suffix.lower()
    if extension == ".docx":
        return extract_docx_text(file_path)
    if extension in {".md", ".txt"}:
        return extract_plain_text(file_path)
    if extension == ".pdf":
        return extract_pdf_text(file_path)
    raise UnsupportedFileError(f"暂不支持的文件类型: {extension}")


def extract_docx_text(file_path: Path) -> str:
    blocks = extract_docx_blocks(file_path)
    return blocks_to_plain_text(blocks)


def extract_docx_blocks(file_path: Path) -> list[dict]:
    document = Document(file_path)
    blocks: list[dict] = []

    for item in iter_docx_block_items(document):
        if isinstance(item, Paragraph):
            block = build_paragraph_block(item)
        else:
            block = build_table_block(item)
        if block:
            blocks.append(block)

    return blocks


def sanitize_document_blocks(blocks: list[dict], trim_tail: bool = False) -> tuple[list[dict], list[str]]:
    cleaned_blocks: list[dict] = []
    for block in blocks:
        normalized = normalize_block(block)
        if normalized:
            cleaned_blocks.append(normalized)
    if trim_tail:
        return trim_non_body_tail(cleaned_blocks)
    return cleaned_blocks, []


def iter_docx_block_items(document: Document):
    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, document)
        elif isinstance(child, CT_Tbl):
            yield Table(child, document)


def build_paragraph_block(paragraph: Paragraph) -> dict | None:
    text = clean_text(paragraph.text)
    if not text:
        return None
    style_name = paragraph.style.name if paragraph.style else ""
    return {"type": "paragraph", "text": text, "style_name": style_name}


def build_table_block(table: Table) -> dict | None:
    rows: list[list[str]] = []
    for row in table.rows:
        cleaned_row = [clean_text(cell.text) for cell in row.cells]
        if any(cell for cell in cleaned_row):
            rows.append(cleaned_row)
    if not rows:
        return None
    return {"type": "table", "rows": rows}


def extract_plain_text(file_path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
        try:
            return compact_text(file_path.read_text(encoding=encoding))
        except UnicodeDecodeError:
            continue
    return compact_text(file_path.read_text(encoding="utf-8", errors="ignore"))


def extract_pdf_text(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    parts = [clean_text(page.extract_text() or "") for page in reader.pages]
    return compact_text("\n\n".join(part for part in parts if part))


def detect_document_type(filename: str, content: str) -> tuple[str, str]:
    if any(keyword in filename for keyword in DRAFT_KEYWORDS):
        return "draft", "根据文件名识别为研究底稿"
    if any(keyword in filename for keyword in BRIEF_KEYWORDS):
        return "brief", "根据文件名识别为每日分析简报"

    preview = content[:5000]
    heading_matches = 0
    for definition in SECTION_DEFINITIONS:
        if any(alias in preview for alias in definition["aliases"]):
            heading_matches += 1

    if "研究底稿" in preview or heading_matches >= 2:
        return "draft", "根据正文中的板块标题识别为研究底稿"

    if "简报" in preview or "今日判断" in preview or "核心结论" in preview:
        return "brief", "根据正文中的简报语义识别为每日分析简报"

    return "unknown", "未能自动识别文件类型"


def extract_brief_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip().lstrip("#").strip()
        if not stripped:
            continue
        if len(stripped) <= 50:
            return stripped
        break
    return fallback


def parse_draft_file(file_path: Path, fallback_text: str = "") -> dict:
    extension = file_path.suffix.lower()
    if extension == ".docx":
        blocks = extract_docx_blocks(file_path)
    else:
        text = fallback_text or extract_text(file_path)
        blocks = text_to_blocks(text)
    blocks, tail_hits = sanitize_document_blocks(blocks, trim_tail=True)
    sections = build_sections_from_blocks(blocks)
    return {
        "content": blocks_to_plain_text(blocks),
        "sections": sections,
        "tail_hits": tail_hits,
        "metadata": build_draft_metadata(sections),
    }


def parse_brief_file(file_path: Path, fallback_text: str = "") -> dict:
    extension = file_path.suffix.lower()
    if extension == ".docx":
        blocks = extract_docx_blocks(file_path)
    else:
        text = fallback_text or extract_text(file_path)
        blocks = text_to_blocks(text)
    blocks, tail_hits = sanitize_document_blocks(blocks, trim_tail=True)
    return {"content": blocks_to_plain_text(blocks), "blocks": annotate_section_blocks(blocks), "tail_hits": tail_hits}


def parse_draft_sections(content: str) -> dict[str, str]:
    blocks = text_to_blocks(content)
    sections = build_sections_from_blocks(blocks)
    return {key: value["plain_text"] for key, value in sections.items()}


def text_to_blocks(text: str) -> list[dict]:
    blocks: list[dict] = []
    buffer: list[str] = []

    for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = clean_text(raw_line)
        if not line:
            if buffer:
                blocks.append({"type": "paragraph", "text": "\n".join(buffer), "style_name": ""})
                buffer = []
            continue
        buffer.append(line)

    if buffer:
        blocks.append({"type": "paragraph", "text": "\n".join(buffer), "style_name": ""})

    return blocks


def normalize_block(block: dict) -> dict | None:
    if block["type"] == "paragraph":
        text = clean_text(block.get("text", ""))
        if not text:
            return None
        normalized = {"type": "paragraph", "text": text}
        if block.get("style_name") is not None:
            normalized["style_name"] = block.get("style_name", "")
        return normalized

    if block["type"] == "table":
        rows = []
        for row in block.get("rows", []):
            cleaned_row = [clean_text(cell) for cell in row]
            if any(cell for cell in cleaned_row):
                rows.append(cleaned_row)
        if not rows:
            return None
        return {"type": "table", "rows": rows}

    return block


def trim_non_body_tail(blocks: list[dict]) -> tuple[list[dict], list[str]]:
    tail_index: int | None = None
    tail_hits: list[str] = []
    trailing_texts: list[str] = []

    for index in range(len(blocks) - 1, -1, -1):
        block = blocks[index]
        if block["type"] != "paragraph":
            if tail_index is not None:
                break
            continue

        text = clean_text(block.get("text", ""))
        if not text:
            continue

        if NON_BODY_TAIL_PATTERN.search(text) or looks_like_non_body_tail(text):
            tail_index = index
            tail_hits.append(text)
            trailing_texts.clear()
            continue

        if tail_index is not None:
            if is_trivial_tail_line(text):
                tail_index = index
                tail_hits.append(text)
                continue
            break

        trailing_texts.append(text)

    if tail_index is None:
        return blocks, []

    trimmed = blocks[:tail_index]
    tail_hits.reverse()
    return trimmed, tail_hits


def build_sections_from_blocks(blocks: list[dict]) -> dict[str, dict]:
    sections = {
        definition["key"]: {
            "section_key": definition["key"],
            "section_number": definition["number"],
            "section_title": definition["title"],
            "blocks": [],
            "plain_text": "",
            "matched_heading": None,
            "start_block_index": None,
            "end_block_index": None,
            "start_paragraph_index": None,
            "end_paragraph_index": None,
            "content_block_count": 0,
        }
        for definition in SECTION_DEFINITIONS
    }

    preface_blocks: list[dict] = []
    current_section_key: str | None = None
    paragraph_index = 0
    last_content_block_index: int | None = None
    last_content_paragraph_index: int | None = None

    def close_current_section() -> None:
        nonlocal current_section_key, last_content_block_index, last_content_paragraph_index
        if current_section_key is None:
            return
        section_payload = sections[current_section_key]
        if last_content_block_index is not None:
            section_payload["end_block_index"] = last_content_block_index
        elif section_payload["start_block_index"] is not None:
            section_payload["end_block_index"] = section_payload["start_block_index"]

        if last_content_paragraph_index is not None:
            section_payload["end_paragraph_index"] = last_content_paragraph_index
        elif section_payload["start_paragraph_index"] is not None:
            section_payload["end_paragraph_index"] = section_payload["start_paragraph_index"]

    for block_index, block in enumerate(blocks):
        current_paragraph_index = None
        if block["type"] == "paragraph":
            paragraph_index += 1
            current_paragraph_index = paragraph_index
        if block["type"] == "paragraph":
            matched_key = match_section_heading(block["text"])
            if matched_key:
                close_current_section()
                current_section_key = matched_key
                last_content_block_index = None
                last_content_paragraph_index = None
                section_payload = sections[current_section_key]
                section_payload["matched_heading"] = clean_text(block["text"])
                section_payload["start_block_index"] = block_index
                section_payload["start_paragraph_index"] = current_paragraph_index
                continue

        if current_section_key is None:
            if not is_document_title(block):
                preface_blocks.append(block)
        else:
            sections[current_section_key]["blocks"].append(block)
            sections[current_section_key]["content_block_count"] += 1
            last_content_block_index = block_index
            if current_paragraph_index is not None:
                last_content_paragraph_index = current_paragraph_index

    if preface_blocks and not sections["report_note"]["blocks"]:
        sections["report_note"]["blocks"].extend(preface_blocks)
        sections["report_note"]["content_block_count"] += len(preface_blocks)

    close_current_section()
    for key, payload in sections.items():
        annotated_blocks = annotate_section_blocks(payload["blocks"])
        payload["blocks"] = annotated_blocks
        payload["plain_text"] = blocks_to_plain_text(annotated_blocks)
        payload["content_length"] = len(payload["plain_text"])
        payload["preview_head"] = payload["plain_text"][:300]
        payload["preview_tail"] = payload["plain_text"][-300:] if payload["plain_text"] else ""
        if payload["start_block_index"] is not None and payload["end_block_index"] is None:
            payload["end_block_index"] = payload["start_block_index"]
        if payload["start_paragraph_index"] is not None and payload["end_paragraph_index"] is None:
            payload["end_paragraph_index"] = payload["start_paragraph_index"]

    return sections


def annotate_section_blocks(blocks: list[dict]) -> list[dict]:
    annotated: list[dict] = []
    for block in blocks:
        if block["type"] == "paragraph":
            text = clean_text(block["text"])
            if not text:
                continue
            subheading = parse_subheading(text)
            if subheading:
                annotated.append(
                    {
                        "type": "heading",
                        "text": text,
                        "title": subheading["title"],
                        "path": subheading["path"],
                        "level": subheading["level"],
                    }
                )
            else:
                annotated.append({"type": "paragraph", "text": text})
        elif block["type"] == "table":
            cleaned_rows = [row for row in block["rows"] if any(cell.strip() for cell in row)]
            if cleaned_rows:
                annotated.append({"type": "table", "rows": cleaned_rows})
    return annotated


def parse_subheading(text: str) -> dict | None:
    match = SUBHEADING_PATTERN.match(text)
    if not match:
        return None

    path = match.group("path")
    title = match.group("title").strip()
    if not title:
        return None

    level = path.count(".") + 1
    if level < 2:
        return None

    return {"path": path, "title": title, "level": min(level, 4)}


def match_section_heading(line: str) -> str | None:
    if not line:
        return None

    text = clean_text(line)
    if not looks_like_section_heading(text):
        return None

    candidates = []
    for candidate in (text, strip_top_level_numbering(text), strip_trailing_heading_suffix(text)):
        if not candidate:
            continue
        stripped_candidate = strip_trailing_heading_suffix(candidate)
        for item in (candidate, stripped_candidate):
            normalized = normalize_heading(item)
            if normalized and normalized not in candidates:
                candidates.append(normalized)

    if not candidates:
        return None

    for candidate_normalized in candidates:
        for definition in SECTION_DEFINITIONS:
            options = [definition["title"], *definition["aliases"]]
            for option in options:
                if candidate_normalized == normalize_heading(option):
                    return definition["key"]

    return None


def looks_like_section_heading(text: str) -> bool:
    if not text:
        return False
    if len(text) > 40:
        return False
    if any(punctuation in text for punctuation in ("。", "；", ";", "！", "？")):
        return False
    return True


def strip_trailing_heading_suffix(text: str) -> str:
    stripped = text.strip()
    stripped = TRAILING_HEADING_SUFFIX_PATTERN.sub("", stripped)
    return stripped.strip()


def strip_top_level_numbering(text: str) -> str | None:
    stripped = text.strip()

    for prefix in ARABIC_NUMBERS:
        candidate = consume_top_level_prefix(stripped, prefix)
        if candidate:
            return candidate

    for prefix in [f"第{item}" for item in CHINESE_NUMBERS] + CHINESE_NUMBERS:
        candidate = consume_top_level_prefix(stripped, prefix)
        if candidate:
            return candidate

    return None


def consume_top_level_prefix(text: str, prefix: str) -> str | None:
    if not text.startswith(prefix):
        return None

    rest = text[len(prefix) :]
    if not rest:
        return None

    first = rest[0]
    if first in ".．":
        if len(rest) > 1 and rest[1].isdigit():
            return None
        rest = rest[1:]
    elif first in "、)）":
        rest = rest[1:]
    elif first.isspace():
        pass
    else:
        return None

    cleaned = rest.strip()
    return cleaned or None


def blocks_to_plain_text(blocks: list[dict]) -> str:
    parts: list[str] = []
    for block in blocks:
        if block["type"] in {"paragraph", "heading"}:
            parts.append(clean_text(block["text"]))
        elif block["type"] == "table":
            for row in block["rows"]:
                row_text = " | ".join(cell.strip() for cell in row if cell.strip())
                if row_text:
                    parts.append(row_text)
    return compact_text("\n\n".join(part for part in parts if part))


def validate_draft_contract(file_path: Path | None, fallback_text: str = "") -> dict:
    if file_path and file_path.exists() and file_path.suffix.lower() == ".docx":
        raw_blocks = extract_docx_blocks(file_path)
    else:
        raw_blocks = text_to_blocks(fallback_text)

    blocks, tail_hits = sanitize_document_blocks(raw_blocks, trim_tail=True)
    sections = build_sections_from_blocks(blocks)

    errors: list[str] = []
    warnings: list[str] = []
    details: list[str] = []
    empty_sections: list[str] = []
    note_only_sections: list[str] = []
    table_count = 0
    structured_item_count = 0

    title = find_first_paragraph_text(blocks)
    if normalize_heading(title or "") != normalize_heading(DRAFT_MAIN_TITLE):
        errors.append(f"文档主标题不符合模板要求，应为《{DRAFT_MAIN_TITLE}》。")
    else:
        details.append(f"文档主标题识别正常：{title}")

    for definition in SECTION_DEFINITIONS:
        section_payload = sections.get(definition["key"], {})
        if not section_payload.get("matched_heading"):
            errors.append(f"模块 {definition['number']}《{definition['title']}》缺少固定一级标题。")
            continue

        section_result = validate_section_contract(definition, section_payload.get("blocks", []))
        errors.extend(section_result["errors"])
        warnings.extend(section_result["warnings"])
        table_count += section_result["table_count"]
        structured_item_count += section_result["structured_item_count"]

        if section_result["is_empty"]:
            empty_sections.append(definition["title"])
        if section_result["note_only"]:
            note_only_sections.append(definition["title"])

        details.append(
            f"模块 {definition['number']}《{definition['title']}》："
            f"{'空模块' if section_result['is_empty'] else '识别正常'}，"
            f"表格 {section_result['table_count']} 张，"
            f"结构化条目 {section_result['structured_item_count']} 条。"
        )

    if tail_hits:
        warnings.append("文档末尾发现疑似 AI 尾巴或非正文提示语，系统已自动忽略这些尾部内容。")
        warnings.extend(f"尾部内容：{item}" for item in tail_hits[:5])

    return {
        "success": not errors,
        "errors": errors,
        "warnings": warnings,
        "details": details,
        "tail_hits": tail_hits,
        "report": {
            "module_count": len([definition for definition in SECTION_DEFINITIONS if sections.get(definition["key"], {}).get("matched_heading")]),
            "table_count": table_count,
            "structured_item_count": structured_item_count,
            "empty_sections": empty_sections,
            "note_only_sections": note_only_sections,
            "tail_detected": bool(tail_hits),
        },
    }


def validate_section_contract(definition: dict, section_blocks: list[dict]) -> dict:
    section_number = definition["number"]
    section_title = definition["title"]
    errors: list[str] = []
    warnings: list[str] = []
    table_count = 0
    structured_item_count = 0
    current_subheading = ""
    note_only = True
    has_meaningful_content = False

    expected_subsections = expected_section_subsections(definition["key"], section_number)
    present_subsections: dict[str, str] = {}
    duplicate_subsections: defaultdict[str, list[str]] = defaultdict(list)
    for block in section_blocks:
        if block["type"] != "heading":
            continue
        path = canonical_subheading_path(block["path"])
        title = clean_text(block["title"])
        if path in present_subsections:
            duplicate_subsections[path].append(title)
            continue
        present_subsections[path] = title

    for path, expected_title in expected_subsections:
        actual_title = present_subsections.get(path)
        if not actual_title:
            errors.append(f"模块 {section_number}《{section_title}》缺少固定子结构 {path} {expected_title}。")
            continue
        if not matches_expected_subsection_title(path, actual_title, expected_title):
            errors.append(
                f"模块 {section_number}《{section_title}》的子结构 {path} 标题应为“{expected_title}”或其兼容别名，当前识别为“{actual_title}”。"
            )
    for path, titles in duplicate_subsections.items():
        errors.append(
            f"模块 {section_number}《{section_title}》的子结构 {path} 重复出现 {len(titles) + 1} 次，请只保留一个固定二级标题。"
        )

    for block in section_blocks:
        if block["type"] == "heading":
            current_subheading = canonical_subheading_path(block["path"])
            continue

        if block["type"] == "table":
            table_count += 1
            headers, rows = split_validation_table(block["rows"])
            if definition["key"] == "report_note":
                errors.append(f"模块 1《{section_title}》的 {current_subheading or '说明区'} 不应出现结构化表格，请改为说明块。")
                continue
            if not current_subheading.endswith((".1", ".2", ".3")):
                errors.append(f"模块 {section_number}《{section_title}》的 {current_subheading or '结构区'} 不应出现表格，请仅在 x.1 / x.2 / x.3 放置 v1 6 列或 v2 9 列表格。")
                continue
            header_mode = identify_draft_table_contract(headers)
            if header_mode is None:
                errors.append(
                    f"模块 {section_number}《{section_title}》的第 {table_count} 张表格列数或列名不符合模板要求，"
                    f"应为 v1 的 {len(DRAFT_STRUCTURED_TABLE_COLUMNS)} 列：{' / '.join(DRAFT_STRUCTURED_TABLE_COLUMNS)}，"
                    f"或 v2 的 {len(DRAFT_STRUCTURED_TABLE_COLUMNS_V2)} 列：{' / '.join(DRAFT_STRUCTURED_TABLE_COLUMNS_V2)}。"
                )
            else:
                structured_item_count += len(rows)
                has_meaningful_content = has_meaningful_content or bool(rows)
                note_only = False
            continue

        if block["type"] != "paragraph":
            continue

        text = clean_text(block["text"])
        if not text:
            continue

        if definition["key"] == "report_note":
            if current_subheading not in {"1.1", "1.2"}:
                errors.append(f"模块 1《{section_title}》存在无法归类的说明段落：{text[:36]}。报告说明仅允许 1.1 数据与规则 / 1.2 编制原则。")
            else:
                has_meaningful_content = True
            continue

        if current_subheading.endswith(".4"):
            has_meaningful_content = True
            continue

        errors.append(
            f"模块 {section_number}《{section_title}》的 {current_subheading or '结构区'} 出现无法归类的自由文本段落：{text[:36]}。x.1 / x.2 / x.3 必须是 v1 6 列或 v2 9 列表格，空结果也要写成占位表格。"
        )

    return {
        "errors": errors,
        "warnings": warnings,
        "table_count": table_count,
        "structured_item_count": structured_item_count,
        "is_empty": not has_meaningful_content and table_count == 0,
        "note_only": note_only and has_meaningful_content,
    }


def expected_section_subsections(section_key: str, section_number: int) -> list[tuple[str, str]]:
    if section_key == "report_note":
        return list(DRAFT_REPORT_NOTE_SUBSECTIONS)
    return [(f"{section_number}.{suffix}", title) for suffix, title in DRAFT_STANDARD_SUBSECTIONS]


def matches_expected_subsection_title(path: str, actual_title: str, expected_title: str) -> bool:
    actual_normalized = normalize_heading(actual_title)
    if actual_normalized == normalize_heading(expected_title):
        return True
    suffix = path.split(".")[-1] if "." in path else path
    for alias in DRAFT_STANDARD_SUBSECTION_ALIASES.get(suffix, []):
        if actual_normalized == normalize_heading(alias):
            return True
    return False


def canonical_subheading_path(path: str) -> str:
    parts = [piece for piece in (path or "").split(".") if piece]
    if len(parts) >= 2:
        return f"{parts[0]}.{parts[1]}"
    return path


def split_validation_table(rows: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    normalized_rows = [trim_row(row) for row in rows if any(cell.strip() for cell in row)]
    if not normalized_rows:
        return [], []
    return normalized_rows[0], normalized_rows[1:]


def identify_draft_table_contract(headers: list[str]) -> str | None:
    compact_headers = [item.strip() for item in headers]
    if compact_headers == DRAFT_STRUCTURED_TABLE_COLUMNS:
        return "v1"
    if compact_headers == DRAFT_STRUCTURED_TABLE_COLUMNS_V2:
        return "v2"
    return None


def trim_row(row: list[str]) -> list[str]:
    last_non_empty = 0
    for index, value in enumerate(row, start=1):
        if value.strip():
            last_non_empty = index
    clipped = row[:last_non_empty] if last_non_empty else row
    return [cell.strip() for cell in clipped]


def find_first_paragraph_text(blocks: list[dict]) -> str:
    for block in blocks:
        if block["type"] == "paragraph":
            return clean_text(block.get("text", ""))
    return ""


def build_draft_metadata(sections: dict[str, dict]) -> dict:
    contract_versions: set[str] = set()
    for section_key, section in sections.items():
        if section_key == "report_note":
            continue
        for block in section.get("blocks", []):
            if block.get("type") != "table":
                continue
            headers, _rows = split_validation_table(block.get("rows", []))
            header_mode = identify_draft_table_contract(headers)
            if header_mode:
                contract_versions.add(header_mode)

    if "v2" in contract_versions:
        contract_version = "v2"
    elif "v1" in contract_versions:
        contract_version = "v1"
    else:
        contract_version = "unknown"

    return {
        "contract_version": contract_version,
        "window_metadata": extract_window_metadata(sections),
    }


def extract_window_metadata(sections: dict[str, dict]) -> dict:
    report_note = sections.get("report_note") or {}
    report_note_blocks = report_note.get("blocks") or []
    primary_texts = extract_report_note_subsection_texts(report_note_blocks, "1.1")
    fallback_texts = collect_report_note_paragraph_texts(report_note_blocks)
    metadata: dict[str, list[str]] = {}
    for key, labels in DRAFT_WINDOW_METADATA_LABELS.items():
        window_range = extract_window_range_from_texts(primary_texts, labels)
        if not window_range:
            window_range = extract_window_range_from_texts(fallback_texts, labels)
        if window_range:
            metadata[key] = [window_range[0].isoformat(), window_range[1].isoformat()]
    return metadata


def extract_report_note_subsection_texts(blocks: list[dict], target_path: str) -> list[str]:
    current_path = ""
    texts: list[str] = []
    for block in blocks:
        if block.get("type") == "heading":
            current_path = canonical_subheading_path(block.get("path") or "")
            continue
        if block.get("type") != "paragraph":
            continue
        text = clean_text(block.get("text", ""))
        if text and current_path == target_path:
            texts.append(text)
    return texts


def collect_report_note_paragraph_texts(blocks: list[dict]) -> list[str]:
    texts: list[str] = []
    for block in blocks:
        if block.get("type") != "paragraph":
            continue
        text = clean_text(block.get("text", ""))
        if text:
            texts.append(text)
    return texts


def extract_window_range_from_texts(texts: list[str], labels: list[str]) -> tuple | None:
    for text in texts:
        for label in labels:
            window_range = extract_window_range_from_text(text, label)
            if window_range:
                return window_range
    return None


def extract_window_range_from_text(text: str, label: str) -> tuple | None:
    cleaned = clean_text(text or "")
    if not cleaned or label not in cleaned:
        return None

    labeled_segment = cleaned.split(label, 1)[1]
    dates = extract_dates_from_text(labeled_segment)
    if len(dates) >= 2:
        return min(dates[:2]), max(dates[:2])
    return None


def extract_dates_from_text(text: str) -> list:
    values = []
    for pattern in (DATE_PATTERN, CHINESE_DATE_PATTERN):
        for year, month, day in pattern.findall(text or ""):
            try:
                values.append(date(int(year), int(month), int(day)))
            except ValueError:
                continue
    return values


def looks_like_non_body_tail(text: str) -> bool:
    lowered = clean_text(text).lower()
    if not lowered:
        return False
    if lowered.endswith("吗？") or lowered.endswith("吗?") or lowered.endswith("是否继续？") or lowered.endswith("是否继续?"):
        return True
    if "ai 生成" in lowered or "需要我把这份底稿" in lowered or "要不要我继续" in lowered:
        return True
    if lowered.startswith("如果你需要") or lowered.startswith("如需我继续"):
        return True
    return False


def is_trivial_tail_line(text: str) -> bool:
    stripped = clean_text(text)
    if not stripped:
        return True
    if len(stripped) <= 10 and all(character in "。！？!?：:）)】]- " for character in stripped):
        return True
    return False


def is_document_title(block: dict) -> bool:
    if block["type"] != "paragraph":
        return False
    text = normalize_heading(block["text"])
    return text in {
        normalize_heading(DRAFT_MAIN_TITLE),
        normalize_heading("沉香行业每日分析简报"),
        normalize_heading("每日分析简报"),
    }


def clean_text(text: str) -> str:
    cleaned = text.replace("\ufeff", " ").replace("\ufffc", " ").replace("\xa0", " ")
    cleaned = cleaned.replace("\u3000", " ").replace("\t", " ")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return compact_text(cleaned)
