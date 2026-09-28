"""Centralized format rules for tourist registration's identity/contact
fields (name, phone, and the four supported document types).

One place so the authoritative backend check and the frontend's real-time
input mask (frontend/src/lib/identityValidation.js) describe the exact same
rules instead of drifting apart. Used by app/schemas/tourist.py:TouristCreate
-- the frontend's own validation is a UX convenience only; this module is
what actually decides whether a registration is accepted.
"""
from __future__ import annotations

import re

NAME_PATTERN = re.compile(r"^[A-Za-z ]+$")
# Indian mobile numbers: exactly 10 digits, first digit 6-9. Deliberately
# specific to this registration field -- see the module docstring in
# frontend/src/lib/identityValidation.js for why this must not be loosened
# to accommodate international numbers elsewhere in the app.
PHONE_PATTERN = re.compile(r"^[6-9][0-9]{9}$")

DOCUMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "aadhaar": re.compile(r"^[0-9]{12}$"),
    "passport": re.compile(r"^[A-Z][0-9]{7}$"),
    "voterid": re.compile(r"^[A-Z]{3}[0-9]{7}$"),
    "pan": re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$"),
}

NAME_ERROR = "Name can contain only letters and spaces."
PHONE_ERROR = "Enter a valid 10-digit mobile number starting with 6-9."
DOCUMENT_ERRORS: dict[str, str] = {
    "aadhaar": "Aadhaar number must contain exactly 12 digits.",
    "passport": "Passport number must contain 1 uppercase letter followed by 7 digits.",
    "voterid": "Voter ID must contain 3 uppercase letters followed by 7 digits.",
    "pan": "PAN must contain 5 uppercase letters, 4 digits, and 1 uppercase letter.",
}


def normalize_name(value: str) -> str:
    """Trim outer whitespace and collapse repeated internal spaces. Never
    touches letters -- an invalid character must still fail validate_name,
    not be silently dropped."""
    return re.sub(r" {2,}", " ", value.strip())


def normalize_document_number(document_type: str, value: str) -> str:
    """Trim, and uppercase for the three alphanumeric document types
    (document IDs are case-insensitive by convention, so 'abcde1234f' and
    'ABCDE1234F' must be treated as the same PAN). Aadhaar is left as-is --
    it's purely numeric, so case never applies. Never strips or rewrites
    any character: 'ABCDE-1234-F' stays exactly that and correctly fails
    validate_document_number below, rather than having its hyphens quietly
    removed and being treated as a valid PAN."""
    normalized = value.strip()
    if document_type != "aadhaar":
        normalized = normalized.upper()
    return normalized


def validate_name(value: str) -> bool:
    return bool(NAME_PATTERN.match(value))


def validate_phone(value: str) -> bool:
    return bool(PHONE_PATTERN.match(value))


def validate_document_number(document_type: str, value: str) -> bool:
    pattern = DOCUMENT_PATTERNS.get(document_type)
    return pattern is not None and bool(pattern.match(value))
