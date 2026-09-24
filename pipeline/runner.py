"""Run an approved mapping over a file: transform, validate, split."""
import pandas as pd
from sqlalchemy import select

from pipeline.db import MappingVersion, SessionLocal
from pipeline.transforms import TransformError, apply_chain
from pipeline.validation import check_duplicates, validate_record


def get_approved_version(spec_id: int) -> MappingVersion | None:
    with SessionLocal.begin() as session:
        return session.scalar(
            select(MappingVersion)
            .where(MappingVersion.spec_id == spec_id, MappingVersion.status == "approved")
            .order_by(MappingVersion.version.desc())
            .limit(1)
        )


def run_pipeline(df: pd.DataFrame, mapping_fields: list[dict]) -> dict:
    valid, exceptions = [], []

    for row_number, raw_row in enumerate(df.to_dict("records"), start=1):
        record, row_issues = {"_row": row_number}, []

        for field in mapping_fields:
            canonical = field["canonical_field"]
            column = field.get("source_column")
            if not column:
                record[canonical] = None
                continue

            raw_value = raw_row.get(column)
            if pd.isna(raw_value) or raw_value is None:
                record[canonical] = None
                continue

            try:
                record[canonical] = apply_chain(str(raw_value), field.get("suggested_transforms", []))
            except TransformError as error:
                record[canonical] = None
                row_issues.append({
                    "rule_id": "TRANSFORM_FAILED",
                    "severity": "block",
                    "field": canonical,
                    "value": str(raw_value),
                    "reason": error.message,
                    "suggested_fix": error.suggested_fix,
                })

        failed_fields = {issue["field"] for issue in row_issues}
        row_issues.extend(
            issue for issue in validate_record(record)
            if not (issue["rule_id"] == "REQUIRED_FIELD" and issue["field"] in failed_fields)
        )
        record["_issues"] = row_issues
        (exceptions if row_issues else valid).append(record)

    # Duplicates are checked across rows, so only records that passed so far
    duplicate_issues = check_duplicates(valid)
    still_valid = []
    for record in valid:
        issues = duplicate_issues.get(record["_row"])
        if issues:
            record["_issues"] = issues
            exceptions.append(record)
        else:
            still_valid.append(record)

    exceptions.sort(key=lambda r: r["_row"])
    return {
        "total_rows": len(df),
        "valid_count": len(still_valid),
        "exception_count": len(exceptions),
        "valid_records": [
            {k: v for k, v in r.items() if not k.startswith("_")} for r in still_valid
        ],
        "exceptions": [
            {"row": r["_row"], "record": {k: v for k, v in r.items() if not k.startswith("_")},
             "issues": r["_issues"]}
            for r in exceptions
        ],
    }