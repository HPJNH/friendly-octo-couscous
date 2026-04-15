from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from functools import wraps

from flask import current_app, flash, redirect, request, session, url_for

from .db import get_connection
from .utils import now_string


ACCESS_SESSION_KEY = "access_session"
ROLE_RANK = {"viewer": 1, "admin": 2}


def _hash_secret(secret: str) -> str:
    payload = f"{current_app.config.get('SECRET_KEY', '')}:{secret or ''}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _code_hint(secret: str) -> str:
    value = (secret or "").strip()
    if len(value) <= 4:
        return value
    return f"{value[:2]}***{value[-2:]}"


def _required_rank(role: str) -> int:
    return ROLE_RANK.get(role, 1)


def access_control_enabled() -> bool:
    return bool(current_app.config.get("ACCESS_CONTROL_ENABLED", True))


def current_access_session() -> dict:
    payload = session.get(ACCESS_SESSION_KEY) or {}
    verified_at = int(payload.get("verified_at", 0) or 0)
    if not verified_at:
        return {}

    max_age = int(current_app.config.get("ACCESS_SESSION_SECONDS", 3600))
    now = int(time.time())
    if now - verified_at > max_age:
        clear_access_session()
        return {}
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
    return current_access_session().get("label", "未登录")


def mark_access_verified(identity_id: int | None, label: str, role: str, method: str) -> None:
    session.permanent = False
    session[ACCESS_SESSION_KEY] = {
        "identity_id": identity_id,
        "label": label,
        "role": role,
        "method": method,
        "verified_at": int(time.time()),
    }


def clear_access_session() -> None:
    session.pop(ACCESS_SESSION_KEY, None)


def ensure_bootstrap_access_codes() -> None:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        count = connection.execute("SELECT COUNT(1) AS count FROM access_identities").fetchone()["count"]
        if count:
            return
        now = now_string()
        seed_rows = [
            ("默认管理员码", current_app.config.get("INITIAL_ADMIN_ACCESS_CODE", "admin-123456"), "admin", "首次启动自动生成"),
            ("默认查看码", current_app.config.get("INITIAL_VIEWER_ACCESS_CODE", "viewer-123456"), "viewer", "首次启动自动生成"),
        ]
        for label, raw_code, role, notes in seed_rows:
            connection.execute(
                """
                INSERT INTO access_identities (
                    label, code_hash, code_hint, role, status, notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
                """,
                (label, _hash_secret(raw_code), _code_hint(raw_code), role, notes, now, now),
            )
        connection.commit()


def verify_admin_password(password: str) -> bool:
    configured = str(current_app.config.get("ADMIN_PASSWORD", "123456"))
    if hmac.compare_digest(password or "", configured):
        mark_access_verified(identity_id=None, label="Bootstrap 管理员", role="admin", method="password")
        return True
    return False


def verify_access_secret(secret: str, required_role: str = "viewer") -> tuple[bool, str]:
    if verify_admin_password(secret):
        return True, "bootstrap-admin"

    code_hash = _hash_secret(secret)
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM access_identities
            WHERE code_hash = ?
              AND status = 'active'
            LIMIT 1
            """,
            (code_hash,),
        ).fetchone()
        if not row:
            return False, "not-found"
        if _required_rank(row["role"]) < _required_rank(required_role):
            return False, "role-denied"
        mark_access_verified(identity_id=row["id"], label=row["label"], role=row["role"], method="access-code")
        connection.execute(
            "UPDATE access_identities SET last_used_at = ?, updated_at = ? WHERE id = ?",
            (now_string(), now_string(), row["id"]),
        )
        connection.commit()
    return True, "access-code"


def build_safe_next(candidate: str | None = None, fallback: str | None = None) -> str:
    value = candidate or (request.full_path.rstrip("?") if request.method == "GET" else request.referrer) or fallback or url_for("main.index")
    if not value:
        return url_for("main.index")
    if value.startswith("/"):
        return value
    for marker in ("http://127.0.0.1", "http://localhost", "http://192.168.", "http://10.", "http://172.16."):
        if value.startswith(marker):
            path = value.split("/", 3)
            if len(path) >= 4:
                return "/" + path[3]
            return url_for("main.index")
    return fallback or url_for("main.index")


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
                "body": "该操作会影响文件状态或系统数据，请先输入管理员访问码或 bootstrap 管理密码。",
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
    return {"items": items, "summary": summary}


def create_access_identity(label: str, raw_code: str, role: str, notes: str = "") -> dict:
    label = (label or "").strip()
    raw_code = (raw_code or "").strip()
    role = "admin" if role == "admin" else "viewer"
    notes = (notes or "").strip()
    if not label:
        raise ValueError("请填写访问资格名称。")
    if len(raw_code) < 6:
        raise ValueError("访问码至少需要 6 位，便于区分与管理。")

    code_hash = _hash_secret(raw_code)
    now = now_string()
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        exists = connection.execute(
            "SELECT id FROM access_identities WHERE code_hash = ? AND status != 'deleted'",
            (code_hash,),
        ).fetchone()
        if exists:
            raise ValueError("这串访问码已经存在，请换一串新的。")
        identity_id = connection.execute(
            """
            INSERT INTO access_identities (
                label, code_hash, code_hint, role, status, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)
            """,
            (label, code_hash, _code_hint(raw_code), role, notes, now, now),
        ).lastrowid
        connection.commit()
    return {"id": identity_id, "label": label, "role": role, "code_hint": _code_hint(raw_code)}


def update_access_identity_status(identity_id: int, status: str) -> dict:
    if status not in {"active", "disabled", "deleted"}:
        raise ValueError("不支持的访问资格状态。")
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute("SELECT * FROM access_identities WHERE id = ?", (identity_id,)).fetchone()
        if not row:
            raise ValueError("未找到对应的访问资格。")
        connection.execute(
            "UPDATE access_identities SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_string(), identity_id),
        )
        connection.commit()
    return {"id": identity_id, "label": row["label"], "status": status}


def generate_access_code(prefix: str = "viewer") -> str:
    token = secrets.token_hex(4)
    return f"{prefix}-{token}"
