"""Deterministic transform library.

Every function is pure: same input, same output, no surprises.
A transform either succeeds or raises TransformError. It NEVER guesses.
The LLM cannot add functions here; approved specs may only name what exists.
"""
from datetime import datetime


class TransformError(Exception):
    """Raised when a value cannot be transformed safely."""

    def __init__(self, message: str, suggested_fix: str = ""):
        super().__init__(message)
        self.message = message
        self.suggested_fix = suggested_fix


DATE_FORMATS = ["%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y", "%d/%m/%Y"]

COUNTRY_MAP = {
    "uk": "GB", "united kingdom": "GB", "gb": "GB", "great britain": "GB", "england": "GB",
    "us": "US", "usa": "US", "united states": "US", "u.s.a.": "US",
    "de": "DE", "germany": "DE", "deutschland": "DE",
    "fr": "FR", "france": "FR",
    "pk": "PK", "pakistan": "PK",
}


def trim(value: str) -> str:
    return value.strip()


def lowercase(value: str) -> str:
    return value.lower()


def parse_date(value: str) -> str:
    """Return an ISO date string, or refuse if the day/month order is ambiguous."""
    value = value.strip()

    # Unambiguous ISO format first
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        pass

    parts = value.replace("-", "/").split("/")
    if len(parts) == 3 and len(parts[0]) <= 2 and len(parts[1]) <= 2:
        first, second = int(parts[0]), int(parts[1])
        # Both <= 12 means we cannot tell DD/MM from MM/DD. Refuse rather than guess.
        if first <= 12 and second <= 12 and first != second:
            raise TransformError(
                f"Date '{value}' is ambiguous: could be day/month or month/day.",
                "Ask the customer which order their system uses, then set the date_order option.",
            )

    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue

    raise TransformError(
        f"Date '{value}' does not match any known format.",
        f"Expected one of: {', '.join(DATE_FORMATS)}",
    )


def normalize_country_iso2(value: str) -> str:
    key = value.strip().lower().rstrip(".")
    if key in COUNTRY_MAP:
        return COUNTRY_MAP[key]
    if len(key) == 2 and key.isalpha():
        return key.upper()
    raise TransformError(
        f"Country '{value}' is not recognised.",
        "Add it to the country map, or ask the customer for an ISO 3166 alpha-2 code.",
    )


REGISTRY = {
    "trim": trim,
    "lowercase": lowercase,
    "parse_date": parse_date,
    "normalize_country_iso2": normalize_country_iso2,
}


def apply_chain(value: str, transform_names: list[str]) -> str:
    """Apply transforms in order. An unknown transform name is a hard failure."""
    for name in transform_names:
        function = REGISTRY.get(name)
        if function is None:
            raise TransformError(
                f"Unknown transform '{name}'.",
                "Approved mappings may only use transforms in the registry.",
            )
        value = function(value)
    return value