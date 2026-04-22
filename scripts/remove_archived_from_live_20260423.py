from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.db import get_connection


EXPECTED_ACTIVE_COUNT = 6
EXPECTED_ARCHIVED_COUNT = 15


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def list_files(root: Path) -> list[dict[str, object]]:
    if not root.exists():
        return []
    items: list[dict[str, object]] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = str(path.relative_to(root)).replace("\\", "/")
        stat = path.stat()
        items.append(
            {
                "relative_path": relative,
                "full_path": str(path),
                "size_bytes": stat.st_size,
                "modified_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return items


def row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def prune_empty_directories(root: Path) -> None:
    if not root.exists():
        return
    for path in sorted((item for item in root.rglob("*") if item.is_dir()), reverse=True):
        if any(path.iterdir()):
            continue
        path.rmdir()


def git_output(*args: str) -> str:
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
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = backup_root / f"wenmai_archived_removed_from_live_{timestamp}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir


def fetch_archived_targets(connection: sqlite3.Connection) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    connection.row_factory = sqlite3.Row
    active_rows = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE lifecycle_status = 'active'
          AND is_current = 1
        ORDER BY report_date, doc_type, id
        """
    ).fetchall()
    archived_rows = connection.execute(
        """
        SELECT *
        FROM documents
        WHERE lifecycle_status = 'archived'
          AND is_current = 0
        ORDER BY report_date, doc_type, id
        """
    ).fetchall()
    if len(active_rows) != EXPECTED_ACTIVE_COUNT:
        raise RuntimeError(f"unexpected active document count: {len(active_rows)}")
    if len(archived_rows) != EXPECTED_ARCHIVED_COUNT:
        raise RuntimeError(f"unexpected archived document count: {len(archived_rows)}")
    return active_rows, archived_rows


def collect_related_rows(connection: sqlite3.Connection, archived_ids: list[int]) -> dict[str, list[sqlite3.Row]]:
    placeholders = ",".join("?" for _ in archived_ids)
    sections = connection.execute(
        f"""
        SELECT *
        FROM sections
        WHERE document_id IN ({placeholders})
           OR source_document_id IN ({placeholders})
        ORDER BY id
        """,
        [*archived_ids, *archived_ids],
    ).fetchall()
    entries = connection.execute(
        f"""
        SELECT *
        FROM entries
        WHERE origin_document_id IN ({placeholders})
        ORDER BY id
        """,
        archived_ids,
    ).fetchall()
    return {"sections": sections, "entries": entries}


def ensure_targets_exist(paths: list[Path], *, label: str) -> None:
    missing = [str(path) for path in paths if not path.exists()]
    if missing:
        raise RuntimeError(f"missing {label}: {missing}")


def backup_targets(
    *,
    backup_dir: Path,
    database_path: Path,
    file_library_root: Path,
    archive_root: Path,
    active_rows: list[sqlite3.Row],
    archived_rows: list[sqlite3.Row],
    related_rows: dict[str, list[sqlite3.Row]],
) -> dict[str, object]:
    copy_file(database_path, backup_dir / "database" / database_path.name)
    write_json(backup_dir / "database" / "active_documents_before.json", [row_to_dict(row) for row in active_rows])
    write_json(backup_dir / "database" / "archived_documents_before.json", [row_to_dict(row) for row in archived_rows])
    write_json(backup_dir / "database" / "archived_sections_before.json", [row_to_dict(row) for row in related_rows["sections"]])
    write_json(backup_dir / "database" / "archived_entries_before.json", [row_to_dict(row) for row in related_rows["entries"]])
    write_json(backup_dir / "manifests" / "file_library_before.json", list_files(file_library_root))
    write_json(backup_dir / "manifests" / "archive_parsed_before.json", list_files(archive_root))
    write_text(backup_dir / "git" / "status_before.txt", git_output("status", "--short", "--branch") + "\n")
    write_text(backup_dir / "git" / "head_before.txt", git_output("rev-parse", "HEAD") + "\n")

    copied_docs: list[str] = []
    copied_parsed: list[str] = []
    for row in archived_rows:
        stored_path = Path(row["stored_path"])
        parsed_path = Path(row["parsed_path"])
        copy_file(stored_path, backup_dir / "archived_documents" / stored_path.relative_to(file_library_root))
        copy_file(parsed_path, backup_dir / "archived_parsed" / parsed_path.relative_to(archive_root))
        copied_docs.append(str(stored_path))
        copied_parsed.append(str(parsed_path))

    return {"copied_documents": copied_docs, "copied_parsed": copied_parsed}


def delete_archived_targets(
    *,
    database_path: Path,
    archived_rows: list[sqlite3.Row],
    related_rows: dict[str, list[sqlite3.Row]],
    active_rows: list[sqlite3.Row],
    file_library_root: Path,
    archive_root: Path,
) -> dict[str, object]:
    archived_ids = [int(row["id"]) for row in archived_rows]
    placeholders = ",".join("?" for _ in archived_ids)
    protected_stored = {str(Path(row["stored_path"]).resolve()) for row in active_rows}
    protected_parsed = {str(Path(row["parsed_path"]).resolve()) for row in active_rows}

    stored_paths = [Path(row["stored_path"]) for row in archived_rows]
    parsed_paths = [Path(row["parsed_path"]) for row in archived_rows]

    for path in stored_paths:
        if str(path.resolve()) in protected_stored:
            raise RuntimeError(f"refusing to delete protected active file: {path}")
    for path in parsed_paths:
        if str(path.resolve()) in protected_parsed:
            raise RuntimeError(f"refusing to delete protected active parsed file: {path}")

    with get_connection(database_path) as connection:
        connection.execute(
            f"DELETE FROM sections WHERE document_id IN ({placeholders}) OR source_document_id IN ({placeholders})",
            [*archived_ids, *archived_ids],
        )
        connection.execute(
            f"DELETE FROM entries WHERE origin_document_id IN ({placeholders})",
            archived_ids,
        )
        connection.execute(
            f"DELETE FROM documents WHERE id IN ({placeholders})",
            archived_ids,
        )
        connection.commit()

    removed_files: list[str] = []
    removed_parsed: list[str] = []
    for path in stored_paths:
        path.unlink()
        removed_files.append(str(path))
    for path in parsed_paths:
        path.unlink()
        removed_parsed.append(str(path))

    prune_empty_directories(file_library_root / "archived")
    prune_empty_directories(archive_root)

    with get_connection(database_path) as connection:
        documents_total = connection.execute("SELECT COUNT(*) AS count FROM documents").fetchone()["count"]
        documents_active = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM documents
            WHERE lifecycle_status = 'active'
              AND is_current = 1
            """
        ).fetchone()["count"]
        documents_archived = connection.execute(
            """
            SELECT COUNT(*) AS count
            FROM documents
            WHERE lifecycle_status = 'archived'
              AND is_current = 0
            """
        ).fetchone()["count"]
        remaining_entries = connection.execute(
            f"SELECT COUNT(*) AS count FROM entries WHERE origin_document_id IN ({placeholders})",
            archived_ids,
        ).fetchone()["count"]
        remaining_sections = connection.execute(
            f"""
            SELECT COUNT(*) AS count
            FROM sections
            WHERE document_id IN ({placeholders})
               OR source_document_id IN ({placeholders})
            """,
            [*archived_ids, *archived_ids],
        ).fetchone()["count"]

    file_library_files = len(list_files(file_library_root))
    archive_parsed_files = len(list_files(archive_root))

    if documents_total != EXPECTED_ACTIVE_COUNT:
        raise RuntimeError(f"unexpected remaining documents count: {documents_total}")
    if documents_active != EXPECTED_ACTIVE_COUNT:
        raise RuntimeError(f"unexpected remaining active count: {documents_active}")
    if documents_archived != 0:
        raise RuntimeError(f"archived documents remain in live db: {documents_archived}")
    if remaining_entries != 0:
        raise RuntimeError(f"archived entry refs remain: {remaining_entries}")
    if remaining_sections != 0:
        raise RuntimeError(f"archived section refs remain: {remaining_sections}")
    if file_library_files != EXPECTED_ACTIVE_COUNT:
        raise RuntimeError(f"unexpected file_library file count: {file_library_files}")
    if archive_parsed_files != EXPECTED_ACTIVE_COUNT:
        raise RuntimeError(f"unexpected archive parsed file count: {archive_parsed_files}")

    return {
        "removed_documents": [row_to_dict(row) for row in archived_rows],
        "removed_sections_count": len(related_rows["sections"]),
        "removed_entries_count": len(related_rows["entries"]),
        "removed_file_paths": removed_files,
        "removed_parsed_paths": removed_parsed,
        "after_counts": {
            "documents": documents_total,
            "documents_active": documents_active,
            "documents_archived": documents_archived,
            "file_library_files": file_library_files,
            "archive_parsed_files": archive_parsed_files,
        },
    }


def main() -> None:
    app = create_app()
    database_path = Path(app.config["DATABASE_PATH"])
    file_library_root = Path(app.config["FILE_LIBRARY_ROOT"])
    archive_root = Path(app.config["ARCHIVE_ROOT"])
    backup_dir = build_backup_dir()

    with get_connection(database_path) as connection:
        active_rows, archived_rows = fetch_archived_targets(connection)
        related_rows = collect_related_rows(connection, [int(row["id"]) for row in archived_rows])

    stored_paths = [Path(row["stored_path"]) for row in archived_rows]
    parsed_paths = [Path(row["parsed_path"]) for row in archived_rows]
    ensure_targets_exist(stored_paths, label="archived document files")
    ensure_targets_exist(parsed_paths, label="archived parsed files")

    backup_meta = backup_targets(
        backup_dir=backup_dir,
        database_path=database_path,
        file_library_root=file_library_root,
        archive_root=archive_root,
        active_rows=active_rows,
        archived_rows=archived_rows,
        related_rows=related_rows,
    )

    delete_meta = delete_archived_targets(
        database_path=database_path,
        archived_rows=archived_rows,
        related_rows=related_rows,
        active_rows=active_rows,
        file_library_root=file_library_root,
        archive_root=archive_root,
    )

    with get_connection(database_path) as connection:
        connection.row_factory = sqlite3.Row
        write_json(
            backup_dir / "database" / "documents_after.json",
            [row_to_dict(row) for row in connection.execute("SELECT * FROM documents ORDER BY report_date, id").fetchall()],
        )

    write_json(backup_dir / "manifests" / "file_library_after.json", list_files(file_library_root))
    write_json(backup_dir / "manifests" / "archive_parsed_after.json", list_files(archive_root))
    write_text(backup_dir / "git" / "status_after.txt", git_output("status", "--short", "--branch") + "\n")
    write_text(backup_dir / "git" / "head_after.txt", git_output("rev-parse", "HEAD") + "\n")

    summary = {
        "executed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "backup_dir": str(backup_dir),
        "archived_document_ids": [int(row["id"]) for row in archived_rows],
        "archived_document_names": [row["original_name"] for row in archived_rows],
        "backup_meta": backup_meta,
        "delete_meta": delete_meta,
    }
    write_json(backup_dir / "archived_removed_summary.json", summary)
    print(json.dumps(summary["delete_meta"]["after_counts"], ensure_ascii=True, indent=2))
    print(f"backup_dir={backup_dir}")
    print("remove_archived_from_live_20260423_ok")


if __name__ == "__main__":
    main()
