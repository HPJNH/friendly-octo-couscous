from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.admin_auth import ACCESS_SESSION_KEY
from app.db import get_connection


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


def seed_viewer_session(client, viewer_id: int, display_name: str) -> None:
    now = int(time.time())
    with client.session_transaction() as session:
        session[ACCESS_SESSION_KEY] = {
            "identity_id": viewer_id,
            "label": "测试访客",
            "role": "viewer",
            "method": "access-code",
            "display_name": display_name,
            "verified_at": now,
            "expires_at": now + 3600,
        }


def seed_admin_session(client, admin_id: int, display_name: str) -> None:
    now = int(time.time())
    with client.session_transaction() as session:
        session[ACCESS_SESSION_KEY] = {
            "identity_id": admin_id,
            "label": "管理员",
            "role": "admin",
            "method": "access-code",
            "display_name": display_name,
            "verified_at": now,
            "expires_at": now + 3600,
        }


def main() -> None:
    main_js = (PROJECT_ROOT / "app" / "static" / "js" / "main.js").read_text(encoding="utf-8")
    for section_id in ("today-focus", "today-new", "recent-versions", "history-archive"):
        assert f'"{section_id}"' in main_js, f"{section_id} should remain in HOME_SCROLL_SPY_SECTIONS"

    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        with patched_env(
            {
                "APP_ENV": "local",
                "APP_RUNTIME_ROOT": str(runtime_root),
                "BOOTSTRAP_ADMIN_ENABLED": "true",
            }
        ):
            app = create_app()
            client = app.test_client()

            with app.app_context():
                with get_connection(app.config["DATABASE_PATH"]) as connection:
                    viewer = connection.execute(
                        """
                        SELECT id
                        FROM access_identities
                        WHERE role = 'viewer' AND status = 'active'
                        ORDER BY id
                        LIMIT 1
                        """
                    ).fetchone()
                    admin = connection.execute(
                        """
                        SELECT id
                        FROM access_identities
                        WHERE role = 'admin' AND status = 'active'
                        ORDER BY id
                        LIMIT 1
                        """
                    ).fetchone()
            assert viewer is not None, "viewer identity should exist when bootstrap admin is enabled in local mode"
            assert admin is not None, "admin identity should exist when bootstrap admin is enabled in local mode"

            names = [
                "闫斌先生",
                "闫力阳先生",
                "孟凡让先生",
                "",
                "A",
                "这是一个非常非常非常长的测试姓名用于验证首页欢迎区极端值收口能力先生",
            ]

            for name in names:
                seed_viewer_session(client, int(viewer["id"]), name)
                response = client.get("/")
                assert response.status_code == 200, f"home page should render for display_name={name!r}"
                html = response.get_data(as_text=True)
                assert 'id="today-focus"' in html
                assert 'id="today-new"' in html
                assert 'id="recent-versions"' in html
                assert 'id="history-archive"' in html
                assert '#today-focus' in html
                assert '#today-new' in html
                assert '#recent-versions' in html
                assert '#history-archive' in html
                assert 'data-nav-key="today_focus"' in html
                assert 'data-nav-key="today_new"' in html
                assert 'data-nav-key="recent_changes"' in html
                assert 'data-nav-key="history_archive"' in html
                assert 'class="welcome-heading"' in html
                assert 'class="hero-subtitle"' in html
                if name:
                    assert name in html
                    assert 'class="welcome-heading-name"' in html
                else:
                    assert 'class="welcome-heading-name"' not in html

            seed_viewer_session(client, int(viewer["id"]), "移动访客")
            mobile_viewer_response = client.get("/", headers={"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile"})
            assert mobile_viewer_response.status_code == 200
            mobile_viewer_html = mobile_viewer_response.get_data(as_text=True)
            assert 'class="topbar-utility"' not in mobile_viewer_html
            assert '/admin/verify' not in mobile_viewer_html
            assert mobile_viewer_html.index('class="welcome-heading"') < mobile_viewer_html.index('workbench-shortcuts-panel')

            seed_admin_session(client, int(admin["id"]), "移动管理员")
            mobile_admin_response = client.get("/", headers={"User-Agent": "Mozilla/5.0 (Android 14; Mobile)"})
            assert mobile_admin_response.status_code == 200
            mobile_admin_html = mobile_admin_response.get_data(as_text=True)
            assert 'class="topbar-utility"' not in mobile_admin_html
            assert '/upload' in mobile_admin_html
            assert mobile_admin_html.index('class="welcome-heading"') < mobile_admin_html.index('workbench-shortcuts-panel')

            seed_viewer_session(client, int(viewer["id"]), "桌面访客")
            desktop_viewer_response = client.get("/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            assert desktop_viewer_response.status_code == 200
            desktop_viewer_html = desktop_viewer_response.get_data(as_text=True)
            assert 'class="topbar-utility"' in desktop_viewer_html
            assert '/admin/verify' in desktop_viewer_html

        print("ui_runtime_edge_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
