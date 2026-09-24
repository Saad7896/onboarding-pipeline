"""Database setup and tables for versioned mapping specs."""
import os
from datetime import datetime, timezone
from sqlalchemy import Boolean, Text

from dotenv import load_dotenv
from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

load_dotenv()

engine = create_engine(os.environ["DATABASE_URL"], future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MappingSpec(Base):
    """One mapping between a customer's source file and our canonical schema."""
    __tablename__ = "mapping_specs"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer: Mapped[str] = mapped_column(String(100))
    source_system: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("customer", "source_system", name="uq_customer_source"),)


class MappingVersion(Base):
    """An immutable snapshot of a mapping. Never updated, only superseded."""
    __tablename__ = "mapping_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    spec_id: Mapped[int] = mapped_column(ForeignKey("mapping_specs.id"))
    version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))          # proposed | approved | superseded
    schema_version: Mapped[str] = mapped_column(String(10))
    source_fingerprint: Mapped[str] = mapped_column(String(64))
    fields: Mapped[list] = mapped_column(JSONB)
    diff: Mapped[list] = mapped_column(JSONB, default=list)  # what changed vs the previous version
    approved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("spec_id", "version", name="uq_spec_version"),)


class IngestBatch(Base):
    """One run of a file through the pipeline. file_hash makes re-uploads detectable."""
    __tablename__ = "ingest_batches"

    id: Mapped[int] = mapped_column(primary_key=True)
    spec_id: Mapped[int] = mapped_column(ForeignKey("mapping_specs.id"))
    mapping_version: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(300))
    file_hash: Mapped[str] = mapped_column(String(64))
    total_rows: Mapped[int] = mapped_column(Integer)
    valid_count: Mapped[int] = mapped_column(Integer)
    exception_count: Mapped[int] = mapped_column(Integer)
    replayed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CanonicalCustomer(Base):
    """A clean customer record. customer_id is unique, so re-runs update rather than duplicate."""
    __tablename__ = "canonical_customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(100))
    legal_name: Mapped[str] = mapped_column(String(300))
    email: Mapped[str] = mapped_column(String(300))
    created_at_source: Mapped[str] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (UniqueConstraint("customer_id", name="uq_canonical_customer_id"),)


class ExceptionRecord(Base):
    """A row that failed, with the reason and what to do about it."""
    __tablename__ = "exception_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("ingest_batches.id"))
    row_number: Mapped[int] = mapped_column(Integer)
    rule_id: Mapped[str] = mapped_column(String(50))
    field: Mapped[str] = mapped_column(String(100))
    bad_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    suggested_fix: Mapped[str] = mapped_column(Text)
    record: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | fixed | waived
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mapping_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    
def init_db() -> None:
    Base.metadata.create_all(engine)



















