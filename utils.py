"""
utils.py
Pure utility helpers: password hashing, string normalisation, status helpers.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from datetime import date, datetime
from typing import Optional

from constants import (
    ADMIN_ADVISOR_KEYS,
    DEFAULT_PASSWORD,
    MIN_PASSWORD_LEN,
    MILESTONE_ORDER,
    STATUS_LABELS,
    STATUS_LABELS_EN,
    STATUS_OPTIONS,
    STATUS_TRANSITIONS,
)


# ── Time ──────────────────────────────────────────────────────────────────────

def now_ts() -> str:
    """Return the current local time as an ISO-8601 string (seconds precision)."""
    return datetime.now().isoformat(timespec="seconds")


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str, iterations: int = 120_000) -> str:
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


# ── String normalisation ──────────────────────────────────────────────────────

_CHAR_REPLACEMENTS: dict[str, str] = {
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u",
}


def normalize_header(value: str) -> str:
    """Lowercase, strip diacritics, keep only alphanumeric + space/underscore, remove spaces."""
    text = str(value).strip().lower()
    for src, dst in _CHAR_REPLACEMENTS.items():
        text = text.replace(src, dst)
    return "".join(ch for ch in text if ch.isalnum() or ch in {" ", "_"}).replace(" ", "")


def normalize_identity(value: str) -> str:
    """Like normalize_header but strips all non-alphanumeric chars (used for key comparisons)."""
    return "".join(ch for ch in normalize_header(str(value)) if ch.isalnum())


# ── Auth helpers ──────────────────────────────────────────────────────────────

def is_admin_advisor(user_id: str) -> bool:
    return normalize_identity(user_id) in ADMIN_ADVISOR_KEYS


# ── Status helpers ────────────────────────────────────────────────────────────

def status_tr(status_value: str) -> str:
    """Return the Turkish or English display label for a raw status string."""
    from i18n import is_english_ui  # local import to avoid circular dependency
    status_key = str(status_value)
    if is_english_ui():
        return STATUS_LABELS_EN.get(status_key, status_key)
    return STATUS_LABELS.get(status_key, status_key)


def allowed_status_options(current_status: str) -> list[str]:
    allowed = STATUS_TRANSITIONS.get(str(current_status), set())
    result = [s for s in STATUS_OPTIONS if s in allowed]
    # Fallback: if DB has an unexpected value, allow all options
    return result if result else list(STATUS_OPTIONS)
