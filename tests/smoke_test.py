from pathlib import Path
import re
import sys
import time

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.admin_auth import ACCESS_SESSION_KEY, change_access_identity_code, create_access_identity, generate_access_code
from app.db import get_connection


def extract_csrf_token(response) -> str:
    text = response.get_data(as_text=True)
    match = re.search(r'name="csrf_token" value="([^"]+)"', text)
    assert match, "csrf token not found"
    return match.group(1)


def main() -> None:
    app = create_app()
    client = app.test_client()

    login_page = client.get("/access/login")
    assert login_page.status_code == 200
    admin_page = client.get("/admin/verify")
    assert admin_page.status_code == 200

    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            viewer = connection.execute(
                """
                SELECT id, label, role
                FROM access_identities
                WHERE role = 'viewer' AND status = 'active'
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
            admin = connection.execute(
                """
                SELECT id, label, role
                FROM access_identities
                WHERE role = 'admin' AND status = 'active'
                ORDER BY id
                LIMIT 1
                """
            ).fetchone()
            sample_entry = connection.execute(
                """
                SELECT id
                FROM entries
                WHERE is_deleted = 0
                  AND entry_type = 'real'
                ORDER BY report_date DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

    assert viewer is not None, "active viewer identity missing"
    assert admin is not None, "active admin identity missing"
    assert sample_entry is not None, "sample entry missing"

    now = int(time.time())
    with client.session_transaction() as session:
        session[ACCESS_SESSION_KEY] = {
            "identity_id": viewer["id"],
            "label": viewer["label"],
            "role": viewer["role"],
            "method": "access-code",
            "verified_at": now,
            "expires_at": now + 3600,
        }

    assert client.get("/").status_code == 200
    assert client.get("/history").status_code == 200
    assert client.get("/library").status_code == 200
    assert client.get("/section/2026-04-12/own_track").status_code == 200
    assert client.get("/access/change-code").status_code == 200
    assert client.get("/upload").status_code == 302

    section_page = client.get("/section/2026-04-12/own_track")
    mark_csrf = extract_csrf_token(section_page)
    mark_response = client.post(
        f"/marks/{sample_entry['id']}/upsert",
        data={
            "csrf_token": mark_csrf,
            "note": "烟雾测试重点",
            "next": "/section/2026-04-12/own_track",
        },
        follow_redirects=False,
    )
    assert mark_response.status_code == 302

    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            created_mark = connection.execute(
                """
                SELECT *
                FROM entry_marks
                WHERE entry_id = ? AND marker_identity_id = ? AND is_active = 1
                ORDER BY id DESC
                LIMIT 1
                """,
                (sample_entry["id"], viewer["id"]),
            ).fetchone()
    assert created_mark is not None, "viewer mark should be created"
    created_mark_id = created_mark["id"]

    with client.session_transaction() as session:
        session[ACCESS_SESSION_KEY] = {
            "identity_id": admin["id"],
            "label": admin["label"],
            "role": admin["role"],
            "method": "access-code",
            "verified_at": now,
            "expires_at": now + 3600,
        }

    assert client.get("/upload").status_code == 200
    assert client.get("/access/manage").status_code == 200

    admin_page_for_mark = client.get("/history")
    admin_mark_csrf = extract_csrf_token(admin_page_for_mark)
    deactivate_response = client.post(
        f"/marks/{created_mark['id']}/deactivate",
        data={
            "csrf_token": admin_mark_csrf,
            "next": "/history",
        },
        follow_redirects=False,
    )
    assert deactivate_response.status_code == 302

    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            inactive_mark = connection.execute(
                "SELECT is_active FROM entry_marks WHERE id = ?",
                (created_mark["id"],),
            ).fetchone()
    assert inactive_mark is not None and inactive_mark["is_active"] == 0, "admin should be able to deactivate mark"

    with app.app_context():
        first_code = generate_access_code()
        second_code = generate_access_code()
        temp_identity = create_access_identity("smoke-unique-check", first_code, "viewer", "smoke")
        try:
            duplicate_blocked = False
            try:
                create_access_identity("smoke-duplicate-check", first_code, "viewer", "smoke")
            except ValueError:
                duplicate_blocked = True
            assert duplicate_blocked, "active duplicate access code should be rejected"

            with app.test_request_context("/access/change-code", method="POST"):
                change_access_identity_code(temp_identity["id"], first_code, second_code, second_code)

            history_reuse_blocked = False
            try:
                create_access_identity("smoke-history-check", first_code, "viewer", "smoke")
            except ValueError:
                history_reuse_blocked = True
            assert history_reuse_blocked, "historical access code reuse should be rejected"
        finally:
            with get_connection(app.config["DATABASE_PATH"]) as connection:
                connection.execute("DELETE FROM entry_marks WHERE id = ?", (created_mark_id,))
                connection.execute("DELETE FROM access_code_history WHERE identity_id = ?", (temp_identity["id"],))
                connection.execute("DELETE FROM access_identities WHERE id = ?", (temp_identity["id"],))
                connection.commit()

    print("smoke_test_ok")


if __name__ == "__main__":
    main()
