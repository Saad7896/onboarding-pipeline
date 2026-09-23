"""Mapping proposer: suggest how source columns map to the canonical schema.

It only PROPOSES. Nothing here changes customer data, and every proposal
must be approved by a human before it is used.
"""
import re
from pipeline.llm_mapper import propose_with_llm

from rapidfuzz import fuzz

from pipeline.canonical import CUSTOMER_FIELDS, SCHEMA_VERSION

CONFIDENT = 0.85
UNCERTAIN = 0.60


def normalize_name(name: str) -> str:
    name = re.sub(r"__c$", "", name, flags=re.IGNORECASE)  # Salesforce custom-field suffix
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)         # AcctName -> Acct Name
    name = re.sub(r"[_\-.]+", " ", name)                     # Email_Addr -> Email Addr
    return re.sub(r"\s+", " ", name).strip().lower()


def name_score(column: str, field: str, spec: dict) -> tuple[float, str]:
    candidate = normalize_name(column)
    options = [field.replace("_", " ")] + spec["synonyms"]
    best = max(options, key=lambda option: fuzz.token_sort_ratio(candidate, option))
    return fuzz.token_sort_ratio(candidate, best) / 100, best


def value_score(spec: dict, profile: dict) -> float | None:
    if spec["type"] == "email":
        return profile["email_share"]
    if spec["type"] == "date":
        return profile["date_share"]
    return None  # no value check for this type yet


def score(profile: dict, field: str, spec: dict) -> tuple[float, str]:
    column = profile["column"]
    n_score, matched = name_score(column, field, spec)
    reason = f"Column name '{column}' resembles '{matched}' ({n_score:.0%} match)."

    v_score = value_score(spec, profile)
    if v_score is None:
        return round(n_score, 2), reason

    reason += f" {v_score:.0%} of values look like {spec['type']} values."
    return round(0.6 * n_score + 0.4 * v_score, 2), reason


def propose_mapping(profiles: list[dict], use_llm: bool = True) -> dict:
    # Layer 1: deterministic heuristics
    candidates = []
    for field, spec in CUSTOMER_FIELDS.items():
        for profile in profiles:
            confidence, reason = score(profile, field, spec)
            candidates.append((confidence, field, profile["column"], reason))

    candidates.sort(reverse=True)
    chosen, used_columns = {}, set()
    for confidence, field, column, reason in candidates:
        if field in chosen or column in used_columns or confidence < UNCERTAIN:
            continue
        chosen[field] = (confidence, column, reason)
        used_columns.add(column)

    # Layer 2: the LLM, for semantic matches the heuristics cannot make
    llm = propose_with_llm(profiles) if use_llm else {}

    profiles_by_column = {p["column"]: p for p in profiles}
    fields = []
    for field, spec in CUSTOMER_FIELDS.items():
        h = chosen.get(field)
        h_column = h[1] if h else None
        h_conf = h[0] if h else 0.0
        h_reason = h[2] if h else "No source column matched by name or value pattern."

        l = llm.get(field)
        l_column = l["source_column"] if l else None
        l_conf = l["confidence"] if l else 0.0
        l_reason = l["reason"] if l else ""

        # Reconcile the two layers
        if h_column and l_column and h_column == l_column:
            column = h_column
            confidence = round(min(0.99, max(h_conf, l_conf) + 0.10), 2)
            agreement = "both_agree"
        elif h_column and l_column and h_column != l_column:
            column, confidence = (h_column, h_conf) if h_conf >= l_conf else (l_column, l_conf)
            confidence = round(confidence * 0.8, 2)  # disagreement lowers trust
            agreement = "disagree"
        elif l_column and not h_column:
            column, confidence, agreement = l_column, round(l_conf * 0.9, 2), "llm_only"
        elif h_column and not l_column:
            column, confidence, agreement = h_column, round(h_conf * 0.9, 2), "heuristic_only"
        else:
            column, confidence, agreement = None, 0.0, "neither"

        if column is None:
            fields.append({
                "canonical_field": field, "source_column": None, "confidence": 0.0,
                "status": "unmapped", "agreement": agreement, "suggested_transforms": [],
                "reason": "Neither name matching nor the model found a suitable column.",
                "notes": ["Required field: ask the customer where this data lives."] if spec["required"] else [],
            })
            continue

        profile = profiles_by_column[column]
        notes = []
        if agreement == "disagree":
            notes.append(f"Layers disagreed: heuristics chose '{h_column}', model chose '{l_column}'. Please review.")
        if spec["type"] == "date" and len(profile["date_formats"]) > 1:
            notes.append(f"Mixed date formats found: {profile['date_formats']}")
        if spec["type"] == "date" and profile["ambiguous_dates"]:
            notes.append(f"Day/month order is ambiguous for: {profile['ambiguous_dates']}. Customer must confirm.")
        if spec["required"] and profile["null_pct"] > 0:
            notes.append(f"Required field, but {profile['null_pct']}% of values are missing.")

        fields.append({
            "canonical_field": field,
            "source_column": column,
            "confidence": confidence,
            "status": "confident" if confidence >= CONFIDENT else "uncertain",
            "agreement": agreement,
            "suggested_transforms": spec["default_transforms"],
            "reason": f"Name/value analysis: {h_reason}" + (f" | Model: {l_reason}" if l_reason else ""),
            "notes": notes,
        })

    mapped = {f["source_column"] for f in fields if f["source_column"]}
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "proposed",
        "fields": fields,
        "unmapped_source_columns": [p["column"] for p in profiles if p["column"] not in mapped],
    }