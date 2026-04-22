from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.admin_auth import create_access_identity, generate_access_code
from app.db import get_connection
from app.utils import now_string


FORMAL_ACCESS_ROSTER = [
    {"label": "俊睿", "role": "admin"},
    {"label": "闫斌先生", "role": "admin"},
    {"label": "赵莹女士", "role": "viewer"},
    {"label": "魏二强先生", "role": "viewer"},
    {"label": "闫力阳先生", "role": "viewer"},
    {"label": "宋庆华先生", "role": "viewer"},
    {"label": "卢亚杰先生", "role": "viewer"},
    {"label": "孟凡让先生", "role": "viewer"},
]

QUESTION_MARK_TOKENS = {"?", "??", "???", "????", "?????"}


def row_to_dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


def build_backup_dir(base_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = base_root / "access_reset_backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def assert_formal_labels_clean() -> None:
    for item in FORMAL_ACCESS_ROSTER:
        label = (item["label"] or "").strip()
        if not label:
            raise ValueError("正式访问名单中存在空名称。")
        if "?" in label or label in QUESTION_MARK_TOKENS:
            raise ValueError(f"正式访问名单存在损坏标签：{label}")


def generate_unique_codes(count: int) -> list[str]:
    generated: list[str] = []
    seen: set[str] = set()
    while len(generated) < count:
        candidate = generate_access_code()
        if candidate in seen:
            continue
        seen.add(candidate)
        generated.append(candidate)
    return generated


def export_credentials(path: Path, rows: list[dict]) -> None:
    lines = [
        "闻脉台访问资格初始化凭证",
        "仅供本地管理员保存，不可提交到 GitHub。",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    for item in rows:
        lines.append(f"{item['label']} | {item['role']} | {item['code']}")
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    assert_formal_labels_clean()
    app = create_app()
    with app.app_context():
        log_root = Path(app.config["LOG_ROOT"])
        backup_dir = build_backup_dir(log_root)
        credentials_file = backup_dir / f"CN_闻脉台_访问资格清单_{datetime.now().strftime('%Y%m%d')}.txt"

        with get_connection(app.config["DATABASE_PATH"]) as connection:
            identities_before = [
                row_to_dict(row)
                for row in connection.execute("SELECT * FROM access_identities ORDER BY id").fetchall()
            ]
            identity_ids = [item["id"] for item in identities_before]
            access_audit_logs = [
                row_to_dict(row)
                for row in connection.execute(
                    """
                    SELECT *
                    FROM audit_logs
                    WHERE action LIKE 'access.%'
                       OR action LIKE 'access_identity.%'
                    ORDER BY id
                    """
                ).fetchall()
            ]
            auth_attempts = [
                row_to_dict(row)
                for row in connection.execute("SELECT * FROM auth_attempts ORDER BY id").fetchall()
            ]

            write_json(backup_dir / "access_identities_before_reset.json", identities_before)
            write_json(backup_dir / "audit_logs_access_before_reset.json", access_audit_logs)
            write_json(backup_dir / "auth_attempts_before_reset.json", auth_attempts)

            connection.execute(
                """
                DELETE FROM audit_logs
                WHERE action LIKE 'access.%'
                   OR action LIKE 'access_identity.%'
                """
            )

            if identity_ids:
                placeholders = ",".join("?" for _ in identity_ids)
                connection.execute(
                    f"""
                    UPDATE audit_logs
                    SET actor_identity_id = NULL
                    WHERE actor_identity_id IN ({placeholders})
                    """,
                    identity_ids,
                )

            connection.execute("DELETE FROM auth_attempts")
            connection.execute("DELETE FROM access_identities")
            connection.commit()

        created_rows: list[dict] = []
        for roster_item, code in zip(FORMAL_ACCESS_ROSTER, generate_unique_codes(len(FORMAL_ACCESS_ROSTER)), strict=True):
            identity = create_access_identity(
                label=roster_item["label"],
                raw_code=code,
                role=roster_item["role"],
                notes=f"2026-04-22 正式访问资格初始化（{roster_item['role']}）",
            )
            if "?" in identity["label"]:
                raise ValueError(f"访问资格初始化后发现损坏标签：{identity['label']}")
            created_rows.append(
                {
                    "label": identity["label"],
                    "role": identity["role"],
                    "code": code,
                }
            )

        role_counts: dict[str, int] = {}
        for item in created_rows:
            role_counts[item["role"]] = role_counts.get(item["role"], 0) + 1

        summary = {
            "executed_at": now_string(),
            "backup_dir": str(backup_dir),
            "credential_file": str(credentials_file),
            "backup_counts": {
                "access_identities": len(identities_before),
                "audit_logs_access": len(access_audit_logs),
                "auth_attempts": len(auth_attempts),
            },
            "created_counts": {
                "admins": role_counts.get("admin", 0),
                "viewers": role_counts.get("viewer", 0),
                "total": len(created_rows),
            },
            "bootstrap_admin_enabled": bool(app.config.get("BOOTSTRAP_ADMIN_ENABLED", False)),
        }
        write_json(backup_dir / "reset_summary.json", summary)
        export_credentials(credentials_file, created_rows)

        print("access_reset_ok")
        print(f"backup_dir={backup_dir}")
        print(f"credential_file={credentials_file}")


if __name__ == "__main__":
    main()
