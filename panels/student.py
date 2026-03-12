"""
panels/student.py  — upgraded UI
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import pandas as pd
import streamlit as st

from components import render_evidence_file, render_milestone_progress, render_task_comments, save_uploaded_evidence
from constants import MILESTONE_LABELS, MILESTONE_ORDER
from db import fetch_df
from models import (
    add_weekly_update,
    build_project_metrics,
    completion_percent,
    current_student_task,
    fetch_feedbacks,
    fetch_tasks,
    fetch_weekly_updates_for_project,
    get_leader,
    get_roster_from_db,
    update_task,
)
from ui_helpers import (
    _t,
    render_active_task_card,
    render_feedback_card,
    render_member_table,
    render_project_cards,
    section_header,
    status_badge_html,
)
from utils import allowed_status_options, status_tr


def render_student_panel(
    conn,
    roster: pd.DataFrame,
    fixed_student_no: Optional[str] = None,
    fixed_project_name: Optional[str] = None,
    is_leader: bool = False,
) -> None:
    if roster.empty:
        st.warning("Seçilen danışmana ait öğrenci bulunamadı.")
        return

    roster_sorted = roster.sort_values(["project_name", "row_no", "student_name"]).reset_index(drop=True)

    # ── Resolve student & project ─────────────────────────────────────────────
    if fixed_student_no:
        scoped = roster_sorted[roster_sorted["student_no"] == fixed_student_no]
        if fixed_project_name:
            scoped = scoped[scoped["project_name"] == fixed_project_name]
        if scoped.empty:
            st.error("Öğrenci kaydı bulunamadı.")
            return
        row = scoped.iloc[0]
    else:
        student_map = {
            f"{r['student_name']} ({r['student_no']}) - {r['project_name']}": idx
            for idx, r in roster_sorted.iterrows()
        }
        selected = st.selectbox("Öğrenci", list(student_map.keys()))
        row = roster_sorted.iloc[student_map[selected]]

    student_no = str(row["student_no"])
    student_name = str(row["student_name"])
    project_name = str(row["project_name"])
    advisor_name = str(row.get("advisor_name", "—"))

    project_members = roster_sorted[roster_sorted["project_name"] == project_name].sort_values("row_no")
    tasks_df = fetch_tasks(conn, project_name)
    my_tasks = tasks_df[tasks_df["assignee_student_no"] == student_no]
    leader_no = get_leader(conn, project_name)

    role_row = conn.execute(
        "SELECT role, responsibility FROM member_roles WHERE project_name = ? AND student_no = ?",
        (project_name, student_no),
    ).fetchone()
    student_role = role_row["role"] if role_row else ("Lider" if is_leader else "Üye")
    student_resp = role_row["responsibility"] if role_row else "—"

    role_icon = "👑" if (leader_no == student_no) else "🎓"
    role_badge_bg = "#fef3c7" if (leader_no == student_no) else "#dbeafe"
    role_badge_color = "#92400e" if (leader_no == student_no) else "#1e40af"

    # ── Student profile hero ──────────────────────────────────────────────────
    my_pct = completion_percent(my_tasks)
    proj_pct = completion_percent(tasks_df)
    bar_color = "#16a34a" if my_pct >= 80 else "#0f4c81" if my_pct >= 40 else "#d97706"

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0a2342 0%,#1a3a6b 100%);
                    border-radius:14px;padding:1.2rem 1.6rem;margin-bottom:1rem;
                    box-shadow:0 4px 16px rgba(10,35,66,0.18);">
            <div style="display:flex;align-items:flex-start;gap:1rem;">
                <div style="width:52px;height:52px;background:rgba(255,215,0,0.15);border:2px solid #ffd700;
                            border-radius:50%;display:flex;align-items:center;justify-content:center;
                            font-size:1.4rem;flex-shrink:0;">{role_icon}</div>
                <div style="flex:1;min-width:0;">
                    <div style="color:#ffd700;font-size:0.68rem;font-weight:700;letter-spacing:.1em;
                                text-transform:uppercase;">{_t('Öğrenci Paneli')}</div>
                    <div style="color:#ffffff;font-size:1.2rem;font-weight:800;margin:0.1rem 0;">{student_name}</div>
                    <div style="color:#a8c8f0;font-size:0.75rem;">{student_no} &nbsp;·&nbsp; {project_name}</div>
                    <div style="margin-top:0.4rem;display:flex;gap:0.4rem;flex-wrap:wrap;">
                        <span style="background:{role_badge_bg};color:{role_badge_color};border-radius:999px;
                                     padding:.1em .6em;font-size:.7rem;font-weight:700;">{role_icon} {_t(student_role)}</span>
                        <span style="background:rgba(255,255,255,0.1);color:#e2e8f0;border-radius:999px;
                                     padding:.1em .6em;font-size:.7rem;">👨&#8205;🏫 {advisor_name}</span>
                    </div>
                </div>
                <div style="text-align:right;flex-shrink:0;">
                    <div style="color:#ffd700;font-size:1.8rem;font-weight:900;line-height:1;">%{int(my_pct)}</div>
                    <div style="color:#a8c8f0;font-size:0.68rem;">{_t('kişisel ilerleme')}</div>
                    <div style="background:rgba(255,255,255,0.15);border-radius:999px;height:6px;
                                width:80px;margin-top:0.3rem;overflow:hidden;margin-left:auto;">
                        <div style="background:{bar_color};height:100%;width:{my_pct}%;border-radius:999px;
                                    transition:width .5s;"></div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Overview metrics ──────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Proje Görevi", len(tasks_df))
    c2.metric("Proje Tamamlanma", f"%{int(proj_pct)}")
    c3.metric("Benim Görevim", len(my_tasks))
    c4.metric("Benim İlerlemem", f"%{int(my_pct)}")

    render_milestone_progress(tasks_df)

    # ── Team members ──────────────────────────────────────────────────────────
    section_header("👥", "Takım Üyeleri", project_name)
    roles_df = fetch_df(conn, "SELECT student_no, role, responsibility FROM member_roles WHERE project_name = ?", (project_name,))
    render_member_table(project_members, roles_df, leader_no)

    # ── Personal task queue ───────────────────────────────────────────────────
    section_header("✅", _t("Görev Sıram"), _t("Milestone sırasına göre aktif göreviniz"))
    if my_tasks.empty:
        st.info("Size atanmış görev yok.")
    else:
        ordered = my_tasks.copy()
        ordered["ms_order"] = ordered["milestone_key"].map(MILESTONE_ORDER).fillna(999).astype(int)
        ordered = ordered.sort_values(["ms_order", "id"])

        # Task list with inline status chips
        rows_html = ""
        for _, t in ordered.iterrows():
            ms_label = _t(MILESTONE_LABELS.get(str(t["milestone_key"]), str(t["milestone_key"])))
            badge = status_badge_html(str(t["status"]))
            deadline = str(t.get("deadline", "") or "—")
            dl_color = "#dc2626" if deadline != "—" else "#94a3b8"
            rows_html += f"""
            <tr style="border-bottom:1px solid #e2e8f0;">
                <td style="padding:.4rem .6rem;font-size:.72rem;color:#64748b;white-space:nowrap;">{ms_label}</td>
                <td style="padding:.4rem .6rem;font-size:.82rem;color:#1e293b;">{t['title']}</td>
                <td style="padding:.4rem .6rem;">{badge}</td>
                <td style="padding:.4rem .6rem;font-size:.72rem;color:{dl_color};white-space:nowrap;">{deadline}</td>
            </tr>"""
        st.markdown(
            f"""<div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;margin-bottom:.75rem;box-shadow:0 1px 4px rgba(0,0,0,.05);">
            <table style="width:100%;border-collapse:collapse;">
            <thead><tr style="background:#0a2342;">
            <th style="padding:.45rem .6rem;font-size:.7rem;color:#fff;text-align:left;letter-spacing:.05em;text-transform:uppercase;">Milestone</th>
            <th style="padding:.45rem .6rem;font-size:.7rem;color:#fff;text-align:left;letter-spacing:.05em;text-transform:uppercase;">Görev</th>
            <th style="padding:.45rem .6rem;font-size:.7rem;color:#fff;text-align:left;letter-spacing:.05em;text-transform:uppercase;">Durum</th>
            <th style="padding:.45rem .6rem;font-size:.7rem;color:#fff;text-align:left;letter-spacing:.05em;text-transform:uppercase;">Deadline</th>
            </tr></thead><tbody>{rows_html}</tbody></table></div>""",
            unsafe_allow_html=True,
        )

        task_row = current_student_task(my_tasks)
        if task_row is None:
            st.markdown(
                f"""<div style="background:#dcfce7;border:1px solid #16a34a;border-radius:10px;
                              padding:.75rem 1rem;font-size:.88rem;font-weight:600;color:#14532d;">
                   🎉 {_t('Tüm milestone görevlerini tamamladınız!')}</div>""",
                unsafe_allow_html=True,
            )
        else:
            current_milestone = _t(MILESTONE_LABELS.get(str(task_row["milestone_key"]), str(task_row["milestone_key"])))
            st.markdown(
                f"""<div style="background:#fef3c7;border-left:4px solid #d97706;border-radius:4px 10px 10px 4px;
                               padding:.6rem .9rem;margin-bottom:.5rem;font-size:.82rem;color:#78350f;">
                    ⚡ <strong>{_t('Aktif Görev')}:</strong> {current_milestone}</div>""",
                unsafe_allow_html=True,
            )
            render_active_task_card(task_row, current_milestone)

            status_options = allowed_status_options(str(task_row["status"]))
            status_idx = status_options.index(task_row["status"]) if task_row["status"] in status_options else 0

            with st.form(f"student_task_form_{student_no}"):
                st.markdown(
                    "<div style='font-size:0.75rem;color:#64748b;margin-bottom:.3rem;'>"
                    "💡 Önceki milestone tamamlanmadan sonraki milestone görevine geçilemez.</div>",
                    unsafe_allow_html=True,
                )
                status = st.selectbox("Durum güncelle", status_options, index=status_idx, format_func=status_tr)
                evidence = st.text_input("Kanıt linki (repo, rapor, vs.)", value=task_row["evidence_link"] or "")
                save_task = st.form_submit_button("💾 Görevi Kaydet",width="stretch")

            stu_evidence_upload = st.file_uploader(
                "Kanıt dosyası yükle (resim, PDF vb.)",
                type=["png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "zip"],
                key=f"stu_evidence_file_{student_no}",
            )
            existing_stu_file = str(task_row.get("evidence_file", "") or "")
            if existing_stu_file:
                with st.expander("Mevcut kanıt dosyası"):
                    render_evidence_file(existing_stu_file)
            if save_task:
                file_path = ""
                if stu_evidence_upload is not None:
                    file_path = save_uploaded_evidence(stu_evidence_upload, int(task_row["id"]))
                ok, msg = update_task(conn, int(task_row["id"]), status, evidence, evidence_file=file_path)
                st.success("Göreviniz güncellendi.") if ok else st.error(msg)
                if ok:
                    st.rerun()

            active_task_id = int(task_row["id"])
            section_header("💬", "Görev Yorumları")
            author_role = "leader" if is_leader else "student"
            render_task_comments(conn, active_task_id, project_name, current_user_id=student_no,
                                 current_user_role=author_role, form_key_suffix=f"stu_{student_no}")

    # ── Weekly update form ────────────────────────────────────────────────────
    monday = date.today() - timedelta(days=date.today().weekday())
    current_task = current_student_task(my_tasks)
    section_header("📅", "Haftalık İlerleme Girişi", "Bu haftaki çalışmalarınızı kaydedin")
    if current_task is None:
        st.info("Haftalık giriş için açık milestone görevi yok.")
    else:
        current_task_id = int(current_task["id"])
        current_task_label = f"#{current_task_id} - {current_task['title']}"
        with st.form(f"weekly_form_{student_no}"):
            st.text_input("İlgili görev", value=current_task_label, disabled=True)
            week_start = st.date_input("Hafta başlangıcı", value=monday)
            col_a, col_b = st.columns(2)
            with col_a:
                completed = st.text_area("Yapılanlar", height=100)
                blockers = st.text_area("Engeller", height=80)
            with col_b:
                next_step = st.text_area("Sonraki adım", height=100)
                evidence_link = st.text_input("Kanıt linki")
            weekly_submit = st.form_submit_button("📅 Haftalık Girişi Kaydet",width="stretch")
        if weekly_submit:
            if not completed.strip() and not next_step.strip():
                st.error("Yapılanlar veya sonraki adım alanından en az biri dolu olmalı.")
            else:
                add_weekly_update(
                    conn=conn, project_name=project_name, student_no=student_no,
                    task_id=current_task_id, week_start=week_start.isoformat(),
                    completed=completed, blockers=blockers, next_step=next_step, evidence_link=evidence_link,
                )
                st.success("Haftalık giriş kaydedildi.")
                st.rerun()

    # ── Past weekly updates ───────────────────────────────────────────────────
    section_header("🗃️", "Geçmiş Haftalık Girişlerim")
    my_weekly_df = fetch_weekly_updates_for_project(conn, project_name, student_no)
    if my_weekly_df.empty:
        st.info("Henüz haftalık giriş yapılmamış.")
    else:
        st.dataframe(
            my_weekly_df[["week_start", "completed", "blockers", "next_step", "evidence_link", "created_at"]].rename(
                columns={"week_start": "Hafta", "completed": "Yapılanlar", "blockers": "Engeller",
                         "next_step": "Sonraki Adım", "evidence_link": "Kanıt", "created_at": "Tarih"}
            ),
            width="stretch", hide_index=True,
        )

    # ── Advisor feedback ──────────────────────────────────────────────────────
    section_header("📢", "Danışman Geri Bildirimleri")
    feedbacks_df = fetch_feedbacks(conn, project_name)
    if feedbacks_df.empty:
        st.info("Henüz danışman geri bildirimi yok.")
    else:
        for _, fb in feedbacks_df.iterrows():
            render_feedback_card(fb)

    # ── Group comparison ──────────────────────────────────────────────────────
    section_header("🏆", "Gruplar Arası Karşılaştırma", "Projenizin diğer gruplar arasındaki konumu")
    scope = st.radio(
        "Karşılaştırma kapsamı",
        ["Danışman grupları", "Tüm gruplar"],
        horizontal=True,
        key="compare_scope",
    )
    compare_roster = roster if scope == "Danışman grupları" else get_roster_from_db(conn)
    compare_df = build_project_metrics(conn, compare_roster, sorted(compare_roster["project_name"].unique()))
    if not compare_df.empty:
        compare_df["Sıra"] = compare_df["Tamamlanma %"].rank(method="dense", ascending=False).astype(int)
        compare_df = compare_df.sort_values(["Sıra", "Geciken Gorev"], ascending=[True, True])
        mine = compare_df[compare_df["Proje"] == project_name]
        rank = int(mine.iloc[0]["Sıra"]) if not mine.empty else "—"
        total = len(compare_df)
        pct = int(my_pct)

        # Leaderboard hero
        podium = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else "🏅"
        lbl_rank  = _t("{rank}. / {total} proje").replace("{rank}", str(rank)).replace("{total}", str(total))
        lbl_score = _t("%{pct} tamamlandı").replace("{pct}", str(pct))
        st.markdown(
            f"""
            <div style="background:linear-gradient(135deg,#f8fafc 0%,#e8f4fd 100%);
                        border:1.5px solid #0f4c81;border-radius:12px;padding:.9rem 1.2rem;
                        margin-bottom:.75rem;display:flex;align-items:center;gap:1rem;">
                <span style="font-size:2rem;">{podium}</span>
                <div>
                    <div style="font-weight:800;font-size:1.1rem;color:#0a2342;">{rank} / {total}</div>
                    <div style="font-size:.78rem;color:#475569;">{project_name} &nbsp;·&nbsp; %{pct} {_t('tamamlandı')}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.dataframe(compare_df,width="stretch", hide_index=True)
