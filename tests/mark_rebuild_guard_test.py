from __future__ import annotations

import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.db import get_connection
from app.mark_service import fetch_entry_mark_summaries, upsert_entry_mark
from app.rebuild_engine import persist_rebuilt_entries
from app.utils import now_string


WATCHED_ENV_KEYS = [
    "APP_ENV",
    "APP_RUNTIME_ROOT",
    "BOOTSTRAP_ADMIN_ENABLED",
]


@contextmanager
def patched_env(overrides: dict[str, str]):
    snapshot = {key: os.environ.get(key) for key in WATCHED_ENV_KEYS}
    try:
        for key in WATCHED_ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in overrides.items():
            os.environ[key] = value
        yield
    finally:
        for key in WATCHED_ENV_KEYS:
            os.environ.pop(key, None)
        for key, value in snapshot.items():
            if value is not None:
                os.environ[key] = value


def create_run(app, run_key: str) -> int:
    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            run_id = connection.execute(
                """
                INSERT INTO rebuild_runs (run_key, started_at, parser_version, status)
                VALUES (?, ?, 'test', 'running')
                """,
                (run_key, now_string()),
            ).lastrowid
            connection.commit()
    return int(run_id)


def build_entry(title: str, *, core_content: str) -> dict:
    now = now_string()
    return {
        "origin_document_id": None,
        "report_date": "2026-04-21",
        "module_id": 2,
        "module_key": "own_track",
        "module_name": "自有线",
        "subsection_path": "2.1",
        "subsection_title": "本期新增",
        "section_type": "新增",
        "source_level": "A1",
        "entry_type": "real",
        "event_key": "own_track:mark-stability-1",
        "title": title,
        "time_text": "2026-04-21",
        "event_date": "2026-04-21",
        "source_name": "测试来源",
        "source_title": title,
        "source_url": "",
        "supporting_sources_json": [],
        "core_content": core_content,
        "why_included": "",
        "note_text": "",
        "first_seen_date": "2026-04-21",
        "last_seen_date": "2026-04-21",
        "is_in_patch_window": 1,
        "is_in_focus_window": 1,
        "display_status": "新增",
        "needs_review": 0,
        "confidence_level": "中",
        "is_current_chain": 1,
        "is_deleted": 0,
        "dedupe_rank": 1,
        "evidence_json": {"delta_text": ""},
        "created_at": now,
        "updated_at": now,
    }


def current_entry(app):
    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            row = connection.execute(
                """
                SELECT id, event_key
                FROM entries
                WHERE event_key = 'own_track:mark-stability-1'
                  AND is_deleted = 0
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
    assert row is not None
    return row


def current_viewer(app):
    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            row = connection.execute(
                """
                SELECT id, label, role
                FROM access_identities
                WHERE role = 'viewer' AND status = 'active'
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
    assert row is not None
    return row


def assert_mark_summary(app, entry_id: int) -> None:
    with app.app_context():
        summaries = fetch_entry_mark_summaries([entry_id], viewer_identity_id=None, viewer_role="viewer")
    summary = summaries[entry_id]
    assert summary["has_marks"]
    assert summary["items"][0]["entry_event_key"] == "own_track:mark-stability-1"


def main() -> None:
    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        env = {
            "APP_ENV": "local",
            "APP_RUNTIME_ROOT": str(runtime_root),
            "BOOTSTRAP_ADMIN_ENABLED": "true",
        }
        with patched_env(env):
            app = create_app()
            viewer = current_viewer(app)

            run_id = create_run(app, "mark-run-1")
            with app.app_context():
                persist_rebuilt_entries(
                    database_path=app.config["DATABASE_PATH"],
                    run_id=run_id,
                    entries=[build_entry("首次标题", core_content="首次内容")],
                    source_index_path=None,
                    evidence_map_path=None,
                    decisions_path=None,
                    migration_report_path=None,
                )
                first_entry = current_entry(app)
                result = upsert_entry_mark(
                    entry_id=int(first_entry["id"]),
                    marker_identity_id=int(viewer["id"]),
                    marker_label=viewer["label"],
                    marker_role=viewer["role"],
                    note="封箱前重点",
                )
                assert result["entry_event_key"] == "own_track:mark-stability-1"
                assert_mark_summary(app, int(first_entry["id"]))

            run_id = create_run(app, "mark-run-2")
            with app.app_context():
                persist_rebuilt_entries(
                    database_path=app.config["DATABASE_PATH"],
                    run_id=run_id,
                    entries=[build_entry("改写后的标题", core_content="改写后的内容")],
                    source_index_path=None,
                    evidence_map_path=None,
                    decisions_path=None,
                    migration_report_path=None,
                )
                second_entry = current_entry(app)
                assert_mark_summary(app, int(second_entry["id"]))
                with get_connection(app.config["DATABASE_PATH"]) as connection:
                    mark_row = connection.execute(
                        """
                        SELECT entry_id, entry_event_key, entry_title
                        FROM entry_marks
                        WHERE marker_identity_id = ?
                          AND is_active = 1
                        LIMIT 1
                        """,
                        (int(viewer["id"]),),
                    ).fetchone()
                assert mark_row is not None
                assert mark_row["entry_id"] == second_entry["id"]
                assert mark_row["entry_event_key"] == "own_track:mark-stability-1"

            del app

            restarted_app = create_app()
            restarted_entry = current_entry(restarted_app)
            assert_mark_summary(restarted_app, int(restarted_entry["id"]))

        print("mark_rebuild_guard_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
