"""
styles.py
Professional CSS theme for the Bitirme Proje Takip application.
Call inject_styles() once at app startup (in main()).
"""
from __future__ import annotations

import streamlit as st


def inject_styles() -> None:
    """Inject all custom CSS into the Streamlit page."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


GLOBAL_CSS = """
<style>
/* ═══════════════════════════════════════════════════════════════
   IMPORTS & ROOT VARIABLES
═══════════════════════════════════════════════════════════════ */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
    --primary:      #0a2342;
    --primary-mid:  #1a3a6b;
    --primary-light:#0f4c81;
    --accent:       #ffd700;
    --accent-soft:  #fff3b0;
    --success:      #16a34a;
    --success-bg:   #dcfce7;
    --warning:      #d97706;
    --warning-bg:   #fef3c7;
    --danger:       #dc2626;
    --danger-bg:    #fee2e2;
    --info:         #0369a1;
    --info-bg:      #e0f2fe;
    --surface:      #ffffff;
    --surface-alt:  #f8fafc;
    --border:       #e2e8f0;
    --border-dark:  #cbd5e1;
    --text-primary: #0f172a;
    --text-secondary:#475569;
    --text-muted:   #94a3b8;
    --radius:       12px;
    --radius-sm:    8px;
    --shadow-sm:    0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
    --shadow:       0 4px 6px rgba(0,0,0,0.07), 0 2px 4px rgba(0,0,0,0.05);
    --shadow-lg:    0 10px 25px rgba(0,0,0,0.1), 0 4px 10px rgba(0,0,0,0.06);
    --transition:   all 0.2s ease;
}

/* ═══════════════════════════════════════════════════════════════
   GLOBAL BASE
═══════════════════════════════════════════════════════════════ */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    color: var(--text-primary);
}

/* Remove Streamlit default top padding */
.block-container {
    padding-top: 1.5rem !important;
    padding-bottom: 3rem !important;
    max-width: 1200px;
}

/* ═══════════════════════════════════════════════════════════════
   HEADER BAND (fixed top)
═══════════════════════════════════════════════════════════════ */
.otu-header {
    position: fixed;
    top: 0; left: 0; right: 0;
    z-index: 999999;
    background: linear-gradient(90deg, #0a2342 0%, #1a3a6b 60%, #0f4c81 100%);
    padding: 0.6rem 2rem;
    display: flex;
    align-items: center;
    gap: 0.85rem;
    box-shadow: 0 2px 12px rgba(0,0,0,0.4);
    border-bottom: 2px solid var(--accent);
}
.otu-header .otu-icon { font-size: 1.6rem; line-height: 1; }
.otu-header .otu-text-block { display: flex; flex-direction: column; line-height: 1.25; }
.otu-header .otu-uni {
    font-size: 0.82rem; font-weight: 700;
    color: var(--accent); letter-spacing: 0.06em; text-transform: uppercase;
}
.otu-header .otu-dept {
    font-size: 0.71rem; font-weight: 400;
    color: #cce0ff; letter-spacing: 0.02em;
}
.otu-header .otu-divider {
    margin-left: auto; font-size: 0.72rem;
    color: #a8c8f0; font-style: italic; font-weight: 300;
}
[data-testid="stAppViewContainer"] > section:first-child { padding-top: 3.6rem !important; }
[data-testid="stHeader"] { top: 2.9rem !important; }

/* ═══════════════════════════════════════════════════════════════
   SIDEBAR
═══════════════════════════════════════════════════════════════ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a2342 0%, #0f3460 100%) !important;
    border-right: 1px solid rgba(255,215,0,0.2);
}
[data-testid="stSidebar"] * {
    color: #e2e8f0 !important;
}
[data-testid="stSidebar"] .stCaption {
    color: #a8c8f0 !important;
    font-size: 0.78rem !important;
    border-bottom: 1px solid rgba(255,255,255,0.08);
    padding-bottom: 0.35rem;
    margin-bottom: 0.35rem;
}
[data-testid="stSidebar"] .stRadio label {
    color: #e2e8f0 !important;
    font-size: 0.82rem !important;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    background: rgba(255,255,255,0.08) !important;
    color: #f1f5f9 !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: var(--radius-sm) !important;
    font-size: 0.82rem !important;
    transition: var(--transition) !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,215,0,0.15) !important;
    border-color: rgba(255,215,0,0.4) !important;
    color: var(--accent) !important;
}

/* ═══════════════════════════════════════════════════════════════
   PAGE TITLE
═══════════════════════════════════════════════════════════════ */
h1 {
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    color: var(--primary) !important;
    letter-spacing: -0.02em;
    margin-bottom: 1rem !important;
    padding-bottom: 0.6rem;
    border-bottom: 3px solid var(--accent);
    display: inline-block;
}

/* ═══════════════════════════════════════════════════════════════
   HEADINGS
═══════════════════════════════════════════════════════════════ */
h2 {
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    color: var(--primary) !important;
    margin-top: 1.5rem !important;
    margin-bottom: 0.75rem !important;
}
h3 {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    color: var(--primary-mid) !important;
    margin-top: 1.2rem !important;
    margin-bottom: 0.6rem !important;
    padding-left: 0.6rem;
    border-left: 3px solid var(--accent);
}
h4 {
    font-size: 0.92rem !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-top: 1rem !important;
}

/* ═══════════════════════════════════════════════════════════════
   METRIC CARDS
═══════════════════════════════════════════════════════════════ */
[data-testid="stMetric"] {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1rem 1.25rem !important;
    box-shadow: var(--shadow-sm);
    transition: var(--transition);
}
[data-testid="stMetric"]:hover {
    box-shadow: var(--shadow);
    border-color: var(--primary-light);
    transform: translateY(-1px);
}
[data-testid="stMetricLabel"] {
    font-size: 0.75rem !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}
[data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 700 !important;
    color: var(--primary) !important;
    line-height: 1.1 !important;
}

/* ═══════════════════════════════════════════════════════════════
   DATAFRAME / TABLE
═══════════════════════════════════════════════════════════════ */
[data-testid="stDataFrame"] {
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    overflow: hidden;
    box-shadow: var(--shadow-sm);
}
[data-testid="stDataFrame"] thead th {
    background: var(--primary) !important;
    color: #fff !important;
    font-weight: 600 !important;
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.6rem 0.8rem !important;
    border: none !important;
}
[data-testid="stDataFrame"] tbody tr:nth-child(even) {
    background: var(--surface-alt) !important;
}
[data-testid="stDataFrame"] tbody tr:hover {
    background: #e8f4fd !important;
}
[data-testid="stDataFrame"] tbody td {
    font-size: 0.83rem !important;
    padding: 0.5rem 0.8rem !important;
    border-bottom: 1px solid var(--border) !important;
    border-right: none !important;
}

/* ═══════════════════════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════════════════════ */
.stButton > button {
    border-radius: var(--radius-sm) !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    padding: 0.45rem 1.1rem !important;
    border: 1px solid var(--border-dark) !important;
    transition: var(--transition) !important;
    box-shadow: var(--shadow-sm) !important;
}
.stButton > button:hover {
    transform: translateY(-1px) !important;
    box-shadow: var(--shadow) !important;
}
.stButton > button[kind="primary"],
.stButton > button[type="primary"] {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%) !important;
    color: #fff !important;
    border-color: transparent !important;
}
.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, var(--primary-mid) 0%, var(--primary) 100%) !important;
}

/* ═══════════════════════════════════════════════════════════════
   FORM & INPUT FIELDS
═══════════════════════════════════════════════════════════════ */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea,
.stSelectbox > div > div > div {
    border-radius: var(--radius-sm) !important;
    border: 1.5px solid var(--border-dark) !important;
    font-size: 0.85rem !important;
    transition: var(--transition) !important;
    background: var(--surface) !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: var(--primary-light) !important;
    box-shadow: 0 0 0 3px rgba(15,76,129,0.12) !important;
    outline: none !important;
}
.stTextInput > label,
.stTextArea > label,
.stSelectbox > label,
.stDateInput > label,
.stFileUploader > label {
    font-size: 0.8rem !important;
    font-weight: 600 !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.2rem !important;
}
/* Form container */
[data-testid="stForm"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.25rem !important;
    box-shadow: var(--shadow-sm) !important;
}
/* Submit buttons */
[data-testid="stFormSubmitButton"] > button {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-light) 100%) !important;
    color: #fff !important;
    border: none !important;
    width: 100%;
    padding: 0.55rem 1rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
}
[data-testid="stFormSubmitButton"] > button:hover {
    background: linear-gradient(135deg, var(--primary-mid) 0%, var(--primary) 100%) !important;
}

/* ═══════════════════════════════════════════════════════════════
   ALERTS / CALLOUTS
═══════════════════════════════════════════════════════════════ */
[data-testid="stAlert"] {
    border-radius: var(--radius-sm) !important;
    border-left-width: 4px !important;
    font-size: 0.85rem !important;
}
/* Success */
.stSuccess {
    background: var(--success-bg) !important;
    border-color: var(--success) !important;
    color: #14532d !important;
}
/* Error */
.stError {
    background: var(--danger-bg) !important;
    border-color: var(--danger) !important;
    color: #7f1d1d !important;
}
/* Warning */
.stWarning {
    background: var(--warning-bg) !important;
    border-color: var(--warning) !important;
    color: #78350f !important;
}
/* Info */
.stInfo {
    background: var(--info-bg) !important;
    border-color: var(--info) !important;
    color: #0c4a6e !important;
}

/* ═══════════════════════════════════════════════════════════════
   PROGRESS BAR
═══════════════════════════════════════════════════════════════ */
[data-testid="stProgress"] > div {
    border-radius: 999px !important;
    height: 10px !important;
    background: var(--border) !important;
    overflow: hidden;
}
[data-testid="stProgress"] > div > div {
    background: linear-gradient(90deg, var(--primary-light) 0%, var(--accent) 100%) !important;
    border-radius: 999px !important;
    transition: width 0.6s ease !important;
}

/* ═══════════════════════════════════════════════════════════════
   EXPANDER
═══════════════════════════════════════════════════════════════ */
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-sm) !important;
    box-shadow: var(--shadow-sm) !important;
    overflow: hidden;
    margin-bottom: 0.5rem !important;
}
[data-testid="stExpander"] summary {
    background: var(--surface-alt) !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    color: var(--primary) !important;
    padding: 0.6rem 0.9rem !important;
    border-radius: 0 !important;
    transition: var(--transition) !important;
}
[data-testid="stExpander"] summary:hover {
    background: #e8f4fd !important;
}

/* ═══════════════════════════════════════════════════════════════
   RADIO / CHECKBOX
═══════════════════════════════════════════════════════════════ */
.stRadio > label, .stCheckbox > label {
    font-weight: 600 !important;
    font-size: 0.82rem !important;
    color: var(--text-secondary) !important;
    text-transform: uppercase;
    letter-spacing: 0.04em;
}

/* ═══════════════════════════════════════════════════════════════
   CAPTION / SMALL TEXT
═══════════════════════════════════════════════════════════════ */
.stCaption, small, [data-testid="stCaptionContainer"] {
    font-size: 0.76rem !important;
    color: var(--text-muted) !important;
    line-height: 1.5;
}

/* ═══════════════════════════════════════════════════════════════
   STATUS BADGE HELPERS  (use via st.markdown with unsafe_allow_html)
═══════════════════════════════════════════════════════════════ */
.badge {
    display: inline-block;
    padding: 0.18em 0.65em;
    border-radius: 999px;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    line-height: 1.4;
}
.badge-todo    { background: #e2e8f0; color: #475569; }
.badge-doing   { background: #dbeafe; color: #1e40af; }
.badge-done    { background: #dcfce7; color: #16a34a; }
.badge-low     { background: #dcfce7; color: #166534; }
.badge-medium  { background: #fef3c7; color: #92400e; }
.badge-high    { background: #fee2e2; color: #991b1b; }
.badge-advisor { background: #ede9fe; color: #5b21b6; }
.badge-leader  { background: #fef3c7; color: #92400e; }
.badge-student { background: #dbeafe; color: #1e40af; }

/* ═══════════════════════════════════════════════════════════════
   CARD HELPER   (use via st.markdown with unsafe_allow_html)
═══════════════════════════════════════════════════════════════ */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.1rem 1.3rem;
    box-shadow: var(--shadow-sm);
    margin-bottom: 0.75rem;
    transition: var(--transition);
}
.card:hover {
    box-shadow: var(--shadow);
    border-color: var(--primary-light);
    transform: translateY(-1px);
}
.card-title {
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 0.4rem;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}
.card-subtitle {
    font-size: 0.75rem;
    color: var(--text-muted);
    margin-bottom: 0.5rem;
}

/* ═══════════════════════════════════════════════════════════════
   DIVIDER
═══════════════════════════════════════════════════════════════ */
hr {
    border: none !important;
    border-top: 1px solid var(--border) !important;
    margin: 1.25rem 0 !important;
}

/* ═══════════════════════════════════════════════════════════════
   SCROLLBAR (WebKit)
═══════════════════════════════════════════════════════════════ */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: var(--surface-alt); }
::-webkit-scrollbar-thumb { background: var(--border-dark); border-radius: 999px; }
::-webkit-scrollbar-thumb:hover { background: var(--text-muted); }

/* ═══════════════════════════════════════════════════════════════
   SUBHEADER (st.subheader)
═══════════════════════════════════════════════════════════════ */
h2[data-testid="stHeading"],
.stSubheader, h2 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

/* ═══════════════════════════════════════════════════════════════
   FILE UPLOADER
═══════════════════════════════════════════════════════════════ */
[data-testid="stFileUploader"] {
    border: 2px dashed var(--border-dark) !important;
    border-radius: var(--radius-sm) !important;
    padding: 0.75rem !important;
    background: var(--surface-alt) !important;
    transition: var(--transition) !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--primary-light) !important;
    background: #e8f4fd !important;
}

/* ═══════════════════════════════════════════════════════════════
   LOGIN PAGE CENTERING
═══════════════════════════════════════════════════════════════ */
.login-wrapper {
    max-width: 420px;
    margin: 2rem auto;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 2rem 2.5rem;
    box-shadow: var(--shadow-lg);
}
.login-logo {
    text-align: center;
    font-size: 3rem;
    margin-bottom: 0.5rem;
}
.login-title {
    text-align: center;
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 0.25rem;
}
.login-sub {
    text-align: center;
    font-size: 0.77rem;
    color: var(--text-muted);
    margin-bottom: 1.5rem;
}

/* ═══════════════════════════════════════════════════════════════
   SELECTBOX
═══════════════════════════════════════════════════════════════ */
[data-testid="stSelectbox"] > div {
    border-radius: var(--radius-sm) !important;
}

/* ═══════════════════════════════════════════════════════════════
   ANIMATIONS
═══════════════════════════════════════════════════════════════ */
@keyframes fadeInUp {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
}
.block-container > div {
    animation: fadeInUp 0.25s ease both;
}
</style>
"""
