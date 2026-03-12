"""
models.py
All database read/write business logic:
- Roster (students)
- Auth users
- Leaders & member roles
- Tasks
- Weekly updates
- Advisor feedback
- Task comments
- CSV import helpers
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import Dict, Iterable, Optional

import pandas as pd
import streamlit as st

from constants import (
    DEFAULT_ADVISOR,
    DEFAULT_PASSWORD,
    MILESTONE_LABELS,
    MILESTONE_ORDER,
    MILESTONES,
    STATUS_OPTIONS,
    STATUS_TRANSITIONS,
)
from db import db_lock, fetch_df
from utils import (
    allowed_status_options,
    hash_password,
    normalize_header,
    now_ts,
    status_tr,
    verify_password,
)


# ═══════════════════════════════════════════════════════════════
# CSV Loading
# ═══════════════════════════════════════════════════════════════

def _parse_roster_df(df: pd.DataFrame) -> pd.DataFrame:
    """Shared column mapping & normalisation for any roster DataFrame."""
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
    df = _parse_roster_df(df)
    df.attrs["source_encoding"] = used_encoding
    return df


def load_roster_from_upload(uploaded_file) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp1254", "iso-8859-9", "latin1"]
    raw_bytes = uploaded_file.getvalue()
    df = None
    for enc in encodings:
        try:
            df = pd.read_csv(io.BytesIO(raw_bytes), sep=";", encoding=enc, dtype=str).fillna("")
            break
        except Exception:
            continue
    if df is None:
        raise ValueError("CSV okunamadi.")
    return _parse_roster_df(df)


# ═══════════════════════════════════════════════════════════════
# Students / Roster
# ═══════════════════════════════════════════════════════════════

def student_count(conn) -> int:
    row = conn.execute("SELECT COUNT(*) AS cnt FROM students").fetchone()
    return int(row["cnt"])


def upsert_students(conn, roster: pd.DataFrame) -> int:
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
    with db_lock():
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
    sync_projects_catalog(conn)
    return len(records)


def sync_projects_catalog(conn) -> int:
    """Keep the project catalog aligned with the current students table."""
    ts = now_ts()
    projects = fetch_df(
        conn,
        """
        SELECT project_name, MIN(advisor_name) AS advisor_name
        FROM students
        WHERE project_name <> ''
        GROUP BY project_name
        """,
    )
    rows = [
        (str(row["project_name"]).strip(), str(row["advisor_name"]).strip() or DEFAULT_ADVISOR, ts, ts)
        for _, row in projects.iterrows()
    ]
    with db_lock():
        if rows:
            conn.executemany(
                """
                INSERT INTO projects(project_name, advisor_name, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(project_name) DO UPDATE SET
                    advisor_name = excluded.advisor_name,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            placeholders = ",".join(["?"] * len(rows))
            conn.execute(f"DELETE FROM projects WHERE project_name NOT IN ({placeholders})", [r[0] for r in rows])
        else:
            conn.execute("DELETE FROM projects")
        conn.commit()
    return len(rows)


def upsert_students_for_advisor(conn, advisor_name: str, roster: pd.DataFrame) -> int:
    """Safely replace only the current advisor's roster from an uploaded CSV."""
    advisor = str(advisor_name).strip()
    scoped = roster.copy()
    scoped["advisor_name"] = scoped["advisor_name"].astype(str).str.strip()
    mismatched = scoped[(scoped["advisor_name"] != "") & (scoped["advisor_name"] != advisor)]
    if not mismatched.empty:
        found = sorted(mismatched["advisor_name"].unique().tolist())
        raise ValueError(f"CSV sadece '{advisor}' danismaninin kayitlarini icermeli. Bulunan farkli danismanlar: {', '.join(found)}")

    scoped["advisor_name"] = advisor
    ts = now_ts()
    records = [
        (
            str(row["student_no"]).strip(),
            int(row["row_no"]),
            str(row["student_name"]).strip(),
            str(row["project_name"]).strip(),
            advisor,
            str(row["program"]).strip(),
            ts,
            ts,
        )
        for _, row in scoped.iterrows()
    ]
    row_nos = [r[1] for r in records]
    if row_nos:
        placeholders = ",".join(["?"] * len(row_nos))
        conflict_rows = fetch_df(
            conn,
            f"""
            SELECT row_no, advisor_name
            FROM students
            WHERE row_no IN ({placeholders}) AND advisor_name <> ?
            """,
            tuple(row_nos + [advisor]),
        )
        if not conflict_rows.empty:
            collisions = ", ".join(str(int(v)) for v in conflict_rows["row_no"].tolist())
            raise ValueError(f"CSV icindeki satir numaralari baska danisman kayitlariyla cakisiyor: {collisions}")

    with db_lock():
        if records:
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
            placeholders = ",".join(["?"] * len(row_nos))
            conn.execute(
                f"DELETE FROM students WHERE advisor_name = ? AND row_no NOT IN ({placeholders})",
                [advisor, *row_nos],
            )
        else:
            conn.execute("DELETE FROM students WHERE advisor_name = ?", (advisor,))
        conn.commit()
    sync_projects_catalog(conn)
    return len(records)


def get_roster_from_db(conn, advisor_name: Optional[str] = None) -> pd.DataFrame:
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


def list_advisors(conn) -> list[str]:
    df = fetch_df(conn, "SELECT DISTINCT advisor_name FROM students WHERE advisor_name <> '' ORDER BY advisor_name")
    if df.empty:
        return []
    return df["advisor_name"].astype(str).tolist()


def get_student_memberships(conn, student_no: str) -> pd.DataFrame:
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


def add_single_student(
    conn,
    student_no: str,
    student_name: str,
    project_name: str,
    advisor_name: str,
    program: str,
) -> int:
    ts = now_ts()
    max_row = conn.execute("SELECT COALESCE(MAX(row_no), 0) AS mx FROM students").fetchone()["mx"]
    new_row_no = int(max_row) + 1
    with db_lock():
        conn.execute(
            """
            INSERT INTO students(row_no, student_no, student_name, project_name, advisor_name, program, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                new_row_no,
                student_no.strip(),
                student_name.strip(),
                project_name.strip(),
                advisor_name.strip() or DEFAULT_ADVISOR,
                program.strip(),
                ts,
                ts,
            ),
        )
        conn.commit()
    sync_projects_catalog(conn)
    return new_row_no


# ═══════════════════════════════════════════════════════════════
# Auth Users
# ═══════════════════════════════════════════════════════════════

def sync_auth_users(conn) -> None:
    """Create auth_users records for all students/advisors in the roster.
    Call this only when the roster changes, not on every rerun.
    """
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
        sno = str(row["student_no"]).strip()
        display_name = str(row["student_name"]).strip() or sno
        if sno not in existing_student_ids:
            student_insert_records.append((sno, "student", display_name, hash_password(DEFAULT_PASSWORD), ts, ts))
        student_update_records.append((display_name, ts, sno, "student"))

    with db_lock():
        if student_insert_records:
            conn.executemany(
                """
                INSERT INTO auth_users(user_id, role, display_name, password_hash, force_password_change, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 1, ?, ?)
                """,
                student_insert_records,
            )
        if student_update_records:
            conn.executemany(
                "UPDATE auth_users SET display_name = ?, is_active = 1, updated_at = ? WHERE user_id = ? AND role = ?",
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
            aname = str(row["advisor_name"]).strip()
            if aname not in existing_advisor_ids:
                advisor_insert_records.append((aname, "advisor", aname, hash_password(DEFAULT_PASSWORD), ts, ts))
            advisor_update_records.append((aname, ts, aname, "advisor"))

        if advisor_insert_records:
            conn.executemany(
                """
                INSERT INTO auth_users(user_id, role, display_name, password_hash, force_password_change, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, 1, 1, ?, ?)
                """,
                advisor_insert_records,
            )
        if advisor_update_records:
            conn.executemany(
                "UPDATE auth_users SET display_name = ?, is_active = 1, updated_at = ? WHERE user_id = ? AND role = ?",
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


def authenticate_user(conn, user_id: str, role: str, password: str) -> Optional[dict]:
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


def update_password(conn, user_id: str, role: str, new_password: str) -> None:
    if new_password == DEFAULT_PASSWORD:
        raise ValueError("Varsayilan sifreyi kullanamazsiniz.")
    with db_lock():
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, force_password_change = 0, updated_at = ? WHERE user_id = ? AND role = ?",
            (hash_password(new_password), now_ts(), user_id, role),
        )
        conn.commit()


def reset_password_to_default(conn, user_id: str, role: str) -> bool:
    row = conn.execute(
        "SELECT user_id FROM auth_users WHERE user_id = ? AND role = ?", (user_id, role)
    ).fetchone()
    if not row:
        return False
    with db_lock():
        conn.execute(
            "UPDATE auth_users SET password_hash = ?, force_password_change = 1, updated_at = ? WHERE user_id = ? AND role = ?",
            (hash_password(DEFAULT_PASSWORD), now_ts(), user_id, role),
        )
        conn.commit()
    return True


# ═══════════════════════════════════════════════════════════════
# Leaders & Member Roles
# ═══════════════════════════════════════════════════════════════

def clear_runtime_data(conn) -> None:
    """Delete project activity records while keeping students and auth users."""
    with db_lock():
        conn.execute("DELETE FROM task_comments")
        conn.execute("DELETE FROM weekly_updates")
        conn.execute("DELETE FROM advisor_feedback")
        conn.execute("DELETE FROM tasks")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name IN ('tasks', 'weekly_updates', 'advisor_feedback', 'task_comments')"
        )
        conn.commit()


def rename_project(conn, advisor_name: str, old_project_name: str, new_project_name: str) -> tuple[bool, str]:
    old_name = str(old_project_name).strip()
    new_name = str(new_project_name).strip()
    advisor = str(advisor_name).strip()

    if not old_name or not new_name:
        return False, "Proje adi bos olamaz."
    if old_name == new_name:
        return False, "Yeni proje adi mevcut adla ayni."

    owned_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM students WHERE advisor_name = ? AND project_name = ?",
        (advisor, old_name),
    ).fetchone()["cnt"]
    if int(owned_count) == 0:
        return False, "Bu proje bu danismana ait degil."

    foreign_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM students WHERE advisor_name <> ? AND project_name = ?",
        (advisor, old_name),
    ).fetchone()["cnt"]
    if int(foreign_count) > 0:
        return False, "Bu proje adi baska danisman kayitlarinda da kullaniliyor."

    target_exists = conn.execute(
        "SELECT COUNT(*) AS cnt FROM students WHERE project_name = ?",
        (new_name,),
    ).fetchone()["cnt"]
    if int(target_exists) > 0:
        return False, "Bu proje adi zaten kullaniliyor."

    ts = now_ts()
    with db_lock():
        conn.execute(
            """
            INSERT INTO projects(project_name, advisor_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(project_name) DO UPDATE SET
                advisor_name = excluded.advisor_name,
                updated_at = excluded.updated_at
            """,
            (new_name, advisor, ts, ts),
        )
        conn.execute(
            "UPDATE students SET project_name = ?, updated_at = ? WHERE advisor_name = ? AND project_name = ?",
            (new_name, ts, advisor, old_name),
        )
        conn.execute("UPDATE leaders SET project_name = ?, assigned_at = ? WHERE project_name = ?", (new_name, ts, old_name))
        conn.execute("UPDATE member_roles SET project_name = ?, updated_at = ? WHERE project_name = ?", (new_name, ts, old_name))
        conn.execute("UPDATE tasks SET project_name = ?, updated_at = ? WHERE project_name = ?", (new_name, ts, old_name))
        conn.execute("UPDATE weekly_updates SET project_name = ? WHERE project_name = ?", (new_name, old_name))
        conn.execute("UPDATE advisor_feedback SET project_name = ? WHERE project_name = ?", (new_name, old_name))
        conn.execute("UPDATE task_comments SET project_name = ? WHERE project_name = ?", (new_name, old_name))
        conn.execute("DELETE FROM projects WHERE project_name = ?", (old_name,))
        conn.commit()
    sync_projects_catalog(conn)
    return True, "Proje adi guncellendi."


def _project_exists(conn, project_name: str) -> bool:
    row = conn.execute("SELECT 1 FROM projects WHERE project_name = ?", (project_name,)).fetchone()
    return row is not None


def get_leader(conn, project_name: str) -> Optional[str]:
    row = conn.execute("SELECT student_no FROM leaders WHERE project_name = ?", (project_name,)).fetchone()
    return row["student_no"] if row else None


def set_leader(conn, project_name: str, student_no: str, assigned_by: str) -> None:
    if not _project_exists(conn, project_name):
        raise ValueError("Proje bulunamadi.")
    with db_lock():
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


def upsert_role(conn, project_name: str, student_no: str, role: str, responsibility: str) -> None:
    if not _project_exists(conn, project_name):
        raise ValueError("Proje bulunamadi.")
    with db_lock():
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


def bootstrap_defaults(conn, roster: pd.DataFrame) -> None:
    first_students = roster.sort_values(["project_name", "row_no"]).groupby("project_name", as_index=False).first()
    for _, row in first_students.iterrows():
        project_name = str(row["project_name"])
        student_no = str(row["student_no"])
        advisor_name = str(row["advisor_name"]).strip() or DEFAULT_ADVISOR
        if not get_leader(conn, project_name):
            set_leader(conn, project_name, student_no, advisor_name)
            upsert_role(conn, project_name, student_no, "Lider", "Varsayilan lider (projedeki ilk ogrenci).")


def ensure_project_member_roles(conn, project_name: str, project_members: pd.DataFrame) -> None:
    if project_members.empty:
        return
    leader_no = get_leader(conn, project_name)
    existing = set(
        fetch_df(conn, "SELECT student_no FROM member_roles WHERE project_name = ?", (project_name,))[
            "student_no"
        ].astype(str).tolist()
    )
    inserts = []
    ts = now_ts()
    seen: set[str] = set()
    for _, member in project_members.sort_values("row_no").iterrows():
        sno = str(member["student_no"])
        if sno in seen or sno in existing:
            continue
        seen.add(sno)
        role = "Lider" if leader_no and sno == leader_no else "Uye"
        responsibility = "Varsayilan lider (projedeki ilk ogrenci)." if role == "Lider" else "Grup uyesi."
        inserts.append((project_name, sno, role, responsibility, ts))
    if inserts:
        with db_lock():
            conn.executemany(
                "INSERT INTO member_roles(project_name, student_no, role, responsibility, updated_at) VALUES (?, ?, ?, ?, ?)",
                inserts,
            )
            conn.commit()


def initialize_all_projects(conn, roster: pd.DataFrame) -> tuple[int, int]:
    if roster.empty:
        return (0, 0)
    created_tasks = 0
    touched_projects = 0
    for project_name, grp in roster.groupby("project_name"):
        project_name = str(project_name)
        members = grp.sort_values("row_no")
        ensure_project_member_roles(conn, project_name, members)
        created_tasks += _ensure_project_sequential_tasks(conn, project_name, members)
        touched_projects += 1
    return touched_projects, created_tasks


def _ensure_project_sequential_tasks(conn, project_name: str, project_members: pd.DataFrame) -> int:
    if project_members.empty:
        return 0
    leader_no = get_leader(conn, project_name)
    creator = leader_no or str(project_members.sort_values("row_no").iloc[0]["student_no"])
    existing_df = fetch_df(
        conn,
        "SELECT milestone_key, assignee_student_no FROM tasks WHERE project_name = ?",
        (project_name,),
    )
    existing_pairs = {
        (str(r["assignee_student_no"]), str(r["milestone_key"]))
        for _, r in existing_df.iterrows()
        if str(r["milestone_key"]) in MILESTONE_LABELS
    }
    ts = now_ts()
    inserts = []
    for _, member in project_members.sort_values("row_no").iterrows():
        sno = str(member["student_no"])
        sname = str(member["student_name"]).strip()
        for milestone_key, milestone_label in MILESTONES:
            if (sno, milestone_key) in existing_pairs:
                continue
            inserts.append((
                project_name, milestone_key,
                f"{milestone_label} - {sname}",
                f"{milestone_label} adimi icin bireysel gorev.",
                sno, "TODO", "Orta", None, None,
                "Repo linki, rapor veya ilgili kanit", "",
                creator, ts, ts,
            ))
            existing_pairs.add((sno, milestone_key))
    if inserts:
        with db_lock():
            conn.executemany(
                """
                INSERT INTO tasks(
                    project_name, milestone_key, title, description, assignee_student_no, status,
                    priority, deadline, dependency_task_id, evidence_required, evidence_link,
                    created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                inserts,
            )
            conn.commit()
    return len(inserts)


# ═══════════════════════════════════════════════════════════════
# Tasks
# ═══════════════════════════════════════════════════════════════

def fetch_tasks(conn, project_name: str) -> pd.DataFrame:
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


def create_task(
    conn,
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
    if not _project_exists(conn, project_name):
        raise ValueError("Proje bulunamadi.")
    ts = now_ts()
    with db_lock():
        conn.execute(
            """
            INSERT INTO tasks(
                project_name, milestone_key, title, description, assignee_student_no, status,
                priority, deadline, dependency_task_id, evidence_required, evidence_link,
                created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 'TODO', ?, ?, ?, ?, '', ?, ?, ?)
            """,
            (
                project_name, milestone_key, title.strip(), description.strip(),
                assignee_student_no, priority, deadline, dependency_task_id,
                evidence_required.strip(), created_by, ts, ts,
            ),
        )
        conn.commit()


def update_task(
    conn,
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
    allowed = STATUS_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        return False, f"Durum gecisi gecersiz: {status_tr(current_status)} -> {status_tr(target_status)}"

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
                    return False, f"Onceki milestone tamamlanmadan bu goreve gecilemez. Tamamlanmamis: {prev_label}"

    with db_lock():
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


def current_student_task(my_tasks: pd.DataFrame) -> Optional[pd.Series]:
    if my_tasks.empty:
        return None
    scoped = my_tasks.copy()
    scoped["ms_order"] = scoped["milestone_key"].map(MILESTONE_ORDER).fillna(999).astype(int)
    scoped = scoped.sort_values(["ms_order", "id"])
    open_tasks = scoped[scoped["status"] != "DONE"]
    return None if open_tasks.empty else open_tasks.iloc[0]


# ═══════════════════════════════════════════════════════════════
# Weekly Updates
# ═══════════════════════════════════════════════════════════════

def add_weekly_update(
    conn,
    project_name: str,
    student_no: str,
    task_id: Optional[int],
    week_start: str,
    completed: str,
    blockers: str,
    next_step: str,
    evidence_link: str,
) -> None:
    if not _project_exists(conn, project_name):
        raise ValueError("Proje bulunamadi.")
    existing = conn.execute(
        """
        SELECT id
        FROM weekly_updates
        WHERE project_name = ? AND student_no = ? AND COALESCE(task_id, -1) = COALESCE(?, -1) AND week_start = ?
        """,
        (project_name, student_no, task_id, week_start),
    ).fetchone()
    with db_lock():
        if existing:
            conn.execute(
                """
                UPDATE weekly_updates
                SET completed = ?, blockers = ?, next_step = ?, evidence_link = ?, created_at = ?
                WHERE id = ?
                """,
                (
                    completed.strip(),
                    blockers.strip(),
                    next_step.strip(),
                    evidence_link.strip(),
                    now_ts(),
                    int(existing["id"]),
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO weekly_updates(
                    project_name, student_no, task_id, week_start, completed,
                    blockers, next_step, evidence_link, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_name, student_no, task_id, week_start,
                    completed.strip(), blockers.strip(), next_step.strip(), evidence_link.strip(), now_ts(),
                ),
            )
        conn.commit()


def fetch_weekly_updates_for_project(
    conn, project_name: str, student_no: Optional[str] = None
) -> pd.DataFrame:
    if student_no:
        return fetch_df(
            conn,
            """
            SELECT id, student_no, task_id, week_start, completed, blockers, next_step, evidence_link, created_at
            FROM weekly_updates
            WHERE project_name = ? AND student_no = ?
            ORDER BY created_at DESC
            """,
            (project_name, student_no),
        )
    return fetch_df(
        conn,
        """
        SELECT id, student_no, task_id, week_start, completed, blockers, next_step, evidence_link, created_at
        FROM weekly_updates
        WHERE project_name = ?
        ORDER BY created_at DESC
        """,
        (project_name,),
    )


# ═══════════════════════════════════════════════════════════════
# Advisor Feedback
# ═══════════════════════════════════════════════════════════════

def add_feedback(
    conn,
    project_name: str,
    advisor_name: str,
    feedback: str,
    action_item: str,
    revision_required: bool,
) -> None:
    if not _project_exists(conn, project_name):
        raise ValueError("Proje bulunamadi.")
    with db_lock():
        conn.execute(
            """
            INSERT INTO advisor_feedback(project_name, advisor_name, feedback, action_item, revision_required, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (project_name, advisor_name, feedback.strip(), action_item.strip(), int(revision_required), now_ts()),
        )
        conn.commit()


def fetch_feedbacks(conn, project_name: str) -> pd.DataFrame:
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


# ═══════════════════════════════════════════════════════════════
# Task Comments
# ═══════════════════════════════════════════════════════════════

def add_task_comment(
    conn,
    task_id: int,
    project_name: str,
    author_id: str,
    author_role: str,
    comment: str,
) -> None:
    if not _project_exists(conn, project_name):
        raise ValueError("Proje bulunamadi.")
    with db_lock():
        conn.execute(
            """
            INSERT INTO task_comments(task_id, project_name, author_id, author_role, comment, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, project_name, author_id, author_role, comment.strip(), now_ts()),
        )
        conn.commit()


def fetch_task_comments(conn, task_id: int) -> pd.DataFrame:
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


# ═══════════════════════════════════════════════════════════════
# Metrics helpers
# ═══════════════════════════════════════════════════════════════

def completion_percent(tasks_df: pd.DataFrame) -> float:
    if tasks_df.empty:
        return 0.0
    done = int((tasks_df["status"] == "DONE").sum())
    return round(done * 100 / len(tasks_df), 1)


def overdue_count(tasks_df: pd.DataFrame) -> int:
    if tasks_df.empty:
        return 0
    deadlines = pd.to_datetime(tasks_df["deadline"], errors="coerce")
    today = pd.Timestamp.today().normalize()
    mask = (deadlines < today) & (tasks_df["status"] != "DONE")
    return int(mask.fillna(False).sum())


def build_project_metrics(conn, roster: pd.DataFrame, projects: Iterable[str]) -> pd.DataFrame:
    from datetime import date, timedelta
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
        rows.append({
            "Proje": project,
            "Ogrenci Sayisi": int(len(group)),
            "Lider": leader_name,
            "Tamamlanma %": completion,
            "Geciken Gorev": overdue,
            "Son 14 Gun Aktivite": int(activity),
            "Risk": risk,
        })
    return pd.DataFrame(rows)


def member_progress(project_members: pd.DataFrame, tasks_df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, member in project_members.sort_values("row_no").iterrows():
        sno = str(member["student_no"])
        scoped = tasks_df[tasks_df["assignee_student_no"] == sno]
        rows.append({
            "Ogrenci No": sno,
            "Ogrenci": member["student_name"],
            "Atanan Gorev": int(len(scoped)),
            "Tamamlanan": int((scoped["status"] == "DONE").sum()),
            "Ilerleme %": completion_percent(scoped),
        })
    return pd.DataFrame(rows)
