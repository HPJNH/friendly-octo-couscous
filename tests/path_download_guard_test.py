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
from app.services import get_document_download_path, get_export_download_path


WATCHED_ENV_KEYS = [
    "APP_ENV",
    "APP_RUNTIME_ROOT",
    "ACCESS_CONTROL_ENABLED",
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


def insert_document(connection, *, stored_path: Path, lifecycle_status: str = "active") -> int:
    cursor = connection.execute(
        """
        INSERT INTO documents (
            report_date, doc_type, original_name, stored_name, stored_path, parsed_path, file_ext,
            uploaded_at, title, content, html_content, file_hash, metadata_json, lifecycle_status, is_current
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (
            "2026-04-21",
            "draft",
            stored_path.name,
            stored_path.name,
            str(stored_path),
            "",
            stored_path.suffix or ".docx",
            "2026-04-21 10:00:00",
            stored_path.name,
            "content",
            "<p>content</p>",
            "hash-demo",
            "{}",
            lifecycle_status,
        ),
    )
    return int(cursor.lastrowid)


def insert_export(connection, *, stored_path: Path, status: str = "active") -> int:
    cursor = connection.execute(
        """
        INSERT INTO export_files (
            report_date, file_name, stored_path, file_ext, created_at, status, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-04-21",
            stored_path.name,
            str(stored_path),
            stored_path.suffix or ".pdf",
            "2026-04-21 10:00:00",
            status,
            "{}",
        ),
    )
    return int(cursor.lastrowid)


def main() -> None:
    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        env = {
            "APP_ENV": "local",
            "APP_RUNTIME_ROOT": str(runtime_root),
            "ACCESS_CONTROL_ENABLED": "false",
        }
        with patched_env(env):
            app = create_app()
            inside_document = app.config["FILE_LIBRARY_ROOT"] / "active" / "draft" / "2026-04-21" / "inside.docx"
            inside_document.parent.mkdir(parents=True, exist_ok=True)
            inside_document.write_text("doc", encoding="utf-8")

            inside_export = app.config["EXPORT_ROOT"] / "inside.pdf"
            inside_export.parent.mkdir(parents=True, exist_ok=True)
            inside_export.write_bytes(b"%PDF-1.4 test")

            outside_root = runtime_root.parent / "outside-download-guard"
            outside_root.mkdir(parents=True, exist_ok=True)
            outside_document = outside_root / "outside.docx"
            outside_export = outside_root / "outside.pdf"
            outside_document.write_text("doc", encoding="utf-8")
            outside_export.write_bytes(b"%PDF-1.4 outside")

            with app.app_context():
                with get_connection(app.config["DATABASE_PATH"]) as connection:
                    inside_document_id = insert_document(connection, stored_path=inside_document)
                    outside_document_id = insert_document(connection, stored_path=outside_document)
                    inside_export_id = insert_export(connection, stored_path=inside_export)
                    outside_export_id = insert_export(connection, stored_path=outside_export)
                    connection.commit()

                assert get_document_download_path(inside_document_id) == inside_document.resolve()
                assert get_export_download_path(inside_export_id) == inside_export.resolve()

                blocked_document = False
                try:
                    get_document_download_path(outside_document_id)
                except ValueError as exc:
                    blocked_document = "受控根目录" in str(exc)
                assert blocked_document, "document download path should be constrained to FILE_LIBRARY_ROOT"

                blocked_export = False
                try:
                    get_export_download_path(outside_export_id)
                except ValueError as exc:
                    blocked_export = "受控根目录" in str(exc)
                assert blocked_export, "export download path should be constrained to EXPORTS_ROOT"

        print("path_download_guard_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
