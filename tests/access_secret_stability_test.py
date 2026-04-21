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
from app.admin_auth import create_access_identity, verify_access_secret, _fingerprint_secret
from app.db import get_connection


WATCHED_ENV_KEYS = [
    "APP_ENV",
    "APP_RUNTIME_ROOT",
    "SECRET_KEY",
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


def load_identity_row(app, identity_id: int):
    with app.app_context():
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            return connection.execute(
                "SELECT id, code_hash, secret_hash, code_hint FROM access_identities WHERE id = ?",
                (identity_id,),
            ).fetchone()


def main() -> None:
    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        code = "246810"

        with patched_env(
            {
                "APP_ENV": "local",
                "APP_RUNTIME_ROOT": str(runtime_root),
                "SECRET_KEY": "rotation-secret-A",
                "BOOTSTRAP_ADMIN_ENABLED": "false",
            }
        ):
            app = create_app()
            with app.app_context():
                created = create_access_identity(
                    label="secret-key-rotation-viewer",
                    raw_code=code,
                    role="viewer",
                    notes="secret key rotation stability test",
                )
                old_fingerprint = _fingerprint_secret(code)
            row = load_identity_row(app, created["id"])
            assert row is not None
            assert row["code_hash"] == old_fingerprint

        with patched_env(
            {
                "APP_ENV": "local",
                "APP_RUNTIME_ROOT": str(runtime_root),
                "SECRET_KEY": "rotation-secret-B",
                "BOOTSTRAP_ADMIN_ENABLED": "false",
            }
        ):
            app = create_app()
            with app.app_context():
                new_fingerprint = _fingerprint_secret(code)
                with app.test_request_context("/access/login", method="POST"):
                    verified, reason = verify_access_secret(code, required_role="viewer")
                    assert verified is True
                    assert reason == "access-code"
                row = load_identity_row(app, created["id"])
                assert row is not None
                assert row["code_hash"] == new_fingerprint
                assert row["code_hash"] != old_fingerprint

                try:
                    create_access_identity(
                        label="duplicate-code-check",
                        raw_code=code,
                        role="viewer",
                        notes="should be rejected after secret key rotation",
                    )
                except ValueError as exc:
                    assert "已经被使用过" in str(exc)
                else:
                    raise AssertionError("duplicate access code should still be rejected after secret key rotation")

        print("access_secret_stability_test_ok")
    finally:
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
