"""Database setup and tables for versioned mapping specs."""
import os
from datetime import datetime, timezone

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


def init_db() -> None:
    Base.metadata.create_all(engine)



















