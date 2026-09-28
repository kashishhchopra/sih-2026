"""Smart Identity & Contact Validation: format rules for name, phone, and
the four supported document types (app/core/identity_validators.py), plus
their wiring into TouristCreate (app/schemas/tourist.py)."""
import pytest
from pydantic import ValidationError

from app.core.identity_validators import (
    normalize_document_number,
    normalize_name,
    validate_document_number,
    validate_name,
    validate_phone,
)
from app.schemas.tourist import TouristCreate

# ---------------------------------------------------------------- name
@pytest.mark.parametrize("value", ["Rahul Sharma", "Rahul", "Amit Kumar", "Priya"])
def test_valid_names(value):
    assert validate_name(value) is True


@pytest.mark.parametrize("value", ["Rahul123", "Rahul@Sharma", "Rahul-Sharma", "Rahul_123", ""])
def test_invalid_names(value):
    assert validate_name(value) is False


def test_normalize_name_trims_and_collapses_spaces():
    assert normalize_name("  Rahul   Sharma  ") == "Rahul Sharma"


def test_normalize_name_never_removes_letters():
    # A name with digits stays exactly as typed -- normalization must never
    # silently turn an invalid value into something that looks valid.
    assert normalize_name("Rahul123") == "Rahul123"
    assert validate_name(normalize_name("Rahul123")) is False


# ---------------------------------------------------------------- phone
@pytest.mark.parametrize("value", ["9876543210", "8765432109", "7654321098", "6123456789"])
def test_valid_phones(value):
    assert validate_phone(value) is True


@pytest.mark.parametrize("value", [
    "987654321", "98765432101", "5123456789", "98765abc10", "98765 43210", "98765-43210",
])
def test_invalid_phones(value):
    assert validate_phone(value) is False


# ---------------------------------------------------------------- aadhaar
@pytest.mark.parametrize("value", ["123456789012"])
def test_valid_aadhaar(value):
    assert validate_document_number("aadhaar", value) is True


@pytest.mark.parametrize("value", [
    "12345678901", "1234567890123", "1234abcd9012", "1234 5678 9012", "1234-5678-9012",
])
def test_invalid_aadhaar(value):
    assert validate_document_number("aadhaar", value) is False


# ---------------------------------------------------------------- passport
@pytest.mark.parametrize("value", ["A1234567", "P7654321", "Z1234567"])
def test_valid_passport(value):
    assert validate_document_number("passport", value) is True


@pytest.mark.parametrize("value", ["AB123456", "a1234567", "A123456", "A12345678", "A1234ABC", "12345678"])
def test_invalid_passport(value):
    assert validate_document_number("passport", value) is False


# ---------------------------------------------------------------- voter id
@pytest.mark.parametrize("value", ["ABC1234567", "XYZ7654321", "DEL1234567"])
def test_valid_voterid(value):
    assert validate_document_number("voterid", value) is True


@pytest.mark.parametrize("value", [
    "AB12345678", "ABCD123456", "abc1234567", "ABC123456", "ABC12345678", "ABC12AB567",
])
def test_invalid_voterid(value):
    assert validate_document_number("voterid", value) is False


# ---------------------------------------------------------------- pan
@pytest.mark.parametrize("value", ["ABCDE1234F", "PQRSX5678K"])
def test_valid_pan(value):
    assert validate_document_number("pan", value) is True


@pytest.mark.parametrize("value", [
    "ABCD1234F", "ABCDEF1234G", "abcde1234f", "ABCDE12345", "ABCDE1234", "ABCDE12AB4F",
])
def test_invalid_pan(value):
    assert validate_document_number("pan", value) is False


# ---------------------------------------------------------------- normalization
def test_normalize_document_number_uppercases_alphanumeric_types():
    assert normalize_document_number("pan", "abcde1234f") == "ABCDE1234F"
    assert validate_document_number("pan", normalize_document_number("pan", "abcde1234f")) is True


def test_normalize_document_number_leaves_aadhaar_digits_alone():
    assert normalize_document_number("aadhaar", " 123456789012 ") == "123456789012"


def test_normalize_document_number_never_strips_invalid_characters():
    # Hyphens must NOT be silently removed and the result treated as valid --
    # only trim + uppercase, nothing else.
    normalized = normalize_document_number("pan", "ABCDE-1234-F")
    assert normalized == "ABCDE-1234-F"
    assert validate_document_number("pan", normalized) is False


def test_duplicate_identity_normalizes_consistently_for_casing():
    """'abcde1234f' and 'ABCDE1234F' must normalize to the exact same
    stored value, so a duplicate-identity check downstream isn't fooled by
    letter casing."""
    a = normalize_document_number("pan", "abcde1234f")
    b = normalize_document_number("pan", "ABCDE1234F")
    assert a == b == "ABCDE1234F"


# ---------------------------------------------------------------- schema wiring
def _base_kwargs(**over):
    import datetime as dt

    now = dt.datetime.utcnow()
    base = dict(
        full_name="Rahul Sharma", nationality="Indian", document_type="aadhaar",
        document_number="123456789012", phone="9876543210",
        photo="data:image/png;base64,iVBORw0KGgo=",
        trip_start=now, trip_end=now + dt.timedelta(days=5),
    )
    base.update(over)
    return base


def test_schema_rejects_invalid_name():
    with pytest.raises(ValidationError, match="letters and spaces"):
        TouristCreate(**_base_kwargs(full_name="Rahul123"))


def test_schema_rejects_invalid_phone():
    with pytest.raises(ValidationError, match="10-digit mobile number"):
        TouristCreate(**_base_kwargs(phone="5123456789"))


def test_schema_rejects_invalid_aadhaar():
    with pytest.raises(ValidationError, match="exactly 12 digits"):
        TouristCreate(**_base_kwargs(document_number="1234abcd9012"))


def test_schema_rejects_invalid_pan():
    with pytest.raises(ValidationError, match="5 uppercase letters"):
        TouristCreate(**_base_kwargs(document_type="pan", document_number="ABCDE12345"))


def test_schema_normalizes_and_accepts_lowercase_pan():
    t = TouristCreate(**_base_kwargs(document_type="pan", document_number="abcde1234f"))
    assert t.document_number == "ABCDE1234F"


def test_schema_accepts_valid_voterid():
    t = TouristCreate(**_base_kwargs(document_type="voterid", document_number="abc1234567"))
    assert t.document_number == "ABC1234567"


def test_schema_accepts_valid_passport_with_visa_fields():
    import datetime as dt

    now = dt.datetime.utcnow()
    t = TouristCreate(**_base_kwargs(
        document_type="passport", document_number="a1234567",
        visa_type="Tourist", visa_expiry=now + dt.timedelta(days=10),
        trip_end=now + dt.timedelta(days=5),
    ))
    assert t.document_number == "A1234567"


def test_schema_trims_and_collapses_name_whitespace():
    t = TouristCreate(**_base_kwargs(full_name="  Rahul   Sharma  "))
    assert t.full_name == "Rahul Sharma"
