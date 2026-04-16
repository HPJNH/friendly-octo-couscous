import sqlite3
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    doc_type TEXT NOT NULL,
    original_name TEXT NOT NULL,
    stored_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    parsed_path TEXT,
    file_ext TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    title TEXT,
    content TEXT NOT NULL,
    html_content TEXT NOT NULL,
    file_hash TEXT NOT NULL,
    metadata_json TEXT,
    lifecycle_status TEXT NOT NULL DEFAULT 'active',
    withdrawn_at TEXT,
    is_current INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_documents_report_date
    ON documents(report_date, doc_type, is_current);

CREATE INDEX IF NOT EXISTS idx_documents_library_lookup
    ON documents(doc_type, lifecycle_status, is_current, report_date, uploaded_at DESC);

CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    report_date TEXT NOT NULL,
    section_key TEXT NOT NULL,
    section_title TEXT NOT NULL,
    raw_content TEXT NOT NULL,
    raw_html TEXT NOT NULL,
    display_content TEXT NOT NULL,
    display_html TEXT NOT NULL,
    status TEXT NOT NULL,
    note TEXT,
    similarity REAL,
    previous_section_id INTEGER,
    source_document_id INTEGER,
    source_date TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id),
    FOREIGN KEY(previous_section_id) REFERENCES sections(id),
    FOREIGN KEY(source_document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_sections_lookup
    ON sections(report_date, section_key, document_id);

CREATE TABLE IF NOT EXISTS export_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    file_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    file_ext TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    metadata_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_export_files_report_date
    ON export_files(report_date, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_export_files_status_lookup
    ON export_files(status, report_date, created_at DESC);

CREATE TABLE IF NOT EXISTS rebuild_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_key TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    parser_version TEXT NOT NULL,
    status TEXT NOT NULL,
    source_index_path TEXT,
    evidence_map_path TEXT,
    decisions_path TEXT,
    migration_report_path TEXT,
    summary_json TEXT
);

CREATE INDEX IF NOT EXISTS idx_rebuild_runs_started_at
    ON rebuild_runs(started_at DESC);

CREATE TABLE IF NOT EXISTS entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER,
    origin_document_id INTEGER,
    report_date TEXT NOT NULL,
    module_id INTEGER NOT NULL,
    module_key TEXT NOT NULL,
    module_name TEXT NOT NULL,
    subsection_path TEXT NOT NULL,
    subsection_title TEXT NOT NULL,
    section_type TEXT NOT NULL,
    source_level TEXT NOT NULL,
    entry_type TEXT NOT NULL,
    event_key TEXT NOT NULL,
    title TEXT NOT NULL,
    time_text TEXT,
    event_date TEXT,
    source_name TEXT,
    source_title TEXT,
    source_url TEXT,
    supporting_sources_json TEXT,
    core_content TEXT NOT NULL,
    why_included TEXT,
    note_text TEXT,
    first_seen_date TEXT,
    last_seen_date TEXT,
    is_in_patch_window INTEGER NOT NULL DEFAULT 0,
    is_in_focus_window INTEGER NOT NULL DEFAULT 0,
    display_status TEXT NOT NULL,
    needs_review INTEGER NOT NULL DEFAULT 0,
    confidence_level TEXT NOT NULL DEFAULT '中',
    is_current_chain INTEGER NOT NULL DEFAULT 1,
    is_deleted INTEGER NOT NULL DEFAULT 0,
    dedupe_rank INTEGER NOT NULL DEFAULT 0,
    evidence_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(run_id) REFERENCES rebuild_runs(id),
    FOREIGN KEY(origin_document_id) REFERENCES documents(id)
);

CREATE INDEX IF NOT EXISTS idx_entries_report_module
    ON entries(report_date, module_key, section_type);

CREATE INDEX IF NOT EXISTS idx_entries_event_key
    ON entries(event_key, report_date DESC);

CREATE INDEX IF NOT EXISTS idx_entries_display_status
    ON entries(display_status, needs_review, is_deleted);

CREATE TABLE IF NOT EXISTS access_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    code_hash TEXT NOT NULL UNIQUE,
    code_hint TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    status TEXT NOT NULL DEFAULT 'active',
    notes TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_used_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_access_identities_status
    ON access_identities(status, role, updated_at DESC);

CREATE TABLE IF NOT EXISTS auth_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    remote_key TEXT NOT NULL,
    failure_count INTEGER NOT NULL DEFAULT 0,
    first_failed_at TEXT,
    last_failed_at TEXT,
    locked_until TEXT,
    updated_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_auth_attempts_scope_remote
    ON auth_attempts(scope, remote_key);

CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_identity_id INTEGER,
    actor_label TEXT,
    actor_role TEXT,
    remote_key TEXT,
    user_agent TEXT,
    action TEXT NOT NULL,
    target_type TEXT NOT NULL,
    target_id INTEGER,
    target_label TEXT,
    detail_json TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY(actor_identity_id) REFERENCES access_identities(id)
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at
    ON audit_logs(created_at DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_audit_logs_actor
    ON audit_logs(actor_identity_id, created_at DESC);
"""


def get_connection(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(database_path: Path) -> None:
    with get_connection(database_path) as connection:
        connection.executescript(SCHEMA)
        ensure_column(connection, "documents", "lifecycle_status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(connection, "documents", "withdrawn_at", "TEXT")
        ensure_column(connection, "sections", "metadata_json", "TEXT")
        ensure_column(connection, "entries", "run_id", "INTEGER")
        ensure_column(connection, "entries", "origin_document_id", "INTEGER")
        ensure_column(connection, "entries", "report_date", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "module_id", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "entries", "module_key", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "module_name", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "subsection_path", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "subsection_title", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "section_type", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "source_level", "TEXT NOT NULL DEFAULT 'C'")
        ensure_column(connection, "entries", "entry_type", "TEXT NOT NULL DEFAULT 'real'")
        ensure_column(connection, "entries", "event_key", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "title", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "time_text", "TEXT")
        ensure_column(connection, "entries", "event_date", "TEXT")
        ensure_column(connection, "entries", "source_name", "TEXT")
        ensure_column(connection, "entries", "source_title", "TEXT")
        ensure_column(connection, "entries", "source_url", "TEXT")
        ensure_column(connection, "entries", "supporting_sources_json", "TEXT")
        ensure_column(connection, "entries", "core_content", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "why_included", "TEXT")
        ensure_column(connection, "entries", "note_text", "TEXT")
        ensure_column(connection, "entries", "first_seen_date", "TEXT")
        ensure_column(connection, "entries", "last_seen_date", "TEXT")
        ensure_column(connection, "entries", "is_in_patch_window", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "entries", "is_in_focus_window", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "entries", "display_status", "TEXT NOT NULL DEFAULT '历史保留'")
        ensure_column(connection, "entries", "needs_review", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "entries", "confidence_level", "TEXT NOT NULL DEFAULT '中'")
        ensure_column(connection, "entries", "is_current_chain", "INTEGER NOT NULL DEFAULT 1")
        ensure_column(connection, "entries", "is_deleted", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "entries", "dedupe_rank", "INTEGER NOT NULL DEFAULT 0")
        ensure_column(connection, "entries", "evidence_json", "TEXT")
        ensure_column(connection, "entries", "created_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "entries", "updated_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "rebuild_runs", "source_index_path", "TEXT")
        ensure_column(connection, "rebuild_runs", "evidence_map_path", "TEXT")
        ensure_column(connection, "rebuild_runs", "decisions_path", "TEXT")
        ensure_column(connection, "rebuild_runs", "migration_report_path", "TEXT")
        ensure_column(connection, "rebuild_runs", "summary_json", "TEXT")
        ensure_column(connection, "access_identities", "label", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "access_identities", "code_hash", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "access_identities", "code_hint", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "access_identities", "role", "TEXT NOT NULL DEFAULT 'viewer'")
        ensure_column(connection, "access_identities", "status", "TEXT NOT NULL DEFAULT 'active'")
        ensure_column(connection, "access_identities", "notes", "TEXT")
        ensure_column(connection, "access_identities", "created_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "access_identities", "updated_at", "TEXT NOT NULL DEFAULT ''")
        ensure_column(connection, "access_identities", "last_used_at", "TEXT")
        ensure_column(connection, "access_identities", "secret_hash", "TEXT")


def ensure_column(connection: sqlite3.Connection, table_name: str, column_name: str, column_type: str) -> None:
    columns = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    if any((column["name"] if hasattr(column, "keys") else column[1]) == column_name for column in columns):
        return
    try:
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
    except sqlite3.OperationalError as error:
        if "duplicate column name" not in str(error).lower():
            raise
