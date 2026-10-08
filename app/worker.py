"""Database-backed polling worker. Run separately with `python -m app.worker`."""
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import or_, select

from .config import OUTPUT_DIR, WORKER_LEASE_SECONDS, WORKER_POLL_SECONDS
from .database import Base, SessionLocal, engine
from .generator import create_certificate
from .mailer import send_certificate_email
from .models import CertificateRecord, CertificateStatus, CertificateTemplate, GenerationJob, JobStatus
from .schemas import RecipientInput

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def process_one_job() -> bool:
    """Claim and process one queued job; each recipient failure is isolated."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        job = db.scalar(select(GenerationJob).where(or_(
                            GenerationJob.status == JobStatus.queued,
                            (GenerationJob.status == JobStatus.processing) &
                            or_(GenerationJob.lease_expires_at.is_(None),
                                GenerationJob.lease_expires_at < now)))
                        .order_by(GenerationJob.created_at).with_for_update(skip_locked=True))
        if job is None:
            return False
        job.status = JobStatus.processing
        job.started_at = job.started_at or now
        job.lease_expires_at = now + timedelta(seconds=WORKER_LEASE_SECONDS)
        db.commit()
        job_id, event_name, issued_on = job.id, job.event_name, job.issued_on
        design, template_id, send_email = job.design, job.template_id, job.send_email
        title_text, accent_color, signatory = job.title_text, job.accent_color, job.signatory
        font_family = job.font_family
        template = db.get(CertificateTemplate, template_id) if template_id else None
        template_path = Path(template.background_path) if template else None
        record_ids = list(db.scalars(select(CertificateRecord.id).where(CertificateRecord.job_id == job_id)))

    for record_id in record_ids:
        with SessionLocal() as db:
            record = db.get(CertificateRecord, record_id)
            if record is None or record.status != CertificateStatus.queued:
                continue
            job = db.get(GenerationJob, job_id)
            if job:
                job.lease_expires_at = datetime.now(timezone.utc) + timedelta(seconds=WORKER_LEASE_SECONDS)
            if not record.recipient_name or not record.course_name or not record.email:
                record.status = CertificateStatus.failed
                record.error = "Recipient did not pass input validation"
            else:
                try:
                    path = OUTPUT_DIR / job_id / f"{record.id}.pdf"
                    create_certificate(recipient_name=record.recipient_name, course_name=record.course_name,
                                       event_name=event_name, issued_on=issued_on, destination=path,
                                       design=design, template_path=template_path, title_text=title_text,
                                       accent_color=accent_color, signatory=signatory,
                                       font_family=font_family)
                    record.file_path = str(path)
                    record.status = CertificateStatus.succeeded
                    if send_email:
                        try:
                            send_certificate_email(
                                recipient_email=record.email, recipient_name=record.recipient_name,
                                course_name=record.course_name, event_name=event_name,
                                certificate_path=path,
                            )
                            record.email_status = "sent"
                            record.email_error = None
                        except Exception:
                            logger.exception("Certificate email failed for record %s", record.id)
                            record.email_status = "failed"
                            record.email_error = "Email delivery failed; download the certificate and retry"
                except Exception:
                    logger.exception("Certificate generation failed for record %s", record.id)
                    record.status = CertificateStatus.failed
                    record.error = "Certificate generation failed"
                    if send_email:
                        record.email_status = "not_sent"
                        record.email_error = "Certificate generation failed"
            db.commit()

    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        if job is None:
            return True
        records = list(db.scalars(select(CertificateRecord).where(CertificateRecord.job_id == job_id)))
        job.succeeded = sum(r.status == CertificateStatus.succeeded for r in records)
        job.failed = sum(r.status == CertificateStatus.failed for r in records)
        email_failed = sum(r.email_status == "failed" for r in records)
        job.status = JobStatus.completed_with_errors if job.failed or email_failed else JobStatus.completed
        job.finished_at = datetime.now(timezone.utc)
        job.lease_expires_at = None
        db.commit()
    logger.info("Finished certificate job %s", job_id)
    return True


def run_worker() -> None:
    Base.metadata.create_all(engine)
    logger.info("Certificate worker started")
    while True:
        try:
            if not process_one_job():
                time.sleep(WORKER_POLL_SECONDS)
        except Exception:
            logger.exception("Worker loop error")
            time.sleep(WORKER_POLL_SECONDS)


if __name__ == "__main__":
    run_worker()
