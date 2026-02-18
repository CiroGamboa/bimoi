"""Tests for phone number normalization (E.164)."""


from bimoi.infrastructure.phone import normalize_phone


def test_normalize_with_country_code_returns_e164():
    assert normalize_phone("+39 312 345 6789", default_region=None) == "+393123456789"
    assert normalize_phone("+1 202 555 1234", default_region=None) == "+12025551234"


def test_normalize_without_country_code_uses_default_region():
    assert normalize_phone("202 555 1234", default_region="US") == "+12025551234"
    assert normalize_phone("312 345 6789", default_region="IT") == "+393123456789"


def test_normalize_invalid_returns_none():
    assert normalize_phone("", default_region=None) is None
    assert normalize_phone("   ", default_region=None) is None
    assert normalize_phone("abc", default_region=None) is None
    assert normalize_phone("+1", default_region=None) is None
    assert normalize_phone("123", default_region="US") is None  # too short


def test_normalize_whitespace_stripped():
    assert normalize_phone("  +12025551234  ", default_region=None) == "+12025551234"
