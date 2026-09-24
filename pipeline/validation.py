"""Deterministic validation. Rules are data, so adding one is a config change."""
import re

from pipeline.canonical import CUSTOMER_FIELDS

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def check_required(record: dict) -> list[dict]:
    issues = []
    for field, spec in CUSTOMER_FIELDS.items():
        if spec["required"] and not record.get(field):
            issues.append({
                "rule_id": "REQUIRED_FIELD",
                "severity": "block",
                "field": field,
                "value": record.get(field),
                "reason": f"Required field '{field}' is empty.",
                "suggested_fix": f"Ask the customer to supply {spec['description'].lower()}.",
            })
    return issues


def check_types(record: dict) -> list[dict]:
    issues = []
    email = record.get("email")
    if email and not EMAIL_RE.match(email):
        issues.append({
            "rule_id": "INVALID_EMAIL",
            "severity": "block",
            "field": "email",
            "value": email,
            "reason": f"'{email}' is not a valid email address.",
            "suggested_fix": "Correct the address in the source system, or waive if the contact is unreachable.",
        })
    return issues


def check_business_rules(record: dict) -> list[dict]:
    issues = []
    created = record.get("created_at")
    if created and created > "2026-12-31":
        issues.append({
            "rule_id": "CREATED_IN_FUTURE",
            "severity": "block",
            "field": "created_at",
            "value": created,
            "reason": "Account creation date is in the future.",
            "suggested_fix": "Check the source system for a data entry or timezone error.",
        })
    return issues


def validate_record(record: dict) -> list[dict]:
    return check_required(record) + check_types(record) + check_business_rules(record)


def check_duplicates(records: list[dict]) -> dict[int, list[dict]]:
    """Return {row_number: issues} for rows whose customer_id was already seen."""
    seen, duplicates = {}, {}
    for record in records:
        customer_id = record.get("customer_id")
        if not customer_id:
            continue
        if customer_id in seen:
            duplicates[record["_row"]] = [{
                "rule_id": "DUPLICATE_CUSTOMER_ID",
                "severity": "block",
                "field": "customer_id",
                "value": customer_id,
                "reason": f"customer_id '{customer_id}' already appeared in row {seen[customer_id]}.",
                "suggested_fix": "Remove the duplicate row, or confirm these are genuinely different customers.",
            }]
        else:
            seen[customer_id] = record["_row"]
    return duplicates