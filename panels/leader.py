"""
panels/leader.py  — professional UI upgrade
Group leader panel: team overview, role management, task creation,
task tracking, milestone progress, comments, password reset.
Leaders go here directly (no student-view toggle — leaders ARE leaders).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from components import render_evidence_file, render_milestone_progress, render_task_comments, save_uploaded_evidence
from constants import MILESTONE_LABELS, MILESTONES, PRIORITY_OPTIONS, ROLE_OPTIONS
from db import fetch_df
from models import (
    completion_percent,
    create_task,
    fetch_tasks,
    get_leader,
    member_progress,
    overdue_count,
    reset_password_to_default,
    update_task,
    upsert_role,
)
from ui_helpers import (
    _t,
    render_active_task_card,
    render_member_table,
    section_header,
    status_badge_html,
)
from utils import allowed_status_options, status_tr


def render_leader_panel(
    conn,
    roster: pd.DataFrame,
    fixed_project_name: Optional[str] = None,
    fixed_leader_no: Optional[str] = None,
) -> None:
    if roster.empty:
        st.warning(_t("Seçilen danışmana ait öğrenci bulunamadı."))
        return

    # ── Resolve project & leader ───────────────────────────────────────────────
    if fixed_project_name and fixed_leader_no:
        project_name = fixed_project_name
        leader_no = fixed_leader_no
        current = get_leader(conn, project_name)
        if current != leader_no:
            st.error(_t("Bu proje için lider paneline erişim yetkiniz yok."))
            return
    else:
        allowed_projects = set(roster["project_name"].astype(str).tolist())
        leaders_df = fetch_df(conn, "SELECT project_name, student_no FROM leaders ORDER BY project_name")
        leaders_df = leaders_df[leaders_df["project_name"].astype(str).isin(allowed_projects)]
        if leaders_df.empty:
            st.warning(_t("Lider ataması yok. Danışman panelinden atayın."))
            return
        leader_options: Dict[str, tuple[str, str]] = {}
        for _, row in leaders_df.iterrows():
            listed_project = str(row["project_name"])
            sno = str(row["student_no"])
            member = roster[(roster["project_name"] == listed_project) & (roster["student_no"] == sno)]
            student_name = str(member.iloc[0]["student_name"]) if not member.empty else "Bilinmeyen"
            leader_options[f"{student_name} ({sno}) - {listed_project}"] = (listed_project, sno)
        selected = st.selectbox("Lider", sorted(leader_options.keys()))
        project_name, leader_no = leader_options[selected]

    team_df = roster[roster["project_name"] == project_name].sort_values("row_no")
    tasks_df = fetch_tasks(conn, project_name)
    my_tasks = tasks_df[tasks_df["assignee_student_no"] == leader_no]
    roles_df = fetch_df(conn, "SELECT student_no, role, responsibility FROM member_roles WHERE project_name = ?", (project_name,))

    # ── Hero banner ────────────────────────────────────────────────────────────
    leader_row = roster[roster["student_no"].astype(str) == str(leader_no)]
    leader_name = str(leader_row.iloc[0]["student_name"]) if not leader_row.empty else leader_no
    my_pct  = completion_percent(my_tasks)
    prj_pct = completion_percent(tasks_df)
    overdue = overdue_count(tasks_df)

    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#ffffff 0%,#eef5fb 100%);
                    border:1px solid #dbe5ef;border-radius:14px;padding:1.2rem 1.6rem;margin-bottom:1rem;
                    box-shadow:0 4px 16px rgba(15,23,42,0.08);">
            <div style="display:flex;align-items:flex-start;gap:1rem;">
                <div style="width:52px;height:52px;background:#dbeafe;border:2px solid #93c5fd;
                            border-radius:50%;display:flex;align-items:center;justify-content:center;
                            font-size:1.5rem;flex-shrink:0;">👑</div>
                <div style="flex:1;">
                    <div style="color:#0f4c81;font-size:0.68rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;">{_t('Grup Lider Paneli')}</div>
                    <div style="color:#0f172a;font-size:1.2rem;font-weight:800;margin:0.1rem 0;">{leader_name}</div>
                    <div style="color:#64748b;font-size:0.75rem;">📁 {project_name}</div>
                </div>
                <div style="display:flex;gap:1.5rem;text-align:center;flex-shrink:0;">
                    <div>
                        <div style="color:#0f4c81;font-size:1.5rem;font-weight:900;line-height:1;">%{int(prj_pct)}</div>
                        <div style="color:#64748b;font-size:0.65rem;">{_t('Proje')}</div>
                    </div>
                    <div>
                        <div style="color:{'#dc2626' if overdue>0 else '#16a34a'};font-size:1.5rem;font-weight:900;line-height:1;">{overdue}</div>
                        <div style="color:#64748b;font-size:0.65rem;">{_t('Geciken')}</div>
                    </div>
                    <div>
                        <div style="color:#1d4ed8;font-size:1.5rem;font-weight:900;line-height:1;">{len(team_df)}</div>
                        <div style="color:#64748b;font-size:0.65rem;">{_t('Üye')}</div>
                    </div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Overview metrics ───────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    c1.metric(_t("Proje Görevi"),       len(tasks_df))
    c2.metric(_t("Proje Tamamlanma"),   f"%{int(prj_pct)}")
    c3.metric(_t("Benim Görevim"),      len(my_tasks))
    c4.metric(_t("Benim İlerlemem"),    f"%{int(my_pct)}")

    # ── Milestone progress ─────────────────────────────────────────────────────
    section_header("📊", _t("Milestone İlerlemesi"))
    render_milestone_progress(tasks_df)

    # ── Team table ─────────────────────────────────────────────────────────────
    section_header("👥", _t("Takım Üyeleri & Roller"))
    render_member_table(team_df, roles_df, leader_no)

    # ── Role assignment ────────────────────────────────────────────────────────
    section_header("🎭", _t("Rol Atama"), _t("Takım üyelerine rol ve görev tanımı atayın"))
    member_options = {f"{r['student_name']} ({r['student_no']})": str(r["student_no"]) for _, r in team_df.iterrows()}
    with st.form(f"role_form_{project_name}"):
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            member_label = st.selectbox(_t("Üye Seç"), list(member_options.keys()))
            role = st.selectbox(_t("Rol"), ROLE_OPTIONS)
        with col_r2:
            responsibility = st.text_area(_t("Görev Tanımı"), height=100)
        role_submit = st.form_submit_button(_t("💾 Rolü Kaydet"),width="stretch")
    if role_submit:
        upsert_role(conn, project_name, member_options[member_label], role, responsibility)
        st.success(_t("Rol güncellendi."))
        st.rerun()

    # ── Create new task ────────────────────────────────────────────────────────
    section_header("➕", _t("Yeni Görev Oluştur"), _t("Milestone bazlı görev planlayın ve üyeye atayın"))
    existing_tasks = fetch_tasks(conn, project_name)
    dependency_map: Dict[str, Optional[int]] = {_t("Yok"): None}
    for _, row in existing_tasks.iterrows():
        dependency_map[f"#{int(row['id'])} - {row['title']}"] = int(row["id"])
    milestone_map = {_t(label): key for key, label in MILESTONES}

    with st.form(f"new_task_form_{project_name}"):
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            milestone_label = st.selectbox(_t("Milestone"), list(milestone_map.keys()))
            title = st.text_input(_t("Görev Başlığı"), placeholder=_t("Kısa ve açıklayıcı bir başlık"))
            assignee = st.selectbox(_t("Sorumlu Üye"), list(member_options.keys()))
            priority = st.selectbox(_t("Öncelik"), PRIORITY_OPTIONS, index=1)
        with col_t2:
            description = st.text_area(_t("Açıklama"), height=100)
            no_deadline = st.checkbox(_t("Deadline yok"))
            deadline_date = st.date_input(_t("Deadline"), value=date.today() + timedelta(days=7), disabled=no_deadline)
            dependency = st.selectbox(_t("Bağımlılık"), list(dependency_map.keys()))
            evidence_required = st.text_input(_t("İstenen Kanıt"), value=_t("Repo linki veya rapor"))
        task_submit = st.form_submit_button(_t("✅ Görevi Oluştur"),width="stretch")
    if task_submit:
        if not title.strip():
            st.error(_t("Görev başlığı gerekli."))
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
            st.success(_t("Görev oluşturuldu."))
            st.rerun()

    # ── Task tracking ──────────────────────────────────────────────────────────
    tasks_df = fetch_tasks(conn, project_name)
    if tasks_df.empty:
        st.info(_t("Bu proje için henüz görev yok."))
        return

    section_header("🗂️", _t("Görev Takibi"), _t("Tüm görevleri görüntüleyin ve durumlarını güncelleyin"))

    # Task list with inline status badges
    rows_html = ""
    for _, t in tasks_df.iterrows():
        ms_label = _t(MILESTONE_LABELS.get(str(t["milestone_key"]), str(t["milestone_key"])))
        # Find assignee name
        assignee_no = str(t.get("assignee_student_no", ""))
        assignee_row = roster[roster["student_no"].astype(str) == assignee_no]
        assignee_name = str(assignee_row.iloc[0]["student_name"]) if not assignee_row.empty else assignee_no
        badge = status_badge_html(str(t["status"]))
        deadline = str(t.get("deadline", "") or "—")
        dl_color = "#dc2626" if deadline not in ("—", "") else "#94a3b8"
        rows_html += f"""
        <tr style="border-bottom:1px solid #f1f5f9;">
            <td style="padding:.4rem .6rem;font-size:.72rem;color:#64748b;">{ms_label}</td>
            <td style="padding:.4rem .6rem;font-size:.82rem;color:#1e293b;font-weight:500;">{t['title']}</td>
            <td style="padding:.4rem .6rem;font-size:.78rem;color:#475569;">{assignee_name}</td>
            <td style="padding:.4rem .6rem;">{badge}</td>
            <td style="padding:.4rem .6rem;font-size:.72rem;color:{dl_color};">{deadline}</td>
        </tr>"""

    st.markdown(
        f"""<div style="border:1px solid #e2e8f0;border-radius:10px;overflow:hidden;
                        box-shadow:0 1px 4px rgba(0,0,0,.05);margin-bottom:.75rem;">
        <table style="width:100%;border-collapse:collapse;">
        <thead><tr style="background:#eaf2f9;">
        <th style="padding:.45rem .6rem;font-size:.7rem;color:#0f4c81;text-align:left;letter-spacing:.05em;text-transform:uppercase;">{_t('Milestone')}</th>
        <th style="padding:.45rem .6rem;font-size:.7rem;color:#0f4c81;text-align:left;letter-spacing:.05em;text-transform:uppercase;">{_t('Görev')}</th>
        <th style="padding:.45rem .6rem;font-size:.7rem;color:#0f4c81;text-align:left;letter-spacing:.05em;text-transform:uppercase;">{_t('Sorumlu')}</th>
        <th style="padding:.45rem .6rem;font-size:.7rem;color:#0f4c81;text-align:left;letter-spacing:.05em;text-transform:uppercase;">{_t('Durum')}</th>
        <th style="padding:.45rem .6rem;font-size:.7rem;color:#0f4c81;text-align:left;letter-spacing:.05em;text-transform:uppercase;">{_t('Deadline')}</th>
        </tr></thead><tbody>{rows_html}</tbody></table></div>""",
        unsafe_allow_html=True,
    )

    # ── Update a task ──────────────────────────────────────────────────────────
    section_header("✏️", _t("Görev Güncelle"))
    task_sel_options = {
        f"#{int(r['id'])} [{status_tr(r['status'])}] {r['title']}": int(r["id"])
        for _, r in tasks_df.iterrows()
    }
    selected_task = st.selectbox(_t("Düzenlenecek görev"), list(task_sel_options.keys()))
    task_id = task_sel_options[selected_task]
    row = tasks_df[tasks_df["id"] == task_id].iloc[0]
    render_active_task_card(row, MILESTONE_LABELS.get(str(row["milestone_key"]), ""))

    status_options = allowed_status_options(str(row["status"]))
    status_idx = status_options.index(row["status"]) if row["status"] in status_options else 0

    with st.form(f"task_update_form_{project_name}"):
        col_u1, col_u2 = st.columns(2)
        with col_u1:
            status = st.selectbox(_t("Durum"), status_options, index=status_idx, format_func=status_tr)
        with col_u2:
            evidence_link = st.text_input(_t("Kanıt linki"), value=row["evidence_link"] or "")
        upd_submit = st.form_submit_button(_t("💾 Güncelle"),width="stretch")

    ldr_evidence_upload = st.file_uploader(
        _t("Kanıt dosyası yükle (resim, PDF vb.)"),
        type=["png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "zip"],
        key=f"ldr_evidence_file_{project_name}",
    )
    existing_ldr_file = str(row.get("evidence_file", "") or "")
    if existing_ldr_file:
        with st.expander(_t("Mevcut kanıt dosyası")):
            render_evidence_file(existing_ldr_file)

    if upd_submit:
        file_path = ""
        if ldr_evidence_upload is not None:
            file_path = save_uploaded_evidence(ldr_evidence_upload, task_id)
        ok, msg = update_task(conn, task_id, status, evidence_link, skip_milestone_check=True, evidence_file=file_path)
        st.success(_t("Görev güncellendi.")) if ok else st.error(msg)
        if ok:
            st.rerun()

    # ── Task comments ──────────────────────────────────────────────────────────
    section_header("💬", _t("Görev Yorumları"))
    with st.expander(f"Yorumlar: #{task_id} - {row['title']}"):
        render_task_comments(conn, task_id, project_name, current_user_id=leader_no,
                             current_user_role="leader", form_key_suffix=f"ldr_{project_name}")

    # ── Member progress summary ────────────────────────────────────────────────
    section_header("📈", _t("Üye İlerleme Özeti"))
    progress_df = member_progress(team_df, tasks_df)
    if not progress_df.empty:
        st.dataframe(progress_df,width="stretch", hide_index=True)

    # ── Member password reset ──────────────────────────────────────────────────
    section_header("🔑", _t("Üye Şifre Sıfırlama"),
                   _t("Şifreyi unutan takım arkadaşınızın şifresini sıfırlayın"))
    other_members = team_df[team_df["student_no"].astype(str) != str(leader_no)].copy()
    if other_members.empty:
        st.info(_t("Grubunuzda şifre sıfırlanabilecek başka üye bulunmuyor."))
    else:
        reset_options = {
            f"{r['student_name']} ({r['student_no']})": str(r["student_no"])
            for _, r in other_members.sort_values("student_name").iterrows()
        }
        with st.form(f"leader_pwd_reset_form_{project_name}"):
            selected_member_label = st.selectbox(_t("Üye seçin"), list(reset_options.keys()),
                                                  key=f"ldr_pwd_reset_pick_{project_name}")
            confirm_reset = st.checkbox(_t("Bu üyenin şifresinin sıfırlanacağını onaylıyorum"),
                                        key=f"ldr_pwd_reset_confirm_{project_name}")
            reset_submit = st.form_submit_button(_t("🔑 Şifreyi Sıfırla"), disabled=not confirm_reset,
                                                  width="stretch")
        if reset_submit:
            target_no = reset_options[selected_member_label]
            is_member = not team_df[team_df["student_no"].astype(str) == target_no].empty
            if not is_member:
                st.error(_t("Bu öğrenci grubunuzda kayıtlı değil."))
            else:
                ok = reset_password_to_default(conn, target_no, "student")
                st.success(f"{selected_member_label} {_t('şifresi sıfırlandı.')}") if ok else st.error(_t("Sıfırlama başarısız."))
