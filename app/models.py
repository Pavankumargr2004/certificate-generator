from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    completed_with_errors = "completed_with_errors"


class CertificateStatus(str, Enum):
    queued = "queued"
    succeeded = "succeeded"
    failed = "failed"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    username: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(160))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_name: Mapped[str] = mapped_column(String(200))
    issued_on: Mapped[str] = mapped_column(String(40))
    design: Mapped[str] = mapped_column(String(32), default="classic")
    template_id: Mapped[str | None] = mapped_column(ForeignKey("certificate_templates.id"), nullable=True)
    title_text: Mapped[str] = mapped_column(String(120), default="CERTIFICATE OF COMPLETION")
    accent_color: Mapped[str] = mapped_column(String(7), default="#B28B3D")
    signatory: Mapped[str] = mapped_column(String(120), default="")
    font_family: Mapped[str] = mapped_column(String(16), default="serif")
    send_email: Mapped[bool] = mapped_column(default=False)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    status: Mapped[JobStatus] = mapped_column(SAEnum(JobStatus), default=JobStatus.queued, index=True)
    total: Mapped[int] = mapped_column(Integer)
    succeeded: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    certificates: Mapped[list["CertificateRecord"]] = relationship(back_populates="job", cascade="all, delete-orphan")


class CertificateTemplate(Base):
    __tablename__ = "certificate_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(120))
    background_path: Mapped[str] = mapped_column(Text)
    owner_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CertificateRecord(Base):
    __tablename__ = "certificates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    job_id: Mapped[str] = mapped_column(ForeignKey("generation_jobs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    recipient_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    course_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    status: Mapped[CertificateStatus] = mapped_column(SAEnum(CertificateStatus), default=CertificateStatus.queued)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    email_status: Mapped[str] = mapped_column(String(16), default="not_requested")
    email_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    job: Mapped[GenerationJob] = relationship(back_populates="certificates")
