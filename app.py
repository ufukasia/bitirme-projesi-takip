from __future__ import annotations

import hashlib
import hmac
import os
import shutil
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd
import streamlit as st

UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

DEFAULT_ADVISOR = "Dr. UFUK ASIL"
DEFAULT_PASSWORD = "12345"
MIN_PASSWORD_LEN = 6
STATUS_OPTIONS = ["TODO", "DOING", "DONE"]
STATUS_LABELS = {
    "TODO": "YAPILACAK",
    "DOING": "DEVAM EDIYOR",
    "DONE": "TAMAMLANDI",
}
STATUS_TRANSITIONS = {
    "TODO": {"TODO", "DOING"},
    "DOING": {"TODO", "DOING", "DONE"},
    "DONE": {"DOING", "DONE"},
}
ADMIN_ADVISOR_KEYS = {"drufukasil", "drufukasl"}
ROLE_OPTIONS = ["Lider", "Uye", "Arastirma", "Yazilim", "DevOps", "Test", "Veri", "Sunum", "Diger"]
PRIORITY_OPTIONS = ["Dusuk", "Orta", "Yuksek"]

MILESTONES = [
    ("M1", "Literatur taramasi"),
    ("M2", "Algoritma ve uygulama plani"),
    ("M3", "Uygulamayi boot etme"),
    ("M4", "Uygulamayi deneme ve sonuclari degerlendirme"),
    ("M5", "Hatalari duzeltme ve tekrar deneme"),
    ("M6", "Proje yazimi ve final rapor"),
]
MILESTONE_LABELS = {key: label for key, label in MILESTONES}
MILESTONE_ORDER = {key: idx for idx, (key, _) in enumerate(MILESTONES)}


def status_tr(status_value: str) -> str:
    return STATUS_LABELS.get(str(status_value), str(status_value))


def normalize_identity(value: str) -> str:
    text = normalize_header(str(value))
    return "".join(ch for ch in text if ch.isalnum())


def is_admin_advisor(user_id: str) -> bool:
    return normalize_identity(user_id) in ADMIN_ADVISOR_KEYS


def allowed_status_options(current_status: str) -> list[str]:
    allowed = STATUS_TRANSITIONS.get(str(current_status), {str(current_status)})
    return [s for s in STATUS_OPTIONS if s in allowed]


def normalize_header(value: str) -> str:
    text = str(value).strip().lower()
    repl = {
        "ç": "c",
        "ğ": "g",
        "ı": "i",
        "ö": "o",
        "ş": "s",
        "ü": "u",
        "Ç": "c",
        "Ğ": "g",
        "İ": "i",
        "Ö": "o",
        "Ş": "s",
        "Ü": "u",
        "Ã§": "c",
        "ÄŸ": "g",
        "Ä±": "i",
        "Ã¶": "o",
        "ÅŸ": "s",
        "Ã¼": "u",
        "Ã‡": "c",
        "Ä": "g",
        "Ä°": "i",
        "Ã–": "o",
        "Å": "s",
        "Ãœ": "u",
        "ÃƒÂ§": "c",
        "Ã„Å¸": "g",
        "Ã„Â±": "i",
        "ÃƒÂ¶": "o",
        "Ã…Å¸": "s",
        "ÃƒÂ¼": "u",
        "Ãƒâ€¡": "c",
        "Ã„Â": "g",
        "Ã„Â°": "i",
        "Ãƒâ€“": "o",
        "Ã…Â": "s",
        "ÃƒÅ“": "u",
    }
    for src, dst in repl.items():
        text = text.replace(src, dst)
    return "".join(ch for ch in text if ch.isalnum() or ch in {" ", "_"}).replace(" ", "")


@st.cache_data(show_spinner=False)
def load_roster(csv_path: str) -> pd.DataFrame:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV bulunamadi: {path}")

    encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]
    df = None
    used_encoding = None
    for enc in encodings:
        try:
            df = pd.read_csv(path, sep=";", encoding=enc, dtype=str).fillna("")
            used_encoding = enc
            break
        except Exception:
            continue
    if df is None:
        raise ValueError("CSV okunamadi.")

    col_map: Dict[str, str] = {}
    for col in df.columns:
        raw = str(col).strip()
        norm = normalize_header(raw)
        if raw == "#" or norm in {"sira", "index"}:
            col_map[col] = "row_no"
        elif "ogrencino" in norm or "studentno" in norm:
            col_map[col] = "student_no"
        elif "ogrenciadi" in norm or "studentname" in norm:
            col_map[col] = "student_name"
        elif "projeadi" in norm or "projectname" in norm:
            col_map[col] = "project_name"
        elif "danismanadi" in norm or "advisorname" in norm:
            col_map[col] = "advisor_name"
        elif "program" in norm:
            col_map[col] = "program"

    df = df.rename(columns=col_map)
    expected = ["row_no", "student_no", "student_name", "project_name", "advisor_name", "program"]
    if not all(col in df.columns for col in expected):
        if len(df.columns) < 6:
            raise ValueError("CSV kolonlari yetersiz.")
        fallback = dict(zip(list(df.columns)[:6], expected))
        df = df.rename(columns=fallback)

    df = df[expected].copy()
    for col in ["student_no", "student_name", "project_name", "advisor_name", "program"]:
        df[col] = df[col].astype(str).str.strip()

    df["student_no"] = df["student_no"].str.replace(r"^\?+", "", regex=True)
    fallback_row = pd.Series(range(1, len(df) + 1), index=df.index)
    df["row_no"] = pd.to_numeric(df["row_no"], errors="coerce").fillna(fallback_row).astype(int)
    df = df[(df["student_no"] != "") & (df["project_name"] != "")].copy()
    df = df.sort_values(["project_name", "row_no", "student_name"]).reset_index(drop=True)
    df.attrs["source_encoding"] = used_encoding
    return df


def now_ts() -> str:
    return datetime.now().isoformat(timespec="seconds")


def hash_password(password: str, iterations: int = 120000) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algo, iteration_text, salt_hex, digest_hex = encoded_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except Exception:
        return False

    current = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(current, expected)


def ensure_students_schema(conn: sqlite3.Connection) -> None:
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


def init_db(conn: sqlite3.Connection) -> None:
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
        CREATE INDEX IF NOT EXISTS idx_auth_role ON auth_users(role);
        CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_name);
        CREATE INDEX IF NOT EXISTS idx_updates_project ON weekly_updates(project_name);
        CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id);
        """
    )
    conn.commit()
    ensure_students_schema(conn)
    try:
        conn.execute("""ALTER TABLE tasks ADD COLUMN evidence_file TEXT DEFAULT ''""")
        conn.commit()
    except Exception:
        pass


_db_lock = threading.Lock()


@st.cache_resource(show_spinner=False)
def get_conn(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    init_db(conn)
    return conn


def to_sql_param(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bytes)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    try:
        if pd.isna(value):
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


def fetch_df(conn: sqlite3.Connection, query: str, params: tuple = ()) -> pd.DataFrame:
    safe_params = tuple(to_sql_param(p) for p in (params or ()))
    try:
        return pd.read_sql_query(query, conn, params=safe_params)
    except Exception:
        cursor = conn.execute(query, safe_params)
        rows = cursor.fetchall()
        columns = [col[0] for col in cursor.description] if cursor.description else []
        return pd.DataFrame(rows, columns=columns)


def student_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) AS cnt FROM students").fetchone()
    return int(row["cnt"])


def upsert_students(conn: sqlite3.Connection, roster: pd.DataFrame) -> int:
    ts = now_ts()
    records = [
        (
            str(row["student_no"]),
            int(row["row_no"]),
            str(row["student_name"]).strip(),
            str(row["project_name"]).strip(),
            str(row["advisor_name"]).strip() or DEFAULT_ADVISOR,
            str(row["program"]).strip(),
            ts,
            ts,
        )
        for _, row in roster.iterrows()
    ]
    current_row_nos = [r[1] for r in records]
    with _db_lock:
        conn.executemany(
            """
            INSERT INTO students(
                student_no, row_no, student_name, project_name, advisor_name, program, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(row_no) DO UPDATE SET
                student_no = excluded.student_no,
                student_name = excluded.student_name,
                project_name = excluded.project_name,
                advisor_name = excluded.advisor_name,
                program = excluded.program,
                updated_at = excluded.updated_at
            """,
            records,
        )
        if current_row_nos:
            placeholders = ",".join(["?"] * len(current_row_nos))
            conn.execute(
                f"DELETE FROM students WHERE row_no NOT IN ({placeholders})",
                current_row_nos,
            )
        conn.commit()
    return len(records)


def get_roster_from_db(conn: sqlite3.Connection, advisor_name: Optional[str] = None) -> pd.DataFrame:
    if advisor_name:
        return fetch_df(
            conn,
            """
            SELECT row_no, student_no, student_name, project_name, advisor_name, program
            FROM students
            WHERE advisor_name = ?
            ORDER BY project_name, row_no, student_name
            """,
            (advisor_name,),
        )
    return fetch_df(
        conn,
        """
        SELECT row_no, student_no, student_name, project_name, advisor_name, program
        FROM students
        ORDER BY advisor_name, project_name, row_no, student_name
        """,
    )


def list_advisors(conn: sqlite3.Connection) -> list[str]:
    df = fetch_df(conn, "SELECT DISTINCT advisor_name FROM students WHERE advisor_name <> '' ORDER BY advisor_name")
    if df.empty:
        return []
    return df["advisor_name"].astype(str).tolist()


def import_students_from_csv(conn: sqlite3.Connection, csv_path: str) -> int:
    roster = load_roster(csv_path)
    return upsert_students(conn, roster)


def sync_auth_users(conn: sqlite3.Connection) -> None:
    ts = now_ts()
    student_rows = fetch_df(
        conn,
        """
        SELECT student_no, MIN(student_name) AS student_name
        FROM students
        WHERE student_no <> ''
        GROUP BY student_no
        """,
    )
    active_student_ids = set(student_rows["student_no"].astype(str).str.strip().tolist())
    existing_student_ids = set(
        fetch_df(conn, "SELECT user_id FROM auth_users WHERE role = 'student'")["user_id"].astype(str).tolist()
    )
    student_insert_records = []
    student_update_records = []
    for _, row in student_rows.iterrows():
        student_no = str(row["student_no"]).strip()
        display_name = str(row["student_name"]).strip() or student_no
        if student_no not in existing_student_ids:
            student_insert_records.append(
                (student_no, "student", display_name, hash_password(DEFAULT_PASSWORD), ts, ts)
            )
        student_update_records.append((display_name, ts, student_no, "student"))

    if student_insert_records:
        conn.executemany(
            """
            INSERT INTO auth_users(
                user_id, role, display_name, password_hash, force_password_change, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 1, 1, ?, ?)
            """,
            student_insert_records,
        )
    if student_update_records:
        conn.executemany(
            """
            UPDATE auth_users
            SET display_name = ?, is_active = 1, updated_at = ?
            WHERE user_id = ? AND role = ?
            """,
            student_update_records,
        )
    if active_student_ids:
        placeholders = ",".join(["?"] * len(active_student_ids))
        conn.execute(
            f"UPDATE auth_users SET is_active = 0, updated_at = ? WHERE role = 'student' AND user_id NOT IN ({placeholders})",
            [ts, *sorted(active_student_ids)],
        )
    else:
        conn.execute("UPDATE auth_users SET is_active = 0, updated_at = ? WHERE role = 'student'", (ts,))

    advisor_rows = fetch_df(conn, "SELECT DISTINCT advisor_name FROM students WHERE advisor_name <> ''")
    active_advisor_ids = set(advisor_rows["advisor_name"].astype(str).str.strip().tolist())
    existing_advisor_ids = set(
        fetch_df(conn, "SELECT user_id FROM auth_users WHERE role = 'advisor'")["user_id"].astype(str).tolist()
    )
    advisor_insert_records = []
    advisor_update_records = []
    for _, row in advisor_rows.iterrows():
        advisor_name = str(row["advisor_name"]).strip()
        if advisor_name not in existing_advisor_ids:
            advisor_insert_records.append(
                (advisor_name, "advisor", advisor_name, hash_password(DEFAULT_PASSWORD), ts, ts)
            )
        advisor_update_records.append((advisor_name, ts, advisor_name, "advisor"))

    if advisor_insert_records:
        conn.executemany(
            """
            INSERT INTO auth_users(
                user_id, role, display_name, password_hash, force_password_change, is_active, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 1, 1, ?, ?)
            """,
            advisor_insert_records,
        )
    if advisor_update_records:
        conn.executemany(
            """
            UPDATE auth_users
            SET display_name = ?, is_active = 1, updated_at = ?
            WHERE user_id = ? AND role = ?
            """,
            advisor_update_records,
        )
    if active_advisor_ids:
        placeholders = ",".join(["?"] * len(active_advisor_ids))
        conn.execute(
            f"UPDATE auth_users SET is_active = 0, updated_at = ? WHERE role = 'advisor' AND user_id NOT IN ({placeholders})",
            [ts, *sorted(active_advisor_ids)],
        )
    else:
        conn.execute("UPDATE auth_users SET is_active = 0, updated_at = ? WHERE role = 'advisor'", (ts,))

    conn.commit()


def authenticate_user(conn: sqlite3.Connection, user_id: str, role: str, password: str) -> Optional[dict]:
    clean_user_id = user_id.strip()
    if role == "advisor":
        row = conn.execute(
            """
            SELECT user_id, role, display_name, password_hash, force_password_change, is_active
            FROM auth_users
            WHERE lower(user_id) = lower(?) AND role = ?
            """,
            (clean_user_id, role),
        ).fetchone()
    else:
        row = conn.execute(
            """
            SELECT user_id, role, display_name, password_hash, force_password_change, is_active
            FROM auth_users
            WHERE user_id = ? AND role = ?
            """,
            (clean_user_id, role),
        ).fetchone()
    if not row or int(row["is_active"]) != 1:
        return None
    if not verify_password(password, str(row["password_hash"])):
        return None
    return {
        "user_id": str(row["user_id"]),
        "role": str(row["role"]),
        "display_name": str(row["display_name"]),
        "force_password_change": bool(int(row["force_password_change"])),
    }


def update_password(conn: sqlite3.Connection, user_id: str, role: str, new_password: str) -> None:
    conn.execute(
        """
        UPDATE auth_users
        SET password_hash = ?, force_password_change = 0, updated_at = ?
        WHERE user_id = ? AND role = ?
        """,
        (hash_password(new_password), now_ts(), user_id, role),
    )
    conn.commit()


def reset_password_to_default(conn: sqlite3.Connection, user_id: str, role: str) -> bool:
    row = conn.execute(
        "SELECT user_id FROM auth_users WHERE user_id = ? AND role = ?",
        (user_id, role),
    ).fetchone()
    if not row:
        return False
    conn.execute(
        """
        UPDATE auth_users
        SET password_hash = ?, force_password_change = 1, updated_at = ?
        WHERE user_id = ? AND role = ?
        """,
        (hash_password(DEFAULT_PASSWORD), now_ts(), user_id, role),
    )
    conn.commit()
    return True


def add_single_student(
    conn: sqlite3.Connection,
    student_no: str,
    student_name: str,
    project_name: str,
    advisor_name: str,
    program: str,
) -> int:
    ts = now_ts()
    max_row = conn.execute("SELECT COALESCE(MAX(row_no), 0) AS mx FROM students").fetchone()["mx"]
    new_row_no = int(max_row) + 1
    conn.execute(
        """
        INSERT INTO students(row_no, student_no, student_name, project_name, advisor_name, program, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (new_row_no, student_no.strip(), student_name.strip(), project_name.strip(),
         advisor_name.strip() or DEFAULT_ADVISOR, program.strip(), ts, ts),
    )
    conn.commit()
    return new_row_no


def get_student_memberships(conn: sqlite3.Connection, student_no: str) -> pd.DataFrame:
    return fetch_df(
        conn,
        """
        SELECT row_no, student_no, student_name, project_name, advisor_name, program
        FROM students
        WHERE student_no = ?
        ORDER BY row_no
        """,
        (student_no,),
    )


def get_leader(conn: sqlite3.Connection, project_name: str) -> Optional[str]:
    row = conn.execute("SELECT student_no FROM leaders WHERE project_name = ?", (project_name,)).fetchone()
    return row["student_no"] if row else None


def set_leader(conn: sqlite3.Connection, project_name: str, student_no: str, assigned_by: str) -> None:
    conn.execute(
        """
        INSERT INTO leaders(project_name, student_no, assigned_by, assigned_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(project_name) DO UPDATE SET
            student_no = excluded.student_no,
            assigned_by = excluded.assigned_by,
            assigned_at = excluded.assigned_at
        """,
        (project_name, student_no, assigned_by, now_ts()),
    )
    conn.commit()


def upsert_role(conn: sqlite3.Connection, project_name: str, student_no: str, role: str, responsibility: str) -> None:
    conn.execute(
        """
        INSERT INTO member_roles(project_name, student_no, role, responsibility, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(project_name, student_no) DO UPDATE SET
            role = excluded.role,
            responsibility = excluded.responsibility,
            updated_at = excluded.updated_at
        """,
        (project_name, student_no, role, responsibility, now_ts()),
    )
    conn.commit()


def bootstrap_defaults(conn: sqlite3.Connection, roster: pd.DataFrame) -> None:
    first_students = roster.sort_values(["project_name", "row_no"]).groupby("project_name", as_index=False).first()
    for _, row in first_students.iterrows():
        project_name = str(row["project_name"])
        student_no = str(row["student_no"])
        advisor_name = str(row["advisor_name"]).strip() or DEFAULT_ADVISOR
        if not get_leader(conn, project_name):
            set_leader(conn, project_name, student_no, advisor_name)
            upsert_role(conn, project_name, student_no, "Lider", "Varsayilan lider (projedeki ilk ogrenci).")


def ensure_project_member_roles(conn: sqlite3.Connection, project_name: str, project_members: pd.DataFrame) -> None:
    if project_members.empty:
        return
    leader_no = get_leader(conn, project_name)
    existing = set(
        fetch_df(
            conn,
            "SELECT student_no FROM member_roles WHERE project_name = ?",
            (project_name,),
        )["student_no"].astype(str).tolist()
    )
    inserts = []
    ts = now_ts()
    seen_student_nos: set[str] = set()
    for _, member in project_members.sort_values("row_no").iterrows():
        student_no = str(member["student_no"])
        if student_no in seen_student_nos:
            continue
        seen_student_nos.add(student_no)
        if student_no in existing:
            continue
        role = "Lider" if leader_no and student_no == leader_no else "Uye"
        responsibility = "Varsayilan lider (projedeki ilk ogrenci)." if role == "Lider" else "Grup uyesi."
        inserts.append((project_name, student_no, role, responsibility, ts))
    if inserts:
        conn.executemany(
            """
            INSERT INTO member_roles(project_name, student_no, role, responsibility, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            inserts,
        )
        conn.commit()


def ensure_project_sequential_tasks(conn: sqlite3.Connection, project_name: str, project_members: pd.DataFrame) -> int:
    if project_members.empty:
        return 0
    leader_no = get_leader(conn, project_name)
    creator = leader_no or str(project_members.sort_values("row_no").iloc[0]["student_no"])
    existing_df = fetch_df(
        conn,
        """
        SELECT milestone_key, assignee_student_no
        FROM tasks
        WHERE project_name = ?
        """,
        (project_name,),
    )
    existing_pairs = set(
        (
            str(row["assignee_student_no"]),
            str(row["milestone_key"]),
        )
        for _, row in existing_df.iterrows()
        if str(row["milestone_key"]) in MILESTONE_LABELS
    )

    ts = now_ts()
    inserts = []
    for _, member in project_members.sort_values("row_no").iterrows():
        student_no = str(member["student_no"])
        student_name = str(member["student_name"]).strip()
        for milestone_key, milestone_label in MILESTONES:
            pair = (student_no, milestone_key)
            if pair in existing_pairs:
                continue
            inserts.append(
                (
                    project_name,
                    milestone_key,
                    f"{milestone_label} - {student_name}",
                    f"{milestone_label} adimi icin bireysel gorev.",
                    student_no,
                    "TODO",
                    "Orta",
                    None,
                    None,
                    "Repo linki, rapor veya ilgili kanit",
                    "",
                    creator,
                    ts,
                    ts,
                )
            )
            existing_pairs.add(pair)

    if inserts:
        conn.executemany(
            """
            INSERT INTO tasks(
                project_name, milestone_key, title, description, assignee_student_no, status,
                priority, deadline, dependency_task_id, evidence_required, evidence_link,
                created_by, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            inserts,
        )
        conn.commit()
    return len(inserts)


def initialize_all_projects(conn: sqlite3.Connection, roster: pd.DataFrame) -> tuple[int, int]:
    if roster.empty:
        return (0, 0)
    created_tasks = 0
    touched_projects = 0
    for project_name, grp in roster.groupby("project_name"):
        project_name = str(project_name)
        members = grp.sort_values("row_no")
        ensure_project_member_roles(conn, project_name, members)
        created_tasks += ensure_project_sequential_tasks(conn, project_name, members)
        touched_projects += 1
    return touched_projects, created_tasks


def current_student_task(my_tasks: pd.DataFrame) -> Optional[pd.Series]:
    if my_tasks.empty:
        return None
    scoped = my_tasks.copy()
    scoped["ms_order"] = scoped["milestone_key"].map(MILESTONE_ORDER).fillna(999).astype(int)
    scoped = scoped.sort_values(["ms_order", "id"])
    open_tasks = scoped[scoped["status"] != "DONE"]
    if open_tasks.empty:
        return None
    return open_tasks.iloc[0]


def create_task(
    conn: sqlite3.Connection,
    project_name: str,
    milestone_key: str,
    title: str,
    description: str,
    assignee_student_no: str,
    priority: str,
    deadline: Optional[str],
    dependency_task_id: Optional[int],
    evidence_required: str,
    created_by: str,
) -> None:
    ts = now_ts()
    conn.execute(
        """
        INSERT INTO tasks(
            project_name, milestone_key, title, description, assignee_student_no, status,
            priority, deadline, dependency_task_id, evidence_required, evidence_link,
            created_by, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, 'TODO', ?, ?, ?, ?, '', ?, ?, ?)
        """,
        (
            project_name,
            milestone_key,
            title.strip(),
            description.strip(),
            assignee_student_no,
            priority,
            deadline,
            dependency_task_id,
            evidence_required.strip(),
            created_by,
            ts,
            ts,
        ),
    )
    conn.commit()


def update_task(
    conn: sqlite3.Connection,
    task_id: int,
    status: str,
    evidence_link: str,
    skip_milestone_check: bool = False,
    evidence_file: str = "",
) -> tuple[bool, str]:
    row = conn.execute(
        "SELECT status, project_name, milestone_key, assignee_student_no FROM tasks WHERE id = ?",
        (task_id,),
    ).fetchone()
    if not row:
        return False, "Gorev bulunamadi."

    current_status = str(row["status"])
    target_status = str(status)
    allowed = STATUS_TRANSITIONS.get(current_status, {current_status})
    if target_status not in allowed:
        return (
            False,
            f"Durum gecisi gecersiz: {status_tr(current_status)} -> {status_tr(target_status)}",
        )

    existing_file = conn.execute("SELECT evidence_file FROM tasks WHERE id = ?", (task_id,)).fetchone()
    has_file = bool(evidence_file) or bool(existing_file and existing_file["evidence_file"])
    if target_status == "DONE" and not evidence_link.strip() and not has_file:
        return False, "TAMAMLANDI durumuna gecmek icin kanit linki veya dosya zorunludur."

    if not skip_milestone_check and target_status in ("DOING", "DONE"):
        task_milestone = str(row["milestone_key"])
        task_ms_order = MILESTONE_ORDER.get(task_milestone, 0)
        if task_ms_order > 0:
            assignee = str(row["assignee_student_no"])
            project = str(row["project_name"])
            prev_milestones = [k for k, idx in MILESTONE_ORDER.items() if idx < task_ms_order]
            if prev_milestones:
                placeholders = ",".join(["?"] * len(prev_milestones))
                incomplete = conn.execute(
                    f"""
                    SELECT COUNT(*) AS cnt FROM tasks
                    WHERE project_name = ? AND assignee_student_no = ?
                      AND milestone_key IN ({placeholders})
                      AND status <> 'DONE'
                    """,
                    [project, assignee, *prev_milestones],
                ).fetchone()["cnt"]
                if int(incomplete) > 0:
                    prev_label = MILESTONE_LABELS.get(prev_milestones[-1], prev_milestones[-1])
                    return (
                        False,
                        f"Onceki milestone tamamlanmadan bu goreve gecilemez. Tamamlanmamis: {prev_label}",
                    )

    if evidence_file:
        conn.execute(
            "UPDATE tasks SET status = ?, evidence_link = ?, evidence_file = ?, updated_at = ? WHERE id = ?",
            (target_status, evidence_link.strip(), evidence_file, now_ts(), task_id),
        )
    else:
        conn.execute(
            "UPDATE tasks SET status = ?, evidence_link = ?, updated_at = ? WHERE id = ?",
            (target_status, evidence_link.strip(), now_ts(), task_id),
        )
    conn.commit()
    return True, "ok"


def add_weekly_update(
    conn: sqlite3.Connection,
    project_name: str,
    student_no: str,
    task_id: Optional[int],
    week_start: str,
    completed: str,
    blockers: str,
    next_step: str,
    evidence_link: str,
) -> None:
    conn.execute(
        """
        INSERT INTO weekly_updates(
            project_name, student_no, task_id, week_start, completed,
            blockers, next_step, evidence_link, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_name,
            student_no,
            task_id,
            week_start,
            completed.strip(),
            blockers.strip(),
            next_step.strip(),
            evidence_link.strip(),
            now_ts(),
        ),
    )
    conn.commit()


def add_feedback(
    conn: sqlite3.Connection,
    project_name: str,
    advisor_name: str,
    feedback: str,
    action_item: str,
    revision_required: bool,
) -> None:
    conn.execute(
        """
        INSERT INTO advisor_feedback(
            project_name, advisor_name, feedback, action_item, revision_required, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (project_name, advisor_name, feedback.strip(), action_item.strip(), int(revision_required), now_ts()),
    )
    conn.commit()


def fetch_tasks(conn: sqlite3.Connection, project_name: str) -> pd.DataFrame:
    return fetch_df(
        conn,
        """
        SELECT id, project_name, milestone_key, title, description, assignee_student_no, status, priority,
               deadline, dependency_task_id, evidence_required, evidence_link,
               COALESCE(evidence_file, '') AS evidence_file, updated_at
        FROM tasks
        WHERE project_name = ?
        ORDER BY milestone_key, deadline, id
        """,
        (project_name,),
    )


def save_uploaded_evidence(uploaded_file, task_id: int) -> str:
    import uuid
    ext = Path(uploaded_file.name).suffix.lower()
    safe_name = f"task_{task_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = UPLOADS_DIR / safe_name
    dest.write_bytes(uploaded_file.getvalue())
    return str(dest)


def render_evidence_file(evidence_file_path: str) -> None:
    if not evidence_file_path:
        return
    p = Path(evidence_file_path)
    if not p.exists():
        st.caption(f"Dosya bulunamadi: {p.name}")
        return
    ext = p.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        st.image(str(p), caption=p.name, use_container_width=True)
    elif ext == ".pdf":
        st.caption(f"PDF dosyasi: {p.name}")
        with open(p, "rb") as f:
            st.download_button("PDF indir", f.read(), file_name=p.name, mime="application/pdf")
    else:
        st.caption(f"Dosya: {p.name}")
        with open(p, "rb") as f:
            st.download_button("Dosyayi indir", f.read(), file_name=p.name)


def completion_percent(tasks_df: pd.DataFrame) -> float:
    if tasks_df.empty:
        return 0.0
    done = int((tasks_df["status"] == "DONE").sum())
    return round(done * 100 / len(tasks_df), 1)


def overdue_count(tasks_df: pd.DataFrame) -> int:
    if tasks_df.empty:
        return 0
    deadlines = pd.to_datetime(tasks_df["deadline"], errors="coerce")
    today = pd.Timestamp.now().normalize()
    mask = (deadlines < today) & (tasks_df["status"] != "DONE")
    return int(mask.fillna(False).sum())


def fetch_feedbacks(conn: sqlite3.Connection, project_name: str) -> pd.DataFrame:
    return fetch_df(
        conn,
        """
        SELECT id, advisor_name, feedback, action_item, revision_required, created_at
        FROM advisor_feedback
        WHERE project_name = ?
        ORDER BY created_at DESC
        """,
        (project_name,),
    )


def fetch_weekly_updates_for_project(
    conn: sqlite3.Connection, project_name: str, student_no: str = None
) -> pd.DataFrame:
    if student_no:
        return fetch_df(
            conn,
            """
            SELECT id, student_no, task_id, week_start,
                   completed, blockers, next_step, evidence_link, created_at
            FROM weekly_updates
            WHERE project_name = ? AND student_no = ?
            ORDER BY created_at DESC
            """,
            (project_name, student_no),
        )
    return fetch_df(
        conn,
        """
        SELECT id, student_no, task_id, week_start,
               completed, blockers, next_step, evidence_link, created_at
        FROM weekly_updates
        WHERE project_name = ?
        ORDER BY created_at DESC
        """,
        (project_name,),
    )


def add_task_comment(
    conn: sqlite3.Connection,
    task_id: int,
    project_name: str,
    author_id: str,
    author_role: str,
    comment: str,
) -> None:
    conn.execute(
        """
        INSERT INTO task_comments(task_id, project_name, author_id, author_role, comment, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (task_id, project_name, author_id, author_role, comment.strip(), now_ts()),
    )
    conn.commit()


def fetch_task_comments(conn: sqlite3.Connection, task_id: int) -> pd.DataFrame:
    return fetch_df(
        conn,
        """
        SELECT id, task_id, author_id, author_role, comment, created_at
        FROM task_comments
        WHERE task_id = ?
        ORDER BY created_at ASC
        """,
        (task_id,),
    )


def load_roster_from_upload(uploaded_file) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]
    raw_bytes = uploaded_file.getvalue()
    df = None
    for enc in encodings:
        try:
            import io
            df = pd.read_csv(io.BytesIO(raw_bytes), sep=";", encoding=enc, dtype=str).fillna("")
            break
        except Exception:
            continue
    if df is None:
        raise ValueError("CSV okunamadi.")

    col_map: Dict[str, str] = {}
    for col in df.columns:
        raw = str(col).strip()
        norm = normalize_header(raw)
        if raw == "#" or norm in {"sira", "index"}:
            col_map[col] = "row_no"
        elif "ogrencino" in norm or "studentno" in norm:
            col_map[col] = "student_no"
        elif "ogrenciadi" in norm or "studentname" in norm:
            col_map[col] = "student_name"
        elif "projeadi" in norm or "projectname" in norm:
            col_map[col] = "project_name"
        elif "danismanadi" in norm or "advisorname" in norm:
            col_map[col] = "advisor_name"
        elif "program" in norm:
            col_map[col] = "program"

    df = df.rename(columns=col_map)
    expected = ["row_no", "student_no", "student_name", "project_name", "advisor_name", "program"]
    if not all(col in df.columns for col in expected):
        if len(df.columns) < 6:
            raise ValueError("CSV kolonlari yetersiz.")
        fallback = dict(zip(list(df.columns)[:6], expected))
        df = df.rename(columns=fallback)

    df = df[expected].copy()
    for col in ["student_no", "student_name", "project_name", "advisor_name", "program"]:
        df[col] = df[col].astype(str).str.strip()

    df["student_no"] = df["student_no"].str.replace(r"^\?+", "", regex=True)
    fallback_row = pd.Series(range(1, len(df) + 1), index=df.index)
    df["row_no"] = pd.to_numeric(df["row_no"], errors="coerce").fillna(fallback_row).astype(int)
    df = df[(df["student_no"] != "") & (df["project_name"] != "")].copy()
    df = df.sort_values(["project_name", "row_no", "student_name"]).reset_index(drop=True)
    return df


def render_task_comments(
    conn: sqlite3.Connection,
    task_id: int,
    project_name: str,
    current_user_id: str,
    current_user_role: str,
    form_key_suffix: str = "",
) -> None:
    comments_df = fetch_task_comments(conn, task_id)
    if not comments_df.empty:
        for _, c in comments_df.iterrows():
            role_badge = {"advisor": "Danisman", "leader": "Lider", "student": "Ogrenci"}.get(
                str(c["author_role"]), str(c["author_role"])
            )
            st.caption(f"**[{role_badge}] {c['author_id']}** — {str(c['created_at'])[:16]}")
            st.markdown(f"> {c['comment']}")
    else:
        st.caption("Henuz yorum yok.")

    with st.form(f"comment_form_{task_id}_{form_key_suffix}"):
        new_comment = st.text_area("Yorum yazin", key=f"comment_text_{task_id}_{form_key_suffix}")
        comment_submit = st.form_submit_button("Yorum ekle")
    if comment_submit:
        if not new_comment.strip():
            st.error("Yorum bos olamaz.")
        else:
            add_task_comment(conn, task_id, project_name, current_user_id, current_user_role, new_comment)
            st.success("Yorum eklendi.")
            st.rerun()


def member_progress(project_members: pd.DataFrame, tasks_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, member in project_members.sort_values("row_no").iterrows():
        student_no = str(member["student_no"])
        scoped = tasks_df[tasks_df["assignee_student_no"] == student_no]
        rows.append(
            {
                "Ogrenci No": student_no,
                "Ogrenci": member["student_name"],
                "Atanan Gorev": int(len(scoped)),
                "Tamamlanan": int((scoped["status"] == "DONE").sum()),
                "Ilerleme %": completion_percent(scoped),
            }
        )
    return pd.DataFrame(rows)


def build_project_metrics(conn: sqlite3.Connection, roster: pd.DataFrame, projects: Iterable[str]) -> pd.DataFrame:
    rows = []
    recent_start = (date.today() - timedelta(days=14)).isoformat()
    for project in projects:
        group = roster[roster["project_name"] == project]
        if group.empty:
            continue

        leader_no = get_leader(conn, project)
        leader_name = "-"
        if leader_no:
            hit = group[group["student_no"] == leader_no]
            leader_name = str(hit.iloc[0]["student_name"]) if not hit.empty else leader_no

        tasks_df = fetch_tasks(conn, project)
        completion = completion_percent(tasks_df)
        overdue = overdue_count(tasks_df)
        activity = conn.execute(
            "SELECT COUNT(*) AS cnt FROM weekly_updates WHERE project_name = ? AND week_start >= ?",
            (project, recent_start),
        ).fetchone()["cnt"]

        if completion >= 80 and overdue == 0:
            risk = "Dusuk"
        elif completion >= 50 and overdue <= 2:
            risk = "Orta"
        else:
            risk = "Yuksek"

        rows.append(
            {
                "Proje": project,
                "Ogrenci Sayisi": int(len(group)),
                "Lider": leader_name,
                "Tamamlanma %": completion,
                "Geciken Gorev": overdue,
                "Son 14 Gun Aktivite": int(activity),
                "Risk": risk,
            }
        )
    return pd.DataFrame(rows)


def render_milestone_progress(tasks_df: pd.DataFrame) -> None:
    st.markdown("#### Milestone bazli ilerleme")
    for milestone_key, label in MILESTONES:
        scoped = tasks_df[tasks_df["milestone_key"] == milestone_key]
        percent = completion_percent(scoped)
        st.write(f"{label}: %{percent}")
        st.progress(percent / 100 if percent > 0 else 0.0)


def render_advisor_panel(conn: sqlite3.Connection, advisor_name: str, roster: pd.DataFrame) -> None:
    st.subheader(f"Danisman paneli: {advisor_name}")
    projects = sorted(roster["project_name"].unique())
    if not projects:
        st.warning("Secilen danismana ait grup/ogrenci kaydi yok.")
        return

    summary_df = build_project_metrics(conn, roster, projects)
    completion_by_project: Dict[str, float] = {}
    if not summary_df.empty:
        completion_by_project = {
            str(row["Proje"]): float(row["Tamamlanma %"])
            for _, row in summary_df.iterrows()
        }

    st.markdown("### Danismana ait gruplar ve ogrenciler")
    group_rows = []
    for project in projects:
        grp = roster[roster["project_name"] == project].sort_values("row_no")
        leader_no = get_leader(conn, project)
        if leader_no:
            hit = grp[grp["student_no"].astype(str) == str(leader_no)]
            if not hit.empty:
                leader_text = f"{hit.iloc[0]['student_name']} ({leader_no})"
            else:
                leader_text = str(leader_no)
        else:
            leader_text = "-"

        member_labels = [
            f"{r['student_name']} ({r['student_no']})"
            for _, r in grp.iterrows()
        ]
        group_rows.append(
            {
                "Proje": project,
                "Proje Sorumlusu": leader_text,
                "Grup Uyeleri": ", ".join(member_labels),
                "Ogrenci Sayisi": int(len(grp)),
                "Ilerleme %": completion_by_project.get(project, 0.0),
            }
        )
    group_table = pd.DataFrame(group_rows)
    if not group_table.empty:
        group_table = group_table.sort_values(["Ilerleme %", "Ogrenci Sayisi"], ascending=[False, False])
    st.dataframe(group_table, use_container_width=True, hide_index=True)

    st.markdown("### Acilis ozeti: tum projelerin durumu")
    if summary_df.empty:
        st.info("Henuz gorev girisi yok.")
    else:
        summary_df = summary_df.sort_values(["Tamamlanma %", "Geciken Gorev"], ascending=[False, True])
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

    st.markdown("### Ogrenci arama ve bireysel takip")
    search_query = st.text_input(
        "Ogrenci adi veya numarasi ile arayiniz",
        key="advisor_student_search",
        placeholder="Ornek: Ali Veli veya 2001234567",
    )
    if search_query.strip():
        q = search_query.strip().lower()
        matches = roster[
            roster["student_name"].str.lower().str.contains(q, na=False)
            | roster["student_no"].str.contains(q, na=False)
        ]
        if matches.empty:
            st.warning(f"\"{search_query}\" ile eslesen ogrenci bulunamadi.")
        else:
            unique_students = matches[["student_no", "student_name"]].drop_duplicates()
            if len(unique_students) > 1:
                pick_options = {
                    f"{r['student_name']} ({r['student_no']})": str(r["student_no"])
                    for _, r in unique_students.iterrows()
                }
                picked = st.selectbox("Birden fazla sonuc bulundu, secin", list(pick_options.keys()), key="search_pick")
                picked_no = pick_options[picked]
            else:
                picked_no = str(unique_students.iloc[0]["student_no"])

            stu_rows = roster[roster["student_no"] == picked_no]
            if stu_rows.empty:
                st.error("Ogrenci kaydi bulunamadi.")
            else:
                stu_info = stu_rows.iloc[0]
                stu_name = str(stu_info["student_name"])
                stu_project = str(stu_info["project_name"])

                st.markdown(f"---")
                st.markdown(f"#### {stu_name} ({picked_no})")

                c1, c2 = st.columns(2)
                c1.markdown(f"**Proje:** {stu_project}")
                c2.markdown(f"**Program:** {stu_info.get('program', '-')}")

                leader_no = get_leader(conn, stu_project)
                is_stu_leader = (leader_no == picked_no)
                team = roster[roster["project_name"] == stu_project].sort_values("row_no")
                role_df = fetch_df(
                    conn,
                    "SELECT student_no, role, responsibility FROM member_roles WHERE project_name = ?",
                    (stu_project,),
                )
                stu_role_row = role_df[role_df["student_no"] == picked_no]
                stu_role = str(stu_role_row.iloc[0]["role"]) if not stu_role_row.empty else "Atanmadi"
                stu_resp = str(stu_role_row.iloc[0]["responsibility"]) if not stu_role_row.empty else "-"

                c3, c4 = st.columns(2)
                c3.markdown(f"**Rol:** {stu_role} {'(Lider)' if is_stu_leader else ''}")
                c4.markdown(f"**Gorevi:** {stu_resp}")

                st.markdown("**Takim Arkadaşları:**")
                team_labels = [
                    f"{'👑 ' if get_leader(conn, stu_project) == str(r['student_no']) else ''}{r['student_name']} ({r['student_no']})"
                    for _, r in team.iterrows()
                ]
                st.caption(" | ".join(team_labels))

                stu_tasks = fetch_tasks(conn, stu_project)
                my_tasks = stu_tasks[stu_tasks["assignee_student_no"] == picked_no]

                c5, c6, c7 = st.columns(3)
                c5.metric("Atanan Gorev", len(my_tasks))
                c6.metric("Tamamlanan", int((my_tasks["status"] == "DONE").sum()) if not my_tasks.empty else 0)
                c7.metric("Ilerleme", f"%{completion_percent(my_tasks)}")

                if not my_tasks.empty:
                    st.markdown("**Gorev Durumu (Milestone Bazli):**")
                    task_table = my_tasks.copy()
                    task_table["Milestone"] = task_table["milestone_key"].map(MILESTONE_LABELS)
                    task_table["Durum"] = task_table["status"].map(status_tr)
                    task_table["Deadline"] = task_table["deadline"].replace("", "-").fillna("-")
                    st.dataframe(
                        task_table[["id", "Milestone", "title", "Durum", "priority", "Deadline", "evidence_link"]].rename(columns={
                            "id": "ID", "title": "Gorev", "priority": "Oncelik", "evidence_link": "Kanit",
                        }),
                        use_container_width=True, hide_index=True,
                    )
                    for _, t in my_tasks.iterrows():
                        ef = str(t.get("evidence_file", "") or "")
                        if ef:
                            with st.expander(f"Kanit dosyasi: #{int(t['id'])} - {t['title']}"):
                                render_evidence_file(ef)
                else:
                    st.info("Bu ogrenciye atanmis gorev yok.")

                stu_weekly = fetch_weekly_updates_for_project(conn, stu_project, picked_no)
                if not stu_weekly.empty:
                    st.markdown("**Haftalik Giris Gecmisi:**")
                    st.dataframe(
                        stu_weekly[["week_start", "completed", "blockers", "next_step", "evidence_link", "created_at"]].rename(columns={
                            "week_start": "Hafta", "completed": "Yapilanlar", "blockers": "Engeller",
                            "next_step": "Sonraki Adim", "evidence_link": "Kanit", "created_at": "Tarih",
                        }),
                        use_container_width=True, hide_index=True,
                    )
                else:
                    st.caption("Henuz haftalik giris yapilmamis.")

                stu_fb = fetch_feedbacks(conn, stu_project)
                if not stu_fb.empty:
                    st.markdown("**Projeye Verilen Geri Bildirimler:**")
                    for _, fb in stu_fb.iterrows():
                        is_rev = bool(int(fb["revision_required"])) if fb["revision_required"] else False
                        icon = "\U0001f534" if is_rev else "\U0001f4ac"
                        st.caption(f"{icon} {str(fb['created_at'])[:10]} - {fb['feedback'][:80]}{'...' if len(str(fb['feedback'])) > 80 else ''}")

                st.markdown("---")

    st.markdown("### Proje lideri atama")
    project_name = st.selectbox("Proje", projects, key="advisor_project_pick")
    members = roster[roster["project_name"] == project_name].sort_values("row_no")
    options = {f"{r['student_name']} ({r['student_no']})": str(r["student_no"]) for _, r in members.iterrows()}
    current_leader = get_leader(conn, project_name)
    labels = list(options.keys())
    default_idx = 0
    if current_leader:
        for i, label in enumerate(labels):
            if options[label] == current_leader:
                default_idx = i
                break

    with st.form("leader_assign_form"):
        label = st.selectbox("Lider adayi", labels, index=default_idx)
        submitted = st.form_submit_button("Lideri kaydet")
    if submitted:
        leader_no = options[label]
        set_leader(conn, project_name, leader_no, advisor_name)
        upsert_role(conn, project_name, leader_no, "Lider", "Danisman tarafindan atanmis lider")
        st.success("Lider guncellendi.")
        st.rerun()

    st.markdown("### CSV ile ogrenci listesi guncelleme")
    with st.expander("CSV yukle / guncelle"):
        uploaded_csv = st.file_uploader("CSV dosyasi secin", type=["csv"], key="advisor_csv_upload")
        if uploaded_csv is not None:
            try:
                new_roster = load_roster_from_upload(uploaded_csv)
                st.dataframe(new_roster, use_container_width=True, hide_index=True)
                st.caption(f"{len(new_roster)} ogrenci kaydi bulundu.")
                if st.button("Ogrenci listesini guncelle", key="apply_csv_btn"):
                    count = upsert_students(conn, new_roster)
                    sync_auth_users(conn)
                    bootstrap_defaults(conn, new_roster)
                    initialize_all_projects(conn, new_roster)
                    st.cache_data.clear()
                    st.success(f"{count} ogrenci kaydi guncellendi.")
                    st.rerun()
            except Exception as e:
                st.error(f"CSV okuma hatasi: {e}")

    st.markdown("### Tek ogrenci ekleme")
    with st.expander("Yeni ogrenci ekle"):
        existing_projects = sorted(roster["project_name"].unique().tolist()) if not roster.empty else []
        with st.form("add_single_student_form"):
            new_student_no = st.text_input("Ogrenci No")
            new_student_name = st.text_input("Ogrenci Adi Soyadi")
            use_existing_project = st.checkbox("Mevcut bir projeye ekle", value=True)
            if use_existing_project and existing_projects:
                new_project_name = st.selectbox("Mevcut proje sec", existing_projects, key="existing_proj_select")
            else:
                new_project_name = st.text_input("Yeni proje adi")
            new_program = st.text_input("Program", value="")
            add_student_submit = st.form_submit_button("Ogrenciyi ekle")
        if add_student_submit:
            if not new_student_no.strip():
                st.error("Ogrenci no bos olamaz.")
            elif not new_student_name.strip():
                st.error("Ogrenci adi bos olamaz.")
            elif not new_project_name.strip():
                st.error("Proje adi bos olamaz.")
            else:
                existing_check = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM students WHERE student_no = ? AND project_name = ?",
                    (new_student_no.strip(), new_project_name.strip()),
                ).fetchone()["cnt"]
                if int(existing_check) > 0:
                    st.error(f"{new_student_no} numarali ogrenci zaten '{new_project_name}' projesinde kayitli.")
                else:
                    add_single_student(
                        conn,
                        student_no=new_student_no,
                        student_name=new_student_name,
                        project_name=new_project_name,
                        advisor_name=advisor_name,
                        program=new_program,
                    )
                    updated_roster = get_roster_from_db(conn, advisor_name)
                    sync_auth_users(conn)
                    bootstrap_defaults(conn, updated_roster)
                    initialize_all_projects(conn, updated_roster)
                    st.cache_data.clear()
                    st.success(f"{new_student_name} ({new_student_no}) basariyla '{new_project_name}' projesine eklendi.")
                    st.rerun()

    st.markdown("### Sifre sifirlama")
    with st.expander("Ogrenci / danisman sifresi sifirla"):
        st.caption("Secilen kullanicinin sifresi 12345'e sifirlanir ve ilk giriste degistirmesi zorunlu olur.")
        reset_role_label = st.selectbox("Kullanici turu", ["Ogrenci", "Danisman"], key="pwd_reset_role")
        reset_role = "student" if reset_role_label == "Ogrenci" else "advisor"
        if reset_role == "student":
            student_list = roster[["student_no", "student_name"]].drop_duplicates().sort_values("student_name")
            if student_list.empty:
                st.info("Sifirlanacak ogrenci yok.")
            else:
                reset_options = {
                    f"{r['student_name']} ({r['student_no']})": str(r["student_no"])
                    for _, r in student_list.iterrows()
                }
                selected_reset_user = st.selectbox("Ogrenci secin", list(reset_options.keys()), key="pwd_reset_student")
                reset_user_id = reset_options[selected_reset_user]
                if st.button("Sifreyi sifirla", key="pwd_reset_btn_student"):
                    ok = reset_password_to_default(conn, reset_user_id, "student")
                    if ok:
                        st.success(f"{selected_reset_user} sifresi 12345 olarak sifirlandi.")
                    else:
                        st.error("Kullanici bulunamadi.")
        else:
            advisor_list = fetch_df(
                conn,
                "SELECT user_id, display_name FROM auth_users WHERE role = 'advisor' AND is_active = 1 ORDER BY display_name",
            )
            if advisor_list.empty:
                st.info("Sifirlanacak danisman yok.")
            else:
                adv_reset_options = {
                    str(r["display_name"]): str(r["user_id"])
                    for _, r in advisor_list.iterrows()
                }
                selected_adv_reset = st.selectbox("Danisman secin", list(adv_reset_options.keys()), key="pwd_reset_advisor")
                reset_adv_id = adv_reset_options[selected_adv_reset]
                if st.button("Sifreyi sifirla", key="pwd_reset_btn_advisor"):
                    ok = reset_password_to_default(conn, reset_adv_id, "advisor")
                    if ok:
                        st.success(f"{selected_adv_reset} sifresi 12345 olarak sifirlandi.")
                    else:
                        st.error("Kullanici bulunamadi.")

    st.markdown("### Proje detayi")
    detail_project = st.selectbox("Detay goruntulenecek proje", projects, key="advisor_detail_project")
    project_members = roster[roster["project_name"] == detail_project]
    tasks_df = fetch_tasks(conn, detail_project)

    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam gorev", len(tasks_df))
    c2.metric("Tamamlanma", f"%{completion_percent(tasks_df)}")
    c3.metric("Geciken gorev", overdue_count(tasks_df))

    st.dataframe(member_progress(project_members, tasks_df), use_container_width=True, hide_index=True)
    render_milestone_progress(tasks_df)

    if not tasks_df.empty:
        table = tasks_df.copy()
        table["Milestone"] = table["milestone_key"].map(MILESTONE_LABELS)
        table["status"] = table["status"].map(status_tr)
        table["deadline"] = table["deadline"].replace("", "-").fillna("-")
        st.dataframe(
            table[["id", "Milestone", "title", "assignee_student_no", "status", "priority", "deadline", "evidence_link"]],
            use_container_width=True,
            hide_index=True,
        )

    if not tasks_df.empty:
        st.markdown("### Gorev durumu guncelleme")
        task_options_adv = {
            f"#{int(r['id'])} [{status_tr(r['status'])}] {r['title']}": int(r["id"])
            for _, r in tasks_df.iterrows()
        }
        selected_task_adv = st.selectbox("Gorev secin", list(task_options_adv.keys()), key="advisor_task_select")
        adv_task_id = task_options_adv[selected_task_adv]
        adv_task_row = tasks_df[tasks_df["id"] == adv_task_id].iloc[0]
        adv_status_options = allowed_status_options(str(adv_task_row["status"]))
        adv_status_idx = adv_status_options.index(adv_task_row["status"]) if adv_task_row["status"] in adv_status_options else 0
        with st.form(f"advisor_task_update_form_{detail_project}"):
            adv_new_status = st.selectbox("Yeni durum", adv_status_options, index=adv_status_idx, format_func=status_tr)
            adv_evidence = st.text_input("Kanit linki", value=adv_task_row["evidence_link"] or "")
            adv_task_submit = st.form_submit_button("Gorevi guncelle")
        adv_evidence_upload = st.file_uploader(
            "Kanit dosyasi yukle (resim, PDF vb.)",
            type=["png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "zip"],
            key=f"adv_evidence_file_{detail_project}",
        )
        existing_adv_file = str(adv_task_row.get("evidence_file", "") or "")
        if existing_adv_file:
            st.caption("Mevcut kanit dosyasi:")
            render_evidence_file(existing_adv_file)
        if adv_task_submit:
            file_path = ""
            if adv_evidence_upload is not None:
                file_path = save_uploaded_evidence(adv_evidence_upload, adv_task_id)
            ok, msg = update_task(conn, adv_task_id, adv_new_status, adv_evidence, skip_milestone_check=True, evidence_file=file_path)
            if ok:
                st.success("Gorev guncellendi.")
                st.rerun()
            else:
                st.error(msg)

        st.markdown("### Gorev yorumlari")
        with st.expander(f"Yorumlar: #{adv_task_id} - {adv_task_row['title']}"):
            render_task_comments(
                conn, adv_task_id, detail_project,
                current_user_id=advisor_name,
                current_user_role="advisor",
                form_key_suffix=f"adv_{detail_project}",
            )

    weekly_df = fetch_weekly_updates_for_project(conn, detail_project)
    if not weekly_df.empty:
        st.markdown("### Haftalik guncellemeler")
        display_weekly = weekly_df.copy()
        name_map = dict(zip(
            project_members["student_no"].astype(str),
            project_members["student_name"].astype(str),
        ))
        display_weekly["Ogrenci"] = display_weekly["student_no"].map(name_map).fillna(display_weekly["student_no"])
        st.dataframe(
            display_weekly[["Ogrenci", "week_start", "completed", "blockers", "next_step", "evidence_link", "created_at"]].rename(columns={
                "week_start": "Hafta",
                "completed": "Yapilanlar",
                "blockers": "Engeller",
                "next_step": "Sonraki Adim",
                "evidence_link": "Kanit",
                "created_at": "Tarih",
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### Danisman geri bildirimi")
    with st.form("feedback_form"):
        feedback = st.text_area("Geri bildirim")
        action_item = st.text_input("Aksiyon")
        revision_required = st.checkbox("Revizyon gerekli")
        fb_submit = st.form_submit_button("Kaydet")
    if fb_submit:
        if not feedback.strip():
            st.error("Geri bildirim bos olamaz.")
        else:
            add_feedback(conn, detail_project, advisor_name, feedback, action_item, revision_required)
            st.success("Geri bildirim kaydedildi.")
            st.rerun()

    feedbacks_df = fetch_feedbacks(conn, detail_project)
    if not feedbacks_df.empty:
        st.markdown("### Gecmis geri bildirimler")
        for _, fb in feedbacks_df.iterrows():
            is_revision = bool(int(fb["revision_required"])) if fb["revision_required"] else False
            icon = "\U0001f534" if is_revision else "\U0001f4ac"
            with st.expander(f"{icon} {str(fb['created_at'])[:10]} - {fb['advisor_name']}"):
                st.write(fb["feedback"])
                if fb["action_item"]:
                    st.caption(f"Aksiyon: {fb['action_item']}")
                if is_revision:
                    st.error("Revizyon gerekli!")


def render_leader_panel(
    conn: sqlite3.Connection,
    roster: pd.DataFrame,
    fixed_project_name: Optional[str] = None,
    fixed_leader_no: Optional[str] = None,
) -> None:
    st.subheader("Grup yoneticisi paneli")
    if roster.empty:
        st.warning("Secilen danismana ait ogrenci bulunamadi.")
        return

    if fixed_project_name and fixed_leader_no:
        project_name = fixed_project_name
        leader_no = fixed_leader_no
        current = get_leader(conn, project_name)
        if current != leader_no:
            st.error("Bu proje icin lider paneline erisim yetkiniz yok.")
            return
    else:
        allowed_projects = set(roster["project_name"].astype(str).tolist())
        leaders_df = fetch_df(conn, "SELECT project_name, student_no FROM leaders ORDER BY project_name")
        leaders_df = leaders_df[leaders_df["project_name"].astype(str).isin(allowed_projects)]
        if leaders_df.empty:
            st.warning("Lider atamasi yok. Danisman panelinden atayin.")
            return

        leader_options: Dict[str, tuple[str, str]] = {}
        for _, row in leaders_df.iterrows():
            listed_project = str(row["project_name"])
            student_no = str(row["student_no"])
            member = roster[(roster["project_name"] == listed_project) & (roster["student_no"] == student_no)]
            student_name = str(member.iloc[0]["student_name"]) if not member.empty else "Bilinmeyen"
            leader_options[f"{student_name} ({student_no}) - {listed_project}"] = (listed_project, student_no)

        selected = st.selectbox("Lider", sorted(leader_options.keys()))
        project_name, leader_no = leader_options[selected]
    team_df = roster[roster["project_name"] == project_name].sort_values("row_no")
    tasks_df = fetch_tasks(conn, project_name)
    my_tasks = tasks_df[tasks_df["assignee_student_no"] == leader_no]

    st.markdown("### Acilis ozeti: proje + lider ilerleme")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proje gorev", len(tasks_df))
    c2.metric("Proje tamamlanma", f"%{completion_percent(tasks_df)}")
    c3.metric("Kendi gorevim", len(my_tasks))
    c4.metric("Kendi ilerleme", f"%{completion_percent(my_tasks)}")

    roles_df = fetch_df(conn, "SELECT student_no, role, responsibility FROM member_roles WHERE project_name = ?", (project_name,))
    team_view = team_df.merge(roles_df, how="left", on="student_no")
    st.dataframe(team_view[["student_no", "student_name", "role", "responsibility"]], use_container_width=True, hide_index=True)

    member_options = {f"{r['student_name']} ({r['student_no']})": str(r["student_no"]) for _, r in team_df.iterrows()}
    with st.form(f"role_form_{project_name}"):
        member_label = st.selectbox("Uye sec", list(member_options.keys()))
        role = st.selectbox("Rol", ROLE_OPTIONS)
        responsibility = st.text_input("Kisisel gorev tanimi")
        role_submit = st.form_submit_button("Rolu kaydet")
    if role_submit:
        upsert_role(conn, project_name, member_options[member_label], role, responsibility)
        st.success("Rol guncellendi.")
        st.rerun()

    existing_tasks = fetch_tasks(conn, project_name)
    dependency_map = {"Yok": None}
    for _, row in existing_tasks.iterrows():
        dependency_map[f"#{int(row['id'])} - {row['title']}"] = int(row["id"])
    milestone_map = {label: key for key, label in MILESTONES}

    with st.form(f"new_task_form_{project_name}"):
        milestone_label = st.selectbox("Milestone", list(milestone_map.keys()))
        title = st.text_input("Gorev basligi")
        description = st.text_area("Aciklama")
        assignee = st.selectbox("Sorumlu", list(member_options.keys()))
        priority = st.selectbox("Oncelik", PRIORITY_OPTIONS, index=1)
        no_deadline = st.checkbox("Deadline yok", value=False)
        deadline_date = st.date_input("Deadline", value=date.today() + timedelta(days=7))
        dependency = st.selectbox("Bagimlilik", list(dependency_map.keys()))
        evidence_required = st.text_input("Istenen kanit", value="Repo linki veya rapor")
        task_submit = st.form_submit_button("Gorevi kaydet")
    if task_submit:
        if not title.strip():
            st.error("Gorev basligi gerekli.")
        else:
            create_task(
                conn=conn,
                project_name=project_name,
                milestone_key=milestone_map[milestone_label],
                title=title,
                description=description,
                assignee_student_no=member_options[assignee],
                priority=priority,
                deadline=None if no_deadline else deadline_date.isoformat(),
                dependency_task_id=dependency_map[dependency],
                evidence_required=evidence_required,
                created_by=leader_no,
            )
            st.success("Gorev eklendi.")
            st.rerun()

    tasks_df = fetch_tasks(conn, project_name)
    if tasks_df.empty:
        st.info("Bu proje icin gorev yok.")
        return

    st.markdown("### Gorev takibi")
    render_milestone_progress(tasks_df)
    options = {f"#{int(r['id'])} [{status_tr(r['status'])}] {r['title']}": int(r["id"]) for _, r in tasks_df.iterrows()}
    selected_task = st.selectbox("Duzenlenecek gorev", list(options.keys()))
    task_id = options[selected_task]
    row = tasks_df[tasks_df["id"] == task_id].iloc[0]
    status_options = allowed_status_options(str(row["status"]))
    status_idx = status_options.index(row["status"]) if row["status"] in status_options else 0
    with st.form(f"task_update_form_{project_name}"):
        status = st.selectbox("Durum", status_options, index=status_idx, format_func=status_tr)
        evidence_link = st.text_input("Kanit linki", value=row["evidence_link"] or "")
        upd_submit = st.form_submit_button("Guncelle")
    ldr_evidence_upload = st.file_uploader(
        "Kanit dosyasi yukle (resim, PDF vb.)",
        type=["png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "zip"],
        key=f"ldr_evidence_file_{project_name}",
    )
    existing_ldr_file = str(row.get("evidence_file", "") or "")
    if existing_ldr_file:
        st.caption("Mevcut kanit dosyasi:")
        render_evidence_file(existing_ldr_file)
    if upd_submit:
        file_path = ""
        if ldr_evidence_upload is not None:
            file_path = save_uploaded_evidence(ldr_evidence_upload, task_id)
        ok, msg = update_task(conn, task_id, status, evidence_link, skip_milestone_check=True, evidence_file=file_path)
        if ok:
            st.success("Gorev guncellendi.")
            st.rerun()
        else:
            st.error(msg)

    st.markdown("### Gorev yorumlari")
    with st.expander(f"Yorumlar: #{task_id} - {row['title']}"):
        render_task_comments(
            conn, task_id, project_name,
            current_user_id=leader_no,
            current_user_role="leader",
            form_key_suffix=f"ldr_{project_name}",
        )

    table = tasks_df.copy()
    table["Milestone"] = table["milestone_key"].map(MILESTONE_LABELS)
    table["status"] = table["status"].map(status_tr)
    table["deadline"] = table["deadline"].replace("", "-").fillna("-")
    st.dataframe(
        table[["id", "Milestone", "title", "assignee_student_no", "status", "priority", "deadline", "evidence_link"]],
        use_container_width=True,
        hide_index=True,
    )

    # ── Grup üyesi şifre sıfırlama (sadece lider yetkisi) ─────────────────
    st.markdown("### 🔑 Grup üyesi şifre sıfırlama")
    st.caption(
        "Grubunuzdaki bir üyenin şifresi unutulduğunda varsayılan şifreye (12345) sıfırlayabilirsiniz. "
        "Üye ilk girişinde şifresini değiştirmek zorunda kalacaktır."
    )
    # Liderin kendi hesabı hariç sadece gruptaki diğer üyeler listelensin
    other_members = team_df[team_df["student_no"].astype(str) != str(leader_no)].copy()
    if other_members.empty:
        st.info("Grubunuzda şifre sıfırlanabilecek başka üye bulunmuyor.")
    else:
        reset_options = {
            f"{r['student_name']} ({r['student_no']})": str(r["student_no"])
            for _, r in other_members.sort_values("student_name").iterrows()
        }
        with st.form(f"leader_pwd_reset_form_{project_name}"):
            selected_member_label = st.selectbox(
                "Şifresi sıfırlanacak üye",
                list(reset_options.keys()),
                key=f"ldr_pwd_reset_pick_{project_name}",
            )
            confirm_reset = st.checkbox(
                "Bu üyenin şifresinin 12345'e sıfırlanacağını onaylıyorum",
                key=f"ldr_pwd_reset_confirm_{project_name}",
            )
            reset_submit = st.form_submit_button("Şifreyi sıfırla", disabled=not confirm_reset)

        if reset_submit:
            target_no = reset_options[selected_member_label]
            # Güvenlik: atanan öğrencinin gerçekten bu projeye ait olduğunu teyit et
            is_member = not team_df[team_df["student_no"].astype(str) == target_no].empty
            if not is_member:
                st.error("Bu öğrenci grubunuzda kayıtlı değil. İşlem reddedildi.")
            else:
                ok = reset_password_to_default(conn, target_no, "student")
                if ok:
                    st.success(
                        f"{selected_member_label} şifresi 12345 olarak sıfırlandı. "
                        "Üye bir sonraki girişinde yeni şifre belirlemek zorunda kalacak."
                    )
                else:
                    st.error("Kullanıcı bulunamadı veya sıfırlama başarısız oldu.")


def render_student_panel(
    conn: sqlite3.Connection,
    roster: pd.DataFrame,
    fixed_student_no: Optional[str] = None,
    fixed_project_name: Optional[str] = None,
    is_leader: bool = False,
) -> None:
    st.subheader("Ogrenci paneli")
    if roster.empty:
        st.warning("Secilen danismana ait ogrenci bulunamadi.")
        return

    roster_sorted = roster.sort_values(["project_name", "row_no", "student_name"]).reset_index(drop=True)
    if fixed_student_no:
        scoped = roster_sorted[roster_sorted["student_no"] == fixed_student_no]
        if fixed_project_name:
            scoped = scoped[scoped["project_name"] == fixed_project_name]
        if scoped.empty:
            st.error("Ogrenci kaydi bulunamadi.")
            return
        row = scoped.iloc[0]
    else:
        student_map = {
            f"{r['student_name']} ({r['student_no']}) - {r['project_name']}": idx
            for idx, r in roster_sorted.iterrows()
        }
        selected = st.selectbox("Ogrenci", list(student_map.keys()))
        row = roster_sorted.iloc[student_map[selected]]
    student_no = str(row["student_no"])
    student_name = str(row["student_name"])
    project_name = str(row["project_name"])

    project_members = roster_sorted[roster_sorted["project_name"] == project_name].sort_values("row_no")

    tasks_df = fetch_tasks(conn, project_name)
    my_tasks = tasks_df[tasks_df["assignee_student_no"] == student_no]

    st.markdown("### Grup uyeleri ve roller")
    roles_df = fetch_df(
        conn,
        "SELECT student_no, role, responsibility FROM member_roles WHERE project_name = ?",
        (project_name,),
    )
    group_view = project_members.merge(roles_df, how="left", on="student_no")
    group_view["role"] = group_view["role"].fillna("Atanmadi")
    group_view["responsibility"] = group_view["responsibility"].fillna("-")
    st.dataframe(
        group_view[["student_no", "student_name", "role", "responsibility"]],
        use_container_width=True,
        hide_index=True,
    )

    st.markdown("### Acilis ozeti: proje + bireysel ilerleme")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proje gorev", len(tasks_df))
    c2.metric("Proje tamamlanma", f"%{completion_percent(tasks_df)}")
    c3.metric("Kendi gorevim", len(my_tasks))
    c4.metric("Kendi ilerleme", f"%{completion_percent(my_tasks)}")
    render_milestone_progress(tasks_df)

    role_row = conn.execute(
        "SELECT role, responsibility FROM member_roles WHERE project_name = ? AND student_no = ?",
        (project_name, student_no),
    ).fetchone()
    if role_row:
        st.caption(f"Rol: {role_row['role']} | Gorev: {role_row['responsibility']}")
    else:
        st.caption("Bu ogrenciye henuz rol verilmedi.")

    if my_tasks.empty:
        st.info("Size atanmis gorev yok.")
    else:
        ordered = my_tasks.copy()
        ordered["ms_order"] = ordered["milestone_key"].map(MILESTONE_ORDER).fillna(999).astype(int)
        ordered = ordered.sort_values(["ms_order", "id"])

        st.markdown("### Kisisel milestone gorev siraniz")
        personal_table = ordered.copy()
        personal_table["Milestone"] = personal_table["milestone_key"].map(MILESTONE_LABELS)
        personal_table["status"] = personal_table["status"].map(status_tr)
        st.dataframe(
            personal_table[["id", "Milestone", "title", "status", "evidence_link"]],
            use_container_width=True,
            hide_index=True,
        )

        task_row = current_student_task(my_tasks)
        if task_row is None:
            st.success("Tum milestone gorevlerini tamamladiniz.")
        else:
            current_milestone = MILESTONE_LABELS.get(str(task_row["milestone_key"]), str(task_row["milestone_key"]))
            st.warning(f"Siradaki zorunlu gorev: {current_milestone}")
            status_options = allowed_status_options(str(task_row["status"]))
            status_idx = status_options.index(task_row["status"]) if task_row["status"] in status_options else 0

            with st.form(f"student_task_form_{student_no}"):
                st.text_input("Aktif gorev", value=f"#{int(task_row['id'])} - {task_row['title']}", disabled=True)
                st.caption("Not: Onceki milestone tamamlanmadan sonraki milestone gorevine gecilemez.")
                status = st.selectbox("Durum", status_options, index=status_idx, format_func=status_tr)
                evidence = st.text_input("Kanit linki", value=task_row["evidence_link"] or "")
                save_task = st.form_submit_button("Gorevi kaydet")
            stu_evidence_upload = st.file_uploader(
                "Kanit dosyasi yukle (resim, PDF vb.)",
                type=["png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "zip"],
                key=f"stu_evidence_file_{student_no}",
            )
            existing_stu_file = str(task_row.get("evidence_file", "") or "")
            if existing_stu_file:
                st.caption("Mevcut kanit dosyasi:")
                render_evidence_file(existing_stu_file)
            if save_task:
                file_path = ""
                if stu_evidence_upload is not None:
                    file_path = save_uploaded_evidence(stu_evidence_upload, int(task_row["id"]))
                ok, msg = update_task(conn, int(task_row["id"]), status, evidence, evidence_file=file_path)
                if ok:
                    st.success("Goreviniz guncellendi.")
                    st.rerun()
                else:
                    st.error(msg)

            active_task_id = int(task_row["id"])
            st.markdown("#### Gorev yorumlari")
            author_role = "leader" if is_leader else "student"
            render_task_comments(
                conn, active_task_id, project_name,
                current_user_id=student_no,
                current_user_role=author_role,
                form_key_suffix=f"stu_{student_no}",
            )

    monday = date.today() - timedelta(days=date.today().weekday())
    current_task = current_student_task(my_tasks)
    st.markdown("### Haftalik ilerleme girisi")
    if current_task is None:
        st.info("Haftalik giris icin acik milestone gorevi yok.")
    else:
        current_task_id = int(current_task["id"])
        current_task_label = f"#{current_task_id} - {current_task['title']}"
        with st.form(f"weekly_form_{student_no}"):
            st.text_input("Ilgili gorev", value=current_task_label, disabled=True)
            week_start = st.date_input("Hafta baslangici", value=monday)
            completed = st.text_area("Yapilanlar")
            blockers = st.text_area("Engeller")
            next_step = st.text_area("Sonraki adim")
            evidence_link = st.text_input("Kanit link")
            weekly_submit = st.form_submit_button("Haftalik girisi kaydet")
        if weekly_submit:
            if not completed.strip() and not next_step.strip():
                st.error("Yapilanlar veya sonraki adim alanindan en az biri dolu olmali.")
            else:
                add_weekly_update(
                    conn=conn,
                    project_name=project_name,
                    student_no=student_no,
                    task_id=current_task_id,
                    week_start=week_start.isoformat(),
                    completed=completed,
                    blockers=blockers,
                    next_step=next_step,
                    evidence_link=evidence_link,
                )
                st.success("Haftalik giris kaydedildi.")
                st.rerun()

    st.markdown("### Gecmis haftalik girislerim")
    my_weekly_df = fetch_weekly_updates_for_project(conn, project_name, student_no)
    if my_weekly_df.empty:
        st.info("Henuz haftalik giris yapilmamis.")
    else:
        st.dataframe(
            my_weekly_df[["week_start", "completed", "blockers", "next_step", "evidence_link", "created_at"]].rename(columns={
                "week_start": "Hafta",
                "completed": "Yapilanlar",
                "blockers": "Engeller",
                "next_step": "Sonraki Adim",
                "evidence_link": "Kanit",
                "created_at": "Tarih",
            }),
            use_container_width=True,
            hide_index=True,
        )

    st.markdown("### Danisman geri bildirimleri")
    feedbacks_df = fetch_feedbacks(conn, project_name)
    if feedbacks_df.empty:
        st.info("Henuz danisman geri bildirimi yok.")
    else:
        for _, fb in feedbacks_df.iterrows():
            is_revision = bool(int(fb["revision_required"])) if fb["revision_required"] else False
            icon = "\U0001f534" if is_revision else "\U0001f4ac"
            with st.expander(f"{icon} {str(fb['created_at'])[:10]} - {fb['advisor_name']}"):
                st.write(fb["feedback"])
                if fb["action_item"]:
                    st.caption(f"Aksiyon: {fb['action_item']}")
                if is_revision:
                    st.error("Revizyon gerekli!")

    st.markdown("### Diger gruplarla karsilastirma")
    scope = st.radio(
        "Karsilastirma kapsami",
        ["Danisman gruplari", "Tum gruplar"],
        horizontal=True,
    )
    compare_roster = roster if scope == "Danisman gruplari" else get_roster_from_db(conn)
    compare_df = build_project_metrics(conn, compare_roster, sorted(compare_roster["project_name"].unique()))
    if not compare_df.empty:
        compare_df["Sira"] = compare_df["Tamamlanma %"].rank(method="dense", ascending=False).astype(int)
        compare_df = compare_df.sort_values(["Sira", "Geciken Gorev"], ascending=[True, True])
        st.dataframe(compare_df, use_container_width=True, hide_index=True)
        mine = compare_df[compare_df["Proje"] == project_name]
        if not mine.empty:
            st.info(f"{student_name} grubunuz {len(compare_df)} grup icinde {int(mine.iloc[0]['Sira'])}. sirada.")


def clear_auth_session() -> None:
    for key in ["auth_user"]:
        if key in st.session_state:
            del st.session_state[key]


def render_login_form(conn: sqlite3.Connection) -> Optional[dict]:
    st.subheader("Giris")
    st.caption("Ilk sifre tum kullanicilar icin 12345'tir. Ilk giriste sifre degistirme zorunludur.")
    role_label = st.selectbox("Rol", ["Ogrenci", "Danisman"], key="login_role")
    role = "student" if role_label == "Ogrenci" else "advisor"

    if role == "student":
        user_id = st.text_input("Ogrenci No", key="login_student_no")
    else:
        advisor_df = fetch_df(
            conn,
            """
            SELECT user_id, display_name
            FROM auth_users
            WHERE role = 'advisor' AND is_active = 1
            ORDER BY display_name
            """,
        )
        if advisor_df.empty:
            st.error("Aktif danisman kullanicisi bulunamadi.")
            return None
        advisor_options = {
            str(row["display_name"]): str(row["user_id"])
            for _, row in advisor_df.iterrows()
        }
        selected_label = st.selectbox("Danisman", list(advisor_options.keys()), key="login_advisor_select")
        user_id = advisor_options[selected_label]

    password = st.text_input("Sifre", type="password", key="login_password")
    login_clicked = st.button("Giris yap", type="primary")

    if login_clicked:
        auth = authenticate_user(conn, user_id=user_id.strip(), role=role, password=password)
        if not auth:
            st.error("Giris bilgileri gecersiz.")
            return None
        st.session_state["auth_user"] = auth
        st.rerun()
    return None


def enforce_password_change(conn: sqlite3.Connection, auth_user: dict) -> bool:
    if not auth_user.get("force_password_change", False):
        return False

    st.warning("Ilk giriste sifrenizi degistirmeniz gerekiyor.")
    with st.form("change_password_form"):
        new_password = st.text_input("Yeni sifre", type="password")
        confirm_password = st.text_input("Yeni sifre (tekrar)", type="password")
        submitted = st.form_submit_button("Sifreyi guncelle")

    if submitted:
        if len(new_password) < MIN_PASSWORD_LEN:
            st.error(f"Sifre en az {MIN_PASSWORD_LEN} karakter olmali.")
        elif new_password != confirm_password:
            st.error("Sifreler eslesmiyor.")
        elif new_password == DEFAULT_PASSWORD:
            st.error("Varsayilan sifreyi kullanamazsiniz.")
        else:
            update_password(conn, auth_user["user_id"], auth_user["role"], new_password)
            auth_user["force_password_change"] = False
            st.session_state["auth_user"] = auth_user
            st.success("Sifre guncellendi.")
            st.rerun()
    return True


def main() -> None:
    st.set_page_config(
        page_title="Bitirme Proje Takip | OSTİM Teknik Üniversitesi",
        page_icon="🎓",
        layout="wide",
    )

    # ── Sabit üst logo bandı ────────────────────────────────────────────────
    st.markdown(
        """
        <style>
        /* Üst logo şeridi */
        .otu-header {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 999999;
            background: linear-gradient(90deg, #0a2342 0%, #1a3a6b 60%, #0f4c81 100%);
            padding: 0.55rem 1.5rem;
            display: flex;
            align-items: center;
            gap: 0.75rem;
            box-shadow: 0 2px 8px rgba(0,0,0,0.35);
        }
        .otu-header .otu-icon {
            font-size: 1.55rem;
            line-height: 1;
        }
        .otu-header .otu-text-block {
            display: flex;
            flex-direction: column;
            line-height: 1.2;
        }
        .otu-header .otu-uni {
            font-size: 0.82rem;
            font-weight: 700;
            color: #ffd700;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }
        .otu-header .otu-dept {
            font-size: 0.72rem;
            font-weight: 500;
            color: #cce0ff;
            letter-spacing: 0.02em;
        }
        .otu-header .otu-divider {
            margin-left: auto;
            font-size: 0.70rem;
            color: #7ab3e0;
            font-style: italic;
        }
        /* Streamlit içeriğini logo bandının altına it */
        [data-testid="stAppViewContainer"] > section:first-child {
            padding-top: 3.4rem !important;
        }
        [data-testid="stHeader"] {
            top: 2.8rem !important;
        }
        </style>
        <div class="otu-header">
            <span class="otu-icon">🎓</span>
            <div class="otu-text-block">
                <span class="otu-uni">OSTİM Teknik Üniversitesi</span>
                <span class="otu-dept">Yazılım Mühendisliği Bölümü</span>
            </div>
            <span class="otu-divider">Bitirme Proje Takip Sistemi</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.title("🗂️ Bitirme Proje Takip Uygulaması")

    db_path = "project_tracker.db"
    with st.sidebar:
        st.caption(f"Veritabani: {db_path}")

    conn = get_conn(db_path)

    if student_count(conn) == 0:
        st.error("SQLite ogrenci kaydi yok. Uygulama yalnizca SQLite verisi ile calisir.")
        return

    all_roster = get_roster_from_db(conn)
    if all_roster.empty:
        st.error("SQLite ogrenci tablosu bos.")
        return
    bootstrap_defaults(conn, all_roster)
    initialize_all_projects(conn, all_roster)
    sync_auth_users(conn)

    auth_user = st.session_state.get("auth_user")
    if not auth_user:
        render_login_form(conn)
        return

    if enforce_password_change(conn, auth_user):
        with st.sidebar:
            st.caption(f"Giris yapan: {auth_user['display_name']}")
            if st.button("Cikis yap"):
                clear_auth_session()
                st.rerun()
        return

    if auth_user["role"] == "advisor":
        selected_advisor = auth_user["user_id"]
        admin_mode = is_admin_advisor(selected_advisor)
        roster = get_roster_from_db(conn, selected_advisor)
        with st.sidebar:
            st.caption(f"Giris yapan danisman: {selected_advisor}")
            st.caption(f"Yetki: {'Admin' if admin_mode else 'Danisman'}")
            st.caption(f"Ogrenci: {len(roster)}")
            st.caption(f"Proje: {roster['project_name'].nunique() if not roster.empty else 0}")
            if admin_mode:
                with st.expander("\u26a0\ufe0f Veritabani sifirlama (tehlikeli)"):
                    st.warning("Bu islem tum verileri silecektir!")
                    confirm_reset = st.checkbox("Veritabanini silmek istedigimden eminim", key="reset_confirm")
                    reset = st.button("Veritabanini sifirla", disabled=not confirm_reset)
            else:
                reset = False
            if st.button("Cikis yap"):
                clear_auth_session()
                st.rerun()
        if reset:
            db_file = Path(db_path)
            backup_name = f"project_tracker.{datetime.now().strftime('%Y%m%d_%H%M%S')}.backup.db"
            if db_file.exists():
                shutil.copy2(db_file, db_file.parent / backup_name)
                db_file.unlink()
            st.cache_resource.clear()
            st.cache_data.clear()
            clear_auth_session()
            st.success(f"Veritabani sifirlandi. Yedek: {backup_name}")
            st.rerun()
        render_advisor_panel(conn, selected_advisor, roster)
        return

    student_no = auth_user["user_id"]
    memberships = get_student_memberships(conn, student_no)
    if memberships.empty:
        st.error("Bu ogrenci numarasi icin kayit bulunamadi.")
        with st.sidebar:
            if st.button("Cikis yap"):
                clear_auth_session()
                st.rerun()
        return

    project_labels = [
        f"{row['project_name']} (danisman: {row['advisor_name']})"
        for _, row in memberships.iterrows()
    ]
    selected_idx = 0
    selected_project_label = project_labels[0]
    if len(project_labels) > 1:
        selected_project_label = st.selectbox("Projelerim", project_labels)
        selected_idx = project_labels.index(selected_project_label)
    selected_membership = memberships.iloc[selected_idx]
    selected_project = str(selected_membership["project_name"])
    selected_advisor = str(selected_membership["advisor_name"])
    advisor_roster = get_roster_from_db(conn, selected_advisor)
    project_roster = advisor_roster[advisor_roster["project_name"] == selected_project].copy()

    is_leader = get_leader(conn, selected_project) == student_no
    with st.sidebar:
        st.caption(f"Giris yapan ogrenci: {auth_user['display_name']} ({student_no})")
        st.caption(f"Secili proje: {selected_project}")
        st.caption(f"Danisman: {selected_advisor}")
        if st.button("Cikis yap"):
            clear_auth_session()
            st.rerun()

    if is_leader:
        mode = st.radio("Gorunum", ["Ogrenci", "Grup Yoneticisi"], horizontal=True)
        if mode == "Grup Yoneticisi":
            render_leader_panel(
                conn,
                project_roster,
                fixed_project_name=selected_project,
                fixed_leader_no=student_no,
            )
        else:
            render_student_panel(
                conn,
                advisor_roster,
                fixed_student_no=student_no,
                fixed_project_name=selected_project,
                is_leader=True,
            )
    else:
        render_student_panel(
            conn,
            advisor_roster,
            fixed_student_no=student_no,
            fixed_project_name=selected_project,
        )


if __name__ == "__main__":
    main()


