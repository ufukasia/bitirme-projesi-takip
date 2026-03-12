
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from components import render_evidence_file, render_milestone_progress, render_task_comments, save_uploaded_evidence
from constants import MILESTONE_LABELS, MILESTONES, PRIORITY_OPTIONS, ROLE_OPTIONS
from models import (
    add_feedback,
    bootstrap_defaults,
    build_project_metrics,
    completion_percent,
    fetch_feedbacks,
    fetch_tasks,
    fetch_weekly_updates_for_project,
    get_leader,
    get_roster_from_db,
    initialize_all_projects,
    load_roster_from_upload,
    member_progress,
    overdue_count,
    reset_password_to_default,
    set_leader,
    sync_auth_users,
    update_task,
    upsert_role,
    upsert_students,
)
from ui_helpers import (
    render_active_task_card,
    render_feedback_card,
    render_member_table,
    render_project_cards,
    risk_badge_html,
    section_header,
    status_badge_html,
)
from utils import allowed_status_options, status_tr


def render_advisor_panel(conn, advisor_name: str, roster: pd.DataFrame) -> None:
    # ── Page title ────────────────────────────────────────────────────────────
    st.markdown(
        f"""
        <div style="background:linear-gradient(135deg,#0a2342 0%,#1a3a6b 100%);
                    border-radius:14px;padding:1.2rem 1.6rem;margin-bottom:1.2rem;
                    box-shadow:0 4px 16px rgba(10,35,66,0.18);">
            <div style="color:#ffd700;font-size:0.7rem;font-weight:700;letter-spacing:.1em;
                        text-transform:uppercase;margin-bottom:0.2rem;">Danışman Paneli</div>
            <div style="color:#ffffff;font-size:1.3rem;font-weight:800;">{advisor_name}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    projects = sorted(roster["project_name"].unique())
    if not projects:
        st.warning("Bu danışmana ait grup/öğrenci kaydı yok.")
        return

    summary_df = build_project_metrics(conn, roster, projects)
    completion_by_project: Dict[str, float] = {}
    if not summary_df.empty:
        completion_by_project = {
            str(row["Proje"]): float(row["Tamamlanma %"])
            for _, row in summary_df.iterrows()
        }

    # ── Project cards grid ────────────────────────────────────────────────────
    section_header("📁", "Proje Genel Bakışı", f"{len(projects)} aktif proje")

    projects_data = []
    for project in projects:
        grp = roster[roster["project_name"] == project]
        leader_no = get_leader(conn, project)
        leader_name = "-"
        if leader_no:
            hit = grp[grp["student_no"].astype(str) == str(leader_no)]
            leader_name = str(hit.iloc[0]["student_name"]) if not hit.empty else leader_no
        risk_row = summary_df[summary_df["Proje"] == project] if not summary_df.empty else pd.DataFrame()
        risk = str(risk_row.iloc[0]["Risk"]) if not risk_row.empty else "Orta"
        overdue = int(risk_row.iloc[0]["Geciken Gorev"]) if not risk_row.empty else 0
        projects_data.append({
            "name": project,
            "leader": leader_name,
            "members": len(grp),
            "completion": completion_by_project.get(project, 0.0),
            "risk": risk,
            "overdue": overdue,
        })
    render_project_cards(projects_data)

    # ── Summary table ─────────────────────────────────────────────────────────
    if not summary_df.empty:
        section_header("📊", "Proje Özeti", "Tüm projelerin tamamlanma, gecikme ve risk durumu")
        display = summary_df.copy().sort_values(["Tamamlanma %", "Geciken Gorev"], ascending=[False, True])
        st.dataframe(display,width="stretch", hide_index=True)

    # ── Student search ─────────────────────────────────────────────────────────
    section_header("🔍", "Öğrenci Arama", "Ad veya numara ile arayın")
    search_query = st.text_input(
        "Öğrenci ara",
        key="advisor_student_search",
        placeholder="Örnek: Ali Veli veya 2001234567",
        label_visibility="collapsed",
    )
    if search_query.strip():
        q = search_query.strip().lower()
        matches = roster[
            roster["student_name"].str.lower().str.contains(q, na=False)
            | roster["student_no"].str.strip().str.contains(q, na=False)
        ]
        if matches.empty:
            st.warning(f'"{search_query}" ile eşleşen öğrenci bulunamadı.')
        else:
            unique_students = matches[["student_no", "student_name"]].drop_duplicates()
            if len(unique_students) > 1:
                pick_options = {
                    f"{r['student_name']} ({r['student_no']})": str(r["student_no"])
                    for _, r in unique_students.iterrows()
                }
                picked = st.selectbox("Birden fazla sonuç bulundu, seçin", list(pick_options.keys()), key="search_pick")
                picked_no = pick_options[picked]
            else:
                picked_no = str(unique_students.iloc[0]["student_no"])

            stu_rows = roster[roster["student_no"].str.strip() == picked_no.strip()]
            if stu_rows.empty:
                st.error("Öğrenci kaydı bulunamadı.")
            else:
                _render_student_detail(conn, roster, stu_rows, picked_no)

    # ── Leader assignment ─────────────────────────────────────────────────────
    section_header("👑", "Proje Lideri Atama")
    project_name = st.selectbox("Proje seçin", projects, key="advisor_project_pick")
    members = roster[roster["project_name"] == project_name].sort_values("row_no")
    options = {f"{r['student_name']} ({r['student_no']})": str(r["student_no"]) for _, r in members.iterrows()}
    current_leader = get_leader(conn, project_name)
    labels = list(options.keys())
    default_idx = 0
    if current_leader:
        for i, lbl in enumerate(labels):
            if options[lbl] == current_leader:
                default_idx = i
                break
    with st.form("leader_assign_form"):
        label = st.selectbox("Lider adayı", labels, index=default_idx)
        submitted = st.form_submit_button("👑 Lideri Kaydet",width="stretch")
    if submitted:
        leader_no = options[label]
        set_leader(conn, project_name, leader_no, advisor_name)
        upsert_role(conn, project_name, leader_no, "Lider", "Danışman tarafından atanmış lider")
        st.success("Lider güncellendi.")
        st.rerun()

    # ── CSV upload ────────────────────────────────────────────────────────────
    section_header("📤", "CSV Yükleme", "Öğrenci listesini CSV dosyasıyla güncelleyin")
    with st.expander("CSV Yükle / Güncelle"):
        uploaded_csv = st.file_uploader("CSV dosyası seçin", type=["csv"], key="advisor_csv_upload")
        if uploaded_csv is not None:
            try:
                new_roster = load_roster_from_upload(uploaded_csv)
                st.dataframe(new_roster,width="stretch", hide_index=True)
                st.caption(f"{len(new_roster)} öğrenci kaydı bulundu.")
                if st.button("✅ Öğrenci Listesini Güncelle", key="apply_csv_btn"):
                    count = upsert_students(conn, new_roster)
                    sync_auth_users(conn)
                    bootstrap_defaults(conn, new_roster)
                    initialize_all_projects(conn, new_roster)
                    st.cache_data.clear()
                    st.success(f"{count} öğrenci kaydı güncellendi.")
                    st.rerun()
            except Exception as e:
                st.error(f"CSV okuma hatası: {e}")

    # ── Add single student ────────────────────────────────────────────────────
    section_header("➕", "Tek Öğrenci Ekleme")
    _render_add_student_form(conn, roster, advisor_name)

    # ── Password reset ────────────────────────────────────────────────────────
    section_header("🔑", "Şifre Sıfırlama")
    _render_password_reset(conn, roster)

    # ── Project detail / task management ─────────────────────────────────────
    section_header("🗂️", "Proje Detayı & Görev Yönetimi")
    _render_project_detail(conn, roster, projects, advisor_name)


# ── Private helpers ────────────────────────────────────────────────────────────

def _render_student_detail(conn, roster, stu_rows, picked_no: str) -> None:
    from db import fetch_df
    stu_info = stu_rows.iloc[0]
    stu_name = str(stu_info["student_name"])
    stu_project = str(stu_info["project_name"])
    leader_no = get_leader(conn, stu_project)
    is_stu_leader = leader_no == picked_no

    role_df = fetch_df(conn, "SELECT student_no, role, responsibility FROM member_roles WHERE project_name = ?", (stu_project,))
    stu_role_row = role_df[role_df["student_no"] == picked_no]
    stu_role = str(stu_role_row.iloc[0]["role"]) if not stu_role_row.empty else "Atanmadı"
    stu_resp = str(stu_role_row.iloc[0]["responsibility"]) if not stu_role_row.empty else "—"

    role_badge = "👑 Lider" if is_stu_leader else f"👤 {stu_role}"
    role_bg = "#fef3c7" if is_stu_leader else "#dbeafe"
    role_color = "#92400e" if is_stu_leader else "#1e40af"

    st.markdown(
        f"""
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;
                    padding:1rem 1.2rem;margin:0.75rem 0;">
            <div style="display:flex;align-items:center;gap:0.75rem;margin-bottom:0.6rem;">
                <div style="width:42px;height:42px;background:linear-gradient(135deg,#0a2342,#1a3a6b);
                            border-radius:50%;display:flex;align-items:center;justify-content:center;
                            font-size:1.1rem;flex-shrink:0;">🎓</div>
                <div>
                    <div style="font-weight:700;font-size:1rem;color:#0a2342;">{stu_name}</div>
                    <div style="font-size:0.73rem;color:#64748b;">{picked_no} &nbsp;·&nbsp; {stu_project}</div>
                </div>
                <span style="background:{role_bg};color:{role_color};border-radius:999px;
                             padding:.15em .7em;font-size:.73rem;font-weight:700;margin-left:auto;">
                    {role_badge}
                </span>
            </div>
            <div style="font-size:0.77rem;color:#475569;border-top:1px solid #e2e8f0;padding-top:0.5rem;">
                📌 {stu_resp} &nbsp;·&nbsp; 🎓 {stu_info.get('program', '—')}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    stu_tasks = fetch_tasks(conn, stu_project)
    my_tasks = stu_tasks[stu_tasks["assignee_student_no"] == picked_no]

    c5, c6, c7 = st.columns(3)
    c5.metric("Atanan Görev", len(my_tasks))
    c6.metric("Tamamlanan", int((my_tasks["status"] == "DONE").sum()) if not my_tasks.empty else 0)
    c7.metric("İlerleme", f"%{completion_percent(my_tasks)}")

    if not my_tasks.empty:
        st.markdown("**Görev Durumu (Milestone Bazlı):**")
        task_table = my_tasks.copy()
        task_table["Milestone"] = task_table["milestone_key"].map(MILESTONE_LABELS)
        task_table["Durum"] = task_table["status"].map(status_tr)
        task_table["Deadline"] = task_table["deadline"].replace("", "—").fillna("—")
        st.dataframe(
            task_table[["id", "Milestone", "title", "Durum", "priority", "Deadline", "evidence_link"]].rename(
                columns={"id": "ID", "title": "Görev", "priority": "Öncelik", "evidence_link": "Kanıt"}
            ),
            width="stretch", hide_index=True,
        )
        for _, t in my_tasks.iterrows():
            ef = str(t.get("evidence_file", "") or "")
            if ef:
                with st.expander(f"Kanıt dosyası: #{int(t['id'])} - {t['title']}"):
                    render_evidence_file(ef)
    else:
        st.info("Bu öğrenciye atanmış görev yok.")

    team = roster[roster["project_name"] == stu_project].sort_values("row_no")
    render_member_table(team, role_df, leader_no)

    stu_weekly = fetch_weekly_updates_for_project(conn, stu_project, picked_no)
    if not stu_weekly.empty:
        st.markdown("**Haftalık Giriş Geçmişi:**")
        st.dataframe(
            stu_weekly[["week_start", "completed", "blockers", "next_step", "evidence_link", "created_at"]].rename(
                columns={"week_start": "Hafta", "completed": "Yapılanlar", "blockers": "Engeller",
                         "next_step": "Sonraki Adım", "evidence_link": "Kanıt", "created_at": "Tarih"}
            ),
            width="stretch", hide_index=True,
        )

    stu_fb = fetch_feedbacks(conn, stu_project)
    if not stu_fb.empty:
        st.markdown("**Projeye Verilen Geri Bildirimler:**")
        for _, fb in stu_fb.iterrows():
            render_feedback_card(fb)


def _render_add_student_form(conn, roster, advisor_name: str) -> None:
    from models import add_single_student
    with st.expander("➕ Yeni Öğrenci Ekle"):
        existing_projects = sorted(roster["project_name"].unique().tolist()) if not roster.empty else []
        with st.form("add_single_student_form"):
            new_student_no = st.text_input("Öğrenci No", placeholder="2001234567")
            new_student_name = st.text_input("Ad Soyad")
            use_existing_project = st.checkbox("Mevcut bir projeye ekle", value=True)
            if use_existing_project and existing_projects:
                new_project_name = st.selectbox("Mevcut proje seç", existing_projects, key="existing_proj_select")
            else:
                new_project_name = st.text_input("Yeni proje adı")
            new_program = st.text_input("Program", value="")
            add_student_submit = st.form_submit_button("✅ Öğrenciyi Ekle",width="stretch")
        if add_student_submit:
            if not new_student_no.strip():
                st.error("Öğrenci no boş olamaz.")
            elif not new_student_name.strip():
                st.error("Öğrenci adı boş olamaz.")
            elif not new_project_name.strip():
                st.error("Proje adı boş olamaz.")
            else:
                existing_check = conn.execute(
                    "SELECT COUNT(*) AS cnt FROM students WHERE student_no = ? AND project_name = ?",
                    (new_student_no.strip(), new_project_name.strip()),
                ).fetchone()["cnt"]
                if int(existing_check) > 0:
                    st.error(f"{new_student_no} numaralı öğrenci zaten '{new_project_name}' projesinde kayıtlı.")
                else:
                    add_single_student(conn, new_student_no, new_student_name, new_project_name, advisor_name, new_program)
                    updated_roster = get_roster_from_db(conn, advisor_name)
                    sync_auth_users(conn)
                    bootstrap_defaults(conn, updated_roster)
                    initialize_all_projects(conn, updated_roster)
                    st.cache_data.clear()
                    st.success(f"{new_student_name} ({new_student_no}) başarıyla '{new_project_name}' projesine eklendi.")
                    st.rerun()


def _render_password_reset(conn, roster) -> None:
    with st.expander("🔑 Şifre Sıfırla"):
        st.markdown(
            "<div style='font-size:0.78rem;color:#64748b;margin-bottom:0.5rem;'>"
            "Seçilen kullanıcının şifresi <code>12345</code>'e sıfırlanır ve ilk girişte değiştirmesi zorunlu olur."
            "</div>",
            unsafe_allow_html=True,
        )
        reset_role_label = st.selectbox("Kullanıcı türü", ["🎓 Öğrenci", "👨‍🏫 Danışman"], key="pwd_reset_role")
        reset_role = "student" if "Öğrenci" in reset_role_label else "advisor"
        if reset_role == "student":
            student_list = roster[["student_no", "student_name"]].drop_duplicates().sort_values("student_name")
            if student_list.empty:
                st.info("Sıfırlanacak öğrenci yok.")
            else:
                reset_options = {
                    f"{r['student_name']} ({r['student_no']})": str(r["student_no"])
                    for _, r in student_list.iterrows()
                }
                selected_reset_user = st.selectbox("Öğrenci seçin", list(reset_options.keys()), key="pwd_reset_student")
                reset_user_id = reset_options[selected_reset_user]
                if st.button("🔑 Şifreyi Sıfırla", key="pwd_reset_btn_student"):
                    ok = reset_password_to_default(conn, reset_user_id, "student")
                    st.success(f"{selected_reset_user} şifresi sıfırlandı.") if ok else st.error("Kullanıcı bulunamadı.")
        else:
            from db import fetch_df
            advisor_list = fetch_df(
                conn, "SELECT user_id, display_name FROM auth_users WHERE role = 'advisor' AND is_active = 1 ORDER BY display_name"
            )
            if advisor_list.empty:
                st.info("Sıfırlanacak danışman yok.")
            else:
                adv_reset_options = {str(r["display_name"]): str(r["user_id"]) for _, r in advisor_list.iterrows()}
                selected_adv_reset = st.selectbox("Danışman seçin", list(adv_reset_options.keys()), key="pwd_reset_advisor")
                reset_adv_id = adv_reset_options[selected_adv_reset]
                if st.button("🔑 Şifreyi Sıfırla", key="pwd_reset_btn_advisor"):
                    ok = reset_password_to_default(conn, reset_adv_id, "advisor")
                    st.success(f"{selected_adv_reset} şifresi sıfırlandı.") if ok else st.error("Kullanıcı bulunamadı.")


def _render_project_detail(conn, roster, projects, advisor_name: str) -> None:
    detail_project = st.selectbox("Detay görüntülenecek proje", projects, key="advisor_detail_project")
    project_members = roster[roster["project_name"] == detail_project]
    tasks_df = fetch_tasks(conn, detail_project)

    c1, c2, c3 = st.columns(3)
    c1.metric("Toplam Görev", len(tasks_df))
    c2.metric("Tamamlanma", f"%{completion_percent(tasks_df)}")
    c3.metric("Geciken Görev", overdue_count(tasks_df))

    from db import fetch_df
    roles_df = fetch_df(conn, "SELECT student_no, role, responsibility FROM member_roles WHERE project_name = ?", (detail_project,))
    leader_no = get_leader(conn, detail_project)
    render_member_table(project_members, roles_df, leader_no)
    render_milestone_progress(tasks_df)

    if not tasks_df.empty:
        table = tasks_df.copy()
        table["Milestone"] = table["milestone_key"].map(MILESTONE_LABELS)
        table["Durum"] = table["status"].map(status_tr)
        table["deadline"] = table["deadline"].replace("", "—").fillna("—")
        st.dataframe(
            table[["id", "Milestone", "title", "assignee_student_no", "Durum", "priority", "deadline", "evidence_link"]],
            width="stretch", hide_index=True,
        )

    if not tasks_df.empty:
        section_header("✏️", "Görev Durumu Güncelleme")
        task_options_adv = {
            f"#{int(r['id'])} [{status_tr(r['status'])}] {r['title']}": int(r["id"])
            for _, r in tasks_df.iterrows()
        }
        selected_task_adv = st.selectbox("Görev seçin", list(task_options_adv.keys()), key="advisor_task_select")
        adv_task_id = task_options_adv[selected_task_adv]
        adv_task_row = tasks_df[tasks_df["id"] == adv_task_id].iloc[0]
        render_active_task_card(adv_task_row, MILESTONE_LABELS.get(str(adv_task_row["milestone_key"]), ""))

        adv_status_options = allowed_status_options(str(adv_task_row["status"]))
        adv_status_idx = adv_status_options.index(adv_task_row["status"]) if adv_task_row["status"] in adv_status_options else 0
        with st.form(f"advisor_task_update_form_{detail_project}"):
            adv_new_status = st.selectbox("Yeni durum", adv_status_options, index=adv_status_idx, format_func=status_tr)
            adv_evidence = st.text_input("Kanıt linki", value=adv_task_row["evidence_link"] or "")
            adv_task_submit = st.form_submit_button("💾 Görevi Güncelle",width="stretch")
        adv_evidence_upload = st.file_uploader(
            "Kanıt dosyası yükle (resim, PDF vb.)",
            type=["png", "jpg", "jpeg", "gif", "webp", "pdf", "docx", "zip"],
            key=f"adv_evidence_file_{detail_project}",
        )
        existing_adv_file = str(adv_task_row.get("evidence_file", "") or "")
        if existing_adv_file:
            with st.expander("Mevcut kanıt dosyası"):
                render_evidence_file(existing_adv_file)
        if adv_task_submit:
            file_path = ""
            if adv_evidence_upload is not None:
                file_path = save_uploaded_evidence(adv_evidence_upload, adv_task_id)
            ok, msg = update_task(conn, adv_task_id, adv_new_status, adv_evidence, skip_milestone_check=True, evidence_file=file_path)
            st.success("Görev güncellendi.") if ok else st.error(msg)
            if ok:
                st.rerun()

        section_header("💬", "Görev Yorumları")
        with st.expander(f"Yorumlar: #{adv_task_id} - {adv_task_row['title']}"):
            render_task_comments(conn, adv_task_id, detail_project, current_user_id=advisor_name,
                                 current_user_role="advisor", form_key_suffix=f"adv_{detail_project}")

    weekly_df = fetch_weekly_updates_for_project(conn, detail_project)
    if not weekly_df.empty:
        section_header("📅", "Haftalık Güncellemeler")
        name_map = dict(zip(project_members["student_no"].astype(str), project_members["student_name"].astype(str)))
        display_weekly = weekly_df.copy()
        display_weekly["Öğrenci"] = display_weekly["student_no"].map(name_map).fillna(display_weekly["student_no"])
        st.dataframe(
            display_weekly[["Öğrenci", "week_start", "completed", "blockers", "next_step", "evidence_link", "created_at"]].rename(
                columns={"week_start": "Hafta", "completed": "Yapılanlar", "blockers": "Engeller",
                         "next_step": "Sonraki Adım", "evidence_link": "Kanıt", "created_at": "Tarih"}
            ),
            width="stretch", hide_index=True,
        )

    section_header("📝", "Danışman Geri Bildirimi")
    with st.form("feedback_form"):
        feedback = st.text_area("Geri bildirim yazın", height=100)
        action_item = st.text_input("Aksiyon maddesi")
        revision_required = st.checkbox("Revizyon gerekli")
        fb_submit = st.form_submit_button("💾 Kaydet",width="stretch")
    if fb_submit:
        if not feedback.strip():
            st.error("Geri bildirim boş olamaz.")
        else:
            add_feedback(conn, detail_project, advisor_name, feedback, action_item, revision_required)
            st.success("Geri bildirim kaydedildi.")
            st.rerun()

    feedbacks_df = fetch_feedbacks(conn, detail_project)
    if not feedbacks_df.empty:
        section_header("🗃️", "Geçmiş Geri Bildirimler")
        for _, fb in feedbacks_df.iterrows():
            render_feedback_card(fb)
