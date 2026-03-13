
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

import streamlit as st

from constants import DB_PATH, DEFAULT_LANGUAGE, DEFAULT_PASSWORD, LANGUAGE_STATE_KEY, MIN_PASSWORD_LEN
from db import get_conn
from i18n import is_english_ui, patch_streamlit_i18n, render_language_selector
from models import (
    authenticate_user,
    bootstrap_defaults,
    clear_runtime_data,
    get_leader,
    get_roster_from_db,
    get_student_memberships,
    initialize_all_projects,
    student_count,
    sync_auth_users,
    update_password,
)
from panels.advisor import render_advisor_panel
from panels.leader import render_leader_panel
from panels.student import render_student_panel
from styles import inject_styles
from utils import is_admin_advisor


# ── Auth session helpers ───────────────────────────────────────────────────────

def clear_auth_session() -> None:
    st.session_state.pop("auth_user", None)
    # Track that sync has been done for this session
    st.session_state.pop("_sync_done", None)


def render_login_form(conn) -> None:
    # Centred login card
    st.markdown(
        """
        <div class="login-wrapper">
            <div class="login-logo">🎓</div>
            <div class="login-title">Bitirme Proje Takip</div>
            <div class="login-sub">OSTİM Teknik Üniversitesi · Yazılım Mühendisliği</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Narrow centred column for the form
    _, col, _ = st.columns([1, 2, 1])
    with col:
        role_label = st.selectbox(
            "Kullanici Turu",
            ["🎓  Öğrenci", "👨‍🏫  Danışman"],
            key="login_role",
        )
        role = "student" if "Öğrenci" in role_label else "advisor"

        if role == "student":
            user_id = st.text_input("Öğrenci No", placeholder="2001234567", key="login_student_no")
        else:
            from db import fetch_df
            advisor_df = fetch_df(
                conn,
                "SELECT user_id, display_name FROM auth_users WHERE role = 'advisor' AND is_active = 1 ORDER BY display_name",
            )
            if advisor_df.empty:
                st.error("Aktif danışman kullanıcısı bulunamadı.")
                return
            advisor_options = {str(row["display_name"]): str(row["user_id"]) for _, row in advisor_df.iterrows()}
            selected_label = st.selectbox("Danışman", list(advisor_options.keys()), key="login_advisor_select")
            user_id = advisor_options[selected_label]

        password = st.text_input("Şifre", type="password", placeholder="••••••••", key="login_password")
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("Giriş Yap →", type="primary",width="stretch"):
            auth = authenticate_user(conn, user_id=user_id.strip(), role=role, password=password)
            if not auth:
                st.error("Giriş bilgileri geçersiz. Lütfen tekrar deneyin.")
                return
            st.session_state["auth_user"] = auth
            st.rerun()

        st.markdown(
            f"<div style='text-align:center;margin-top:1rem;font-size:0.74rem;color:#64748b;'>"
            f"Ilk giris sifresi: <code>{DEFAULT_PASSWORD}</code><br>Giris sonrasi sifrenizi degistirmeniz zorunludur."
            "</div>",
            unsafe_allow_html=True,
        )


def enforce_password_change(conn, auth_user: dict) -> bool:
    """Return True if the user must change their password (blocks further rendering)."""
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
        elif new_password == DEFAULT_PASSWORD:
            st.error("Varsayilan sifreyi kullanamazsiniz.")
        elif new_password != confirm_password:
            st.error("Sifreler eslesmiyor.")
        else:
            try:
                update_password(conn, auth_user["user_id"], auth_user["role"], new_password)
                auth_user["force_password_change"] = False
                st.session_state["auth_user"] = auth_user
                st.success("Sifre guncellendi.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    return True


# ── Page header HTML ───────────────────────────────────────────────────────────

def _render_header() -> None:
    """Render the fixed top header bar. CSS is handled by styles.py."""
    header_university = "OSTİM Technical University" if is_english_ui() else "OSTİM Teknik Üniversitesi"
    header_department = "Software Engineering Department" if is_english_ui() else "Yazılım Mühendisliği Bölümü"
    header_system = "Capstone Project Tracking System" if is_english_ui() else "Bitirme Proje Takip Sistemi"

    st.markdown(
        f"""
        <div class="otu-header">
            <span class="otu-icon">🎓</span>
            <div class="otu-text-block">
                <span class="otu-uni">{header_university}</span>
                <span class="otu-dept">{header_department}</span>
            </div>
            <span class="otu-divider">{header_system}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    # Language default
    if LANGUAGE_STATE_KEY not in st.session_state:
        st.session_state[LANGUAGE_STATE_KEY] = DEFAULT_LANGUAGE

    # Page config (must be first Streamlit call)
    page_title = (
        "Capstone Project Tracking | OSTIM Technical University"
        if is_english_ui()
        else "Bitirme Proje Takip | OSTİM Teknik Üniversitesi"
    )
    st.set_page_config(page_title=page_title, page_icon="🎓", layout="wide")

    # Inject professional CSS theme (must come early)
    inject_styles()

    with st.sidebar:
        render_language_selector()

    patch_streamlit_i18n()
    _render_header()
    st.title("🗂️ Bitirme Proje Takip Uygulaması")

    # ── DB setup ──────────────────────────────────────────────────────────────
    db_path = DB_PATH
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

    # Bootstrap once per session (not on every rerun)
    if not st.session_state.get("_bootstrap_done"):
        bootstrap_defaults(conn, all_roster)
        initialize_all_projects(conn, all_roster)
        sync_auth_users(conn)
        st.session_state["_bootstrap_done"] = True

    # ── Auth routing ───────────────────────────────────────────────────────────
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

    # ── Advisor branch ─────────────────────────────────────────────────────────
    if auth_user["role"] == "advisor":
        selected_advisor = auth_user["user_id"]
        admin_mode = is_admin_advisor(selected_advisor)
        roster = get_roster_from_db(conn, selected_advisor)
        with st.sidebar:
            role_badge = "🛡️ Admin" if admin_mode else "👨‍🏫 Danışman"
            st.markdown(
                f"""
                <div style="background:#ffffff;border:1px solid #dbe5ef;border-radius:8px;padding:0.7rem 0.8rem;margin-bottom:0.5rem;box-shadow:0 1px 4px rgba(15,23,42,0.06);">
                    <div style="font-size:0.7rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Oturum</div>
                    <div style="font-size:0.88rem;font-weight:700;color:#0f172a;margin-top:0.2rem;">{selected_advisor}</div>
                    <div style="margin-top:0.3rem;"><span style="background:{'#fef3c7' if admin_mode else '#dbeafe'};color:{'#92400e' if admin_mode else '#1d4ed8'};border-radius:999px;padding:0.1em 0.6em;font-size:0.7rem;font-weight:700;">{role_badge}</span></div>
                    <div style="margin-top:0.4rem;font-size:0.73rem;color:#64748b;">👥 {len(roster)} öğrenci &nbsp;·&nbsp; 📁 {roster['project_name'].nunique() if not roster.empty else 0} proje</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            reset = False
            clear_runtime = False
            if admin_mode:
                with st.expander("⚠️ Veritabanı Sıfırlama"):
                    st.warning("Bu işlem tüm verileri silecektir!")
                    confirm_reset = st.checkbox("Veritabanını silmek istediğimden eminm", key="reset_confirm")
                    reset = st.button("Veritabanını Sıfırla", disabled=not confirm_reset)
                    st.markdown("---")
                    st.info("Bu islem ogrenci ve danisman kayitlarini korur; sadece gorev, haftalik guncelleme, geri bildirim ve yorum verilerini temizler.")
                    confirm_runtime_clear = st.checkbox(
                        "Deneme verilerini temizlemek istedigimden eminim",
                        key="runtime_clear_confirm",
                    )
                    clear_runtime = st.button(
                        "Deneme Verilerini Temizle",
                        disabled=not confirm_runtime_clear,
                    )
            if st.button("🚪 Çıkış Yap",width="stretch"):
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

        if clear_runtime:
            db_file = Path(db_path)
            backup_name = f"project_tracker.runtime-clear.{datetime.now().strftime('%Y%m%d_%H%M%S')}.backup.db"
            if db_file.exists():
                shutil.copy2(db_file, db_file.parent / backup_name)
            clear_runtime_data(conn)
            st.cache_data.clear()
            st.success(f"Deneme verileri temizlendi. Yedek: {backup_name}")
            st.rerun()

        render_advisor_panel(conn, selected_advisor, roster)
        return

    # ── Student branch ─────────────────────────────────────────────────────────
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
    if len(project_labels) > 1:
        selected_project_label = st.selectbox("Projelerim", project_labels)
        selected_idx = project_labels.index(selected_project_label)

    selected_membership = memberships.iloc[selected_idx]
    selected_project = str(selected_membership["project_name"])
    selected_advisor = str(selected_membership["advisor_name"])
    advisor_roster = get_roster_from_db(conn, selected_advisor)
    project_roster = advisor_roster[advisor_roster["project_name"] == selected_project].copy()

    is_leader = get_leader(conn, selected_project) == student_no
    role_label = "👑 Lider" if is_leader else "🎓 Üye"
    with st.sidebar:
        st.markdown(
            f"""
            <div style="background:#ffffff;border:1px solid #dbe5ef;border-radius:8px;padding:0.7rem 0.8rem;margin-bottom:0.5rem;box-shadow:0 1px 4px rgba(15,23,42,0.06);">
                <div style="font-size:0.7rem;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.05em;">Oturum</div>
                <div style="font-size:0.88rem;font-weight:700;color:#0f172a;margin-top:0.2rem;">{auth_user['display_name']}</div>
                <div style="font-size:0.73rem;color:#64748b;margin-top:0.1rem;">{student_no}</div>
                <div style="margin-top:0.3rem;"><span style="background:#dbeafe;color:#1d4ed8;border-radius:999px;padding:0.1em 0.6em;font-size:0.7rem;font-weight:700;">{role_label}</span></div>
                <div style="margin-top:0.4rem;font-size:0.73rem;color:#64748b;">📁 {selected_project}</div>
                <div style="font-size:0.7rem;color:#475569;">👨‍🏫 {selected_advisor}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚪 Çıkış Yap",width="stretch"):
            clear_auth_session()
            st.rerun()

    # ── Route by role ─────────────────────────────────────────────────────────
    # Leaders go directly to the leader panel — no toggle. Regular students
    # are strictly limited to the student panel (no leader panel access).
    if is_leader:
        render_leader_panel(
            conn, project_roster,
            fixed_project_name=selected_project,
            fixed_leader_no=student_no,
        )
    else:
        render_student_panel(
            conn, advisor_roster,
            fixed_student_no=student_no,
            fixed_project_name=selected_project,
        )


if __name__ == "__main__":
    main()
