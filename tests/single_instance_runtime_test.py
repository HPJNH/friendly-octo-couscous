from __future__ import annotations

import importlib
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
    "WEB_CONCURRENCY",
    "PUBLIC_BASE_URL",
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


def valid_production_env(runtime_root: Path) -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "APP_RUNTIME_ROOT": str(runtime_root),
        "SECRET_KEY": "single-instance-prod-secret",
        "ADMIN_PASSWORD": "single-instance-prod-admin",
        "SESSION_COOKIE_SECURE": "true",
        "BOOTSTRAP_ADMIN_ENABLED": "false",
        "INITIAL_ADMIN_ACCESS_CODE": "928431",
        "INITIAL_VIEWER_ACCESS_CODE": "563274",
        "HIDE_INTERNAL_PATHS": "true",
        "APP_SERVER_WORKERS": "1",
    }


def main() -> None:
    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        with patched_env({"APP_ENV": "local", "APP_RUNTIME_ROOT": str(runtime_root)}):
            app = create_app()
            assert app.config["APP_RUNTIME_ROOT"] == runtime_root
            assert app.config["DATA_ROOT"] == runtime_root / "data"
            assert app.config["STORAGE_ROOT"] == runtime_root / "storage"
            assert app.config["EXPORTS_ROOT"] == runtime_root / "exports"
            assert app.config["ARCHIVE_ROOT"] == runtime_root / "data" / "processed" / "archive_parsed"
            for key in ("DATA_ROOT", "STORAGE_ROOT", "EXPORTS_ROOT", "ARCHIVE_ROOT"):
                assert app.config[key].exists(), f"{key} should be created"
        del app

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        with patched_env({"APP_ENV": "local", "APP_RUNTIME_ROOT": str(runtime_root)}):
            sys.modules.pop("wsgi", None)
            wsgi_module = importlib.import_module("wsgi")
            assert hasattr(wsgi_module, "app"), "wsgi.py should expose app"
            assert wsgi_module.app.config["APP_RUNTIME_ROOT"] == runtime_root
            sys.modules.pop("wsgi", None)
            del wsgi_module

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        env = valid_production_env(runtime_root)
        env["APP_SERVER_WORKERS"] = "2"
        try:
            with patched_env(env):
                create_app()
        except RuntimeError as exc:
            assert "单实例部署" in str(exc), str(exc)
        else:
            raise AssertionError("production + sqlite + multi workers should fail")

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        blocked_storage = runtime_root / "blocked_storage"
        blocked_storage.parent.mkdir(parents=True, exist_ok=True)
        blocked_storage.write_text("not-a-directory", encoding="utf-8")
        env = valid_production_env(runtime_root)
        env["STORAGE_ROOT"] = str(blocked_storage)
        try:
            with patched_env(env):
                create_app()
        except RuntimeError as exc:
            assert "STORAGE_ROOT" in str(exc), str(exc)
        else:
            raise AssertionError("production with non-writable storage root should fail")

        print("single_instance_runtime_test_ok")
    finally:
        sys.modules.pop("wsgi", None)
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
