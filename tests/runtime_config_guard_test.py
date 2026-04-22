from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import (
    DEFAULT_ADMIN_ACCESS_CODE,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_SECRET_KEY,
    DEFAULT_VIEWER_ACCESS_CODE,
    validate_runtime_config,
)


VALID_PRODUCTION_CONFIG = {
    "APP_ENV": "production",
    "APP_RUNTIME_ROOT": ".",
    "SECRET_KEY": "prod-secret-key-20260421",
    "SESSION_COOKIE_SECURE": True,
    "BOOTSTRAP_ADMIN_ENABLED": False,
    "ADMIN_PASSWORD": "",
    "ADMIN_PASSWORD_HASH": "pbkdf2:sha256:600000$demo$safehashvalue",
    "INITIAL_ADMIN_ACCESS_CODE": "928431",
    "INITIAL_VIEWER_ACCESS_CODE": "563274",
    "HIDE_INTERNAL_PATHS": True,
}


def expect_failure(overrides: dict, expected_fragment: str, *, settings_path: Path | None = Path("config/local_settings.json")):
    config = dict(VALID_PRODUCTION_CONFIG)
    config.update(overrides)
    try:
        validate_runtime_config(
            config,
            settings_path=settings_path,
            env_source_exists=False,
            runtime_paths_explicit=True,
        )
    except RuntimeError as exc:
        assert expected_fragment in str(exc), str(exc)
        return
    raise AssertionError(f"expected runtime config validation failure containing: {expected_fragment}")


def main() -> None:
    validate_runtime_config({"APP_ENV": "local", "SECRET_KEY": DEFAULT_SECRET_KEY}, settings_path=None, env_source_exists=False)
    validate_runtime_config(
        VALID_PRODUCTION_CONFIG,
        settings_path=Path("config/local_settings.json"),
        env_source_exists=False,
        runtime_paths_explicit=True,
    )

    expect_failure({"SECRET_KEY": DEFAULT_SECRET_KEY}, "SECRET_KEY")
    expect_failure({"SESSION_COOKIE_SECURE": False}, "SESSION_COOKIE_SECURE")
    expect_failure({"BOOTSTRAP_ADMIN_ENABLED": True}, "BOOTSTRAP_ADMIN_ENABLED")
    expect_failure({"ADMIN_PASSWORD": DEFAULT_ADMIN_PASSWORD, "ADMIN_PASSWORD_HASH": ""}, "ADMIN_PASSWORD")
    expect_failure({"INITIAL_ADMIN_ACCESS_CODE": DEFAULT_ADMIN_ACCESS_CODE}, "INITIAL_ADMIN_ACCESS_CODE")
    expect_failure({"INITIAL_VIEWER_ACCESS_CODE": DEFAULT_VIEWER_ACCESS_CODE}, "INITIAL_VIEWER_ACCESS_CODE")
    expect_failure({"HIDE_INTERNAL_PATHS": False}, "HIDE_INTERNAL_PATHS")
    expect_failure({}, "真实配置来源", settings_path=None)
    try:
        validate_runtime_config(
            VALID_PRODUCTION_CONFIG,
            settings_path=Path("config/local_settings.json"),
            env_source_exists=False,
            runtime_paths_explicit=False,
        )
    except RuntimeError as exc:
        assert "显式配置 APP_RUNTIME_ROOT" in str(exc), str(exc)
    else:
        raise AssertionError("expected runtime path explicit guard failure")

    print("runtime_config_guard_test_ok")


if __name__ == "__main__":
    main()
