"""
i18n.py
Internationalisation: language selection, translation loading, Streamlit patching.
"""
from __future__ import annotations

import json
import re
from typing import Optional

import pandas as pd
import streamlit as st
from streamlit.delta_generator import DeltaGenerator

from constants import (
    DEFAULT_LANGUAGE,
    LANGUAGE_OPTIONS,
    LANGUAGE_STATE_KEY,
    STATUS_LABELS_EN,
    TRANSLATION_FILE,
)

# ── Translation data ───────────────────────────────────────────────────────────

TRANSLATION_OVERRIDES_TR_EN: dict[str, str] = {
    # ── Login / auth ──────────────────────────────────────────────────────────
    "Giris": "Login",
    "Cikis yap": "Log out",
    "Kullanici Turu": "User Type",
    "Öğrenci No": "Student No",
    # ── Panel headers ─────────────────────────────────────────────────────────
    "Danisman paneli:": "Advisor panel:",
    "Danisman paneli: ": "Advisor panel: ",
    "Giris yapan:": "Logged in:",
    "Giris yapan danisman:": "Logged in advisor:",
    "Giris yapan ogrenci:": "Logged in student:",
    "Secili proje:": "Selected project:",
    "Yetki:": "Role:",
    "Ogrenci paneli": "Student panel",
    "Öğrenci Paneli": "Student Panel",
    "Grup Lider Paneli": "Group Leader Panel",
    "Grup Yoneticisi": "Group Leader",
    "Grup yoneticisi paneli": "Group leader panel",
    "Danışman Paneli": "Advisor Panel",
    "Gorunum": "View",
    # ── Section headers ───────────────────────────────────────────────────────
    "Proje Genel Bakışı": "Project Overview",
    "Proje Özeti": "Project Summary",
    "Tüm projelerin tamamlanma, gecikme ve risk durumu": "Completion, delay, and risk status for all projects",
    "Öğrenci Arama": "Student Search",
    "Ad veya numara ile arayın": "Search by name or number",
    "Proje Lideri Atama": "Project Leader Assignment",
    "CSV Yükleme": "CSV Upload",
    "Öğrenci listesini CSV dosyasıyla güncelleyin": "Update the student list with a CSV file",
    "Tek Öğrenci Ekleme": "Add Single Student",
    "Şifre Sıfırlama": "Password Reset",
    "Proje Detayı & Görev Yönetimi": "Project Details & Task Management",
    "Danışman Geri Bildirimi": "Advisor Feedback",
    "Danışman Geri Bildirimleri": "Advisor Feedback",
    "Geçmiş Geri Bildirimler": "Past Feedback",
    "Haftalık Güncellemeler": "Weekly Updates",
    "Görev Durumu Güncelleme": "Task Status Update",
    "Görev Yorumları": "Task Comments",
    "Milestone İlerlemesi": "Milestone Progress",
    "Takım Üyeleri": "Team Members",
    "Takım Üyeleri & Roller": "Team Members & Roles",
    "Rol Atama": "Role Assignment",
    "Takım üyelerine rol ve görev tanımı atayın": "Assign roles and duties to team members",
    "Yeni Görev Oluştur": "Create New Task",
    "Milestone bazlı görev planlayın ve üyeye atayın": "Plan milestone tasks and assign to a member",
    "Görev Takibi": "Task Tracking",
    "Tüm görevleri görüntüleyin ve durumlarını güncelleyin": "View all tasks and update their status",
    "Görev Güncelle": "Update Task",
    "Üye İlerleme Özeti": "Member Progress Summary",
    "Üye Şifre Sıfırlama": "Member Password Reset",
    "Şifreyi unutan takım arkadaşınızın şifresini sıfırlayın": "Reset password for a team member who forgot it",
    "Geçmiş Haftalık Girişlerim": "My Past Weekly Updates",
    "Haftalık İlerleme Girişi": "Weekly Progress Entry",
    "Bu haftaki çalışmalarınızı kaydedin": "Record your work for this week",
    "Gruplar Arası Karşılaştırma": "Group Comparison",
    "Projenizin diğer gruplar arasındaki konumu": "Your project's ranking among other groups",
    "Milestone sırasına göre aktif göreviniz": "Your active task by milestone order",
    "Görev Sıram": "My Task Queue",
    # ── Metric labels ─────────────────────────────────────────────────────────
    "Proje Görevi": "Project Tasks",
    "Proje Tamamlanma": "Project Completion",
    "Benim Görevim": "My Tasks",
    "Benim İlerlemem": "My Progress",
    "Toplam Görev": "Total Tasks",
    "Tamamlanma": "Completion",
    "Geciken Görev": "Overdue Tasks",
    "Geciken": "Overdue",
    "kişisel ilerleme": "personal progress",
    "tamamlandı": "completed",
    "Proje": "Project",   # standalone metric label
    "Üye": "Member",
    # ── Table column headers ──────────────────────────────────────────────────
    "Ad Soyad": "Full Name",
    "No": "No",
    "Görev": "Task",
    "Sorumlu": "Assignee",
    "Sorumlu Üye": "Assignee",
    "Durum": "Status",
    "Deadline": "Deadline",
    "Milestone": "Milestone",
    "Öncelik": "Priority",
    "Kanıt": "Evidence",
    # ── Form labels ───────────────────────────────────────────────────────────
    "Üye Seç": "Select Member",
    "Üye seçin": "Select Member",
    "Rol": "Role",
    "Görev Tanımı": "Task Definition",
    "Görev Başlığı": "Task Title",
    "Kısa ve açıklayıcı bir başlık": "Short and descriptive title",
    "Açıklama": "Description",
    "Deadline yok": "No deadline",
    "Bağımlılık": "Dependency",
    "İstenen Kanıt": "Required Evidence",
    "Repo linki veya rapor": "Repo link or report",
    "Düzenlenecek görev": "Task to edit",
    "Kanıt linki (repo, rapor, vs.)": "Evidence link (repo, report, etc.)",
    "Kanıt dosyası yükle (resim, PDF vb.)": "Upload evidence file (image, PDF, etc.)",
    "Mevcut kanıt dosyası": "Existing evidence file",
    "Şifreyi unutan takım arkadaşınızın şifresini sıfırlayın": "Reset password for a team member who forgot it",
    "Şifresi sıfırlanacak üye": "Member to reset",
    "Bu üyenin şifresinin sıfırlanacağını onaylıyorum": "I confirm this member's password will be reset",
    "Şifreyi Sıfırla": "Reset Password",
    "🔑 Şifreyi Sıfırla": "🔑 Reset Password",
    "şifresi sıfırlandı.": "password was reset.",
    "Sıfırlama başarısız.": "Reset failed.",
    "Bu proje için lider paneline erişim yetkiniz yok.": "You do not have leader panel access for this project.",
    "Lider ataması yok. Danışman panelinden atayın.": "No leader assigned. Set one from the advisor panel.",
    "Bu proje için henüz görev yok.": "No tasks yet for this project.",
    "Tüm milestone görevlerini tamamladınız!": "All milestone tasks completed!",
    "Aktif Görev": "Active Task",
    # ── Buttons ───────────────────────────────────────────────────────────────
    "💾 Rolü Kaydet": "💾 Save Role",
    "✅ Görevi Oluştur": "✅ Create Task",
    "💾 Güncelle": "💾 Update",
    "💾 Görevi Kaydet": "💾 Save Task",
    "💾 Kaydet": "💾 Save",
    "📅 Haftalık Girişi Kaydet": "📅 Save Weekly Update",
    "💬 Yorum Ekle": "💬 Add Comment",
    "Yorumlar": "Comments",
    # ── Badges / labels ───────────────────────────────────────────────────────
    "Atanmadı": "Unassigned",
    "Revizyon": "Revision",
    "Revizyon İste": "Revision Required",
    "Aksiyon": "Action Item",
    "Yapılanlar": "Completed Work",
    "Engeller": "Blockers",
    "Sonraki Adım": "Next Step",
    "Hafta": "Week",
    "Tarih": "Date",
    "Rol güncellendi.": "Role updated.",
    "Görev oluşturuldu.": "Task created.",
    "Görev güncellendi.": "Task updated.",
    # ── Existing entries (kept for compatibility) ─────────────────────────────
    "Giris yapan danisman:": "Logged in advisor:",
    "Secili proje:": "Selected project:",
    "### Gorev durumu guncelleme": "### Task status update",
    "### Gorev yorumlari": "### Task comments",
    "#### Gorev yorumlari": "#### Task comments",
    "**Gorev Durumu (Milestone Bazli):**": "**Task Status (By Milestone):**",
    "Gorev basligi": "Task title",
    "Gorev basligi gerekli.": "Task title is required.",
    "Gorev eklendi.": "Task added.",
    "Gorev guncellendi.": "Task updated.",
    "Gorev bulunamadi.": "Task not found.",
    "Goreviniz guncellendi.": "Your task has been updated.",
    "Yeni durum": "New status",
    "Kullanici turu": "User type",
    "Yok": "None",
    "Uye": "Member",
    "Tamamlanan": "Completed",
    "Geciken Gorev": "Overdue Tasks",
    "Tamamlanma %": "Completion %",
    "Son 14 Gun Aktivite": "Last 14 Days Activity",
    "Sira": "Rank",
    "Sifreyi sifirla": "Reset password",
    "Sifreyi guncelle": "Update password",
    "Ilgili gorev": "Related task",
    "Hafta baslangici": "Week start",
    "Yapilanlar": "Completed work",
    "Kanit link": "Evidence link",
    "Kanit linki": "Evidence link",
    "Haftalik girisi kaydet": "Save weekly update",
    "Kendi gorevim": "My tasks",
    "Kendi ilerleme": "My progress",
    "Proje gorev": "Project tasks",
    "Proje tamamlanma": "Project completion",
    "Lider adayi": "Leader candidate",
    "Acilis ozeti: proje + bireysel ilerleme": "Overview: project + individual progress",
    "Acilis ozeti: proje + lider ilerleme": "Overview: project + leader progress",
    "Acilis ozeti: tum projelerin durumu": "Overview: all projects status",
    "Dusuk": "Low",
    "Orta": "Medium",
    "Yuksek": "High",
    "Bitirme Proje Takip | OSTİM Teknik Üniversitesi": "Capstone Project Tracking | OSTIM Technical University",
    "🗂️ Bitirme Proje Takip Uygulaması": "🗂️ Capstone Project Tracking App",
}

SEGMENT_TRANSLATIONS_TR_EN: list[tuple[str, str]] = [
    ("Bitirme Proje Takip Uygulamasi", "Capstone Project Tracking App"),
    ("Bitirme Proje Takip Uygulaması", "Capstone Project Tracking App"),
    ("Bitirme Proje Takip Sistemi", "Capstone Project Tracking System"),
    ("OSTİM Teknik Üniversitesi", "OSTIM Technical University"),
    ("Yazılım Mühendisliği Bölümü", "Software Engineering Department"),
    ("Danisman paneli", "Advisor panel"),
    ("Danışman paneli", "Advisor panel"),
    ("Giris yapan danisman:", "Logged in advisor:"),
    ("Giris yapan ogrenci:", "Logged in student:"),
    ("Giris yapan:", "Logged in:"),
    ("Secili proje:", "Selected project:"),
    ("Veritabani:", "Database:"),
    ("Veritabani sifirlandi. Yedek:", "Database reset. Backup:"),
    ("Sifre en az ", "Password must be at least "),
    (" karakter olmali.", " characters."),
    (" ile eslesen ogrenci bulunamadi.", " matched student not found."),
    (" numarali ogrenci zaten '", " student number is already registered in project '"),
    ("' projesinde kayitli.", "'."),
    (" basariyla '", " successfully added to project '"),
    ("' projesine eklendi.", "'."),
    (" sifresi 12345 olarak sifirlandi.", " password was reset to 12345."),
    (" şifresi 12345 olarak sıfırlandı.", " password was reset to 12345."),
    (" grup icinde ", " among "),
    (". sirada.", "th place."),
    ("CSV okuma hatasi:", "CSV read error:"),
    ("Kanit dosyasi: #", "Evidence file: #"),
    (" | Gorev:", " | Task:"),
    ("Problem Tanimi, Amac ve Kapsamin Belirlenmesi", "Defining the Problem, Objectives, and Scope"),
    ("Alan Analizi, Literatur Taramasi ve Benzer Sistem Incelemesi", "Domain Analysis, Literature Review, and Similar System Review"),
    ("Yazilim Sureci ve Proje Yonetim Yapisinin Olusturulmasi", "Establishing the Software Process and Project Management Structure"),
    ("Gereksinim Analizi ve Sistem Ozelliklerinin Belirlenmesi", "Requirements Analysis and Identification of System Features"),
    ("Sistem Modellemesi ve Analiz Tasariminin Tamamlanmasi", "Completing System Modeling and Analysis Design"),
    ("Sistem Mimarisi ve Yazilim Tasariminin Olusturulmasi", "Designing the System Architecture and Software Design"),
    ("Uygulama Gelistirme ve MVP Surumunun Tamamlanmasi", "Application Development and Completion of the MVP Version"),
    ("Test, Dogrulama ve Iyilestirme Surecinin Tamamlanmasi", "Completion of the Testing, Validation, and Improvement Process"),
    ("Sonuclarin Degerlendirilmesi ve Final Tesliminin Hazirlanmasi", "Evaluation of Results and Preparation of the Final Submission"),
    (" ogrenci kaydi bulundu.", " student records found."),
    (" ogrenci kaydi guncellendi.", " student records updated."),
    ("Siradaki zorunlu gorev:", "Next required task:"),
]

TOKEN_TRANSLATIONS_TR_EN: dict[str, str] = {
    "Gorev": "Task", "gorev": "task",
    "Ogrenci": "Student", "ogrenci": "student",
    "Danisman": "Advisor", "danisman": "advisor",
    "Proje": "Project", "proje": "project",
    "Lider": "Leader", "lider": "leader",
    "Sifre": "Password", "sifre": "password",
    "Kanit": "Evidence", "kanit": "evidence",
    "Haftalik": "Weekly", "haftalik": "weekly",
    "Acilis": "Overview", "acilis": "overview",
    "Gecmis": "Past", "gecmis": "past",
    "Karsilastirma": "Comparison", "karsilastirma": "comparison",
    "Tamamlanma": "Completion", "tamamlanma": "completion",
    "Ilerleme": "Progress", "ilerleme": "progress",
    "Öğrenci": "Student", "öğrenci": "student",
    "Danışman": "Advisor", "danışman": "advisor",
    "Görev": "Task", "görev": "task",
    "Şifre": "Password", "şifre": "password",
}

TEXT_CLEANUPS_EN: list[tuple[str, str]] = [
    ("Quest", "Task"), ("quest", "task"),
    ("Mission", "Task"), ("mission", "task"),
    ("Entrance", "Login"),
    ("Open summary", "Overview"),
    ("Opening summary", "Overview"),
    ("Group admin panel", "Group leader panel"),
    ("Checked in by", "Logged in"),
    ("Checking in consultant", "Logged in advisor"),
    ("User tour", "User type"),
    ("new situation", "new status"),
    ("situation", "status"),
    ("proof link", "evidence link"),
    ("start of the week", "week start"),
    ("Spare", "Backup"),
    ("paneli", "panel"),
]

# ── Internal cache ─────────────────────────────────────────────────────────────
_TRANSLATIONS_CACHE: Optional[dict[str, str]] = None
_I18N_PATCHED = False


# ── Language helpers ───────────────────────────────────────────────────────────

def get_current_language() -> str:
    lang = str(st.session_state.get(LANGUAGE_STATE_KEY, DEFAULT_LANGUAGE))
    return lang if lang in {"tr", "en"} else DEFAULT_LANGUAGE


def is_english_ui() -> bool:
    return get_current_language() == "en"


def load_translations() -> dict[str, str]:
    global _TRANSLATIONS_CACHE
    if _TRANSLATIONS_CACHE is not None:
        return _TRANSLATIONS_CACHE
    mapping: dict[str, str] = {}
    if TRANSLATION_FILE.exists():
        try:
            raw = json.loads(TRANSLATION_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if isinstance(key, str) and isinstance(value, str) and value.strip():
                        mapping[key] = value
        except Exception:
            pass
    mapping.update(TRANSLATION_OVERRIDES_TR_EN)
    _TRANSLATIONS_CACHE = mapping
    return mapping


def translate_text_for_language(value: str, language: str) -> str:
    if language != "en" or not isinstance(value, str):
        return value
    text = value
    if "<style" in text or "</style>" in text or "<div" in text or "</div>" in text or "data-testid=" in text:
        return text
    direct = load_translations().get(text)
    if direct:
        text = direct
    for src, dst in SEGMENT_TRANSLATIONS_TR_EN:
        text = text.replace(src, dst)
    for src, dst in TOKEN_TRANSLATIONS_TR_EN.items():
        text = re.sub(rf"\b{re.escape(src)}\b", dst, text)
    for src, dst in TEXT_CLEANUPS_EN:
        if src.replace(" ", "").isalpha():
            text = re.sub(rf"\b{re.escape(src)}\b", dst, text)
        else:
            text = text.replace(src, dst)
    text = re.sub(r"\s{2,}", " ", text)
    return text


def translate_text(value: str) -> str:
    return translate_text_for_language(value, get_current_language())


def translate_dataframe(df: "pd.DataFrame") -> "pd.DataFrame":
    if not is_english_ui() or df.empty:
        return df
    translated = df.copy()
    translated.columns = [translate_text(str(col)) for col in translated.columns]
    for col in translated.columns:
        series = translated[col]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            translated[col] = series.map(lambda v: translate_text(v) if isinstance(v, str) else v)
    return translated


# ── Streamlit method patching ──────────────────────────────────────────────────

def patch_streamlit_i18n() -> None:
    global _I18N_PATCHED
    if _I18N_PATCHED:
        return

    def patch_callable(target: object, name: str, wrapper_factory) -> None:
        current = getattr(target, name, None)
        if current is None or getattr(current, "_i18n_patched", False):
            return
        wrapped = wrapper_factory(current)
        setattr(wrapped, "_i18n_patched", True)
        setattr(target, name, wrapped)

    def wrap_label_method(func, is_bound_method: bool):
        def wrapped(*args, **kwargs):
            args_list = list(args)
            label_index = 1 if is_bound_method else 0
            if len(args_list) > label_index and isinstance(args_list[label_index], str):
                args_list[label_index] = translate_text(args_list[label_index])
            elif isinstance(kwargs.get("label"), str):
                kwargs["label"] = translate_text(kwargs["label"])
            for key in ("help", "placeholder"):
                if isinstance(kwargs.get(key), str):
                    kwargs[key] = translate_text(kwargs[key])
            return func(*args_list, **kwargs)
        return wrapped

    def wrap_select_like_method(func, is_bound_method: bool):
        def wrapped(*args, **kwargs):
            args_list = list(args)
            label_index = 1 if is_bound_method else 0
            current_lang = get_current_language()
            if len(args_list) > label_index and isinstance(args_list[label_index], str):
                args_list[label_index] = translate_text_for_language(args_list[label_index], current_lang)
            elif isinstance(kwargs.get("label"), str):
                kwargs["label"] = translate_text_for_language(kwargs["label"], current_lang)
            raw_key = kwargs.get("key")
            if isinstance(raw_key, str):
                kwargs["key"] = f"{raw_key}__{current_lang}"
            if current_lang == "en":
                from utils import status_tr as _status_tr
                existing_format = kwargs.get("format_func")
                if existing_format is _status_tr:
                    kwargs["format_func"] = lambda option: STATUS_LABELS_EN.get(str(option), str(option))
                elif existing_format is None:
                    kwargs["format_func"] = lambda option, lang=current_lang: translate_text_for_language(str(option), lang)
                else:
                    kwargs["format_func"] = (
                        lambda option, inner=existing_format, lang=current_lang:
                            translate_text_for_language(str(inner(option)), lang)
                    )
            return func(*args_list, **kwargs)
        return wrapped

    def wrap_write_method(func, is_bound_method: bool):
        def wrapped(*args, **kwargs):
            args_list = list(args)
            start = 1 if is_bound_method else 0
            for idx in range(start, len(args_list)):
                value = args_list[idx]
                if isinstance(value, str):
                    args_list[idx] = translate_text(value)
                elif isinstance(value, pd.DataFrame):
                    args_list[idx] = translate_dataframe(value)
            return func(*args_list, **kwargs)
        return wrapped

    def wrap_dataframe_method(func, is_bound_method: bool):
        def wrapped(*args, **kwargs):
            args_list = list(args)
            data_index = 1 if is_bound_method else 0
            if len(args_list) > data_index and isinstance(args_list[data_index], pd.DataFrame):
                args_list[data_index] = translate_dataframe(args_list[data_index])
            elif isinstance(kwargs.get("data"), pd.DataFrame):
                kwargs["data"] = translate_dataframe(kwargs["data"])
            return func(*args_list, **kwargs)
        return wrapped

    def wrap_metric_method(func, is_bound_method: bool):
        def wrapped(*args, **kwargs):
            args_list = list(args)
            label_index = 1 if is_bound_method else 0
            value_index = 2 if is_bound_method else 1
            if len(args_list) > label_index and isinstance(args_list[label_index], str):
                args_list[label_index] = translate_text(args_list[label_index])
            elif isinstance(kwargs.get("label"), str):
                kwargs["label"] = translate_text(kwargs["label"])
            if len(args_list) > value_index and isinstance(args_list[value_index], str):
                args_list[value_index] = translate_text(args_list[value_index])
            elif isinstance(kwargs.get("value"), str):
                kwargs["value"] = translate_text(kwargs["value"])
            return func(*args_list, **kwargs)
        return wrapped

    for method_name in [
        "title", "header", "subheader", "caption", "markdown", "text",
        "success", "error", "warning", "info", "button", "checkbox",
        "text_input", "text_area", "file_uploader", "date_input",
        "form_submit_button", "download_button", "expander",
    ]:
        patch_callable(DeltaGenerator, method_name, lambda func: wrap_label_method(func, True))
        patch_callable(st, method_name, lambda func: wrap_label_method(func, False))

    for method_name in ["selectbox", "radio", "multiselect"]:
        patch_callable(DeltaGenerator, method_name, lambda func: wrap_select_like_method(func, True))
        patch_callable(st, method_name, lambda func: wrap_select_like_method(func, False))

    patch_callable(DeltaGenerator, "write", lambda func: wrap_write_method(func, True))
    patch_callable(st, "write", lambda func: wrap_write_method(func, False))
    patch_callable(DeltaGenerator, "dataframe", lambda func: wrap_dataframe_method(func, True))
    patch_callable(st, "dataframe", lambda func: wrap_dataframe_method(func, False))
    patch_callable(DeltaGenerator, "metric", lambda func: wrap_metric_method(func, True))
    patch_callable(st, "metric", lambda func: wrap_metric_method(func, False))
    _I18N_PATCHED = True


def render_language_selector() -> None:
    labels = list(LANGUAGE_OPTIONS.keys())
    current_lang = get_current_language()
    current_label = next((label for label, code in LANGUAGE_OPTIONS.items() if code == current_lang), labels[0])
    selected_label = st.radio(
        "Dil / Language",
        labels,
        index=labels.index(current_label),
        horizontal=True,
        key="ui_language_picker",
    )
    selected_lang = LANGUAGE_OPTIONS.get(selected_label, DEFAULT_LANGUAGE)
    if selected_lang != current_lang:
        st.session_state[LANGUAGE_STATE_KEY] = selected_lang
        st.rerun()
