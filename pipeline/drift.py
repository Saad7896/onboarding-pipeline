"""Schema drift detection.

An approved mapping is a contract against a specific source schema. When the
source changes, we refuse to run and report exactly which mapped fields broke,
rather than silently loading wrong or empty data.
"""
from rapidfuzz import fuzz

from pipeline.profiler import infer_kind, schema_fingerprint


def detect_drift(profiles: list[dict], approved_version) -> dict:
    """Compare an incoming file against the schema an approved mapping was built on."""
    incoming_fingerprint = schema_fingerprint(profiles)
    if incoming_fingerprint == approved_version.source_fingerprint:
        return {"drift_detected": False, "fingerprint": incoming_fingerprint}

    incoming = {p["column"]: infer_kind(p) for p in profiles}

    # Columns the approved mapping actually depends on
    mapped_columns = {
        field["source_column"]: field["canonical_field"]
        for field in approved_version.fields
        if field.get("source_column")
    }

    missing = [column for column in mapped_columns if column not in incoming]
    added = [column for column in incoming if column not in mapped_columns]

    # For each missing column, is one of the new columns plausibly a rename?
    rename_candidates = []
    for column in missing:
        best_score, best_match = 0, None
        for candidate in added:
            score = fuzz.token_sort_ratio(column.lower(), candidate.lower()) / 100
            if score > best_score:
                best_score, best_match = score, candidate
        if best_match and best_score >= 0.45:
            rename_candidates.append({
                "missing_column": column,
                "likely_rename_to": best_match,
                "similarity": round(best_score, 2),
                "affects_field": mapped_columns[column],
            })

    broken_fields = [
        {
            "canonical_field": mapped_columns[column],
            "source_column": column,
            "problem": "source column no longer present in the file",
            "suggestion": next(
                (f"'{c['likely_rename_to']}' looks like a rename ({c['similarity']:.0%} similar)."
                 for c in rename_candidates if c["missing_column"] == column),
                "Ask the customer where this data moved to.",
            ),
        }
        for column in missing
    ]

    return {
        "drift_detected": True,
        "approved_fingerprint": approved_version.source_fingerprint[:12],
        "incoming_fingerprint": incoming_fingerprint[:12],
        "mapping_version": approved_version.version,
        "missing_columns": missing,
        "new_columns": added,
        "broken_fields": broken_fields,
        "rename_candidates": rename_candidates,
        "safe_to_run": len(broken_fields) == 0,
        "message": (
            f"{len(broken_fields)} mapped field(s) broke. Review and approve a new mapping version."
            if broken_fields else
            "The schema changed, but no mapped field was affected. Safe to run."
        ),
    }