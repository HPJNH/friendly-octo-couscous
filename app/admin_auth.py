from __future__ import annotations

import json
import hashlib
import hmac
import secrets
import time
from functools import wraps
from pathlib import Path

from flask import current_app, flash, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_connection
from .security import get_recent_audit_logs, rotate_csrf_token
from .url_runtime import sanitize_redirect_target
from .utils import now_string


ACCESS_SESSION_KEY = "access_session"
ROLE_RANK = {"viewer": 1, "admin": 2}
ACCESS_CODE_DIGITS = 6


def _fingerprint_secret(secret: str) -> str:
    payload = f"{current_app.config.get('SECRET_KEY', '')}:{secret or ''}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _code_hint(secret: str) -> str:
    value = (secret or "").strip()
    if len(value) <= 4:
        return value
    return f"{value[:2]}***{value[-2:]}"


def _required_rank(role: str) -> int:
    return ROLE_RANK.get(role, 1)


def _normalize_access_code(secret: str) -> str:
    return str(secret or "").strip()


def _validate_access_code_format(secret: str) -> str:
    value = _normalize_access_code(secret)
    if len(value) != ACCESS_CODE_DIGITS or not value.isdigit():
        raise ValueError(f"访问码必须是 {ACCESS_CODE_DIGITS} 位数字。")
    return value


def _get_identity_row(identity_id: int | None):
    if not identity_id:
        return None
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        return connection.execute(
            """
            SELECT *
            FROM access_identities
            WHERE id = ?
            LIMIT 1
            """,
            (identity_id,),
        ).fetchone()


def _code_fingerprint_exists(connection, fingerprint: str, exclude_identity_id: int | None = None) -> bool:
    history_exists = connection.execute(
        """
        SELECT 1
        FROM access_code_history
        WHERE code_hash = ?
        LIMIT 1
        """,
        (fingerprint,),
    ).fetchone()
    if history_exists:
        return True

    params: list[object] = [fingerprint]
    query = """
        SELECT 1
        FROM access_identities
        WHERE code_hash = ?
    """
    if exclude_identity_id is not None:
        query += " AND id != ?"
        params.append(exclude_identity_id)
    query += " LIMIT 1"
    current_exists = connection.execute(query, tuple(params)).fetchone()
    return current_exists is not None


def _access_code_secret_exists(connection, secret: str, exclude_identity_id: int | None = None) -> bool:
    normalized_secret = _normalize_access_code(secret)
    if not normalized_secret:
        return False

    current_fingerprint = _fingerprint_secret(normalized_secret)
    if _code_fingerprint_exists(connection, current_fingerprint, exclude_identity_id=exclude_identity_id):
        return True

    params: list[object] = []
    current_query = """
        SELECT secret_hash
        FROM access_identities
        WHERE COALESCE(secret_hash, '') != ''
    """
    if exclude_identity_id is not None:
        current_query += " AND id != ?"
        params.append(exclude_identity_id)
    current_rows = connection.execute(current_query, tuple(params)).fetchall()
    for row in current_rows:
        if check_password_hash(row["secret_hash"], normalized_secret):
            return True

    history_params: list[object] = []
    history_query = """
        SELECT secret_hash
        FROM access_code_history
        WHERE COALESCE(secret_hash, '') != ''
    """
    if exclude_identity_id is not None:
        history_query += " AND COALESCE(identity_id, 0) != ?"
        history_params.append(exclude_identity_id)
    history_rows = connection.execute(history_query, tuple(history_params)).fetchall()
    for row in history_rows:
        if check_password_hash(row["secret_hash"], normalized_secret):
            return True

    return False


def _retire_access_code_history(connection, identity_id: int, retired_at: str) -> None:
    connection.execute(
        """
        UPDATE access_code_history
        SET is_current = 0,
            retired_at = COALESCE(retired_at, ?)
        WHERE identity_id = ?
          AND is_current = 1
        """,
        (retired_at, identity_id),
    )


def _record_access_code_history(
    connection,
    *,
    identity_id: int | None,
    fingerprint: str,
    secret_hash: str,
    code_hint: str,
    created_at: str,
    is_current: bool,
    retired_at: str | None = None,
) -> None:
    connection.execute(
        """
        INSERT OR IGNORE INTO access_code_history (
            identity_id,
            code_hash,
            secret_hash,
            code_hint,
            is_current,
            created_at,
            retired_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (identity_id, fingerprint, secret_hash, code_hint, 1 if is_current else 0, created_at, retired_at),
    )
    connection.execute(
        """
        UPDATE access_code_history
        SET identity_id = COALESCE(identity_id, ?),
            secret_hash = COALESCE(NULLIF(secret_hash, ''), ?),
            code_hint = ?,
            is_current = ?,
            retired_at = ?
        WHERE code_hash = ?
        """,
        (identity_id, secret_hash, code_hint, 1 if is_current else 0, None if is_current else retired_at, fingerprint),
    )


def _iter_access_history_backups(log_root: Path) -> list[Path]:
    backup_root = log_root / "access_reset_backups"
    if not backup_root.exists():
        return []
    return sorted(backup_root.glob("*/access_identities_before_reset.json"))


def ensure_access_code_history() -> None:
    database_path = current_app.config["DATABASE_PATH"]
    log_root = Path(current_app.config.get("LOG_ROOT", ""))
    now = now_string()
    with get_connection(database_path) as connection:
        current_rows = connection.execute(
            """
            SELECT id, code_hash, secret_hash, code_hint, created_at, updated_at, status
            FROM access_identities
            """
        ).fetchall()
        for row in current_rows:
            is_current = row["status"] == "active"
            retired_at = None if is_current else (row["updated_at"] or now)
            _record_access_code_history(
                connection,
                identity_id=row["id"],
                fingerprint=row["code_hash"],
                secret_hash=row["secret_hash"] or "",
                code_hint=row["code_hint"] or "",
                created_at=row["created_at"] or now,
                is_current=is_current,
                retired_at=retired_at,
            )

        for backup_path in _iter_access_history_backups(log_root):
            try:
                payload = json.loads(backup_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                fingerprint = str(item.get("code_hash") or "").strip()
                if not fingerprint:
                    continue
                connection.execute(
                    """
                    INSERT OR IGNORE INTO access_code_history (
                        identity_id,
                        code_hash,
                        secret_hash,
                        code_hint,
                        is_current,
                        created_at,
                        retired_at
                    ) VALUES (?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        None,
                        fingerprint,
                        "",
                        str(item.get("code_hint") or ""),
                        str(item.get("created_at") or now),
                        str(item.get("updated_at") or now),
                    ),
                )
        connection.commit()


def _identity_matches_secret(row, secret: str) -> bool:
    normalized_secret = _normalize_access_code(secret)
    if not normalized_secret:
        return False
    secret_hash = row["secret_hash"] or ""
    if secret_hash:
        return check_password_hash(secret_hash, normalized_secret)
    return hmac.compare_digest(row["code_hash"], _fingerprint_secret(normalized_secret))


def _find_active_identity_by_secret(connection, secret: str):
    normalized_secret = _normalize_access_code(secret)
    if not normalized_secret:
        return None

    fingerprint = _fingerprint_secret(normalized_secret)
    exact_rows = connection.execute(
        """
        SELECT *
        FROM access_identities
        WHERE status = 'active'
          AND code_hash = ?
        ORDER BY updated_at DESC, id DESC
        """,
        (fingerprint,),
    ).fetchall()
    seen_ids = {row["id"] for row in exact_rows}
    for row in exact_rows:
        if _identity_matches_secret(row, normalized_secret):
            return row

    fallback_rows = connection.execute(
        """
        SELECT *
        FROM access_identities
        WHERE status = 'active'
        ORDER BY updated_at DESC, id DESC
        """
    ).fetchall()
    for row in fallback_rows:
        if row["id"] in seen_ids:
            continue
        if _identity_matches_secret(row, normalized_secret):
            return row
    return None


def _sync_identity_secret_material(connection, row, secret: str) -> None:
    normalized_secret = _normalize_access_code(secret)
    if not normalized_secret:
        return

    fingerprint = _fingerprint_secret(normalized_secret)
    now = now_string()
    secret_hash = row["secret_hash"] or ""
    if not secret_hash:
        secret_hash = generate_password_hash(normalized_secret)

    connection.execute(
        """
        UPDATE access_identities
        SET code_hash = ?,
            secret_hash = ?,
            last_used_at = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (fingerprint, secret_hash, now, now, row["id"]),
    )
    _record_access_code_history(
        connection,
        identity_id=row["id"],
        fingerprint=fingerprint,
        secret_hash=secret_hash,
        code_hint=row["code_hint"] or _code_hint(normalized_secret),
        created_at=row["created_at"] or now,
        is_current=True,
    )


def _session_ttl(role: str) -> int:
    if role == "admin":
        return int(current_app.config.get("ADMIN_SESSION_SECONDS", 3600))
    return int(current_app.config.get("ACCESS_SESSION_SECONDS", 3600))


def access_control_enabled() -> bool:
    return bool(current_app.config.get("ACCESS_CONTROL_ENABLED", True))


def bootstrap_admin_enabled() -> bool:
    return bool(current_app.config.get("BOOTSTRAP_ADMIN_ENABLED", False))


def current_access_session() -> dict:
    payload = session.get(ACCESS_SESSION_KEY) or {}
    verified_at = int(payload.get("verified_at", 0) or 0)
    if not verified_at:
        return {}

    now = int(time.time())
    expires_at = int(payload.get("expires_at", 0) or 0)
    if not expires_at:
        expires_at = verified_at + _session_ttl(payload.get("role", "viewer"))
    if now > expires_at:
        clear_access_session()
        return {}

    identity_id = payload.get("identity_id")
    method = payload.get("method", "access-code")
    if identity_id is None:
        if method == "password":
            if not bootstrap_admin_enabled():
                clear_access_session()
                return {}
            return payload
        clear_access_session()
        return {}

    row = _get_identity_row(identity_id)
    if not row or row["status"] != "active":
        clear_access_session()
        return {}

    if payload.get("label") != row["label"] or payload.get("role") != row["role"]:
        payload = {
            **payload,
            "label": row["label"],
            "role": row["role"],
        }
        session[ACCESS_SESSION_KEY] = payload
    return payload


def is_access_verified(required_role: str = "viewer") -> bool:
    if not access_control_enabled():
        return True
    payload = current_access_session()
    if not payload:
        return False
    return _required_rank(payload.get("role", "viewer")) >= _required_rank(required_role)


def is_admin_verified() -> bool:
    return is_access_verified("admin")


def current_access_role() -> str:
    return current_access_session().get("role", "guest")


def current_access_label() -> str:
    return current_access_session().get("label", "未验证")


def get_current_access_identity() -> dict | None:
    payload = current_access_session()
    identity_id = payload.get("identity_id")
    row = _get_identity_row(identity_id)
    if not row or row["status"] != "active":
        return None
    return {
        "id": row["id"],
        "label": row["label"],
        "role": row["role"],
        "status": row["status"],
        "code_hint": row["code_hint"],
        "notes": row["notes"] or "",
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_used_at": row["last_used_at"] or "尚未使用",
    }


def mark_access_verified(identity_id: int | None, label: str, role: str, method: str) -> None:
    verified_at = int(time.time())
    session.permanent = False
    session[ACCESS_SESSION_KEY] = {
        "identity_id": identity_id,
        "label": label,
        "role": role,
        "method": method,
        "verified_at": verified_at,
        "expires_at": verified_at + _session_ttl(role),
    }
    rotate_csrf_token()


def clear_access_session() -> None:
    session.pop(ACCESS_SESSION_KEY, None)
    rotate_csrf_token()


def ensure_bootstrap_access_codes() -> None:
    if not bootstrap_admin_enabled():
        return
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        count = connection.execute("SELECT COUNT(1) AS count FROM access_identities").fetchone()["count"]
        if count:
            return
        now = now_string()
        seed_rows = [
            ("默认管理员访问码", current_app.config.get("INITIAL_ADMIN_ACCESS_CODE", "admin-123456"), "admin", "首次启动自动生成"),
            ("默认查看访问码", current_app.config.get("INITIAL_VIEWER_ACCESS_CODE", "viewer-123456"), "viewer", "首次启动自动生成"),
        ]
        for label, raw_code, role, notes in seed_rows:
            fingerprint = _fingerprint_secret(raw_code)
            secret_hash = generate_password_hash(raw_code)
            identity_id = connection.execute(
                """
                INSERT INTO access_identities (
                    label, code_hash, secret_hash, code_hint, role, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (
                    label,
                    fingerprint,
                    secret_hash,
                    _code_hint(raw_code),
                    role,
                    notes,
                    now,
                    now,
                ),
            ).lastrowid
            _record_access_code_history(
                connection,
                identity_id=identity_id,
                fingerprint=fingerprint,
                secret_hash=secret_hash,
                code_hint=_code_hint(raw_code),
                created_at=now,
                is_current=True,
            )
        connection.commit()


def verify_admin_password(password: str) -> bool:
    if not bootstrap_admin_enabled():
        return False
    password = _normalize_access_code(password)
    configured_hash = str(current_app.config.get("ADMIN_PASSWORD_HASH", "") or "").strip()
    configured = str(current_app.config.get("ADMIN_PASSWORD", "123456"))
    if configured_hash:
        if check_password_hash(configured_hash, password or ""):
            mark_access_verified(identity_id=None, label="Bootstrap 管理员", role="admin", method="password")
            return True
    elif hmac.compare_digest(password or "", configured):
        mark_access_verified(identity_id=None, label="Bootstrap 管理员", role="admin", method="password")
        return True
    return False


def verify_access_secret(secret: str, required_role: str = "viewer") -> tuple[bool, str]:
    secret = _normalize_access_code(secret)
    if not secret.isdigit() or len(secret) != ACCESS_CODE_DIGITS:
        return False, "not-found"
    if verify_admin_password(secret):
        return True, "bootstrap-admin"

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = _find_active_identity_by_secret(connection, secret)
        if not row:
            return False, "not-found"
        if _required_rank(row["role"]) < _required_rank(required_role):
            return False, "role-denied"

        mark_access_verified(identity_id=row["id"], label=row["label"], role=row["role"], method="access-code")
        _sync_identity_secret_material(connection, row, secret)
        connection.commit()
    return True, "access-code"


def build_safe_next(candidate: str | None = None, fallback: str | None = None) -> str:
    value = candidate or (request.full_path.rstrip("?") if request.method == "GET" else request.referrer) or fallback or url_for("main.index")
    return sanitize_redirect_target(value, fallback or url_for("main.index"))


def access_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_access_verified("viewer"):
            return view(*args, **kwargs)
        flash(
            {
                "title": "需要访问验证",
                "body": "当前系统已启用访问控制，请先输入访问码后再进入浏览页面。",
            },
            "error",
        )
        return redirect(url_for("main.access_login", next=build_safe_next(request.values.get("next"))))

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if is_admin_verified():
            return view(*args, **kwargs)
        flash(
            {
                "title": "需要管理权限",
                "body": "该操作会影响文件状态或系统数据，请先输入管理员访问码。",
            },
            "error",
        )
        return redirect(url_for("main.admin_verify", next=build_safe_next(request.values.get("next"))))

    return wrapped


def get_access_management_view() -> dict:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM access_identities
            ORDER BY
                CASE role WHEN 'admin' THEN 0 ELSE 1 END,
                CASE status WHEN 'active' THEN 0 WHEN 'disabled' THEN 1 ELSE 2 END,
                updated_at DESC
            """
        ).fetchall()

    items = []
    summary = {"active": 0, "disabled": 0, "deleted": 0, "admins": 0, "viewers": 0}
    for row in rows:
        summary[row["status"]] = summary.get(row["status"], 0) + 1
        summary["admins" if row["role"] == "admin" else "viewers"] += 1
        items.append(
            {
                "id": row["id"],
                "label": row["label"],
                "code_hint": row["code_hint"],
                "role": row["role"],
                "status": row["status"],
                "notes": row["notes"] or "",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_used_at": row["last_used_at"] or "尚未使用",
                "can_disable": row["status"] == "active",
                "can_activate": row["status"] == "disabled",
                "can_delete": row["status"] != "deleted",
            }
        )
    return {"items": items, "summary": summary, "recent_logs": get_recent_audit_logs(limit=18)}


def create_access_identity(label: str, raw_code: str, role: str, notes: str = "") -> dict:
    label = (label or "").strip()
    raw_code = _validate_access_code_format(raw_code)
    role = "admin" if role == "admin" else "viewer"
    notes = (notes or "").strip()
    if not label:
        raise ValueError("请填写访问资格名称。")

    fingerprint = _fingerprint_secret(raw_code)
    secret_hash = generate_password_hash(raw_code)
    now = now_string()
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        if _access_code_secret_exists(connection, raw_code):
            raise ValueError("这串访问码已经被使用过了，请换一串新的 6 位数字。")
        identity_id = connection.execute(
            """
            INSERT INTO access_identities (
                label, code_hash, secret_hash, code_hint, role, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (
                label,
                fingerprint,
                secret_hash,
                _code_hint(raw_code),
                role,
                notes,
                now,
                now,
            ),
        ).lastrowid
        _record_access_code_history(
            connection,
            identity_id=identity_id,
            fingerprint=fingerprint,
            secret_hash=secret_hash,
            code_hint=_code_hint(raw_code),
            created_at=now,
            is_current=True,
        )
        connection.commit()
    return {"id": identity_id, "label": label, "role": role, "code_hint": _code_hint(raw_code)}


def update_access_identity_status(identity_id: int, status: str) -> dict:
    if status not in {"active", "disabled", "deleted"}:
        raise ValueError("不支持的访问资格状态。")
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM access_identities WHERE id = ?", (identity_id,)).fetchone()
        if not row:
            raise ValueError("未找到对应的访问资格。")
        updated_at = now_string()
        connection.execute(
            "UPDATE access_identities SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, identity_id),
        )
        if status == "active":
            _record_access_code_history(
                connection,
                identity_id=identity_id,
                fingerprint=row["code_hash"],
                secret_hash=row["secret_hash"] or "",
                code_hint=row["code_hint"] or "",
                created_at=row["created_at"] or updated_at,
                is_current=True,
            )
        else:
            _retire_access_code_history(connection, identity_id, updated_at)
        connection.commit()
    return {"id": identity_id, "label": row["label"], "status": status}


def change_access_identity_code(identity_id: int, current_code: str, new_code: str, confirm_new_code: str) -> dict:
    current_code = _normalize_access_code(current_code)
    new_code = _validate_access_code_format(new_code)
    confirm_new_code = _normalize_access_code(confirm_new_code)
    if new_code != confirm_new_code:
        raise ValueError("两次输入的新访问码不一致。")
    if current_code == new_code:
        raise ValueError("新访问码不能与当前访问码相同。")

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM access_identities WHERE id = ? LIMIT 1", (identity_id,)).fetchone()
        if not row or row["status"] != "active":
            raise ValueError("当前访问资格已失效，请重新登录后再试。")
        if not _identity_matches_secret(row, current_code):
            raise ValueError("当前访问码不正确。")

        new_fingerprint = _fingerprint_secret(new_code)
        if _access_code_secret_exists(connection, new_code, exclude_identity_id=identity_id):
            raise ValueError("这串新访问码已经被使用过了，请换一串新的 6 位数字。")

        updated_at = now_string()
        new_secret_hash = generate_password_hash(new_code)
        _retire_access_code_history(connection, identity_id, updated_at)
        connection.execute(
            """
            UPDATE access_identities
            SET code_hash = ?,
                secret_hash = ?,
                code_hint = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                new_fingerprint,
                new_secret_hash,
                _code_hint(new_code),
                updated_at,
                identity_id,
            ),
        )
        _record_access_code_history(
            connection,
            identity_id=identity_id,
            fingerprint=new_fingerprint,
            secret_hash=new_secret_hash,
            code_hint=_code_hint(new_code),
            created_at=updated_at,
            is_current=True,
        )
        connection.commit()

    mark_access_verified(identity_id=row["id"], label=row["label"], role=row["role"], method="access-code")
    return {"id": row["id"], "label": row["label"], "role": row["role"], "code_hint": _code_hint(new_code)}


def generate_access_code(_prefix: str | None = None) -> str:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        while True:
            candidate = f"{secrets.randbelow(1000000):06d}"
            if _access_code_secret_exists(connection, candidate):
                continue
            return candidate
