from __future__ import annotations

import os
import shutil
import sys
import tempfile
from contextlib import contextmanager
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from werkzeug.datastructures import FileStorage


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.db import get_connection
from app.services import process_single_file


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
            with app.app_context():
                storage = FileStorage(
                    stream=BytesIO("研究底稿测试".encode("utf-8")),
                    filename="2026-04-21_研究底稿.txt",
                    content_type="text/plain",
                )
                with patch(
                    "app.services.validate_draft_contract",
                    return_value={"success": True, "warnings": [], "report": {}, "details": [], "errors": []},
                ), patch(
                    "app.services.parse_document",
                    return_value={
                        "title": "测试底稿",
                        "content": "测试内容",
                        "html_content": "",
                        "sections": {},
                        "document_metadata": {"parser_version": "test", "doc_type": "draft"},
                    },
                ), patch(
                    "app.services.rebuild_effective_chain_from",
                    side_effect=RuntimeError("forced rebuild failure"),
                ):
                    result = process_single_file(storage)

                assert not result.success
                assert "回滚" in result.message

                with get_connection(app.config["DATABASE_PATH"]) as connection:
                    status_row = connection.execute(
                        """
                        SELECT lifecycle_status, is_current
                        FROM documents
                        WHERE report_date = '2026-04-21'
                          AND doc_type = 'draft'
                        ORDER BY id DESC
                        LIMIT 1
                        """
                    ).fetchone()
                    active_count = connection.execute(
                        """
                        SELECT COUNT(1) AS count
                        FROM documents
                        WHERE report_date = '2026-04-21'
                          AND doc_type = 'draft'
                          AND lifecycle_status = 'active'
                          AND is_current = 1
                        """
                    ).fetchone()["count"]

                assert status_row is not None
                assert status_row["lifecycle_status"] == "withdrawn"
                assert status_row["is_current"] == 0
                assert active_count == 0

        print("upload_failure_guard_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
