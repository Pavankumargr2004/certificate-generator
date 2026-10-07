from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .config import APP_ENV, MAX_RECIPIENTS_PER_JOB, TEMPLATE_DIR
from .database import Base, SessionLocal, engine
from .font_catalog import FONT_CATALOG
from .generator import BUILTIN_DESIGNS, create_certificate
from .models import CertificateRecord, CertificateStatus, CertificateTemplate, GenerationJob
from .schemas import JobCreate, JobResult, PreviewCreate, RecipientInput
from .worker import process_one_job


@asynccontextmanager
async def lifespan(_: FastAPI):
    if APP_ENV != "production":
        Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Bulk Certificate Generator", version="1.0.0", lifespan=lifespan)


def serialize_job(db: Session, job: GenerationJob) -> dict:
    records = list(db.scalars(select(CertificateRecord).where(CertificateRecord.job_id == job.id)
                              .order_by(CertificateRecord.position)))
    succeeded = sum(r.status == CertificateStatus.succeeded for r in records)
    failed = sum(r.status == CertificateStatus.failed for r in records)
    return {
        "id": job.id, "event_name": job.event_name, "issued_on": job.issued_on,
        "status": job.status, "total": job.total, "succeeded": succeeded, "failed": failed,
        "progress_percent": round((succeeded + failed) * 100 / job.total, 2) if job.total else 100,
        "created_at": job.created_at.isoformat(), "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "certificates": [{"id": r.id, "recipient_name": r.recipient_name, "course_name": r.course_name,
                          "email": r.email, "status": r.status, "error": r.error,
                          "download_url": f"/api/v1/certificates/{r.id}/download" if r.status == CertificateStatus.succeeded else None}
                         for r in records],
    }


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def readiness() -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready"}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database is not ready") from exc


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(Path(__file__).parent / "static" / "index.html", media_type="text/html")


@app.get("/api/v1/templates")
def list_templates() -> dict:
    with SessionLocal() as db:
        uploaded = list(db.scalars(select(CertificateTemplate).order_by(CertificateTemplate.created_at.desc())))
    return {"templates": BUILTIN_DESIGNS + [
        {"id": item.id, "name": item.name, "description": "Uploaded image background", "kind": "uploaded"}
        for item in uploaded
    ]}


@app.get("/api/v1/fonts")
def list_certificate_fonts() -> dict:
    return {"fonts": [{"id": font["id"], "name": font["name"], "category": font["category"]}
                      for font in FONT_CATALOG]}


@app.post("/api/v1/templates", status_code=201)
async def upload_template(name: str = Form(min_length=2, max_length=120),
                          file: UploadFile = File(...)) -> dict:
    name = name.strip()
    if len(name) < 2:
        raise HTTPException(422, "Template name must have at least two characters")
    contents = await file.read(12 * 1024 * 1024 + 1)
    if len(contents) > 12 * 1024 * 1024:
        raise HTTPException(413, "Template images must be 12 MB or smaller")
    try:
        with Image.open(BytesIO(contents)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise HTTPException(415, "Upload a PNG or JPEG certificate background")
            if image.width * image.height > 20_000_000:
                raise HTTPException(413, "Template image dimensions are too large")
            image.load()
            normalized = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(415, "The uploaded file is not a readable PNG or JPEG image") from exc

    template_id = str(uuid4())
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    destination = TEMPLATE_DIR / f"{template_id}.png"
    normalized.save(destination, format="PNG", optimize=True)
    with SessionLocal() as db:
        template = CertificateTemplate(id=template_id, name=name, background_path=str(destination))
        db.add(template)
        db.commit()
    return {"id": template_id, "name": name, "description": "Uploaded image background", "kind": "uploaded"}


def resolve_template(db: Session, template_id: str | None) -> Path | None:
    if not template_id:
        return None
    template = db.get(CertificateTemplate, template_id)
    if template is None or not Path(template.background_path).is_file():
        raise HTTPException(404, "Uploaded certificate template not found")
    return Path(template.background_path)


@app.post("/api/v1/certificates/preview")
def preview_certificate(payload: PreviewCreate) -> Response:
    with SessionLocal() as db:
        template_path = resolve_template(db, payload.template_id)
    pdf_bytes = create_certificate(
        recipient_name=payload.recipient.name, course_name=payload.recipient.course_name,
        event_name=payload.event_name, issued_on=payload.issued_on.isoformat(),
        design=payload.design, template_path=template_path, title_text=payload.title_text,
        accent_color=payload.accent_color, signatory=payload.signatory,
        font_family=payload.font_family,
    )
    return Response(content=pdf_bytes, media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=certificate-preview.pdf"})


@app.post("/api/v1/certificate-jobs", response_model=JobResult, status_code=202)
def create_job(payload: JobCreate, background_tasks: BackgroundTasks) -> dict:
    if len(payload.recipients) > MAX_RECIPIENTS_PER_JOB:
        raise HTTPException(413, f"A job may contain at most {MAX_RECIPIENTS_PER_JOB} recipients")
    job = GenerationJob(event_name=payload.event_name, issued_on=payload.issued_on.isoformat(), total=len(payload.recipients))
    with SessionLocal() as db:
        if payload.template_id:
            resolve_template(db, payload.template_id)
        job.design = payload.design
        job.template_id = payload.template_id
        job.title_text = payload.title_text
        job.accent_color = payload.accent_color
        job.signatory = payload.signatory
        job.font_family = payload.font_family
        db.add(job)
        db.flush()
        for position, item in enumerate(payload.recipients):
            try:
                recipient = RecipientInput.model_validate(item)
                record = CertificateRecord(job_id=job.id, position=position, recipient_name=recipient.name,
                                           course_name=recipient.course_name, email=recipient.email)
            except ValidationError as exc:
                errors = "; ".join(f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors())
                record = CertificateRecord(job_id=job.id, position=position, status=CertificateStatus.failed,
                                           error=f"Invalid recipient: {errors[:1000]}")
                job.failed += 1
            db.add(record)
        db.commit()
        db.refresh(job)
        response = serialize_job(db, job)
    if APP_ENV != "production":
        background_tasks.add_task(process_one_job)
    return response


@app.get("/api/v1/certificate-jobs/{job_id}", response_model=JobResult)
def get_job(job_id: str) -> dict:
    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        if job is None:
            raise HTTPException(404, "Certificate job not found")
        return serialize_job(db, job)


@app.get("/api/v1/certificates/{certificate_id}/download")
def download_certificate(certificate_id: str) -> FileResponse:
    with SessionLocal() as db:
        record = db.get(CertificateRecord, certificate_id)
        if record is None:
            raise HTTPException(404, "Certificate not found")
        if record.status != CertificateStatus.succeeded or not record.file_path:
            raise HTTPException(409, "Certificate is not available for download")
        path = Path(record.file_path)
        if not path.is_file():
            raise HTTPException(404, "Certificate file is no longer available")
        name = (record.recipient_name or "certificate").replace("/", "_").replace("\\", "_")
        return FileResponse(path, media_type="application/pdf", filename=f"{name}-certificate.pdf")
