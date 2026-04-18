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


ADMIN_LABEL = "俊睿"
ADMIN_CODE = "256614"
VIEWER_LABELS = [
    "闫斌先生",
    "赵莹女士",
    "魏二强先生",
    "闫力阳先生",
    "宋庆华先生",
    "卢亚杰先生",
    "孟凡让先生",
]


def row_to_dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


def build_backup_dir(base_root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = base_root / "access_reset_backups" / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def generate_unique_codes(count: int) -> list[str]:
    codes: set[str] = {ADMIN_CODE}
    generated: list[str] = []
    while len(generated) < count:
        candidate = generate_access_code()
        if candidate in codes:
            continue
        codes.add(candidate)
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
        lines.extend(
            [
                f"用户名：{item['label']}",
                f"角色：{item['role']}",
                f"初始访问码：{item['code']}",
                "",
            ]
        )
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def main() -> None:
    app = create_app()
    with app.app_context():
        log_root = Path(app.config["LOG_ROOT"])
        backup_dir = build_backup_dir(log_root)
        credentials_file = backup_dir / f"CN_闻脉台_访问资格清单_{datetime.now().strftime('%Y%m%d')}.txt"

        with get_connection(app.config["DATABASE_PATH"]) as connection:
            identities_before = [
                row_to_dict(row)
                for row in connection.execute(
                    "SELECT * FROM access_identities ORDER BY id"
                ).fetchall()
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
                for row in connection.execute(
                    "SELECT * FROM auth_attempts ORDER BY id"
                ).fetchall()
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
        admin_identity = create_access_identity(
            label=ADMIN_LABEL,
            raw_code=ADMIN_CODE,
            role="admin",
            notes="阶段五-D 重置后的管理员资格",
        )
        created_rows.append({"label": admin_identity["label"], "role": "admin", "code": ADMIN_CODE})

        for label, code in zip(VIEWER_LABELS, generate_unique_codes(len(VIEWER_LABELS)), strict=True):
            identity = create_access_identity(
                label=label,
                raw_code=code,
                role="viewer",
                notes="阶段五-D 重置后的浏览资格",
            )
            created_rows.append({"label": identity["label"], "role": "viewer", "code": code})

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
                "admins": 1,
                "viewers": len(VIEWER_LABELS),
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
