"""
components.py
Reusable UI rendering helpers used across multiple panels.
"""
from __future__ import annotations

import uuid
from pathlib import Path

import pandas as pd
import streamlit as st

from constants import MILESTONE_LABELS, MILESTONES, UPLOADS_DIR
from models import (
    add_task_comment,
    completion_percent,
    fetch_task_comments,
)
from utils import status_tr


# ── Evidence files ─────────────────────────────────────────────────────────────

def save_uploaded_evidence(uploaded_file, task_id: int) -> str:
    """Save an uploaded file to UPLOADS_DIR and return the path string."""
    ext = Path(uploaded_file.name).suffix.lower()
    safe_name = f"task_{task_id}_{uuid.uuid4().hex[:8]}{ext}"
    dest = UPLOADS_DIR / safe_name
    dest.write_bytes(uploaded_file.getvalue())
    return str(dest)


def render_evidence_file(evidence_file_path: str) -> None:
    """Display or offer download for a stored evidence file."""
    if not evidence_file_path:
        return
    p = Path(evidence_file_path)
    if not p.exists():
        st.caption(f"Dosya bulunamadi: {p.name}")
        return
    ext = p.suffix.lower()
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"):
        st.image(str(p), caption=p.name,width="stretch")
    elif ext == ".pdf":
        st.caption(f"PDF dosyasi: {p.name}")
        with open(p, "rb") as f:
            st.download_button("PDF indir", f.read(), file_name=p.name, mime="application/pdf")
    else:
        st.caption(f"Dosya: {p.name}")
        with open(p, "rb") as f:
            st.download_button("Dosyayi indir", f.read(), file_name=p.name)


# ── Task comments ──────────────────────────────────────────────────────────────

def render_task_comments(
    conn,
    task_id: int,
    project_name: str,
    current_user_id: str,
    current_user_role: str,
    form_key_suffix: str = "",
) -> None:
    comments_df = fetch_task_comments(conn, task_id)

    ROLE_COLORS = {
        "advisor": ("rgba(139,92,246,0.15)", "#6d28d9", "👨‍🏫 Danışman"),
        "leader":  ("rgba(245,158,11,0.15)",  "#b45309", "👑 Lider"),
        "student": ("rgba(59,130,246,0.15)",  "#1d4ed8", "🎓 Öğrenci"),
    }

    if not comments_df.empty:
        for _, c in comments_df.iterrows():
            role_key = str(c["author_role"])
            bg, color, label = ROLE_COLORS.get(role_key, ("rgba(0,0,0,0.05)", "#333", role_key))
            ts = str(c["created_at"])[:16]
            comment_text = str(c["comment"]).replace("<", "&lt;").replace(">", "&gt;")
            st.markdown(
                f"""
                <div style="background:{bg};border-left:3px solid {color};border-radius:0 8px 8px 0;
                            padding:0.55rem 0.85rem;margin-bottom:0.45rem;">
                    <div style="display:flex;align-items:center;gap:0.5rem;margin-bottom:0.25rem;">
                        <span style="background:{color};color:#fff;border-radius:999px;padding:0.1em 0.55em;
                                     font-size:0.68rem;font-weight:700;">{label}</span>
                        <span style="font-weight:600;font-size:0.82rem;color:#1e293b;">{c["author_id"]}</span>
                        <span style="font-size:0.72rem;color:#94a3b8;margin-left:auto;">{ts}</span>
                    </div>
                    <div style="font-size:0.84rem;color:#334155;line-height:1.5;">{comment_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            "<div style='font-size:0.8rem;color:#94a3b8;padding:0.5rem 0;'>Henüz yorum yok.</div>",
            unsafe_allow_html=True,
        )

    with st.form(f"comment_form_{task_id}_{form_key_suffix}"):
        new_comment = st.text_area("Yorum yaz", key=f"comment_text_{task_id}_{form_key_suffix}", height=80)
        comment_submit = st.form_submit_button("💬 Yorum Ekle",width="stretch")
    if comment_submit:
        if not new_comment.strip():
            st.error("Yorum boş olamaz.")
        else:
            add_task_comment(conn, task_id, project_name, current_user_id, current_user_role, new_comment)
            st.success("Yorum eklendi.")
            st.rerun()


# ── Milestone progress ─────────────────────────────────────────────────────────

def render_milestone_progress(tasks_df: pd.DataFrame) -> None:
    from i18n import translate_text

    st.markdown(f"#### 📊 {translate_text('Milestone İlerlemesi')}")
    cols = st.columns(len(MILESTONES))
    for col, (milestone_key, label) in zip(cols, MILESTONES):
        scoped = tasks_df[tasks_df["milestone_key"] == milestone_key]
        total = len(scoped)
        done = int((scoped["status"] == "DONE").sum()) if total > 0 else 0
        percent = completion_percent(scoped)

        if percent >= 100:
            bar_color, text_color, bg = "#16a34a", "#14532d", "#dcfce7"
        elif percent >= 50:
            bar_color, text_color, bg = "#0f4c81", "#0a2342", "#dbeafe"
        elif percent > 0:
            bar_color, text_color, bg = "#d97706", "#78350f", "#fef3c7"
        else:
            bar_color, text_color, bg = "#94a3b8", "#475569", "#f1f5f9"

        short_label = milestone_key
        col.markdown(
            f"""
            <div style="background:{bg};border-radius:10px;padding:0.65rem 0.7rem;text-align:center;height:100%;">
                <div style="font-size:0.65rem;font-weight:700;color:{text_color};text-transform:uppercase;
                            letter-spacing:.05em;margin-bottom:0.2rem;">{short_label}</div>
                <div style="font-size:1.3rem;font-weight:800;color:{bar_color};">{int(percent)}%</div>
                <div style="font-size:0.67rem;color:{text_color};margin-top:0.1rem;">{done}/{total} görev</div>
                <div style="background:#e2e8f0;border-radius:999px;height:5px;margin-top:0.4rem;overflow:hidden;">
                    <div style="background:{bar_color};height:100%;width:{percent}%;border-radius:999px;transition:width .5s;"></div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
