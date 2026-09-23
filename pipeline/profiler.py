"""Profiling: describe the customer's data without changing it."""
import re

import pandas as pd

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DATE_PATTERNS = {
    "YYYY-MM-DD": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "NN/NN/YYYY": re.compile(r"^\d{2}/\d{2}/\d{4}$"),
    "NN-NN-YYYY": re.compile(r"^\d{2}-\d{2}-\d{4}$"),
}
# Dates like 06/01/2025 could be 6 January or 1 June
AMBIGUOUS_DATE_RE = re.compile(r"^(\d{2})[/-](\d{2})[/-]\d{4}$")


def profile_column(name: str, values: pd.Series) -> dict:
    non_null = [v.strip() for v in values.dropna()]
    total = len(non_null)

    date_formats = {}
    for fmt, pattern in DATE_PATTERNS.items():
        count = sum(1 for v in non_null if pattern.match(v))
        if count:
            date_formats[fmt] = count

    ambiguous_dates = sorted({
        v for v in non_null
        if (m := AMBIGUOUS_DATE_RE.match(v)) and int(m.group(1)) <= 12 and int(m.group(2)) <= 12
    })

    email_count = sum(1 for v in non_null if EMAIL_RE.match(v))

    return {
        "column": name,
        "null_pct": round(values.isna().mean() * 100, 1),
        "distinct_values": int(values.nunique()),
        "samples": non_null[:3],
        "email_share": round(email_count / total, 2) if total else 0.0,
        "date_share": round(sum(date_formats.values()) / total, 2) if total else 0.0,
        "date_formats": date_formats,
        "ambiguous_dates": ambiguous_dates,
    }


def profile_dataframe(df: pd.DataFrame) -> list[dict]:
    return [profile_column(col, df[col]) for col in df.columns]