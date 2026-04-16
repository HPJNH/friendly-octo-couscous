import json
import os
from datetime import timedelta
from pathlib import Path

from flask import Flask

from .admin_auth import ensure_bootstrap_access_codes
from .constants import SUPPORTED_EXTENSIONS
from .db import init_db
from .routes import bp
from .services import upgrade_existing_documents


def load_local_settings(base_dir: Path) -> dict:
    candidate_paths = [
        base_dir / "config" / "local_settings.json",
        base_dir / "local_settings.json",
    ]
    for settings_path in candidate_paths:
        if not settings_path.exists():
            continue
        try:
            return json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
    return {}


def get_setting(name: str, settings: dict, default):
    return os.environ.get(name, settings.get(name, default))


def get_int_setting(name: str, settings: dict, default: int) -> int:
    value = get_setting(name, settings, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def get_bool_setting(name: str, settings: dict, default: bool) -> bool:
    value = get_setting(name, settings, default)
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def resolve_path_setting(base_dir: Path, value, default_relative: str) -> Path:
    configured_path = Path(str(value or default_relative))
    if configured_path.is_absolute():
        return configured_path
    return base_dir / configured_path


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parent.parent
    settings = load_local_settings(base_dir)
    max_content_length_mb = get_int_setting("MAX_CONTENT_LENGTH_MB", settings, 50)
    admin_session_minutes = get_int_setting("ADMIN_SESSION_MINUTES", settings, 60)
    access_session_minutes = get_int_setting("ACCESS_SESSION_MINUTES", settings, 720)
    auth_max_failures = get_int_setting("AUTH_MAX_FAILURES", settings, 5)
    auth_window_minutes = get_int_setting("AUTH_WINDOW_MINUTES", settings, 30)
    auth_lock_minutes = get_int_setting("AUTH_LOCK_MINUTES", settings, 15)

    app = Flask(__name__, instance_relative_config=False)
    app.config.update(
        PROJECT_NAME="沉香行业情报浏览系统_1.0",
        SECRET_KEY=get_setting("SECRET_KEY", settings, "agarwood-intelligence-local-browser"),
        ADMIN_PASSWORD=get_setting("ADMIN_PASSWORD", settings, "123456"),
        ADMIN_PASSWORD_HASH=get_setting("ADMIN_PASSWORD_HASH", settings, ""),
        ACCESS_CONTROL_ENABLED=get_bool_setting("ACCESS_CONTROL_ENABLED", settings, True),
        ADMIN_SESSION_SECONDS=admin_session_minutes * 60,
        ACCESS_SESSION_SECONDS=access_session_minutes * 60,
        AUTH_MAX_FAILURES=auth_max_failures,
        AUTH_WINDOW_MINUTES=auth_window_minutes,
        AUTH_LOCK_MINUTES=auth_lock_minutes,
        INITIAL_ADMIN_ACCESS_CODE=get_setting("INITIAL_ADMIN_ACCESS_CODE", settings, "admin-123456"),
        INITIAL_VIEWER_ACCESS_CODE=get_setting("INITIAL_VIEWER_ACCESS_CODE", settings, "viewer-123456"),
        BASE_DIR=base_dir,
        DATA_ROOT=resolve_path_setting(base_dir, get_setting("DATA_ROOT", settings, "data"), "data"),
        STORAGE_ROOT=resolve_path_setting(base_dir, get_setting("STORAGE_ROOT", settings, "storage"), "storage"),
        DATABASE_PATH=resolve_path_setting(
            base_dir,
            get_setting("DATABASE_PATH", settings, "data/database/intelligence_browser.db"),
            "data/database/intelligence_browser.db",
        ),
        TEMP_UPLOAD_ROOT=resolve_path_setting(
            base_dir,
            get_setting("TEMP_UPLOAD_ROOT", settings, "storage/cache/incoming"),
            "storage/cache/incoming",
        ),
        FILE_LIBRARY_ROOT=resolve_path_setting(
            base_dir,
            get_setting("FILE_LIBRARY_ROOT", settings, "storage/file_library"),
            "storage/file_library",
        ),
        ARCHIVE_ROOT=resolve_path_setting(
            base_dir,
            get_setting("ARCHIVE_ROOT", settings, "data/processed/archive_parsed"),
            "data/processed/archive_parsed",
        ),
        EXPORT_ROOT=resolve_path_setting(
            base_dir,
            get_setting("EXPORT_ROOT", settings, "exports/pdf"),
            "exports/pdf",
        ),
        REPORT_EXPORT_ROOT=resolve_path_setting(
            base_dir,
            get_setting("REPORT_EXPORT_ROOT", settings, "exports/reports"),
            "exports/reports",
        ),
        DOCS_ROOT=resolve_path_setting(base_dir, get_setting("DOCS_ROOT", settings, "docs"), "docs"),
        LOG_ROOT=resolve_path_setting(
            base_dir,
            get_setting("LOG_ROOT", settings, "storage/logs"),
            "storage/logs",
        ),
        RAW_DATA_ROOT=resolve_path_setting(base_dir, get_setting("RAW_DATA_ROOT", settings, "data/raw"), "data/raw"),
        REVIEW_DATA_ROOT=resolve_path_setting(
            base_dir,
            get_setting("REVIEW_DATA_ROOT", settings, "data/review"),
            "data/review",
        ),
        VERIFICATION_DATA_ROOT=resolve_path_setting(
            base_dir,
            get_setting("VERIFICATION_DATA_ROOT", settings, "data/verification"),
            "data/verification",
        ),
        LINKED_DATA_ROOT=resolve_path_setting(
            base_dir,
            get_setting("LINKED_DATA_ROOT", settings, "data/raw/linked"),
            "data/raw/linked",
        ),
        HOST=get_setting("HOST", settings, "0.0.0.0"),
        PORT=get_int_setting("PORT", settings, 5050),
        LAN_ACCESS_HOST=get_setting("LAN_ACCESS_HOST", settings, ""),
        MAX_CONTENT_LENGTH=max_content_length_mb * 1024 * 1024,
        MAX_CONTENT_LENGTH_MB=max_content_length_mb,
        SUPPORTED_EXTENSIONS=SUPPORTED_EXTENSIONS,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=get_bool_setting("SESSION_COOKIE_SECURE", settings, False),
        SESSION_REFRESH_EACH_REQUEST=False,
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=access_session_minutes),
        HIDE_INTERNAL_PATHS=get_bool_setting("HIDE_INTERNAL_PATHS", settings, True),
    )

    for path_key in (
        "DATA_ROOT",
        "STORAGE_ROOT",
        "TEMP_UPLOAD_ROOT",
        "FILE_LIBRARY_ROOT",
        "ARCHIVE_ROOT",
        "EXPORT_ROOT",
        "REPORT_EXPORT_ROOT",
        "DOCS_ROOT",
        "LOG_ROOT",
        "RAW_DATA_ROOT",
        "REVIEW_DATA_ROOT",
        "VERIFICATION_DATA_ROOT",
        "LINKED_DATA_ROOT",
    ):
        app.config[path_key].mkdir(parents=True, exist_ok=True)
    app.config["DATABASE_PATH"].parent.mkdir(parents=True, exist_ok=True)

    init_db(app.config["DATABASE_PATH"])
    app.register_blueprint(bp)
    with app.app_context():
        ensure_bootstrap_access_codes()
        upgrade_existing_documents()
    return app
