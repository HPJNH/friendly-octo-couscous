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
from app.db import get_connection, init_db
from app.utils import now_string


WATCHED_ENV_KEYS = [
    "APP_ENV",
    "DEPLOYMENT_MODE",
    "APP_RUNTIME_ROOT",
    "DATA_ROOT",
    "STORAGE_ROOT",
    "EXPORTS_ROOT",
    "ARCHIVE_ROOT",
    "DATABASE_PATH",
    "TEMP_UPLOAD_ROOT",
    "FILE_LIBRARY_ROOT",
    "EXPORT_ROOT",
    "REPORT_EXPORT_ROOT",
    "LOG_ROOT",
    "RAW_DATA_ROOT",
    "REVIEW_DATA_ROOT",
    "VERIFICATION_DATA_ROOT",
    "LINKED_DATA_ROOT",
    "SECRET_KEY",
    "ADMIN_PASSWORD",
    "ADMIN_PASSWORD_HASH",
    "SESSION_COOKIE_SECURE",
    "BOOTSTRAP_ADMIN_ENABLED",
    "INITIAL_ADMIN_ACCESS_CODE",
    "INITIAL_VIEWER_ACCESS_CODE",
    "HIDE_INTERNAL_PATHS",
    "APP_SERVER_WORKERS",
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


def valid_production_env(runtime_root: Path) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "APP_RUNTIME_ROOT": str(runtime_root),
        "SECRET_KEY": "production-runtime-guard-secret",
        "ADMIN_PASSWORD": "production-runtime-guard-admin",
        "SESSION_COOKIE_SECURE": "true",
        "BOOTSTRAP_ADMIN_ENABLED": "false",
        "INITIAL_ADMIN_ACCESS_CODE": "928431",
        "INITIAL_VIEWER_ACCESS_CODE": "563274",
        "HIDE_INTERNAL_PATHS": "true",
        "APP_SERVER_WORKERS": "1",
    }


def prepare_runtime_dirs(runtime_root: Path) -> None:
    for relative in (
        "data",
        "data/database",
        "data/processed/archive_parsed",
        "data/processed/archive_parsed/2026-04-21",
        "data/raw/drafts",
        "data/review",
        "data/verification",
        "data/raw/linked",
        "exports",
        "exports/pdf",
        "exports/reports",
        "storage",
        "storage/cache/incoming",
        "storage/file_library/active/drafts/2026-04-21",
        "storage/logs",
    ):
        (runtime_root / relative).mkdir(parents=True, exist_ok=True)


def seed_valid_runtime(runtime_root: Path) -> None:
    prepare_runtime_dirs(runtime_root)
    database_path = runtime_root / "data" / "database" / "intelligence_browser.db"
    init_db(database_path)
    now = now_string()
    with get_connection(database_path) as connection:
        document_id = connection.execute(
            """
            INSERT INTO documents (
                report_date, doc_type, original_name, stored_name, stored_path, parsed_path, file_ext,
                uploaded_at, title, content, html_content, file_hash, metadata_json, lifecycle_status, is_current
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', 1)
            """,
            (
                "2026-04-21",
                "draft",
                "valid-runtime.docx",
                "valid-runtime.docx",
                str(runtime_root / "storage" / "file_library" / "active" / "drafts" / "2026-04-21" / "valid-runtime.docx"),
                str(runtime_root / "data" / "processed" / "archive_parsed" / "2026-04-21" / "valid-runtime.json"),
                ".docx",
                now,
                "受控运行态验证",
                "有效内容",
                "<p>有效内容</p>",
                "hash-demo",
                "{}",
            ),
        ).lastrowid
        connection.execute(
            """
            INSERT INTO sections (
                document_id, report_date, section_key, section_title, raw_content, raw_html,
                display_content, display_html, status, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                document_id,
                "2026-04-21",
                "own_track",
                "本期新增",
                "raw",
                "<p>raw</p>",
                "display",
                "<p>display</p>",
                "新增",
                "{}",
                now,
            ),
        )
        connection.execute(
            """
            INSERT INTO entries (
                run_id, origin_document_id, report_date, module_id, module_key, module_name,
                subsection_path, subsection_title, section_type, source_level, entry_type, event_key,
                title, time_text, event_date, source_name, source_title, source_url, supporting_sources_json,
                core_content, why_included, note_text, first_seen_date, last_seen_date, is_in_patch_window,
                is_in_focus_window, display_status, needs_review, confidence_level, is_current_chain,
                is_deleted, dedupe_rank, evidence_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                None,
                document_id,
                "2026-04-21",
                1,
                "own_track",
                "自有线",
                "2.1",
                "本期新增",
                "新增",
                "A1",
                "real",
                "own_track:valid-runtime",
                "受控运行态验证",
                "2026-04-21",
                "2026-04-21",
                "测试来源",
                "受控运行态验证",
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
        connection.executemany(
            """
            INSERT INTO access_identities (
                label, code_hash, secret_hash, code_hint, role, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            [
                ("正式管理员", "hash-admin", "", "11***11", "admin", "", now, now),
                ("正式浏览", "hash-viewer", "", "22***22", "viewer", "", now, now),
            ],
        )
        connection.commit()

    (runtime_root / "data" / "raw" / "drafts" / "valid-runtime.docx").write_text("raw", encoding="utf-8")
    (
        runtime_root
        / "storage"
        / "file_library"
        / "active"
        / "drafts"
        / "2026-04-21"
        / "valid-runtime.docx"
    ).write_text("library", encoding="utf-8")
    (
        runtime_root
        / "data"
        / "processed"
        / "archive_parsed"
        / "2026-04-21"
        / "valid-runtime.json"
    ).write_text("{}", encoding="utf-8")


def expect_failure(env: dict[str, str], expected_fragment: str) -> None:
    try:
        with patched_env(env):
            create_app()
    except RuntimeError as exc:
        assert expected_fragment in str(exc), str(exc)
        return
    raise AssertionError(f"expected failure containing: {expected_fragment}")


def main() -> None:
    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        expect_failure(valid_production_env(runtime_root), "DATA_ROOT")

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        prepare_runtime_dirs(runtime_root)
        expect_failure(valid_production_env(runtime_root), "DATABASE_PATH 缺失")

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        prepare_runtime_dirs(runtime_root)
        init_db(runtime_root / "data" / "database" / "intelligence_browser.db")
        expect_failure(valid_production_env(runtime_root), "壳库特征")

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        seed_valid_runtime(runtime_root)
        with patched_env(valid_production_env(runtime_root)):
            app = create_app()
            assert app.config["APP_ENV"] == "production"
            assert app.config["DATABASE_PATH"].exists()
        del app

        print("runtime_fail_closed_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
