from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path

from bs4 import BeautifulSoup


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

MOBILE_VIEWER_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile"
MOBILE_ADMIN_UA = "Mozilla/5.0 (Android 14; Mobile)"
DESKTOP_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"


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
            "label": "Test Viewer",
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
            "label": "Test Admin",
            "role": "admin",
            "method": "access-code",
            "display_name": display_name,
            "verified_at": now,
            "expires_at": now + 3600,
        }


def assert_sidebar_footer_inside_scroll(html: str, path: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    sidebar = soup.select_one("#sidebar")
    assert sidebar is not None, f"sidebar missing on {path}"
    scroll = sidebar.select_one(".sidebar-scroll")
    assert scroll is not None, f"sidebar scroll missing on {path}"
    footer = sidebar.select_one(".sidebar-footer")
    assert footer is not None, f"sidebar footer missing on {path}"
    assert scroll in footer.parents, f"sidebar footer should stay inside sidebar scroll on {path}"


def assert_selectors_present(html: str, path: str, selectors: list[str]) -> None:
    soup = BeautifulSoup(html, "html.parser")
    for selector in selectors:
        assert soup.select_one(selector) is not None, f"{selector} missing on {path}"


def assert_home_reading_nav_targets(html: str, path: str) -> None:
    soup = BeautifulSoup(html, "html.parser")
    reading_topics = soup.select_one("#reading-topics")
    assert reading_topics is not None, f"reading-topics missing on {path}"

    reading_sections = soup.select('section.section-cluster[id^="reading-category-"]')
    assert reading_sections, f"reading category sections missing on {path}"

    reading_section_ids = [section.get("id", "") for section in reading_sections]
    assert all(reading_section_ids), f"reading category section id missing on {path}"
    assert len(reading_section_ids) == len(set(reading_section_ids)), f"reading category section ids should be unique on {path}"

    nav_links = soup.select('[data-nav-group="reading"][href*="#reading-category-"]')
    assert nav_links, f"reading nav links missing on {path}"
    for link in nav_links:
        href = link.get("href", "")
        assert "#" in href, f"reading nav href missing hash target on {path}"
        target_id = href.split("#", 1)[1]
        assert target_id in reading_section_ids, f"reading nav target {target_id!r} missing on {path}"
        assert soup.find(id=target_id) is not None, f"reading nav target node {target_id!r} missing on {path}"


def load_identity_ids(app) -> tuple[int, int]:
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
    return int(viewer["id"]), int(admin["id"])


def main() -> None:
    main_js = (PROJECT_ROOT / "app" / "static" / "js" / "main.js").read_text(encoding="utf-8")
    for section_id in ("today-focus", "today-new", "recent-versions", "history-archive"):
        assert f'"{section_id}"' in main_js, f"{section_id} should remain in HOME_SCROLL_SPY_SECTIONS"
    assert 'section.section-cluster[id^="reading-category-"]' in main_js

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
            viewer_id, admin_id = load_identity_ids(app)

            names = [
                "Analyst",
                "Operations Desk",
                "",
                "A",
                "A very long display name used to keep the home welcome block under layout pressure",
            ]

            for name in names:
                seed_viewer_session(client, viewer_id, name)
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
                assert_home_reading_nav_targets(html, f"/ home display_name={name!r}")
                if name:
                    assert name in html
                    assert 'class="welcome-heading-name"' in html
                else:
                    assert 'class="welcome-heading-name"' not in html

            seed_viewer_session(client, viewer_id, "mobile-viewer")
            mobile_viewer_response = client.get("/", headers={"User-Agent": MOBILE_VIEWER_UA})
            assert mobile_viewer_response.status_code == 200
            mobile_viewer_html = mobile_viewer_response.get_data(as_text=True)
            assert 'class="topbar-utility"' not in mobile_viewer_html
            assert "/admin/verify" not in mobile_viewer_html
            assert mobile_viewer_html.index('class="welcome-heading"') < mobile_viewer_html.index("workbench-shortcuts-panel")
            assert_sidebar_footer_inside_scroll(mobile_viewer_html, "/ mobile viewer")
            assert_home_reading_nav_targets(mobile_viewer_html, "/ mobile viewer")
            assert_selectors_present(
                mobile_viewer_html,
                "/ mobile viewer",
                [".sidebar-scroll", ".sidebar-footer", ".workbench-shortcuts-panel", "#today-focus"],
            )

            seed_admin_session(client, admin_id, "mobile-admin")
            mobile_admin_response = client.get("/", headers={"User-Agent": MOBILE_ADMIN_UA})
            assert mobile_admin_response.status_code == 200
            mobile_admin_html = mobile_admin_response.get_data(as_text=True)
            assert 'class="topbar-utility"' not in mobile_admin_html
            assert "/upload" in mobile_admin_html
            assert mobile_admin_html.index('class="welcome-heading"') < mobile_admin_html.index("workbench-shortcuts-panel")
            assert_sidebar_footer_inside_scroll(mobile_admin_html, "/ mobile admin")
            assert_home_reading_nav_targets(mobile_admin_html, "/ mobile admin")
            assert_selectors_present(
                mobile_admin_html,
                "/ mobile admin",
                [".sidebar-scroll", ".sidebar-footer", ".workbench-shortcuts-panel", "#today-focus"],
            )

            seed_viewer_session(client, viewer_id, "desktop-viewer")
            desktop_viewer_response = client.get("/", headers={"User-Agent": DESKTOP_UA})
            assert desktop_viewer_response.status_code == 200
            desktop_viewer_html = desktop_viewer_response.get_data(as_text=True)
            assert 'class="topbar-utility"' in desktop_viewer_html
            assert "/admin/verify" in desktop_viewer_html
            assert_sidebar_footer_inside_scroll(desktop_viewer_html, "/ desktop viewer")
            assert_home_reading_nav_targets(desktop_viewer_html, "/ desktop viewer")
            assert_selectors_present(
                desktop_viewer_html,
                "/ desktop viewer",
                [".sidebar-scroll", ".sidebar-footer", ".topbar-utility", "#today-focus"],
            )

            viewer_page_checks = [
                ("/history", [".history-hero-panel", ".history-trajectory-stage"]),
                ("/library", [".library-section-card", ".soft-hidden-collection"]),
            ]
            for path, selectors in viewer_page_checks:
                seed_viewer_session(client, viewer_id, f"render {path}")
                for label, user_agent in (("mobile", MOBILE_VIEWER_UA), ("desktop", DESKTOP_UA)):
                    response = client.get(path, headers={"User-Agent": user_agent})
                    assert response.status_code == 200, f"{path} should render for {label}"
                    html = response.get_data(as_text=True)
                    assert_sidebar_footer_inside_scroll(html, f"{path} {label}")
                    assert_selectors_present(html, f"{path} {label}", [".sidebar-scroll", ".sidebar-footer", *selectors])

            seed_admin_session(client, admin_id, "access-manager")
            for label, user_agent in (("mobile", MOBILE_ADMIN_UA), ("desktop", DESKTOP_UA)):
                response = client.get("/access/manage", headers={"User-Agent": user_agent})
                assert response.status_code == 200, f"/access/manage should render for {label}"
                html = response.get_data(as_text=True)
                assert_sidebar_footer_inside_scroll(html, f"/access/manage {label}")
                assert_selectors_present(
                    html,
                    f"/access/manage {label}",
                    [".sidebar-scroll", ".sidebar-footer", ".access-stage-layout", ".access-audit-layout", ".access-log-stage"],
                )

        print("ui_runtime_edge_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
