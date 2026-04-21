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


def seed_entry(app) -> tuple[int, int]:
    now = now_string()
    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            connection.execute(
                """
                INSERT INTO entries (
                    run_id, origin_document_id, report_date, module_id, module_key, module_name,
                    subsection_path, subsection_title, section_type, source_level, entry_type, event_key,
                    title, time_text, event_date, source_name, source_title, source_url, supporting_sources_json,
                    core_content, why_included, note_text, first_seen_date, last_seen_date,
                    is_in_patch_window, is_in_focus_window, display_status, needs_review,
                    confidence_level, is_current_chain, is_deleted, dedupe_rank, evidence_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    None,
                    None,
                    "2026-04-21",
                    1,
                    "own_track",
                    "自有线",
                    "2.1",
                    "本期新增",
                    "新增",
                    "A1",
                    "real",
                    "own_track:test-startup",
                    "启动守卫测试",
                    "2026-04-21",
                    "2026-04-21",
                    "测试来源",
                    "启动守卫测试",
                    "",
                    "[]",
                    "测试内容",
                    "",
                    "",
                    "2026-04-21",
                    "2026-04-21",
                    0,
                    1,
                    "新增",
                    0,
                    "中",
                    1,
                    0,
                    0,
                    "{}",
                    now,
                    now,
                ),
            )
            connection.commit()
            row = connection.execute("SELECT id FROM entries LIMIT 1").fetchone()
            run_count = connection.execute("SELECT COUNT(1) AS count FROM rebuild_runs").fetchone()["count"]
    assert row is not None
    return int(row["id"]), int(run_count)


def load_entry_snapshot(app) -> tuple[int, int]:
    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            row = connection.execute("SELECT id FROM entries LIMIT 1").fetchone()
            run_count = connection.execute("SELECT COUNT(1) AS count FROM rebuild_runs").fetchone()["count"]
            total_entries = connection.execute("SELECT COUNT(1) AS count FROM entries").fetchone()["count"]
    assert row is not None
    return int(row["id"]), int(run_count), int(total_entries)


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
            original_entry_id, original_run_count = seed_entry(app)
            del app

            restarted_app = create_app()
            restarted_entry_id, restarted_run_count, total_entries = load_entry_snapshot(restarted_app)
            assert restarted_entry_id == original_entry_id
            assert restarted_run_count == original_run_count
            assert total_entries == 1

        print("startup_noop_guard_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
