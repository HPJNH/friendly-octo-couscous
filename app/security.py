from __future__ import annotations

import hmac
import json
import secrets
from datetime import datetime
from datetime import timedelta

from flask import current_app, request, session
from markupsafe import Markup, escape

from .db import get_connection
from .utils import now_local, now_string


CSRF_SESSION_KEY = "_csrf_token"
AUTH_WINDOW_MINUTES_DEFAULT = 30
AUTH_LOCK_MINUTES_DEFAULT = 15
AUTH_MAX_FAILURES_DEFAULT = 5
AUDIT_ACTION_LABELS = {
    "access.logout": "退出会话",
    "access_identity.create": "创建访问资格",
    "access_identity.disable": "停用访问资格",
    "access_identity.activate": "重新启用访问资格",
    "access_identity.delete": "删除访问资格",
    "access_identity.change_code": "修改访问码",
    "document.upload": "上传文件",
    "document.withdraw": "撤回文件",
    "document.activate": "设为当前版本",
    "document.delete": "删除文件",
    "export.delete": "删除导出文件",
}
AUDIT_TARGET_LABELS = {
    "document": "文件",
    "export": "导出成果",
    "access_identity": "访问资格",
    "session": "会话",
}


def get_csrf_token() -> str:
    token = session.get(CSRF_SESSION_KEY)
    if token:
        return token
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token() -> str:
    token = secrets.token_urlsafe(32)
    session[CSRF_SESSION_KEY] = token
    return token


def csrf_input() -> Markup:
    token = escape(get_csrf_token())
    return Markup(f'<input type="hidden" name="csrf_token" value="{token}">')


def get_request_csrf_token() -> str:
    return (
        request.form.get("csrf_token")
        or request.headers.get("X-CSRFToken")
        or request.headers.get("X-CSRF-Token")
        or ""
    )


def validate_csrf_token(candidate: str | None) -> bool:
    current_token = session.get(CSRF_SESSION_KEY) or ""
    if not current_token or not candidate:
        return False
    return hmac.compare_digest(str(candidate), str(current_token))


def get_remote_identity() -> str:
    forwarded = (request.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    remote_addr = forwarded or request.remote_addr or "unknown"
    return remote_addr[:120]


def get_user_agent_excerpt() -> str:
    return (request.headers.get("User-Agent") or "")[:240]


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def get_auth_policy(scope: str) -> dict:
    upper_scope = scope.upper()
    max_failures = int(
        current_app.config.get(f"{upper_scope}_MAX_FAILURES", current_app.config.get("AUTH_MAX_FAILURES", AUTH_MAX_FAILURES_DEFAULT))
    )
    window_minutes = int(
        current_app.config.get(f"{upper_scope}_WINDOW_MINUTES", current_app.config.get("AUTH_WINDOW_MINUTES", AUTH_WINDOW_MINUTES_DEFAULT))
    )
    lock_minutes = int(
        current_app.config.get(f"{upper_scope}_LOCK_MINUTES", current_app.config.get("AUTH_LOCK_MINUTES", AUTH_LOCK_MINUTES_DEFAULT))
    )
    return {
        "max_failures": max(1, max_failures),
        "window_minutes": max(1, window_minutes),
        "lock_minutes": max(1, lock_minutes),
    }


def get_auth_lock_state(scope: str, remote_identity: str | None = None) -> dict:
    remote_key = remote_identity or get_remote_identity()
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM auth_attempts
            WHERE scope = ? AND remote_key = ?
            LIMIT 1
            """,
            (scope, remote_key),
        ).fetchone()
    if not row:
        return {"locked": False, "remaining_seconds": 0, "failure_count": 0}

    locked_until = _parse_time(row["locked_until"])
    now = now_local()
    if locked_until and locked_until > now:
        return {
            "locked": True,
            "remaining_seconds": int((locked_until - now).total_seconds()),
            "failure_count": row["failure_count"],
        }
    return {"locked": False, "remaining_seconds": 0, "failure_count": row["failure_count"]}


def register_auth_failure(scope: str, remote_identity: str | None = None) -> dict:
    remote_key = remote_identity or get_remote_identity()
    policy = get_auth_policy(scope)
    now = now_local()
    now_text = now_string()
    window_start = now - timedelta(minutes=policy["window_minutes"])

    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        row = connection.execute(
            """
            SELECT *
            FROM auth_attempts
            WHERE scope = ? AND remote_key = ?
            LIMIT 1
            """,
            (scope, remote_key),
        ).fetchone()
        failure_count = 1
        first_failed_at = now_text
        if row:
            first_failed = _parse_time(row["first_failed_at"])
            if first_failed and first_failed >= window_start:
                failure_count = int(row["failure_count"] or 0) + 1
                first_failed_at = row["first_failed_at"] or now_text
            locked_until = None
            if failure_count >= policy["max_failures"]:
                locked_until = (now + timedelta(minutes=policy["lock_minutes"])).strftime("%Y-%m-%d %H:%M:%S")
            connection.execute(
                """
                UPDATE auth_attempts
                SET failure_count = ?, first_failed_at = ?, last_failed_at = ?, locked_until = ?, updated_at = ?
                WHERE id = ?
                """,
                (failure_count, first_failed_at, now_text, locked_until, now_text, row["id"]),
            )
        else:
            locked_until = None
            if failure_count >= policy["max_failures"]:
                locked_until = (now + timedelta(minutes=policy["lock_minutes"])).strftime("%Y-%m-%d %H:%M:%S")
            connection.execute(
                """
                INSERT INTO auth_attempts (
                    scope, remote_key, failure_count, first_failed_at, last_failed_at, locked_until, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (scope, remote_key, failure_count, now_text, now_text, locked_until, now_text),
            )
        connection.commit()

    state = get_auth_lock_state(scope, remote_key)
    state["failure_count"] = failure_count
    return state


def clear_auth_failures(scope: str, remote_identity: str | None = None) -> None:
    remote_key = remote_identity or get_remote_identity()
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        connection.execute("DELETE FROM auth_attempts WHERE scope = ? AND remote_key = ?", (scope, remote_key))
        connection.commit()


def _json_detail(detail: dict | None) -> str:
    return json.dumps(detail or {}, ensure_ascii=False)


def log_audit_event(
    *,
    action: str,
    target_type: str,
    target_id: int | None = None,
    target_label: str = "",
    detail: dict | None = None,
    actor: dict | None = None,
) -> None:
    actor_payload = actor or {}
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        connection.execute(
            """
            INSERT INTO audit_logs (
                actor_identity_id,
                actor_label,
                actor_role,
                remote_key,
                user_agent,
                action,
                target_type,
                target_id,
                target_label,
                detail_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                actor_payload.get("identity_id"),
                actor_payload.get("label", "unknown"),
                actor_payload.get("role", "guest"),
                get_remote_identity(),
                get_user_agent_excerpt(),
                action,
                target_type,
                target_id,
                target_label,
                _json_detail(detail),
                now_string(),
            ),
        )
        connection.commit()


def get_recent_audit_logs(limit: int = 16) -> list[dict]:
    with get_connection(current_app.config["DATABASE_PATH"]) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM audit_logs
            ORDER BY created_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    items = []
    for row in rows:
        detail = json.loads(row["detail_json"] or "{}")
        items.append(
            {
                "id": row["id"],
                "created_at": row["created_at"],
                "actor_label": row["actor_label"] or "unknown",
                "actor_role": row["actor_role"] or "guest",
                "action": row["action"],
                "action_label": AUDIT_ACTION_LABELS.get(row["action"], row["action"]),
                "target_type": row["target_type"],
                "target_type_label": AUDIT_TARGET_LABELS.get(row["target_type"], row["target_type"]),
                "target_label": row["target_label"] or "",
                "detail": detail,
                "remote_key": row["remote_key"] or "",
            }
        )
    return items
