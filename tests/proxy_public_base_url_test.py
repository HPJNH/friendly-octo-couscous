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
from app.admin_auth import build_safe_next
from app.routes import sanitize_absolute_next


WATCHED_ENV_KEYS = [
    "APP_ENV",
    "DEPLOYMENT_MODE",
    "APP_RUNTIME_ROOT",
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


def main() -> None:
    temp_roots: list[Path] = []
    try:
        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        with patched_env({"APP_ENV": "local", "APP_RUNTIME_ROOT": str(runtime_root)}):
            app = create_app()
            with app.test_request_context("/access/login", base_url="http://127.0.0.1:5050"):
                assert build_safe_next("http://127.0.0.1:5050/history?tab=recent", "/") == "/history?tab=recent"
                assert sanitize_absolute_next("http://127.0.0.1:5050/library") == "/library"
                assert build_safe_next("https://evil.example.com/landing", "/") == "/"
            del app

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        with patched_env({"APP_ENV": "local", "APP_RUNTIME_ROOT": str(runtime_root)}):
            app = create_app()
            with app.test_request_context("/admin/verify", base_url="http://192.168.1.50:5050"):
                assert build_safe_next("http://192.168.1.50:5050/upload", "/") == "/upload"
            del app

        runtime_root = Path(tempfile.mkdtemp())
        temp_roots.append(runtime_root)
        env = {
            "APP_ENV": "local",
            "APP_RUNTIME_ROOT": str(runtime_root),
            "PUBLIC_BASE_URL": "https://intel.example.com/",
        }
        with patched_env(env):
            app = create_app()
            assert app.config["PUBLIC_BASE_URL"] == "https://intel.example.com"
            with app.test_request_context("/access/login", base_url="http://127.0.0.1:5050"):
                assert build_safe_next("https://intel.example.com/access/manage?view=all", "/") == "/access/manage?view=all"
                assert sanitize_absolute_next("https://intel.example.com/library") == "/library"
                assert build_safe_next("http://intel.example.com/access/manage", "/") == "/"
                assert build_safe_next("https://evil.example.com/access/manage", "/") == "/"
            sys.modules.pop("wsgi", None)
            wsgi_module = importlib.import_module("wsgi")
            assert hasattr(wsgi_module, "app"), "wsgi.py should expose app"
            assert wsgi_module.app.config["PUBLIC_BASE_URL"] == "https://intel.example.com"
            sys.modules.pop("wsgi", None)
            del wsgi_module
            del app

        print("proxy_public_base_url_test_ok")
    finally:
        sys.modules.pop("wsgi", None)
        for path in reversed(temp_roots):
            shutil.rmtree(path, ignore_errors=True)


if __name__ == "__main__":
    main()
