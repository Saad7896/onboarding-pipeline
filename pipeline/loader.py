"""Persist pipeline results. Safe to re-run: upserts, never blind inserts."""
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from pipeline.db import CanonicalCustomer, ExceptionRecord, IngestBatch, SessionLocal, utcnow


def file_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def content_hash(record: dict) -> str:
    """Hash of the record's values, so we can tell a real change from a replay."""
    payload = json.dumps({k: v for k, v in sorted(record.items())}, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def load_results(spec_id: int, mapping_version: int, filename: str,
                 raw_bytes: bytes, result: dict) -> dict:
    digest = file_hash(raw_bytes)

    with SessionLocal.begin() as session:
        previous = session.scalar(
            select(IngestBatch)
            .where(IngestBatch.spec_id == spec_id, IngestBatch.file_hash == digest)
            .order_by(IngestBatch.id)
            .limit(1)
        )
        is_replay = previous is not None

        batch = IngestBatch(
            spec_id=spec_id,
            mapping_version=mapping_version,
            filename=filename,
            file_hash=digest,
            total_rows=result["total_rows"],
            valid_count=result["valid_count"],
            exception_count=result["exception_count"],
            replayed=is_replay,
        )
        session.add(batch)
        session.flush()

        inserted = updated = unchanged = 0
        for record in result["valid_records"]:
            digest_row = content_hash(record)
            existing = session.scalar(
                select(CanonicalCustomer).where(
                    CanonicalCustomer.customer_id == record["customer_id"]
                )
            )
            if existing and existing.content_hash == digest_row:
                unchanged += 1
                continue

            statement = insert(CanonicalCustomer).values(
                customer_id=record["customer_id"],
                legal_name=record["legal_name"],
                email=record["email"],
                created_at_source=record["created_at"],
                country=record.get("country"),
                content_hash=digest_row,
                batch_id=batch.id,
                updated_at=utcnow(),
            ).on_conflict_do_update(
                index_elements=["customer_id"],
                set_={
                    "legal_name": record["legal_name"],
                    "email": record["email"],
                    "created_at_source": record["created_at"],
                    "country": record.get("country"),
                    "content_hash": digest_row,
                    "batch_id": batch.id,
                    "updated_at": utcnow(),
                },
            )
            session.execute(statement)
            updated += 1 if existing else 0
            inserted += 0 if existing else 1

        # Replays should not pile up duplicate exceptions for the same problem
        if is_replay:
            session.query(ExceptionRecord).filter(
                ExceptionRecord.batch_id == previous.id,
                ExceptionRecord.status == "open",
            ).delete()

        exceptions_written = 0
        for exception in result["exceptions"]:
            for issue in exception["issues"]:
                session.add(ExceptionRecord(
                    batch_id=batch.id,
                    row_number=exception["row"],
                    rule_id=issue["rule_id"],
                    field=issue["field"],
                    bad_value=None if issue["value"] is None else str(issue["value"]),
                    reason=issue["reason"],
                    suggested_fix=issue["suggested_fix"],
                    record=exception["record"],
                    mapping_version=mapping_version,
                ))
                exceptions_written += 1

        return {
            "batch_id": batch.id,
            "is_replay": is_replay,
            "records_inserted": inserted,
            "records_updated": updated,
            "records_unchanged": unchanged,
            "exceptions_written": exceptions_written,
        }


def list_exceptions(status: str | None = None, batch_id: int | None = None) -> list[dict]:
    with SessionLocal.begin() as session:
        query = select(ExceptionRecord).order_by(ExceptionRecord.id)
        if status:
            query = query.where(ExceptionRecord.status == status)
        if batch_id:
            query = query.where(ExceptionRecord.batch_id == batch_id)
        return [
            {
                "id": e.id, "batch_id": e.batch_id, "row": e.row_number,
                "rule_id": e.rule_id, "field": e.field, "bad_value": e.bad_value,
                "reason": e.reason, "suggested_fix": e.suggested_fix,
                "status": e.status, "resolved_by": e.resolved_by,
                "resolution_note": e.resolution_note,
                "mapping_version": e.mapping_version, "record": e.record,
            }
            for e in session.scalars(query).all()
        ]


def resolve_exception(exception_id: int, action: str, resolved_by: str,
                      note: str = "", corrected_value: str | None = None) -> dict:
    """Waive an exception, or fix it by supplying the corrected value.

    A fix is stored as an overlay on the canonical record. The raw file is never edited.
    """
    if action not in {"waive", "fix"}:
        return {"error": "invalid_action", "message": "action must be 'waive' or 'fix'"}

    with SessionLocal.begin() as session:
        exception = session.get(ExceptionRecord, exception_id)
        if exception is None:
            return {"error": "not_found"}
        if exception.status != "open":
            return {"error": "already_resolved", "status": exception.status}

        if action == "waive":
            exception.status = "waived"
            exception.resolved_by = resolved_by
            exception.resolution_note = note
            return {"id": exception_id, "status": "waived", "loaded": False}

        if corrected_value is None:
            return {"error": "missing_value", "message": "A fix requires corrected_value."}

        record = dict(exception.record)
        record[exception.field] = corrected_value

        # Re-validate the corrected record before letting it through
        from pipeline.validation import validate_record
        remaining = [i for i in validate_record(record) if i["field"] != exception.field or True]
        blocking = [i for i in remaining if i["severity"] == "block"]
        if blocking:
            return {
                "error": "still_invalid",
                "message": "The corrected record still fails validation.",
                "issues": blocking,
            }

        statement = insert(CanonicalCustomer).values(
            customer_id=record["customer_id"],
            legal_name=record["legal_name"],
            email=record["email"],
            created_at_source=record["created_at"],
            country=record.get("country"),
            content_hash=content_hash(record),
            batch_id=exception.batch_id,
            updated_at=utcnow(),
        ).on_conflict_do_update(
            index_elements=["customer_id"],
            set_={
                "legal_name": record["legal_name"], "email": record["email"],
                "created_at_source": record["created_at"], "country": record.get("country"),
                "content_hash": content_hash(record), "updated_at": utcnow(),
            },
        )
        session.execute(statement)

        exception.status = "fixed"
        exception.resolved_by = resolved_by
        exception.resolution_note = note or f"Set {exception.field} to '{corrected_value}'"
        return {"id": exception_id, "status": "fixed", "loaded": True, "record": record}