from __future__ import annotations

import json
import re
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.db import get_connection


BAD_MARKERS = ("默认查看码", "默认管理员码", "??", "???", "????", "?????")


def extract_csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "csrf token not found"
    return match.group(1)


def load_formal_codes() -> dict[str, str]:
    credentials = sorted(PROJECT_ROOT.glob("storage/logs/access_identity_rotation/*/FORMAL_ACCESS_CODES.txt"))
    assert credentials, "formal credentials file missing"
    codes: dict[str, str] = {}
    for line in credentials[-1].read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            continue
        label, role, code = parts
        if code.isdigit():
            codes.setdefault(role, code)
    assert "admin" in codes, "admin code missing"
    assert "viewer" in codes, "viewer code missing"
    return codes


def fetch_runtime_targets(database_path: Path) -> dict:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        current_draft = connection.execute(
            """
            SELECT id, report_date
            FROM documents
            WHERE doc_type = 'draft'
              AND lifecycle_status = 'active'
              AND is_current = 1
            ORDER BY report_date DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        assert current_draft is not None, "current draft missing"
        current_entry = connection.execute(
            """
            SELECT id
            FROM entries
            WHERE origin_document_id = ?
              AND is_deleted = 0
            ORDER BY id DESC
            LIMIT 1
            """,
            (current_draft["id"],),
        ).fetchone()
        assert current_entry is not None, "current live entry missing"
        section = connection.execute(
            """
            SELECT section_key
            FROM sections
            WHERE document_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (current_draft["id"],),
        ).fetchone()
        assert section is not None, "current section missing"
        return {
            "draft_id": current_draft["id"],
            "report_date": current_draft["report_date"],
            "entry_id": current_entry["id"],
            "section_key": section["section_key"],
        }


def worker(app, viewer_code: str, draft_id: int) -> dict:
    with app.test_client() as client:
        login_page = client.get("/access/login?next=/")
        csrf_token = extract_csrf_token(login_page.get_data(as_text=True))
        login_response = client.post(
            "/access/login",
            data={"csrf_token": csrf_token, "access_secret": viewer_code, "next": "/"},
            follow_redirects=False,
        )
        statuses = {
            "login": login_response.status_code,
            "/": client.get("/", follow_redirects=False).status_code,
            "/library": client.get("/library", follow_redirects=False).status_code,
            f"/library/document/{draft_id}": client.get(f"/library/document/{draft_id}", follow_redirects=False).status_code,
            f"/library/document/{draft_id}/download": client.get(
                f"/library/document/{draft_id}/download",
                follow_redirects=False,
            ).status_code,
        }
        return statuses


def main() -> None:
    app = create_app()
    codes = load_formal_codes()
    targets = fetch_runtime_targets(Path(app.config["DATABASE_PATH"]))
    summary: dict[str, object] = {"targets": targets}

    with app.test_client() as client:
        home_anon = client.get("/", follow_redirects=False)
        assert home_anon.status_code == 302
        assert home_anon.headers.get("Location") == "/access/login?next=/"

        login_page = client.get("/access/login?next=/")
        assert login_page.status_code == 200
        viewer_csrf = extract_csrf_token(login_page.get_data(as_text=True))
        login_response = client.post(
            "/access/login",
            data={"csrf_token": viewer_csrf, "access_secret": codes["viewer"], "next": "/"},
            follow_redirects=False,
        )
        assert login_response.status_code == 302
        assert login_response.headers.get("Location") == "/"

        viewer_results = {}
        for path in ("/", "/library", "/history", f"/library/document/{targets['draft_id']}"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 200, f"viewer failed on {path}"
            viewer_results[path] = response.status_code
        download_response = client.get(f"/library/document/{targets['draft_id']}/download", follow_redirects=False)
        assert download_response.status_code == 200
        assert "wordprocessingml.document" in (download_response.headers.get("Content-Type") or "")
        viewer_results[f"/library/document/{targets['draft_id']}/download"] = download_response.status_code

        viewer_upload = client.get("/upload", follow_redirects=False)
        assert viewer_upload.status_code == 302
        assert viewer_upload.headers.get("Location") == "/admin/verify?next=/upload"
        summary["viewer_results"] = viewer_results

        section_page = client.get(
            f"/section/{targets['report_date']}/{targets['section_key']}",
            follow_redirects=False,
        )
        assert section_page.status_code == 200
        mark_csrf = extract_csrf_token(section_page.get_data(as_text=True))
        mark_response = client.post(
            f"/marks/{targets['entry_id']}/upsert",
            data={
                "csrf_token": mark_csrf,
                "mark_type": "focus",
                "note": "发布验收重点标记",
                "next": f"/section/{targets['report_date']}/{targets['section_key']}",
            },
            follow_redirects=False,
        )
        assert mark_response.status_code == 302

        admin_page = client.get("/admin/verify?next=/upload")
        assert admin_page.status_code == 200
        admin_csrf = extract_csrf_token(admin_page.get_data(as_text=True))
        admin_verify = client.post(
            "/admin/verify",
            data={"csrf_token": admin_csrf, "access_secret": codes["admin"], "next": "/upload"},
            follow_redirects=False,
        )
        assert admin_verify.status_code == 302
        assert admin_verify.headers.get("Location") == "/upload"

        admin_results = {}
        for path in ("/", "/upload", "/library", "/history", "/access/manage", f"/library/document/{targets['draft_id']}"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 200, f"admin failed on {path}"
            admin_results[path] = response.status_code

        access_manage_html = client.get("/access/manage").get_data(as_text=True)
        for marker in BAD_MARKERS:
            assert marker not in access_manage_html, f"management page still contains dirty marker: {marker}"

        pdf_response = client.get(f"/download/pdf/{targets['report_date']}", follow_redirects=False)
        assert pdf_response.status_code == 200
        assert "application/pdf" in (pdf_response.headers.get("Content-Type") or "")
        admin_results[f"/download/pdf/{targets['report_date']}"] = pdf_response.status_code

        with get_connection(app.config["DATABASE_PATH"]) as connection:
            export_row = connection.execute(
                """
                SELECT id, stored_path, status
                FROM export_files
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()
            assert export_row is not None, "active export missing after pdf generation"
            assert export_row["status"] == "active"
            assert Path(export_row["stored_path"]).exists(), "active export path missing"

            created_mark = connection.execute(
                """
                SELECT id
                FROM entry_marks
                WHERE entry_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (targets["entry_id"],),
            ).fetchone()
            assert created_mark is not None, "acceptance mark missing"
            mark_id = created_mark["id"]

        export_detail = client.get(f"/library/export/{export_row['id']}", follow_redirects=False)
        assert export_detail.status_code == 200
        export_download = client.get(f"/library/export/{export_row['id']}/download", follow_redirects=False)
        assert export_download.status_code == 200
        assert "application/pdf" in (export_download.headers.get("Content-Type") or "")
        admin_results[f"/library/export/{export_row['id']}"] = export_detail.status_code
        admin_results[f"/library/export/{export_row['id']}/download"] = export_download.status_code

        history_page = client.get("/history")
        admin_mark_csrf = extract_csrf_token(history_page.get_data(as_text=True))
        deactivate_response = client.post(
            f"/marks/{mark_id}/deactivate",
            data={"csrf_token": admin_mark_csrf, "next": "/history"},
            follow_redirects=False,
        )
        assert deactivate_response.status_code == 302

        with get_connection(app.config["DATABASE_PATH"]) as connection:
            connection.execute("DELETE FROM entry_marks")
            connection.commit()

        summary["admin_results"] = admin_results

        repeated = {}
        for path in ("/", "/library", f"/library/document/{targets['draft_id']}"):
            statuses = [client.get(path, follow_redirects=False).status_code for _ in range(5)]
            assert statuses == [200, 200, 200, 200, 200], f"repeat access unstable on {path}: {statuses}"
            repeated[path] = statuses
        summary["repeat_statuses"] = repeated

    concurrent_results = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(worker, app, codes["viewer"], targets["draft_id"]) for _ in range(8)]
        for future in as_completed(futures):
            result = future.result()
            assert all(status in {200, 302} for status in result.values()), f"concurrent worker abnormal: {result}"
            concurrent_results.append(result)
    summary["concurrency_workers"] = len(concurrent_results)

    with get_connection(app.config["DATABASE_PATH"]) as connection:
        counts = {
            "documents": connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"],
            "export_files": connection.execute("SELECT COUNT(*) AS count FROM export_files").fetchone()["count"],
            "access_identities": connection.execute(
                "SELECT COUNT(*) AS count FROM access_identities WHERE status = 'active'"
            ).fetchone()["count"],
            "auth_attempts": connection.execute("SELECT COUNT(*) AS count FROM auth_attempts").fetchone()["count"],
            "entry_marks": connection.execute("SELECT COUNT(*) AS count FROM entry_marks").fetchone()["count"],
            "audit_logs": connection.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"],
        }
        dirty_labels = [
            row["label"]
            for row in connection.execute(
                "SELECT label FROM access_identities WHERE status = 'active' ORDER BY id"
            ).fetchall()
            if any(marker in (row["label"] or "") for marker in BAD_MARKERS)
        ]
        bad_audit_labels = [
            row["actor_label"]
            for row in connection.execute(
                "SELECT actor_label FROM audit_logs ORDER BY id DESC LIMIT 20"
            ).fetchall()
            if any(marker in (row["actor_label"] or "") for marker in BAD_MARKERS)
        ]

    assert counts["documents"] == 21, f"documents count mismatch: {counts['documents']}"
    assert counts["export_files"] == 1, f"export count mismatch: {counts['export_files']}"
    assert counts["access_identities"] == 8, f"access identity count mismatch: {counts['access_identities']}"
    assert counts["auth_attempts"] == 0, f"auth attempts not cleared: {counts['auth_attempts']}"
    assert counts["entry_marks"] == 0, f"entry marks not cleaned: {counts['entry_marks']}"
    assert counts["audit_logs"] >= 2, "expected clean audit logs after acceptance"
    assert not dirty_labels, f"dirty access labels remain: {dirty_labels}"
    assert not bad_audit_labels, f"dirty audit labels remain: {bad_audit_labels}"
    summary["counts"] = counts

    print(json.dumps(summary, ensure_ascii=True, indent=2))
    print("release_acceptance_test_ok")


if __name__ == "__main__":
    main()
