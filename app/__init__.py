import json
import os
import sqlite3
import tempfile
from datetime import timedelta
from pathlib import Path

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix

from .admin_auth import ensure_access_code_history, ensure_bootstrap_access_codes
from .constants import SUPPORTED_EXTENSIONS
from .db import init_db
from .routes import bp
from .services import upgrade_existing_documents
from .url_runtime import normalize_public_base_url


DEFAULT_SECRET_KEY = "agarwood-intelligence-local-browser"
DEFAULT_ADMIN_PASSWORD = "123456"
DEFAULT_ADMIN_ACCESS_CODE = "admin-123456"
DEFAULT_VIEWER_ACCESS_CODE = "viewer-123456"
SQLITE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
STRICT_RUNTIME_PATH_KEYS = (
    "APP_RUNTIME_ROOT",
    "DATA_ROOT",
    "STORAGE_ROOT",
    "EXPORTS_ROOT",
    "ARCHIVE_ROOT",
    "DATABASE_PATH",
    "TEMP_UPLOAD_ROOT",
    "FILE_LIBRARY_ROOT",
    "LOG_ROOT",
    "RAW_DATA_ROOT",
    "REVIEW_DATA_ROOT",
    "VERIFICATION_DATA_ROOT",
    "LINKED_DATA_ROOT",
)
RUNTIME_REQUIRED_TABLES = ("documents", "sections", "entries", "access_identities")
MIN_RUNTIME_DATABASE_BYTES = 262_144

CONFIG_SOURCE_ENV_KEYS = (
    "APP_ENV",
    "DEPLOYMENT_MODE",
    "SECRET_KEY",
    "ADMIN_PASSWORD",
    "ADMIN_PASSWORD_HASH",
    "SESSION_COOKIE_SECURE",
    "BOOTSTRAP_ADMIN_ENABLED",
    "INITIAL_ADMIN_ACCESS_CODE",
    "INITIAL_VIEWER_ACCESS_CODE",
    "HIDE_INTERNAL_PATHS",
    "HOST",
    "PORT",
    "APP_RUNTIME_ROOT",
    "DATA_ROOT",
    "STORAGE_ROOT",
    "EXPORTS_ROOT",
    "ARCHIVE_ROOT",
    "DATABASE_PATH",
    "APP_SERVER_WORKERS",
    "WEB_CONCURRENCY",
    "PUBLIC_BASE_URL",
    "TRUST_PROXY_HEADERS",
    "PROXY_FIX_X_FOR",
    "PROXY_FIX_X_PROTO",
    "PROXY_FIX_X_HOST",
    "PROXY_FIX_X_PORT",
    "PROXY_FIX_X_PREFIX",
)

PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "change-me",
    "replace-me",
    "replace_with_real_value",
    "replace-with-a-real-secret-key",
    "replace-with-your-secret-key",
    "replace-with-your-admin-password",
    "replace-with-your-admin-password-hash",
    "replace-with-admin-access-code",
    "replace-with-viewer-access-code",
    "https://example.com",
    "http://example.com",
}


def load_local_settings(base_dir: Path) -> tuple[dict, Path | None]:
    candidate_paths = [
        base_dir / "config" / "local_settings.json",
        base_dir / "local_settings.json",
    ]
    for settings_path in candidate_paths:
        if not settings_path.exists():
            continue
        try:
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}, settings_path
        return payload if isinstance(payload, dict) else {}, settings_path
    return {}, None


def get_setting(name: str, settings: dict, default):
    return os.environ.get(name, settings.get(name, default))


def setting_present(name: str, settings: dict) -> bool:
    return name in os.environ or name in settings


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


def get_non_negative_int_setting(name: str, settings: dict, default: int) -> int:
    value = get_int_setting(name, settings, default)
    return max(value, 0)


def resolve_path_setting(base_dir: Path, value, default_relative: str) -> Path:
    configured_path = Path(str(value or default_relative))
    if configured_path.is_absolute():
        return configured_path
    return base_dir / configured_path


def resolve_runtime_path(runtime_root: Path, value, default_relative: str) -> Path:
    configured_path = Path(str(value or default_relative))
    if configured_path.is_absolute():
        return configured_path
    return runtime_root / configured_path


def resolve_app_env(settings: dict) -> str:
    raw_value = (
        os.environ.get("APP_ENV")
        or os.environ.get("DEPLOYMENT_MODE")
        or settings.get("APP_ENV")
        or settings.get("DEPLOYMENT_MODE")
        or "local"
    )
    normalized = str(raw_value or "").strip().lower()
    if normalized in {"", "local"}:
        return "local"
    if normalized == "production":
        return "production"
    raise RuntimeError("APP_ENV / DEPLOYMENT_MODE 只允许使用 'local' 或 'production'。")


def resolve_server_worker_count(settings: dict) -> int:
    raw_value = (
        os.environ.get("APP_SERVER_WORKERS")
        or os.environ.get("WEB_CONCURRENCY")
        or settings.get("APP_SERVER_WORKERS")
        or settings.get("WEB_CONCURRENCY")
        or 1
    )
    try:
        count = int(raw_value)
    except (TypeError, ValueError):
        count = 1
    return max(count, 1)


def resolve_public_base_url(settings: dict) -> str:
    raw_value = get_setting("PUBLIC_BASE_URL", settings, "")
    try:
        return normalize_public_base_url(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"PUBLIC_BASE_URL 配置无效：{exc}") from exc


def detect_config_source(settings_path: Path | None) -> tuple[bool, bool, str]:
    settings_source_exists = settings_path is not None
    env_source_exists = any(name in os.environ for name in CONFIG_SOURCE_ENV_KEYS)
    if settings_source_exists and env_source_exists:
        return settings_source_exists, env_source_exists, "local_settings.json + environment"
    if settings_source_exists:
        return settings_source_exists, env_source_exists, "local_settings.json"
    if env_source_exists:
        return settings_source_exists, env_source_exists, "environment"
    return settings_source_exists, env_source_exists, "defaults-only"


def _normalize_config_value(value) -> str:
    return str(value or "").strip()


def _is_obvious_placeholder(value) -> bool:
    normalized = _normalize_config_value(value).lower()
    if normalized in PLACEHOLDER_VALUES:
        return True
    placeholder_tokens = ("replace-with", "replace_me", "placeholder", "example-value", "todo")
    return any(token in normalized for token in placeholder_tokens)


def _uses_default_or_placeholder(value, default_value: str) -> bool:
    normalized = _normalize_config_value(value)
    if not normalized:
        return True
    if normalized == default_value:
        return True
    return _is_obvious_placeholder(normalized)


def _is_sqlite_database_path(path: Path | str) -> bool:
    return Path(path).suffix.lower() in SQLITE_SUFFIXES


def runtime_paths_explicitly_configured(settings: dict) -> bool:
    return any(setting_present(name, settings) for name in STRICT_RUNTIME_PATH_KEYS)


def _count_files_under(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for item in path.rglob("*") if item.is_file())


def _inspect_runtime_database(database_path: Path) -> dict[str, object]:
    info: dict[str, object] = {
        "path": database_path,
        "exists": database_path.exists(),
        "is_file": database_path.is_file() if database_path.exists() else False,
        "size_bytes": database_path.stat().st_size if database_path.exists() and database_path.is_file() else 0,
        "table_names": set(),
    }
    if not info["exists"] or not info["is_file"]:
        return info

    try:
        connection = sqlite3.connect(str(database_path))
        connection.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        info["error"] = str(exc)
        return info

    try:
        table_names = {
            row["name"]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        info["table_names"] = table_names
        for table_name in (*RUNTIME_REQUIRED_TABLES, "entry_marks"):
            if table_name in table_names:
                info[f"{table_name}_count"] = connection.execute(
                    f"SELECT COUNT(1) AS count FROM {table_name}"
                ).fetchone()["count"]
            else:
                info[f"{table_name}_count"] = 0
        if "access_identities" in table_names:
            info["active_admin_count"] = connection.execute(
                """
                SELECT COUNT(1) AS count
                FROM access_identities
                WHERE status = 'active' AND role = 'admin'
                """
            ).fetchone()["count"]
            info["active_viewer_count"] = connection.execute(
                """
                SELECT COUNT(1) AS count
                FROM access_identities
                WHERE status = 'active' AND role = 'viewer'
                """
            ).fetchone()["count"]
    except sqlite3.Error as exc:
        info["error"] = str(exc)
    finally:
        connection.close()
    return info


def build_runtime_paths(base_dir: Path, settings: dict) -> dict[str, Path]:
    runtime_root = resolve_path_setting(base_dir, get_setting("APP_RUNTIME_ROOT", settings, "."), ".")
    data_root = resolve_runtime_path(runtime_root, get_setting("DATA_ROOT", settings, "data"), "data")
    storage_root = resolve_runtime_path(runtime_root, get_setting("STORAGE_ROOT", settings, "storage"), "storage")
    exports_root = resolve_runtime_path(runtime_root, get_setting("EXPORTS_ROOT", settings, "exports"), "exports")

    if setting_present("DATABASE_PATH", settings):
        database_path = resolve_runtime_path(
            runtime_root,
            get_setting("DATABASE_PATH", settings, "data/database/intelligence_browser.db"),
            "data/database/intelligence_browser.db",
        )
    else:
        database_path = data_root / "database" / "intelligence_browser.db"

    if setting_present("TEMP_UPLOAD_ROOT", settings):
        temp_upload_root = resolve_runtime_path(
            runtime_root,
            get_setting("TEMP_UPLOAD_ROOT", settings, "storage/cache/incoming"),
            "storage/cache/incoming",
        )
    else:
        temp_upload_root = storage_root / "cache" / "incoming"

    if setting_present("FILE_LIBRARY_ROOT", settings):
        file_library_root = resolve_runtime_path(
            runtime_root,
            get_setting("FILE_LIBRARY_ROOT", settings, "storage/file_library"),
            "storage/file_library",
        )
    else:
        file_library_root = storage_root / "file_library"

    if setting_present("ARCHIVE_ROOT", settings):
        archive_root = resolve_runtime_path(
            runtime_root,
            get_setting("ARCHIVE_ROOT", settings, "data/processed/archive_parsed"),
            "data/processed/archive_parsed",
        )
    else:
        archive_root = data_root / "processed" / "archive_parsed"

    if setting_present("EXPORT_ROOT", settings):
        export_root = resolve_runtime_path(
            runtime_root,
            get_setting("EXPORT_ROOT", settings, "exports/pdf"),
            "exports/pdf",
        )
    else:
        export_root = exports_root / "pdf"

    if setting_present("REPORT_EXPORT_ROOT", settings):
        report_export_root = resolve_runtime_path(
            runtime_root,
            get_setting("REPORT_EXPORT_ROOT", settings, "exports/reports"),
            "exports/reports",
        )
    else:
        report_export_root = exports_root / "reports"

    docs_root = resolve_path_setting(base_dir, get_setting("DOCS_ROOT", settings, "docs"), "docs")

    if setting_present("LOG_ROOT", settings):
        log_root = resolve_runtime_path(runtime_root, get_setting("LOG_ROOT", settings, "storage/logs"), "storage/logs")
    else:
        log_root = storage_root / "logs"

    if setting_present("RAW_DATA_ROOT", settings):
        raw_data_root = resolve_runtime_path(runtime_root, get_setting("RAW_DATA_ROOT", settings, "data/raw"), "data/raw")
    else:
        raw_data_root = data_root / "raw"

    if setting_present("REVIEW_DATA_ROOT", settings):
        review_data_root = resolve_runtime_path(
            runtime_root,
            get_setting("REVIEW_DATA_ROOT", settings, "data/review"),
            "data/review",
        )
    else:
        review_data_root = data_root / "review"

    if setting_present("VERIFICATION_DATA_ROOT", settings):
        verification_data_root = resolve_runtime_path(
            runtime_root,
            get_setting("VERIFICATION_DATA_ROOT", settings, "data/verification"),
            "data/verification",
        )
    else:
        verification_data_root = data_root / "verification"

    if setting_present("LINKED_DATA_ROOT", settings):
        linked_data_root = resolve_runtime_path(
            runtime_root,
            get_setting("LINKED_DATA_ROOT", settings, "data/raw/linked"),
            "data/raw/linked",
        )
    else:
        linked_data_root = raw_data_root / "linked"

    return {
        "APP_RUNTIME_ROOT": runtime_root,
        "DATA_ROOT": data_root,
        "STORAGE_ROOT": storage_root,
        "EXPORTS_ROOT": exports_root,
        "ARCHIVE_ROOT": archive_root,
        "DATABASE_PATH": database_path,
        "TEMP_UPLOAD_ROOT": temp_upload_root,
        "FILE_LIBRARY_ROOT": file_library_root,
        "EXPORT_ROOT": export_root,
        "REPORT_EXPORT_ROOT": report_export_root,
        "DOCS_ROOT": docs_root,
        "LOG_ROOT": log_root,
        "RAW_DATA_ROOT": raw_data_root,
        "REVIEW_DATA_ROOT": review_data_root,
        "VERIFICATION_DATA_ROOT": verification_data_root,
        "LINKED_DATA_ROOT": linked_data_root,
    }


def validate_runtime_config(
    config,
    *,
    settings_path: Path | None = None,
    env_source_exists: bool = False,
    runtime_paths_explicit: bool = False,
) -> list[str]:
    app_env = str(config.get("APP_ENV", "local")).strip().lower()
    warnings: list[str] = []
    worker_count = int(config.get("APP_SERVER_WORKERS", 1) or 1)
    database_path = Path(config.get("DATABASE_PATH", ""))

    if worker_count > 1 and _is_sqlite_database_path(database_path):
        message = "当前默认 SQLite 仅支持单实例部署，APP_SERVER_WORKERS / WEB_CONCURRENCY 不能大于 1。"
        if app_env == "production":
            raise RuntimeError("production 配置校验失败：\n- " + message)
        warnings.append(message)

    if app_env == "local":
        if _uses_default_or_placeholder(config.get("SECRET_KEY"), DEFAULT_SECRET_KEY):
            warnings.append("local 模式仍在使用默认 SECRET_KEY。")
        if not bool(config.get("SESSION_COOKIE_SECURE", False)):
            warnings.append("local 模式 SESSION_COOKIE_SECURE 当前为 false。")
        if bool(config.get("BOOTSTRAP_ADMIN_ENABLED", False)):
            warnings.append("local 模式启用了 BOOTSTRAP_ADMIN_ENABLED，请勿将该配置直接带入 production。")
        return warnings

    errors: list[str] = []
    if app_env != "production":
        raise RuntimeError("运行模式无效：APP_ENV / DEPLOYMENT_MODE 只允许 local 或 production。")

    if settings_path is None and not env_source_exists:
        errors.append("production 模式必须提供真实配置来源：请创建 config/local_settings.json，或通过环境变量注入生产配置。")

    if not runtime_paths_explicit:
        errors.append("production / rehearsal 模式必须显式配置 APP_RUNTIME_ROOT 或关键运行路径，不能回退到仓库默认 runtime。")

    if _uses_default_or_placeholder(config.get("SECRET_KEY"), DEFAULT_SECRET_KEY):
        errors.append("SECRET_KEY 不能为空，也不能继续使用默认值或占位值。")

    if not bool(config.get("SESSION_COOKIE_SECURE", False)):
        errors.append("SESSION_COOKIE_SECURE 在 production 模式下必须为 true。")

    if bool(config.get("BOOTSTRAP_ADMIN_ENABLED", False)):
        errors.append("BOOTSTRAP_ADMIN_ENABLED 在 production 模式下必须为 false。")

    admin_password = _normalize_config_value(config.get("ADMIN_PASSWORD"))
    admin_password_hash = _normalize_config_value(config.get("ADMIN_PASSWORD_HASH"))
    if admin_password and _uses_default_or_placeholder(admin_password, DEFAULT_ADMIN_PASSWORD):
        errors.append("ADMIN_PASSWORD 不能继续使用默认值或占位值。")
    if admin_password_hash and _is_obvious_placeholder(admin_password_hash):
        errors.append("ADMIN_PASSWORD_HASH 不能使用占位值。")
    if not admin_password and not admin_password_hash:
        errors.append("production 模式必须显式配置 ADMIN_PASSWORD 或 ADMIN_PASSWORD_HASH。")

    if _uses_default_or_placeholder(config.get("INITIAL_ADMIN_ACCESS_CODE"), DEFAULT_ADMIN_ACCESS_CODE):
        errors.append("INITIAL_ADMIN_ACCESS_CODE 不能继续使用默认值或占位值。")

    if _uses_default_or_placeholder(config.get("INITIAL_VIEWER_ACCESS_CODE"), DEFAULT_VIEWER_ACCESS_CODE):
        errors.append("INITIAL_VIEWER_ACCESS_CODE 不能继续使用默认值或占位值。")

    if not bool(config.get("HIDE_INTERNAL_PATHS", True)):
        errors.append("HIDE_INTERNAL_PATHS 在 production 模式下必须为 true。")

    if errors:
        raise RuntimeError("production 配置校验失败：\n- " + "\n- ".join(errors))
    return warnings


def _ensure_directory(path: Path, label: str) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"{label} 目录初始化失败：{path} ({exc})") from exc


def _require_existing_directory(path: Path, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"{label} 缺失：{path}")
    if not path.is_dir():
        raise RuntimeError(f"{label} 不是目录：{path}")


def _ensure_directory_writable(path: Path, label: str) -> None:
    try:
        with tempfile.NamedTemporaryFile(dir=path, prefix=".wenmai_probe_", delete=True) as handle:
            handle.write(b"probe")
            handle.flush()
    except OSError as exc:
        raise RuntimeError(f"{label} 不可写：{path} ({exc})") from exc


def initialize_runtime_paths(config) -> None:
    strict_runtime = str(config.get("APP_ENV", "local")).strip().lower() == "production"
    directory_map = {
        "APP_RUNTIME_ROOT": config["APP_RUNTIME_ROOT"],
        "DATA_ROOT": config["DATA_ROOT"],
        "STORAGE_ROOT": config["STORAGE_ROOT"],
        "EXPORTS_ROOT": config["EXPORTS_ROOT"],
        "ARCHIVE_ROOT": config["ARCHIVE_ROOT"],
        "TEMP_UPLOAD_ROOT": config["TEMP_UPLOAD_ROOT"],
        "FILE_LIBRARY_ROOT": config["FILE_LIBRARY_ROOT"],
        "EXPORT_ROOT": config["EXPORT_ROOT"],
        "REPORT_EXPORT_ROOT": config["REPORT_EXPORT_ROOT"],
        "LOG_ROOT": config["LOG_ROOT"],
        "RAW_DATA_ROOT": config["RAW_DATA_ROOT"],
        "REVIEW_DATA_ROOT": config["REVIEW_DATA_ROOT"],
        "VERIFICATION_DATA_ROOT": config["VERIFICATION_DATA_ROOT"],
        "LINKED_DATA_ROOT": config["LINKED_DATA_ROOT"],
        "DATABASE_PARENT": config["DATABASE_PATH"].parent,
    }

    for label, path in directory_map.items():
        if strict_runtime:
            _require_existing_directory(path, label)
        else:
            _ensure_directory(path, label)

    for label in (
        "DATA_ROOT",
        "STORAGE_ROOT",
        "EXPORTS_ROOT",
        "ARCHIVE_ROOT",
        "TEMP_UPLOAD_ROOT",
        "FILE_LIBRARY_ROOT",
        "EXPORT_ROOT",
        "REPORT_EXPORT_ROOT",
        "LOG_ROOT",
        "RAW_DATA_ROOT",
        "REVIEW_DATA_ROOT",
        "VERIFICATION_DATA_ROOT",
        "LINKED_DATA_ROOT",
        "DATABASE_PARENT",
    ):
        _ensure_directory_writable(directory_map[label], label)


def validate_runtime_materials(config) -> list[str]:
    app_env = str(config.get("APP_ENV", "local")).strip().lower()
    warnings: list[str] = []
    strict_runtime = app_env == "production"
    database_path = Path(config["DATABASE_PATH"])
    raw_root = Path(config["RAW_DATA_ROOT"])
    file_library_root = Path(config["FILE_LIBRARY_ROOT"])
    archive_root = Path(config["ARCHIVE_ROOT"])

    if not strict_runtime:
        if not database_path.exists():
            warnings.append("local 模式未找到 DATABASE_PATH，对应数据库会在本地模式下按需初始化。")
            return warnings
        inspect = _inspect_runtime_database(database_path)
        if inspect.get("error"):
            warnings.append(f"local 模式数据库检查发现异常：{inspect['error']}")
        elif int(inspect.get("size_bytes", 0) or 0) < MIN_RUNTIME_DATABASE_BYTES:
            warnings.append("local 模式检测到较小数据库文件，请确认不是误跑出的壳库。")
        return warnings

    errors: list[str] = []
    if not database_path.exists():
        errors.append(f"DATABASE_PATH 缺失：{database_path}")
    elif not database_path.is_file():
        errors.append(f"DATABASE_PATH 不是有效文件：{database_path}")

    inspect = _inspect_runtime_database(database_path)
    if inspect.get("error"):
        errors.append(f"数据库文件不可读或不是有效 SQLite：{inspect['error']}")

    table_names = inspect.get("table_names", set()) or set()
    missing_tables = [table_name for table_name in RUNTIME_REQUIRED_TABLES if table_name not in table_names]
    if missing_tables:
        errors.append("数据库缺少核心业务表：" + ", ".join(missing_tables))

    size_bytes = int(inspect.get("size_bytes", 0) or 0)
    entries_count = int(inspect.get("entries_count", 0) or 0)
    documents_count = int(inspect.get("documents_count", 0) or 0)
    sections_count = int(inspect.get("sections_count", 0) or 0)
    if size_bytes < MIN_RUNTIME_DATABASE_BYTES and (
        missing_tables or (entries_count == 0 and documents_count == 0 and sections_count == 0)
    ):
        errors.append(
            f"DATABASE_PATH 文件过小（{size_bytes} bytes），检测到明显壳库特征。"
        )
    if entries_count == 0 and documents_count == 0 and sections_count == 0:
        errors.append("检测到壳库特征：entries / documents / sections 全为 0。")

    raw_count = _count_files_under(raw_root)
    library_count = _count_files_under(file_library_root)
    archive_count = _count_files_under(archive_root)
    if entries_count > 0 and raw_count == 0:
        errors.append("RAW_DATA_ROOT 为空，与当前数据库条目状态不匹配。")
    if documents_count > 0 and library_count == 0:
        errors.append("FILE_LIBRARY_ROOT 为空，与当前 documents 状态不匹配。")
    if documents_count > 0 and archive_count == 0:
        errors.append("ARCHIVE_ROOT 为空，与当前 documents / sections 状态不匹配。")

    if errors:
        raise RuntimeError("runtime 守卫失败：\n- " + "\n- ".join(errors))
    return warnings


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parent.parent
    settings, settings_path = load_local_settings(base_dir)
    app_env = resolve_app_env(settings)
    settings_source_exists, env_source_exists, config_source_label = detect_config_source(settings_path)
    runtime_paths_explicit = runtime_paths_explicitly_configured(settings)
    runtime_paths = build_runtime_paths(base_dir, settings)
    max_content_length_mb = get_int_setting("MAX_CONTENT_LENGTH_MB", settings, 50)
    admin_session_minutes = get_int_setting("ADMIN_SESSION_MINUTES", settings, 60)
    access_session_minutes = get_int_setting("ACCESS_SESSION_MINUTES", settings, 720)
    auth_max_failures = get_int_setting("AUTH_MAX_FAILURES", settings, 5)
    auth_window_minutes = get_int_setting("AUTH_WINDOW_MINUTES", settings, 30)
    auth_lock_minutes = get_int_setting("AUTH_LOCK_MINUTES", settings, 15)
    app_server_workers = resolve_server_worker_count(settings)
    public_base_url = resolve_public_base_url(settings)
    trust_proxy_headers = get_bool_setting("TRUST_PROXY_HEADERS", settings, False)
    proxy_fix_x_for = get_non_negative_int_setting("PROXY_FIX_X_FOR", settings, 1)
    proxy_fix_x_proto = get_non_negative_int_setting("PROXY_FIX_X_PROTO", settings, 1)
    proxy_fix_x_host = get_non_negative_int_setting("PROXY_FIX_X_HOST", settings, 1)
    proxy_fix_x_port = get_non_negative_int_setting("PROXY_FIX_X_PORT", settings, 1)
    proxy_fix_x_prefix = get_non_negative_int_setting("PROXY_FIX_X_PREFIX", settings, 0)
    preferred_url_scheme = public_base_url.split("://", 1)[0] if public_base_url else "http"

    app = Flask(__name__, instance_relative_config=False)
    app.config.update(
        APP_ENV=app_env,
        DEPLOYMENT_MODE=app_env,
        PROJECT_NAME="沉香行业情报浏览系统_1.0",
        BRAND_NAME=get_setting("BRAND_NAME", settings, "闻脉台"),
        PRODUCT_SUBTITLE=get_setting("PRODUCT_SUBTITLE", settings, "沉香行业情报工作台"),
        BRAND_SLOGAN=get_setting("BRAND_SLOGAN", settings, "看见信息，更看见脉络"),
        SECRET_KEY=get_setting("SECRET_KEY", settings, DEFAULT_SECRET_KEY),
        ADMIN_PASSWORD=get_setting("ADMIN_PASSWORD", settings, DEFAULT_ADMIN_PASSWORD),
        ADMIN_PASSWORD_HASH=get_setting("ADMIN_PASSWORD_HASH", settings, ""),
        BOOTSTRAP_ADMIN_ENABLED=get_bool_setting("BOOTSTRAP_ADMIN_ENABLED", settings, False),
        ACCESS_CONTROL_ENABLED=get_bool_setting("ACCESS_CONTROL_ENABLED", settings, True),
        ADMIN_SESSION_SECONDS=admin_session_minutes * 60,
        ACCESS_SESSION_SECONDS=access_session_minutes * 60,
        AUTH_MAX_FAILURES=auth_max_failures,
        AUTH_WINDOW_MINUTES=auth_window_minutes,
        AUTH_LOCK_MINUTES=auth_lock_minutes,
        INITIAL_ADMIN_ACCESS_CODE=get_setting("INITIAL_ADMIN_ACCESS_CODE", settings, DEFAULT_ADMIN_ACCESS_CODE),
        INITIAL_VIEWER_ACCESS_CODE=get_setting("INITIAL_VIEWER_ACCESS_CODE", settings, DEFAULT_VIEWER_ACCESS_CODE),
        BASE_DIR=base_dir,
        SETTINGS_PATH=str(settings_path) if settings_source_exists else "",
        RUNTIME_CONFIG_SOURCE=config_source_label,
        STARTUP_RUNTIME_REPAIRS_ENABLED=app_env == "local",
        APP_SERVER_WORKERS=app_server_workers,
        SINGLE_INSTANCE_ONLY=True,
        SERVER_ENTRYPOINT="wsgi:app",
        LOCAL_ENTRYPOINT="python run.py",
        PUBLIC_BASE_URL=public_base_url,
        TRUST_PROXY_HEADERS=trust_proxy_headers,
        PROXY_FIX_X_FOR=proxy_fix_x_for,
        PROXY_FIX_X_PROTO=proxy_fix_x_proto,
        PROXY_FIX_X_HOST=proxy_fix_x_host,
        PROXY_FIX_X_PORT=proxy_fix_x_port,
        PROXY_FIX_X_PREFIX=proxy_fix_x_prefix,
        PREFERRED_URL_SCHEME=preferred_url_scheme,
        LINKED_SOURCE_SAFE_MODE=get_bool_setting("LINKED_SOURCE_SAFE_MODE", settings, True),
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
    app.config.update(runtime_paths)

    app.config["RUNTIME_CONFIG_WARNINGS"] = validate_runtime_config(
        app.config,
        settings_path=settings_path,
        env_source_exists=env_source_exists,
        runtime_paths_explicit=runtime_paths_explicit,
    )

    if trust_proxy_headers:
        app.wsgi_app = ProxyFix(
            app.wsgi_app,
            x_for=proxy_fix_x_for,
            x_proto=proxy_fix_x_proto,
            x_host=proxy_fix_x_host,
            x_port=proxy_fix_x_port,
            x_prefix=proxy_fix_x_prefix,
        )

    initialize_runtime_paths(app.config)
    app.config["RUNTIME_CONFIG_WARNINGS"].extend(validate_runtime_materials(app.config))

    init_db(app.config["DATABASE_PATH"], allow_create=app_env == "local")
    app.register_blueprint(bp)
    with app.app_context():
        ensure_bootstrap_access_codes()
        ensure_access_code_history()
        if app.config.get("STARTUP_RUNTIME_REPAIRS_ENABLED", False):
            upgrade_existing_documents()
    return app
