from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.db import get_connection
from app.utils import now_string


FORMAL_ADMIN_LABELS = ["俊睿", "闫斌先生"]
FORMAL_VIEWER_LABELS = ["赵莹女士", "魏二强先生", "闫力阳先生", "宋庆华先生", "卢亚杰先生", "孟凡让先生"]
FORMAL_NOTES = {
    "admin": "2026-04-22 发布前净化后的正式管理员资格",
    "viewer": "2026-04-22 发布前净化后的正式浏览资格",
}
QUESTION_MARK_TOKENS = {"?", "??", "???", "????", "?????"}


def row_to_dict(row) -> dict:
    return {key: row[key] for key in row.keys()}


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def list_files(root: Path) -> list[dict]:
    if not root.exists():
        return []
    items = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root)).replace("\\", "/")
        items.append(
            {
                "relative_path": relative,
                "full_path": str(path),
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def run_git_command(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def build_backup_dir() -> Path:
    backup_root = PROJECT_ROOT.parent.parent / "情报浏览系统_forensic_backups"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / f"wenmai_release_purify_20260422-{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def parse_formal_credentials(credentials_path: Path) -> list[dict]:
    parsed: list[dict] = []
    for line in credentials_path.read_text(encoding="utf-8").splitlines():
        if "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 3:
            continue
        label, role, code = parts
        if not code.isdigit():
            continue
        parsed.append({"label": label, "role": role, "code": code})
    return parsed


def build_clean_credentials_text(parsed_credentials: list[dict]) -> str:
    admin_codes = [item["code"] for item in parsed_credentials if item["role"] == "admin"]
    viewer_codes = [item["code"] for item in parsed_credentials if item["role"] == "viewer"]
    if len(admin_codes) != len(FORMAL_ADMIN_LABELS):
        raise RuntimeError(f"正式 admin 访问码数量异常：{len(admin_codes)}")
    if len(viewer_codes) != len(FORMAL_VIEWER_LABELS):
        raise RuntimeError(f"正式 viewer 访问码数量异常：{len(viewer_codes)}")

    lines = [
        "闻脉台正式访问资格清单",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "仅供本地管理员保存，不可提交到 GitHub。",
        "",
    ]
    for label, code in zip(FORMAL_ADMIN_LABELS, admin_codes, strict=True):
        lines.append(f"{label} | admin | {code}")
    for label, code in zip(FORMAL_VIEWER_LABELS, viewer_codes, strict=True):
        lines.append(f"{label} | viewer | {code}")
    return "\n".join(lines).strip() + "\n"


def remove_file(path: Path | None) -> bool:
    if not path or not path.exists():
        return False
    path.unlink()
    return True


def prune_empty_directories(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted((item for item in root.rglob("*") if item.is_dir()), reverse=True):
        if any(path.iterdir()):
            continue
        path.rmdir()


def clear_directory_contents(root: Path, *, keep_names: set[str] | None = None) -> list[str]:
    keep_names = keep_names or set()
    removed: list[str] = []
    if not root.exists():
        return removed
    for path in sorted(root.rglob("*"), reverse=True):
        if path.name in keep_names:
            continue
        if path.is_file():
            removed.append(str(path))
            path.unlink()
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass
    return removed


def ensure_question_free(value: str, *, label: str) -> None:
    text = (value or "").strip()
    if not text:
        raise RuntimeError(f"{label} 为空。")
    if "?" in text or text in QUESTION_MARK_TOKENS:
        raise RuntimeError(f"{label} 仍然包含损坏字符：{text}")


def sync_access_identities(connection) -> dict:
    rows = connection.execute(
        """
        SELECT *
        FROM access_identities
        WHERE status = 'active'
        ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, id ASC
        """
    ).fetchall()
    if len(rows) != 8:
        raise RuntimeError(f"当前 active 访问资格数量异常：{len(rows)}")

    admin_rows = [row for row in rows if row["role"] == "admin"]
    viewer_rows = [row for row in rows if row["role"] == "viewer"]
    if len(admin_rows) != len(FORMAL_ADMIN_LABELS):
        raise RuntimeError(f"admin 数量异常：{len(admin_rows)}")
    if len(viewer_rows) != len(FORMAL_VIEWER_LABELS):
        raise RuntimeError(f"viewer 数量异常：{len(viewer_rows)}")

    updated: list[dict] = []
    now = now_string()
    for row, label in zip(admin_rows, FORMAL_ADMIN_LABELS, strict=True):
        ensure_question_free(label, label="正式 admin 标签")
        connection.execute(
            """
            UPDATE access_identities
            SET label = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (label, FORMAL_NOTES["admin"], now, row["id"]),
        )
        updated.append({"id": row["id"], "role": row["role"], "label": label, "code_hint": row["code_hint"]})

    for row, label in zip(viewer_rows, FORMAL_VIEWER_LABELS, strict=True):
        ensure_question_free(label, label="正式 viewer 标签")
        connection.execute(
            """
            UPDATE access_identities
            SET label = ?, notes = ?, updated_at = ?
            WHERE id = ?
            """,
            (label, FORMAL_NOTES["viewer"], now, row["id"]),
        )
        updated.append({"id": row["id"], "role": row["role"], "label": label, "code_hint": row["code_hint"]})

    verified_rows = connection.execute(
        """
        SELECT id, label, role, notes, code_hint
        FROM access_identities
        WHERE status = 'active'
        ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, id ASC
        """
    ).fetchall()
    for row in verified_rows:
        ensure_question_free(row["label"], label=f"访问资格 {row['id']} 标签")
        ensure_question_free(row["notes"], label=f"访问资格 {row['id']} 备注")
    return {"updated": updated}


def rewrite_credentials_file(log_root: Path, backup_dir: Path) -> dict:
    candidates = sorted(log_root.glob("access_identity_rotation/*/FORMAL_ACCESS_CODES.txt"))
    if not candidates:
        raise RuntimeError("未找到正式访问码文件 FORMAL_ACCESS_CODES.txt。")
    credentials_path = candidates[-1]
    original_text = credentials_path.read_text(encoding="utf-8")
    write_text(backup_dir / "credentials" / credentials_path.name, original_text)
    parsed = parse_formal_credentials(credentials_path)
    cleaned_text = build_clean_credentials_text(parsed)
    credentials_path.write_text(cleaned_text, encoding="utf-8")
    return {
        "path": str(credentials_path),
        "admin_count": sum(1 for item in parsed if item["role"] == "admin"),
        "viewer_count": sum(1 for item in parsed if item["role"] == "viewer"),
    }


def resolve_actual_parsed_path(archive_root: Path, stored_value: str | None) -> Path | None:
    if not stored_value:
        return None
    db_path = Path(stored_value)
    if db_path.exists():
        return db_path
    candidate = archive_root / db_path.parent.name / db_path.name
    if candidate.exists():
        return candidate
    matches = list(archive_root.rglob(db_path.name))
    if matches:
        return matches[0]
    return None


def backup_runtime_state(app, backup_dir: Path) -> dict:
    database_path = Path(app.config["DATABASE_PATH"])
    copy_file(database_path, backup_dir / "database" / database_path.name)
    local_backup_files = sorted(database_path.parent.glob("*before_*.db"))
    for path in local_backup_files:
        copy_file(path, backup_dir / "database" / "runtime_side_backups" / path.name)

    with get_connection(app.config["DATABASE_PATH"]) as connection:
        write_json(
            backup_dir / "database" / "documents_before.json",
            [row_to_dict(row) for row in connection.execute("SELECT * FROM documents ORDER BY report_date, id").fetchall()],
        )
        write_json(
            backup_dir / "database" / "export_files_before.json",
            [row_to_dict(row) for row in connection.execute("SELECT * FROM export_files ORDER BY id").fetchall()],
        )
        write_json(
            backup_dir / "database" / "access_identities_before.json",
            [row_to_dict(row) for row in connection.execute("SELECT * FROM access_identities ORDER BY id").fetchall()],
        )
        write_json(
            backup_dir / "database" / "access_code_history_before.json",
            [row_to_dict(row) for row in connection.execute("SELECT * FROM access_code_history ORDER BY id").fetchall()],
        )
        write_json(
            backup_dir / "database" / "audit_logs_before.json",
            [row_to_dict(row) for row in connection.execute("SELECT * FROM audit_logs ORDER BY id").fetchall()],
        )
        write_json(
            backup_dir / "database" / "auth_attempts_before.json",
            [row_to_dict(row) for row in connection.execute("SELECT * FROM auth_attempts ORDER BY id").fetchall()],
        )

    write_json(backup_dir / "manifests" / "file_library_before.json", list_files(Path(app.config["FILE_LIBRARY_ROOT"])))
    write_json(backup_dir / "manifests" / "archive_parsed_before.json", list_files(Path(app.config["ARCHIVE_ROOT"])))
    write_json(backup_dir / "manifests" / "raw_before.json", list_files(Path(app.config["RAW_DATA_ROOT"])))
    write_json(backup_dir / "manifests" / "exports_before.json", list_files(Path(app.config["EXPORTS_ROOT"])))
    write_text(backup_dir / "git" / "status_before.txt", run_git_command("status", "--short", "--branch") + "\n")
    write_text(backup_dir / "git" / "head_before.txt", run_git_command("rev-parse", "HEAD") + "\n")
    return {
        "database_backup": str(backup_dir / "database" / database_path.name),
        "runtime_side_backups": [str(path) for path in local_backup_files],
    }


def cleanup_documents_and_parsed(connection, app, backup_dir: Path) -> dict:
    archive_root = Path(app.config["ARCHIVE_ROOT"])
    deleted_rows = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE lifecycle_status = 'deleted'
        ORDER BY report_date, id
        """
    ).fetchall()
    kept_rows = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE lifecycle_status != 'deleted'
        ORDER BY report_date, id
        """
    ).fetchall()

    doc_20260422 = {
        row["original_name"]: row
        for row in connection.execute(
            "SELECT * FROM documents WHERE report_date = '2026-04-22' ORDER BY id"
        ).fetchall()
    }
    live_0422 = doc_20260422.get("沉香行业情报研究底稿 (11).docx")
    archived_0422 = doc_20260422.get("沉香行业情报研究底稿 (12).docx")
    if not live_0422 or live_0422["lifecycle_status"] != "active" or live_0422["is_current"] != 1:
        raise RuntimeError("2026-04-22 的 (11) 当前不处于 active/current。")
    if not archived_0422 or archived_0422["lifecycle_status"] != "archived" or archived_0422["is_current"] != 0:
        raise RuntimeError("2026-04-22 的 (12) 当前不处于 archived。")

    deleted_documents: list[dict] = []
    deleted_parsed_files: list[str] = []
    for row in deleted_rows:
        stored_path = Path(row["stored_path"]) if row["stored_path"] else None
        if stored_path and stored_path.exists():
            relative = stored_path.relative_to(Path(app.config["FILE_LIBRARY_ROOT"]))
            copy_file(stored_path, backup_dir / "deleted_assets" / "file_library" / relative)
            if remove_file(stored_path):
                deleted_documents.append({"id": row["id"], "name": row["original_name"], "stored_path": str(stored_path)})

        parsed_path = resolve_actual_parsed_path(archive_root, row["parsed_path"])
        if parsed_path and parsed_path.exists():
            relative = parsed_path.relative_to(archive_root)
            copy_file(parsed_path, backup_dir / "deleted_assets" / "archive_parsed" / relative)
            if remove_file(parsed_path):
                deleted_parsed_files.append(str(parsed_path))

        connection.execute("DELETE FROM sections WHERE document_id = ?", (row["id"],))
        connection.execute("DELETE FROM documents WHERE id = ?", (row["id"],))

    fixed_parsed_paths: list[dict] = []
    kept_rows = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE lifecycle_status != 'deleted'
        ORDER BY report_date, id
        """
    ).fetchall()
    referenced_parsed_names: set[str] = set()
    for row in kept_rows:
        actual_path = resolve_actual_parsed_path(archive_root, row["parsed_path"])
        if not actual_path:
            raise RuntimeError(f"保留文档缺少解析归档：{row['original_name']}")
        referenced_parsed_names.add(actual_path.name)
        if str(actual_path) == str(row["parsed_path"]):
            continue
        metadata = json.loads(row["metadata_json"] or "{}")
        metadata["parsed_path"] = str(actual_path)
        connection.execute(
            """
            UPDATE documents
            SET parsed_path = ?, metadata_json = ?
            WHERE id = ?
            """,
            (str(actual_path), json.dumps(metadata, ensure_ascii=False), row["id"]),
        )
        fixed_parsed_paths.append(
            {
                "id": row["id"],
                "name": row["original_name"],
                "from": row["parsed_path"],
                "to": str(actual_path),
            }
        )

    orphan_parsed_files: list[str] = []
    for path in sorted(item for item in archive_root.rglob("*.json") if item.is_file()):
        if path.name in referenced_parsed_names:
            continue
        copy_file(path, backup_dir / "deleted_assets" / "archive_parsed_orphans" / path.relative_to(archive_root))
        if remove_file(path):
            orphan_parsed_files.append(str(path))

    for backup_path in Path(app.config["DATABASE_PATH"]).parent.glob("*before_*.db"):
        copy_file(backup_path, backup_dir / "deleted_assets" / "database_side_backups" / backup_path.name)
        backup_path.unlink()

    prune_empty_directories(Path(app.config["FILE_LIBRARY_ROOT"]))
    prune_empty_directories(archive_root)

    remaining_documents = connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]
    if remaining_documents != 21:
        raise RuntimeError(f"清理后 documents 数量异常：{remaining_documents}")

    return {
        "deleted_document_rows": [row_to_dict(row) for row in deleted_rows],
        "deleted_document_files": deleted_documents,
        "deleted_parsed_files": deleted_parsed_files,
        "fixed_parsed_paths": fixed_parsed_paths,
        "deleted_parsed_orphans": orphan_parsed_files,
        "removed_local_database_backups": [
            str(path) for path in (backup_dir / "deleted_assets" / "database_side_backups").glob("*")
        ],
    }


def cleanup_exports(connection, app, backup_dir: Path) -> dict:
    export_rows = [row_to_dict(row) for row in connection.execute("SELECT * FROM export_files ORDER BY id").fetchall()]
    write_json(backup_dir / "database" / "export_files_stale_before_delete.json", export_rows)

    removed_files: list[str] = []
    for root, keep in [
        (Path(app.config["EXPORT_ROOT"]), {".gitkeep"}),
        (Path(app.config["REPORT_EXPORT_ROOT"]), {".gitkeep"}),
        (Path(app.config["EXPORTS_ROOT"]) / "review_packages", set()),
    ]:
        if root.exists():
            for path in sorted((item for item in root.rglob("*") if item.is_file()), reverse=True):
                if path.name in keep:
                    continue
                copy_file(path, backup_dir / "deleted_assets" / "exports" / path.relative_to(Path(app.config["EXPORTS_ROOT"])))
                path.unlink()
                removed_files.append(str(path))
        prune_empty_directories(root)

    connection.execute("DELETE FROM export_files")
    remaining = connection.execute("SELECT COUNT(*) AS count FROM export_files").fetchone()["count"]
    if remaining != 0:
        raise RuntimeError(f"导出记录清理失败，剩余 {remaining} 条。")
    return {"deleted_rows": export_rows, "removed_files": removed_files}


def cleanup_runtime_residue(connection, app) -> dict:
    removed_files: Counter[str] = Counter()
    for root, keep in [
        (Path(app.config["TEMP_UPLOAD_ROOT"]), set()),
        (Path(app.config["STORAGE_ROOT"]) / "uploads", set()),
        (Path(app.config["VERIFICATION_DATA_ROOT"]), set()),
        (Path(app.config["REVIEW_DATA_ROOT"]), {".gitkeep"}),
    ]:
        for removed in clear_directory_contents(root, keep_names=keep):
            removed_files[str(root)] += 1
        prune_empty_directories(root)

    audit_logs_deleted = connection.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"]
    connection.execute("DELETE FROM audit_logs")
    connection.execute("DELETE FROM auth_attempts")
    return {
        "audit_logs_deleted": audit_logs_deleted,
        "auth_attempts_after": connection.execute("SELECT COUNT(*) AS count FROM auth_attempts").fetchone()["count"],
        "cleared_directories": dict(removed_files),
    }


def collect_runtime_summary(connection, app) -> dict:
    counts = {
        "documents": connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"],
        "documents_active": connection.execute(
            "SELECT COUNT(*) AS count FROM documents WHERE lifecycle_status = 'active' AND is_current = 1"
        ).fetchone()["count"],
        "documents_archived": connection.execute(
            "SELECT COUNT(*) AS count FROM documents WHERE lifecycle_status = 'archived'"
        ).fetchone()["count"],
        "export_files": connection.execute("SELECT COUNT(*) AS count FROM export_files").fetchone()["count"],
        "access_identities": connection.execute(
            "SELECT COUNT(*) AS count FROM access_identities WHERE status = 'active'"
        ).fetchone()["count"],
        "audit_logs": connection.execute("SELECT COUNT(*) AS count FROM audit_logs").fetchone()["count"],
        "auth_attempts": connection.execute("SELECT COUNT(*) AS count FROM auth_attempts").fetchone()["count"],
        "entry_marks": connection.execute("SELECT COUNT(*) AS count FROM entry_marks").fetchone()["count"],
    }
    return {
        "counts": counts,
        "documents": [row_to_dict(row) for row in connection.execute("SELECT * FROM documents ORDER BY report_date, id").fetchall()],
        "access_identities": [
            row_to_dict(row)
            for row in connection.execute(
                """
                SELECT id, label, role, status, notes, code_hint, last_used_at
                FROM access_identities
                ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, id ASC
                """
            ).fetchall()
        ],
        "file_library_manifest": list_files(Path(app.config["FILE_LIBRARY_ROOT"])),
        "archive_parsed_manifest": list_files(Path(app.config["ARCHIVE_ROOT"])),
        "exports_manifest": list_files(Path(app.config["EXPORTS_ROOT"])),
    }


def main() -> None:
    app = create_app()
    backup_dir = build_backup_dir()
    with app.app_context():
        backup_meta = backup_runtime_state(app, backup_dir)
        credentials_meta = rewrite_credentials_file(Path(app.config["LOG_ROOT"]), backup_dir)
        with get_connection(app.config["DATABASE_PATH"]) as connection:
            access_meta = sync_access_identities(connection)
            residue_meta = cleanup_runtime_residue(connection, app)
            document_meta = cleanup_documents_and_parsed(connection, app, backup_dir)
            export_meta = cleanup_exports(connection, app, backup_dir)
            connection.commit()
            after_summary = collect_runtime_summary(connection, app)

        write_json(backup_dir / "manifests" / "file_library_after.json", after_summary["file_library_manifest"])
        write_json(backup_dir / "manifests" / "archive_parsed_after.json", after_summary["archive_parsed_manifest"])
        write_json(backup_dir / "manifests" / "exports_after.json", after_summary["exports_manifest"])
        write_json(backup_dir / "database" / "documents_after.json", after_summary["documents"])
        write_json(backup_dir / "database" / "access_identities_after.json", after_summary["access_identities"])
        write_text(backup_dir / "git" / "status_after_cleanup.txt", run_git_command("status", "--short", "--branch") + "\n")
        write_text(backup_dir / "git" / "head_after_cleanup.txt", run_git_command("rev-parse", "HEAD") + "\n")

        summary = {
            "executed_at": now_string(),
            "backup_dir": str(backup_dir),
            "backup_meta": backup_meta,
            "credentials_meta": credentials_meta,
            "access_meta": access_meta,
            "runtime_residue_meta": residue_meta,
            "document_meta": document_meta,
            "export_meta": export_meta,
            "after_summary": after_summary["counts"],
        }
        write_json(backup_dir / "release_cleanup_summary.json", summary)
        print(json.dumps(summary, ensure_ascii=True, indent=2))
        print(f"backup_dir={backup_dir}")


if __name__ == "__main__":
    main()
