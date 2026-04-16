from __future__ import annotations

import html
from pathlib import Path
import re
from typing import Iterable

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import LongTable, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


PDF_FONT_NAME = "STSong-Light"


def export_pdf(payload: dict, output_path: Path) -> Path:
    register_pdf_font()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=landscape(A4),
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=16 * mm,
        bottomMargin=14 * mm,
        title="沉香行业情报浏览成果",
        author="沉香行业情报浏览系统_1.0",
    )
    styles = build_styles()
    story = build_story(payload, styles, document.width)
    document.build(
        story,
        onFirstPage=lambda canvas, doc: draw_page_footer(canvas, doc, payload),
        onLaterPages=lambda canvas, doc: draw_page_footer(canvas, doc, payload),
    )
    return output_path


def register_pdf_font() -> None:
    if PDF_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(PDF_FONT_NAME))


def build_styles() -> StyleSheet1:
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="PdfCoverTitle",
            parent=styles["Title"],
            fontName=PDF_FONT_NAME,
            fontSize=26,
            leading=34,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#244236"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfCoverMeta",
            parent=styles["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=11,
            leading=18,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#706454"),
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfSectionTitle",
            parent=styles["Heading1"],
            fontName=PDF_FONT_NAME,
            fontSize=20,
            leading=28,
            textColor=colors.HexColor("#2e261c"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfGroupTitle",
            parent=styles["Heading2"],
            fontName=PDF_FONT_NAME,
            fontSize=14,
            leading=22,
            textColor=colors.HexColor("#244236"),
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfBody",
            parent=styles["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=10.5,
            leading=18,
            textColor=colors.HexColor("#2e261c"),
            wordWrap="CJK",
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfBodyMuted",
            parent=styles["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=9.5,
            leading=16,
            textColor=colors.HexColor("#706454"),
            wordWrap="CJK",
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfCardTitle",
            parent=styles["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=11.5,
            leading=18,
            textColor=colors.HexColor("#2e261c"),
            wordWrap="CJK",
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfTiny",
            parent=styles["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=8.8,
            leading=13,
            textColor=colors.HexColor("#706454"),
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfTableCell",
            parent=styles["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=8.6,
            leading=13,
            textColor=colors.HexColor("#2e261c"),
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="PdfTableHeader",
            parent=styles["BodyText"],
            fontName=PDF_FONT_NAME,
            fontSize=8.8,
            leading=12,
            textColor=colors.white,
            wordWrap="CJK",
        )
    )
    return styles


def build_story(payload: dict, styles: StyleSheet1, doc_width: float) -> list:
    story = build_cover_story(payload, styles, doc_width)

    for section in payload["sections"]:
        story.append(PageBreak())
        story.extend(build_section_story(section, styles, doc_width))

    return story


def build_cover_story(payload: dict, styles: StyleSheet1, doc_width: float) -> list:
    summary = payload["summary"]
    facts = [
        ("数据日期", payload["report_date"]),
        ("导出时间", payload["export_time"]),
        ("当日底稿", "已上传" if summary["draft_uploaded"] else "未上传"),
        ("有内容板块数", str(summary["available_sections"])),
        ("新增板块数", str(summary["new_sections"])),
        ("更新板块数", str(summary.get("updated_sections", 0))),
        ("底稿文件", payload["files"].get("draft_name") or "未上传"),
    ]
    section_titles = " / ".join(section["title"] for section in payload["sections"])
    return [
        Spacer(1, 24 * mm),
        Paragraph("沉香行业情报浏览成果", styles["PdfCoverTitle"]),
        Paragraph(payload["report_date"], styles["PdfCoverMeta"]),
        Paragraph(
            "以下内容来自系统整理后的展示结果，用于成果展示、老板预览和对外分享。",
            styles["PdfCoverMeta"],
        ),
        Spacer(1, 10 * mm),
        build_fact_table(facts, doc_width, styles, columns=2),
        Spacer(1, 6 * mm),
        Paragraph(
            f"当前导出板块顺序：{escape_inline(section_titles)}",
            styles["PdfBodyMuted"],
        ),
    ]


def build_section_story(section: dict, styles: StyleSheet1, doc_width: float) -> list:
    story = [
        Paragraph(f"{section['number']}. {escape_inline(section['title'])}", styles["PdfSectionTitle"]),
        Paragraph(
            f"状态：{section['status']}　　日期：{escape_inline(section['report_date'])}",
            styles["PdfBodyMuted"],
        ),
    ]

    if section.get("note"):
        story.append(Paragraph(escape_inline(section["note"]), styles["PdfBodyMuted"]))

    if not section["has_effective_content"]:
        story.append(
            build_notice_box(
                section.get("empty_message") or "本板块本日未提供内容。",
                styles,
                doc_width,
            )
        )
        return story

    groups = section["render_model"].get("groups", [])
    if not groups:
        story.append(build_notice_box("本板块本日未解析出有效内容。", styles, doc_width))
        return story

    for group in groups:
        if group.get("title"):
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(escape_inline(group["title"]), styles["PdfGroupTitle"]))
            if group.get("category"):
                story.append(Paragraph(f"分组：{escape_inline(group['category'])}", styles["PdfBodyMuted"]))
        story.extend(build_block_story(group.get("blocks", []), styles, doc_width))

    return story


def build_block_story(blocks: Iterable[dict], styles: StyleSheet1, doc_width: float) -> list:
    story: list = []
    for block in blocks:
        block_type = block.get("type")
        if block_type == "paragraph":
            story.append(Paragraph(escape_block_text(block.get("text", "")), styles["PdfBody"]))
        elif block_type == "card":
            story.append(build_card_box(block["card"], styles, doc_width))
        elif block_type == "table":
            summary = block.get("summary")
            if summary:
                story.append(Paragraph(f"表格提炼：{escape_inline(summary)}", styles["PdfBodyMuted"]))
            story.append(build_table_box(block.get("headers", []), block.get("rows", []), styles, doc_width))
        elif block_type == "heading":
            story.append(Paragraph(escape_inline(block.get("text", "")), styles["PdfGroupTitle"]))
    return story


def build_card_box(card: dict, styles: StyleSheet1, doc_width: float):
    meta_parts = []
    if card.get("time"):
        meta_parts.append(f"时间：{card['time']}")
    if card.get("source"):
        meta_parts.append(f"来源：{card['source']}")
    if card.get("tags"):
        meta_parts.append("标签：" + " / ".join(card["tags"]))

    card_rows = [[Paragraph(f"<b>{escape_inline(card.get('title') or '情报卡片')}</b>", styles["PdfCardTitle"])]]
    card_rows.append([Paragraph(f"状态：{escape_inline(card.get('status') or '未标注')}", styles["PdfTiny"])])
    if meta_parts:
        card_rows.append([Paragraph(escape_inline("　　".join(meta_parts)), styles["PdfTiny"])])
    card_rows.append([Paragraph(escape_block_text(card.get("core_content", "")), styles["PdfBody"])])
    if card.get("why"):
        card_rows.append([Paragraph(f"<b>观察价值：</b>{escape_block_text(card['why'])}", styles["PdfBodyMuted"])])

    table = Table(card_rows, colWidths=[doc_width], hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffaf0")),
                ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#d8c9b3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#efe0ca")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return table


def build_table_box(headers: list[str], rows: list[list[str]], styles: StyleSheet1, doc_width: float):
    if not headers:
        return build_notice_box("该表格未识别到可展示的表头。", styles, doc_width)

    normalized_rows = [row[: len(headers)] + [""] * max(0, len(headers) - len(row)) for row in rows]
    table_data = [[Paragraph(escape_inline(header or "未命名列"), styles["PdfTableHeader"]) for header in headers]]
    for row in normalized_rows:
        table_data.append([Paragraph(escape_block_text(cell), styles["PdfTableCell"]) for cell in row])

    table = LongTable(
        table_data,
        colWidths=build_column_widths(headers, normalized_rows, doc_width),
        repeatRows=1,
        hAlign="LEFT",
        splitByRow=1,
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#244236")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#fffdf8")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.HexColor("#fffdf8"), colors.HexColor("#f8f2e8")]),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cfbea7")),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#e3d4be")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return table


def build_notice_box(text: str, styles: StyleSheet1, doc_width: float):
    table = Table(
        [[Paragraph(escape_block_text(text), styles["PdfBodyMuted"])]],
        colWidths=[doc_width],
        hAlign="LEFT",
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f0e5")),
                ("BOX", (0, 0), (-1, -1), 0.7, colors.HexColor("#d9cdbb")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    return table


def build_fact_table(facts: list[tuple[str, str]], doc_width: float, styles: StyleSheet1, columns: int = 2):
    rows = []
    paired_cells = []
    cell_width = doc_width / columns
    for label, value in facts:
        text = f"<b>{escape_inline(label)}</b><br/>{escape_block_text(value)}"
        paired_cells.append(Paragraph(text, styles["PdfBody"]))
        if len(paired_cells) == columns:
            rows.append(paired_cells)
            paired_cells = []

    if paired_cells:
        paired_cells.extend("" for _ in range(columns - len(paired_cells)))
        rows.append(paired_cells)

    table = Table(rows, colWidths=[cell_width] * columns, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fffaf0")),
                ("BOX", (0, 0), (-1, -1), 0.9, colors.HexColor("#d6c8b3")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#eadfce")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]
        )
    )
    return table


def build_column_widths(headers: list[str], rows: list[list[str]], doc_width: float) -> list[float]:
    weights = []
    for index, header in enumerate(headers):
        samples = [header]
        for row in rows[:16]:
            if index < len(row):
                samples.append(row[index])
        longest = max((display_width(sample) for sample in samples), default=8)
        weights.append(min(max(longest, 8), 28))

    total_weight = sum(weights) or len(headers)
    return [doc_width * (weight / total_weight) for weight in weights]


def draw_page_footer(canvas, document, payload: dict) -> None:
    canvas.saveState()
    canvas.setFont(PDF_FONT_NAME, 8.5)
    canvas.setFillColor(colors.HexColor("#7a6d5d"))
    canvas.drawString(document.leftMargin, 8 * mm, f"沉香行业情报浏览成果 | {payload['report_date']}")
    canvas.drawRightString(document.pagesize[0] - document.rightMargin, 8 * mm, f"第 {canvas.getPageNumber()} 页")
    canvas.restoreState()


def escape_inline(text: str) -> str:
    return format_markup(text or "")


def escape_block_text(text: str) -> str:
    escaped = format_markup(text or "")
    escaped = escaped.replace("\r\n", "\n").replace("\r", "\n")
    return escaped.replace("\n", "<br/>")


def format_markup(text: str) -> str:
    escaped = html.escape((text or "").strip())
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)


def display_width(text: str) -> int:
    width = 0
    for character in text:
        width += 2 if ord(character) > 127 else 1
    return width
