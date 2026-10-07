from io import BytesIO
from datetime import datetime, timezone

from PIL import Image
from app import worker
from app import main
from app.models import CertificateRecord, CertificateStatus, GenerationJob, JobStatus
from sqlalchemy import select


def payload(recipients=None):
    return {
        "event_name": "Python course",
        "issued_on": "2026-10-07",
        "recipients": recipients or [
            {"name": "Ada Lovelace", "course_name": "Python", "email": "ada@example.com"}
        ],
    }


def test_create_job_and_track_completion(client):
    response = client.post("/api/v1/certificate-jobs", json=payload())
    assert response.status_code == 202
    job = response.json()
    assert job["total"] == 1
    assert job["certificates"][0]["status"] == "queued"
    status = client.get(f"/api/v1/certificate-jobs/{job['id']}").json()
    assert status["status"] == "completed"
    assert status["progress_percent"] == 100
    assert status["succeeded"] == 1


def test_invalid_recipient_is_reported_without_rejecting_batch(client):
    recipients = [
        {"name": "Valid Person", "course_name": "Python", "email": "valid@example.com"},
        {"name": "", "course_name": "Python", "email": "not-an-email"},
    ]
    job = client.post("/api/v1/certificate-jobs", json=payload(recipients)).json()
    assert job["total"] == 2
    assert job["failed"] == 1
    result = client.get(f"/api/v1/certificate-jobs/{job['id']}").json()
    assert result["status"] == "completed_with_errors"
    assert result["succeeded"] == 1
    assert result["certificates"][1]["error"].startswith("Invalid recipient:")


def test_pdf_generation_and_download(client):
    job = client.post("/api/v1/certificate-jobs", json=payload()).json()
    certificate_id = job["certificates"][0]["id"]
    downloaded = client.get(f"/api/v1/certificates/{certificate_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.content.startswith(b"%PDF")


def test_single_generation_failure_does_not_stop_other_recipients(client, monkeypatch):
    original = worker.create_certificate

    def fail_for_one(*, recipient_name, **kwargs):
        if recipient_name == "Fails Here":
            raise RuntimeError("simulated renderer failure")
        return original(recipient_name=recipient_name, **kwargs)

    monkeypatch.setattr(worker, "create_certificate", fail_for_one)
    recipients = [
        {"name": "Fails Here", "course_name": "Python", "email": "a@example.com"},
        {"name": "Still Works", "course_name": "Python", "email": "b@example.com"},
    ]
    job = client.post("/api/v1/certificate-jobs", json=payload(recipients)).json()
    result = client.get(f"/api/v1/certificate-jobs/{job['id']}").json()
    assert result["status"] == "completed_with_errors"
    assert result["failed"] == 1
    assert result["succeeded"] == 1


def test_request_shape_validation_and_missing_job(client):
    home = client.get("/")
    assert home.status_code == 200
    assert "Bulk Certificate Studio" in home.text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    assert client.post("/api/v1/certificate-jobs", json={"recipients": []}).status_code == 422
    assert client.get("/api/v1/certificate-jobs/missing").status_code == 404
    assert client.get("/api/v1/certificates/missing/download").status_code == 404


def test_api_key_is_required_when_configured(client, monkeypatch):
    monkeypatch.setattr(main, "API_KEY", "a" * 40)
    assert client.post("/api/v1/certificate-jobs", json=payload()).status_code == 401
    response = client.post("/api/v1/certificate-jobs", json=payload(), headers={"X-API-Key": "a" * 40})
    assert response.status_code == 202


def test_expired_job_lease_is_reclaimed(client):
    response = client.post("/api/v1/certificate-jobs", json=payload()).json()
    job_id = response["id"]
    with main.SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        record = db.scalar(select(CertificateRecord).where(CertificateRecord.job_id == job_id))
        job.status = JobStatus.processing
        job.lease_expires_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        record.status = CertificateStatus.queued
        record.file_path = None
        db.commit()

    assert worker.process_one_job() is True
    result = client.get(f"/api/v1/certificate-jobs/{job_id}").json()
    assert result["status"] == "completed"
    assert result["succeeded"] == 1


def test_production_mode_requires_key_and_uses_separate_worker(client, monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    monkeypatch.setattr(main, "API_KEY", "b" * 40)
    assert client.post("/api/v1/certificate-jobs", json=payload()).status_code == 401

    response = client.post("/api/v1/certificate-jobs", json=payload(),
                           headers={"X-API-Key": "b" * 40})
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert client.get(f"/api/v1/certificate-jobs/{job_id}",
                      headers={"X-API-Key": "b" * 40}).json()["status"] == "queued"
    assert worker.process_one_job() is True
    result = client.get(f"/api/v1/certificate-jobs/{job_id}",
                        headers={"X-API-Key": "b" * 40}).json()
    assert result["status"] == "completed"


def test_builtin_templates_and_first_recipient_preview(client):
    templates = client.get("/api/v1/templates").json()["templates"]
    assert [template["id"] for template in templates] == ["classic", "modern", "minimal"]
    preview = client.post("/api/v1/certificates/preview", json={
        "event_name": "Spring Academy", "issued_on": "2026-10-07",
        "recipient": {"name": "Ada Lovelace", "course_name": "Mathematics", "email": "ada@example.com"},
        "design": "modern", "title_text": "CERTIFICATE OF EXCELLENCE",
        "accent_color": "#247766", "signatory": "Director of Learning",
    })
    assert preview.status_code == 200
    assert preview.headers["content-type"] == "application/pdf"
    assert preview.content.startswith(b"%PDF")


def test_upload_template_and_apply_to_entire_batch(client):
    image_buffer = BytesIO()
    Image.new("RGB", (1200, 900), "#f4f0e6").save(image_buffer, format="PNG")
    upload = client.post("/api/v1/templates", data={"name": "My Background"},
                         files={"file": ("background.png", image_buffer.getvalue(), "image/png")})
    assert upload.status_code == 201
    template = upload.json()
    assert template["kind"] == "uploaded"

    preview_data = {
        "event_name": "Python course", "issued_on": "2026-10-07",
        "recipient": {"name": "Ada Lovelace", "course_name": "Python", "email": "ada@example.com"},
        "template_id": template["id"], "title_text": "COMPLETION AWARD", "accent_color": "#287A6C",
    }
    preview = client.post("/api/v1/certificates/preview", json=preview_data)
    assert preview.status_code == 200 and preview.content.startswith(b"%PDF")

    body = payload()
    body.update({"template_id": template["id"], "title_text": "COMPLETION AWARD", "accent_color": "#287A6C"})
    job = client.post("/api/v1/certificate-jobs", json=body).json()
    result = client.get(f"/api/v1/certificate-jobs/{job['id']}").json()
    assert result["status"] == "completed"
    downloaded = client.get(result["certificates"][0]["download_url"])
    assert downloaded.status_code == 200 and downloaded.content.startswith(b"%PDF")


def test_template_upload_rejects_non_image(client):
    response = client.post("/api/v1/templates", data={"name": "Not an image"},
                           files={"file": ("note.txt", b"hello", "text/plain")})
    assert response.status_code == 415
