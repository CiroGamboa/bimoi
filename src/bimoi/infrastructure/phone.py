"""Phone number normalization to E.164 for storage and deduplication."""

import phonenumbers


def normalize_phone(raw: str, default_region: str | None = None) -> str | None:
    """Parse and return E.164 form of the number, or None if invalid.

    Use default_region when the input has no leading + (e.g. "123 456 7890"
    with default_region "IT" for Italy). If the number already includes a
    country code, default_region is ignored.
    """
    if not raw or not str(raw).strip():
        return None
    raw = str(raw).strip()
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except phonenumbers.NumberParseException:
        return None
    if not phonenumbers.is_valid_number(parsed):
        return None
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
