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
from app.security import get_remote_identity, log_audit_event, register_auth_failure
from app.db import get_connection


WATCHED_ENV_KEYS = [
    "APP_ENV",
    "APP_RUNTIME_ROOT",
    "TRUST_PROXY_HEADERS",
    "PROXY_FIX_X_FOR",
    "PROXY_FIX_X_PROTO",
    "PROXY_FIX_X_HOST",
    "PROXY_FIX_X_PORT",
    "PROXY_FIX_X_PREFIX",
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


def _exercise_identity_route(client, expected_remote_key: str) -> None:
    response = client.get(
        "/__proxy-check",
        headers={"X-Forwarded-For": "203.0.113.77"},
        environ_overrides={"REMOTE_ADDR": "10.0.0.10"},
    )
    assert response.status_code == 200
    assert response.get_data(as_text=True) == expected_remote_key


def _assert_persisted_remote_key(app, expected_remote_key: str) -> None:
    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            attempt = connection.execute(
                "SELECT remote_key FROM auth_attempts WHERE scope = 'access_login' LIMIT 1"
            ).fetchone()
            audit = connection.execute(
                "SELECT remote_key FROM audit_logs WHERE action = 'entry_mark.updated' LIMIT 1"
            ).fetchone()
    assert attempt is not None and attempt["remote_key"] == expected_remote_key
    assert audit is not None and audit["remote_key"] == expected_remote_key


def _build_app(runtime_root: Path, trust_proxy_headers: bool):
    env = {
        "APP_ENV": "local",
        "APP_RUNTIME_ROOT": str(runtime_root),
        "TRUST_PROXY_HEADERS": "true" if trust_proxy_headers else "false",
        "PROXY_FIX_X_FOR": "1",
    }
    with patched_env(env):
        app = create_app()
    app.config["ACCESS_CONTROL_ENABLED"] = False

    @app.route("/__proxy-check")
    def _proxy_check():
        register_auth_failure("access_login")
        log_audit_event(action="entry_mark.updated", target_type="entry_mark", target_label="proxy-check")
        return get_remote_identity()

    return app


def main() -> None:
    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        app = _build_app(runtime_root, trust_proxy_headers=False)
        client = app.test_client()
        _exercise_identity_route(client, "10.0.0.10")
        _assert_persisted_remote_key(app, "10.0.0.10")

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        app = _build_app(runtime_root, trust_proxy_headers=True)
        client = app.test_client()
        _exercise_identity_route(client, "203.0.113.77")
        _assert_persisted_remote_key(app, "203.0.113.77")

        print("proxy_header_guard_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
