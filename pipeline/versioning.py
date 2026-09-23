"""Create, approve and version mapping specs.

Versions are immutable. An approval or an edit never rewrites history:
it creates a new version and marks the previous one superseded.
"""
from sqlalchemy import select

from pipeline.canonical import CUSTOMER_FIELDS
from pipeline.db import MappingSpec, MappingVersion, SessionLocal, utcnow


def get_or_create_spec(session, customer: str, source_system: str) -> MappingSpec:
    spec = session.scalar(
        select(MappingSpec).where(
            MappingSpec.customer == customer,
            MappingSpec.source_system == source_system,
        )
    )
    if spec is None:
        spec = MappingSpec(customer=customer, source_system=source_system)
        session.add(spec)
        session.flush()
    return spec


def latest_version(session, spec_id: int) -> MappingVersion | None:
    return session.scalar(
        select(MappingVersion)
        .where(MappingVersion.spec_id == spec_id)
        .order_by(MappingVersion.version.desc())
        .limit(1)
    )


def compute_diff(old_fields: list[dict] | None, new_fields: list[dict]) -> list[dict]:
    if not old_fields:
        return [{"change": "initial_version"}]
    old_by_field = {f["canonical_field"]: f for f in old_fields}
    changes = []
    for new in new_fields:
        old = old_by_field.get(new["canonical_field"])
        if old is None:
            changes.append({"change": "field_added", "canonical_field": new["canonical_field"]})
            continue
        if old.get("source_column") != new.get("source_column"):
            changes.append({
                "change": "source_column_changed",
                "canonical_field": new["canonical_field"],
                "from": old.get("source_column"),
                "to": new.get("source_column"),
            })
        if old.get("suggested_transforms") != new.get("suggested_transforms"):
            changes.append({
                "change": "transforms_changed",
                "canonical_field": new["canonical_field"],
                "from": old.get("suggested_transforms"),
                "to": new.get("suggested_transforms"),
            })
    new_names = {f["canonical_field"] for f in new_fields}
    for name in old_by_field:
        if name not in new_names:
            changes.append({"change": "field_removed", "canonical_field": name})
    return changes


def save_proposal(customer: str, source_system: str, proposal: dict, fingerprint: str) -> dict:
    with SessionLocal.begin() as session:
        spec = get_or_create_spec(session, customer, source_system)
        previous = latest_version(session, spec.id)
        version_number = (previous.version + 1) if previous else 1

        version = MappingVersion(
            spec_id=spec.id,
            version=version_number,
            status="proposed",
            schema_version=proposal["schema_version"],
            source_fingerprint=fingerprint,
            fields=proposal["fields"],
            diff=compute_diff(previous.fields if previous else None, proposal["fields"]),
        )
        session.add(version)
        session.flush()
        return {
            "spec_id": spec.id,
            "version": version.version,
            "status": version.status,
            "source_fingerprint": fingerprint,
            "diff": version.diff,
            "fields": version.fields,
            "unmapped_source_columns": proposal["unmapped_source_columns"],
        }


def approve(spec_id: int, approved_by: str, overrides: list[dict]) -> dict:
    """Approve the latest proposal, applying any human edits.

    Returns a new immutable APPROVED version. Refuses to approve if a
    required canonical field is still unmapped.
    """
    with SessionLocal.begin() as session:
        current = latest_version(session, spec_id)
        if current is None:
            return {"error": "no_mapping_found"}
        if current.status == "approved":
            return {"error": "already_approved", "version": current.version}

        overrides_by_field = {o["canonical_field"]: o for o in overrides}
        approved_fields = []
        for field in current.fields:
            field = dict(field)
            override = overrides_by_field.get(field["canonical_field"])
            if override:
                if "source_column" in override:
                    field["source_column"] = override["source_column"]
                if "transforms" in override:
                    field["suggested_transforms"] = override["transforms"]
                field["human_edited"] = True
                field["edit_reason"] = override.get("reason", "")
            field["status"] = "approved" if field["source_column"] else "unmapped"
            approved_fields.append(field)

        missing = [
            f["canonical_field"] for f in approved_fields
            if CUSTOMER_FIELDS[f["canonical_field"]]["required"] and not f["source_column"]
        ]
        if missing:
            return {
                "error": "required_fields_unmapped",
                "missing": missing,
                "message": "Map these required fields, or ask the customer where the data lives.",
            }

        current.status = "superseded"
        new_version = MappingVersion(
            spec_id=spec_id,
            version=current.version + 1,
            status="approved",
            schema_version=current.schema_version,
            source_fingerprint=current.source_fingerprint,
            fields=approved_fields,
            diff=compute_diff(current.fields, approved_fields),
            approved_by=approved_by,
            approved_at=utcnow(),
        )
        session.add(new_version)
        session.flush()
        return {
            "spec_id": spec_id,
            "version": new_version.version,
            "status": "approved",
            "approved_by": approved_by,
            "diff": new_version.diff,
            "fields": approved_fields,
        }


def list_versions(spec_id: int) -> list[dict]:
    with SessionLocal.begin() as session:
        versions = session.scalars(
            select(MappingVersion)
            .where(MappingVersion.spec_id == spec_id)
            .order_by(MappingVersion.version)
        ).all()
        return [
            {
                "version": v.version,
                "status": v.status,
                "source_fingerprint": v.source_fingerprint[:12],
                "approved_by": v.approved_by,
                "created_at": v.created_at.isoformat(),
                "diff": v.diff,
            }
            for v in versions
        ]