from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from flask import current_app

from .db import get_connection
from .utils import now_string


MARK_TYPE_LABELS = {
    "focus": "重点",
}


def _normalize_note(note: str | None) -> str:
    value = " ".join(str(note or "").strip().split())
    if len(value) > 80:
        raise ValueError("重点摘要请尽量控制在 80 个字以内，方便其他成员快速阅读。")
    return value


def _empty_mark_summary(viewer_identity_id: int | None) -> dict:
    return {
        "has_marks": False,
        "count": 0,
        "items": [],
        "highlight_note": "",
        "latest_mark_at": "",
        "latest_marker_label": "",
        "viewer_can_mark": bool(viewer_identity_id),
        "viewer_mark": None,
    }


def _normalize_mark_row(row, *, viewer_identity_id: int | None, viewer_role: str) -> dict:
    is_owner = viewer_identity_id is not None and row["marker_identity_id"] == viewer_identity_id
    is_admin = viewer_role == "admin"
    return {
        "id": row["id"],
        "entry_id": row["entry_id"],
        "entry_event_key": row["entry_event_key"] or "",
        "entry_module_key": row["entry_module_key"] or "",
        "entry_report_date": row["entry_report_date"] or "",
        "entry_title": row["entry_title"] or row["resolved_entry_title"] or "",
        "marker_identity_id": row["marker_identity_id"],
        "marker_label": row["marker_label"] or "成员",
        "marker_role": row["marker_role"] or "viewer",
        "mark_type": row["mark_type"] or "focus",
        "mark_type_label": MARK_TYPE_LABELS.get(row["mark_type"] or "focus", "重点"),
        "note": row["note"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "is_owner": is_owner,
        "can_manage": bool(is_owner or is_admin),
    }


def _load_entry_rows(connection, entry_ids: list[int]) -> dict[int, object]:
    placeholders = ",".join("?" for _ in entry_ids)
    rows = connection.execute(
        f"""
        SELECT id, event_key, module_key, report_date, title
        FROM entries
        WHERE id IN ({placeholders})
        """,
        tuple(entry_ids),
    ).fetchall()
    return {row["id"]: row for row in rows}


def _load_mark_rows(connection, entry_ids: list[int], event_keys: list[str]):
    params: list[object] = []
    where_clauses: list[str] = []
    if entry_ids:
        where_clauses.append(f"m.entry_id IN ({','.join('?' for _ in entry_ids)})")
        params.extend(entry_ids)
    if event_keys:
        where_clauses.append(f"m.entry_event_key IN ({','.join('?' for _ in event_keys)})")
        params.extend(event_keys)
    if not where_clauses:
        return []

    return connection.execute(
        f"""
        SELECT
            m.*,
            ai.label AS marker_label,
            ai.role AS marker_role,
            COALESCE(e.title, m.entry_title, '') AS resolved_entry_title
        FROM entry_marks m
        LEFT JOIN access_identities ai ON ai.id = m.marker_identity_id
        LEFT JOIN entries e ON e.id = m.entry_id
        WHERE m.is_active = 1
          AND ({' OR '.join(where_clauses)})
        ORDER BY m.updated_at DESC, m.id DESC
        """,
        tuple(params),
    ).fetchall()


def fetch_entry_mark_summaries(
    entry_ids: Iterable[int],
    *,
    viewer_identity_id: int | None = None,
    viewer_role: str = "guest",
) -> dict[int, dict]:
    normalized_ids = sorted({int(entry_id) for entry_id in entry_ids if entry_id})
    if not normalized_ids:
        return {}

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        entry_rows = _load_entry_rows(connection, normalized_ids)
        event_keys = sorted(
            {
                str(row["event_key"] or "").strip()
                for row in entry_rows.values()
                if str(row["event_key"] or "").strip()
            }
        )
        rows = _load_mark_rows(connection, normalized_ids, event_keys)

    event_key_to_entry_ids: dict[str, list[int]] = defaultdict(list)
    for entry_id, row in entry_rows.items():
        event_key = str(row["event_key"] or "").strip()
        if event_key:
            event_key_to_entry_ids[event_key].append(entry_id)

    grouped: dict[int, list[dict]] = defaultdict(list)
    seen_mark_ids: dict[int, set[int]] = defaultdict(set)
    for row in rows:
        normalized = _normalize_mark_row(row, viewer_identity_id=viewer_identity_id, viewer_role=viewer_role)
        candidate_entry_ids = event_key_to_entry_ids.get(normalized["entry_event_key"]) or [normalized["entry_id"]]
        for entry_id in candidate_entry_ids:
            if not entry_id or normalized["id"] in seen_mark_ids[entry_id]:
                continue
            grouped[entry_id].append(normalized)
            seen_mark_ids[entry_id].add(normalized["id"])

    summaries: dict[int, dict] = {}
    for entry_id in normalized_ids:
        items = grouped.get(entry_id, [])
        if not items:
            summaries[entry_id] = _empty_mark_summary(viewer_identity_id)
            continue
        viewer_mark = next((item for item in items if item["is_owner"]), None)
        latest_with_note = next((item for item in items if item["note"]), items[0])
        summaries[entry_id] = {
            "has_marks": True,
            "count": len(items),
            "items": items,
            "highlight_note": latest_with_note["note"],
            "latest_mark_at": items[0]["updated_at"],
            "latest_marker_label": items[0]["marker_label"],
            "viewer_can_mark": bool(viewer_identity_id),
            "viewer_mark": viewer_mark,
        }
    return summaries


def apply_mark_summaries_to_cards(
    cards: list[dict],
    *,
    viewer_identity_id: int | None = None,
    viewer_role: str = "guest",
) -> dict[int, dict]:
    entry_ids = [card.get("entry_id") for card in cards if card.get("entry_id")]
    summaries = fetch_entry_mark_summaries(
        entry_ids,
        viewer_identity_id=viewer_identity_id,
        viewer_role=viewer_role,
    )
    for card in cards:
        summary = summaries.get(card.get("entry_id")) or _empty_mark_summary(viewer_identity_id)
        card["mark_summary"] = summary
        card["has_manual_marks"] = summary["has_marks"]
    return summaries


def upsert_entry_mark(
    *,
    entry_id: int,
    marker_identity_id: int,
    marker_label: str,
    marker_role: str,
    mark_type: str = "focus",
    note: str = "",
) -> dict:
    clean_note = _normalize_note(note)
    clean_mark_type = mark_type if mark_type in MARK_TYPE_LABELS else "focus"
    now = now_string()

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        entry_row = connection.execute(
            """
            SELECT id, title, module_key, report_date, event_key
            FROM entries
            WHERE id = ?
              AND is_deleted = 0
            LIMIT 1
            """,
            (entry_id,),
        ).fetchone()
        if not entry_row:
            raise ValueError("这条情报当前不可标记，请刷新页面后再试。")

        identity_row = connection.execute(
            """
            SELECT id, label, role, status
            FROM access_identities
            WHERE id = ?
            LIMIT 1
            """,
            (marker_identity_id,),
        ).fetchone()
        if not identity_row or identity_row["status"] != "active":
            raise ValueError("当前访问资格已失效，请重新登录后再试。")

        existing = connection.execute(
            """
            SELECT *
            FROM entry_marks
            WHERE marker_identity_id = ?
              AND (
                  (entry_event_key = ? AND ? != '')
                  OR entry_id = ?
              )
            LIMIT 1
            """,
            (marker_identity_id, entry_row["event_key"], entry_row["event_key"], entry_id),
        ).fetchone()

        if existing:
            connection.execute(
                """
                UPDATE entry_marks
                SET entry_id = ?,
                    entry_event_key = ?,
                    entry_module_key = ?,
                    entry_report_date = ?,
                    entry_title = ?,
                    mark_type = ?,
                    note = ?,
                    is_active = 1,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    entry_row["id"],
                    entry_row["event_key"],
                    entry_row["module_key"],
                    entry_row["report_date"],
                    entry_row["title"],
                    clean_mark_type,
                    clean_note,
                    now,
                    existing["id"],
                ),
            )
            mark_id = existing["id"]
            action = "updated"
        else:
            mark_id = connection.execute(
                """
                INSERT INTO entry_marks (
                    entry_id,
                    entry_event_key,
                    entry_module_key,
                    entry_report_date,
                    entry_title,
                    marker_identity_id,
                    mark_type,
                    note,
                    is_active,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                """,
                (
                    entry_id,
                    entry_row["event_key"],
                    entry_row["module_key"],
                    entry_row["report_date"],
                    entry_row["title"],
                    marker_identity_id,
                    clean_mark_type,
                    clean_note,
                    now,
                    now,
                ),
            ).lastrowid
            action = "created"

        connection.commit()

    return {
        "id": mark_id,
        "entry_id": entry_row["id"],
        "entry_event_key": entry_row["event_key"],
        "entry_title": entry_row["title"],
        "module_key": entry_row["module_key"],
        "report_date": entry_row["report_date"],
        "marker_identity_id": marker_identity_id,
        "marker_label": marker_label,
        "marker_role": marker_role,
        "mark_type": clean_mark_type,
        "mark_type_label": MARK_TYPE_LABELS.get(clean_mark_type, "重点"),
        "note": clean_note,
        "action": action,
    }


def deactivate_entry_mark(
    *,
    mark_id: int,
    actor_identity_id: int,
    actor_role: str,
) -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            """
            SELECT
                m.*,
                e.title AS live_entry_title,
                e.module_key AS live_module_key,
                e.report_date AS live_report_date
            FROM entry_marks m
            LEFT JOIN entries e ON e.id = m.entry_id
            WHERE m.id = ?
            LIMIT 1
            """,
            (mark_id,),
        ).fetchone()
        if not row or not row["is_active"]:
            raise ValueError("这条重点标记已经失效或不存在。")
        if actor_role != "admin" and row["marker_identity_id"] != actor_identity_id:
            raise PermissionError("你只能取消自己创建的重点标记。")

        now = now_string()
        connection.execute(
            """
            UPDATE entry_marks
            SET is_active = 0,
                updated_at = ?
            WHERE id = ?
            """,
            (now, mark_id),
        )
        connection.commit()

    return {
        "id": row["id"],
        "entry_id": row["entry_id"],
        "entry_event_key": row["entry_event_key"] or "",
        "entry_title": row["live_entry_title"] or row["entry_title"] or "",
        "module_key": row["live_module_key"] or row["entry_module_key"] or "",
        "report_date": row["live_report_date"] or row["entry_report_date"] or "",
        "marker_identity_id": row["marker_identity_id"],
        "mark_type": row["mark_type"] or "focus",
    }
