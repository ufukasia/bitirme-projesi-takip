"""
db.py
SQLite connection management, schema initialisation, and low-level query helpers.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import date, datetime
from typing import Optional

import pandas as pd
import streamlit as st

from constants import DEFAULT_ADVISOR
from utils import now_ts

# ── Thread lock for write operations ──────────────────────────────────────────
_db_lock = threading.Lock()


# ── Connection factory ─────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _init_db(conn)
    return conn


# ── Parameter normalisation ────────────────────────────────────────────────────

def to_sql_param(value: object) -> object:
    """Convert any Python value to a type that sqlite3 can accept."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bytes)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    try:
        if pd.isna(value):  # type: ignore[arg-type]
            return None
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            item_value = value.item()
            if isinstance(item_value, (str, int, float, bytes)) or item_value is None:
                return item_value
            return str(item_value)
        except Exception:
            pass
    return str(value)


# ── Query helpers ──────────────────────────────────────────────────────────────

def fetch_df(conn: sqlite3.Connection, query: str, params: tuple = ()) -> pd.DataFrame:
    """Run a SELECT and return a DataFrame. Falls back to cursor if read_sql fails."""
    safe_params = tuple(to_sql_param(p) for p in (params or ()))
    try:
        return pd.read_sql_query(query, conn, params=safe_params)
    except Exception:
        cursor = conn.execute(query, safe_params)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description] if cursor.description else []
        return pd.DataFrame(rows, columns=columns)


def db_lock() -> threading.Lock:
    """Expose the module-level lock for use by writers in models.py."""
    return _db_lock


# ── Schema ────────────────────────────────────────────────────────────────────

def _ensure_students_schema(conn: sqlite3.Connection) -> None:
    info = conn.execute("PRAGMA table_info(students)").fetchall()
    if not info:
        return
    pk_cols = [row["name"] for row in info if int(row["pk"]) == 1]
    if pk_cols == ["row_no"]:
        return
    conn.executescript(
        """
        ALTER TABLE students RENAME TO students_old;
        CREATE TABLE students (
            row_no INTEGER PRIMARY KEY,
            student_no TEXT NOT NULL,
            student_name TEXT NOT NULL,
            project_name TEXT NOT NULL,
            advisor_name TEXT NOT NULL,
            program TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        """
        INSERT OR REPLACE INTO students (
            row_no, student_no, student_name, project_name, advisor_name, program, created_at, updated_at
        )
        SELECT
            CAST(COALESCE(row_no, rowid) AS INTEGER),
            COALESCE(student_no, ''),
            COALESCE(student_name, ''),
            COALESCE(project_name, ''),
            COALESCE(advisor_name, ?),
            COALESCE(program, ''),
            COALESCE(created_at, ?),
            COALESCE(updated_at, ?)
        FROM students_old
        """,
        (DEFAULT_ADVISOR, now_ts(), now_ts()),
    )
    conn.execute("DROP TABLE students_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_students_advisor ON students(advisor_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_students_project ON students(project_name)")
    conn.commit()


def _ensure_projects_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS projects (
            project_name TEXT PRIMARY KEY,
            advisor_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_projects_advisor ON projects(advisor_name);
        """
    )
    ts = now_ts()
    conn.execute(
        """
        INSERT INTO projects(project_name, advisor_name, created_at, updated_at)
        SELECT project_name, MIN(advisor_name), ?, ?
        FROM students
        WHERE project_name <> ''
        GROUP BY project_name
        ON CONFLICT(project_name) DO UPDATE SET
            advisor_name = excluded.advisor_name,
            updated_at = excluded.updated_at
        """,
        (ts, ts),
    )
    conn.execute("DELETE FROM projects WHERE project_name NOT IN (SELECT DISTINCT project_name FROM students WHERE project_name <> '')")
    conn.commit()


def _ensure_weekly_update_uniqueness(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        DELETE FROM weekly_updates
        WHERE id NOT IN (
            SELECT MAX(id)
            FROM weekly_updates
            GROUP BY project_name, student_no, IFNULL(task_id, -1), week_start
        )
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_weekly_updates_unique
        ON weekly_updates(project_name, student_no, IFNULL(task_id, -1), week_start)
        """
    )
    conn.commit()


def _ensure_integrity_triggers(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS trg_leaders_project_insert
        BEFORE INSERT ON leaders
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in leaders');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_leaders_project_update
        BEFORE UPDATE OF project_name ON leaders
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in leaders');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_member_roles_project_insert
        BEFORE INSERT ON member_roles
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in member_roles');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_member_roles_project_update
        BEFORE UPDATE OF project_name ON member_roles
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in member_roles');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_tasks_project_insert
        BEFORE INSERT ON tasks
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in tasks');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_tasks_project_update
        BEFORE UPDATE OF project_name ON tasks
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in tasks');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_weekly_updates_project_insert
        BEFORE INSERT ON weekly_updates
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in weekly_updates');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_weekly_updates_project_update
        BEFORE UPDATE OF project_name ON weekly_updates
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in weekly_updates');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_feedback_project_insert
        BEFORE INSERT ON advisor_feedback
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in advisor_feedback');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_feedback_project_update
        BEFORE UPDATE OF project_name ON advisor_feedback
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in advisor_feedback');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_comments_project_insert
        BEFORE INSERT ON task_comments
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in task_comments');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_comments_project_update
        BEFORE UPDATE OF project_name ON task_comments
        FOR EACH ROW
        WHEN NOT EXISTS (SELECT 1 FROM projects WHERE project_name = NEW.project_name)
        BEGIN
            SELECT RAISE(ABORT, 'Unknown project_name in task_comments');
        END;
        """
    )
    conn.commit()


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS students (
            row_no INTEGER PRIMARY KEY,
            student_no TEXT NOT NULL,
            student_name TEXT NOT NULL,
            project_name TEXT NOT NULL,
            advisor_name TEXT NOT NULL,
            program TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS auth_users (
            user_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'advisor')),
            display_name TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            force_password_change INTEGER NOT NULL DEFAULT 1,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (user_id, role)
        );
        CREATE TABLE IF NOT EXISTS leaders (
            project_name TEXT PRIMARY KEY,
            student_no TEXT NOT NULL,
            assigned_by TEXT NOT NULL,
            assigned_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS member_roles (
            project_name TEXT NOT NULL,
            student_no TEXT NOT NULL,
            role TEXT NOT NULL,
            responsibility TEXT,
            updated_at TEXT NOT NULL,
            PRIMARY KEY(project_name, student_no)
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            milestone_key TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            assignee_student_no TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'TODO',
            priority TEXT NOT NULL DEFAULT 'Orta',
            deadline TEXT,
            dependency_task_id INTEGER,
            evidence_required TEXT,
            evidence_link TEXT,
            evidence_file TEXT,
            created_by TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS weekly_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            student_no TEXT NOT NULL,
            task_id INTEGER,
            week_start TEXT NOT NULL,
            completed TEXT,
            blockers TEXT,
            next_step TEXT,
            evidence_link TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS advisor_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            advisor_name TEXT NOT NULL,
            feedback TEXT NOT NULL,
            action_item TEXT,
            revision_required INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            project_name TEXT NOT NULL,
            author_id TEXT NOT NULL,
            author_role TEXT NOT NULL CHECK(author_role IN ('student', 'advisor', 'leader')),
            comment TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_students_advisor ON students(advisor_name);
        CREATE INDEX IF NOT EXISTS idx_students_project ON students(project_name);
        CREATE INDEX IF NOT EXISTS idx_auth_user_role_active ON auth_users(role, is_active, user_id);
        CREATE INDEX IF NOT EXISTS idx_auth_role ON auth_users(role);
        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_name);
        CREATE INDEX IF NOT EXISTS idx_updates_project ON weekly_updates(project_name);
        CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id);
        """
    )
    conn.commit()
    _ensure_students_schema(conn)
    _ensure_projects_schema(conn)
    # Migrate: add evidence_file column if it doesn't exist yet
    try:
        conn.execute("ALTER TABLE tasks ADD COLUMN evidence_file TEXT DEFAULT ''")
        conn.commit()
    except Exception:
        pass
    _ensure_weekly_update_uniqueness(conn)
    _ensure_integrity_triggers(conn)
