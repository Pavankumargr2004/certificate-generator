from io import BytesIO
from datetime import datetime, timezone
from zipfile import ZipFile

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


def test_download_all_successful_certificates_as_zip(client):
    job = client.post("/api/v1/certificate-jobs", json=payload()).json()
    assert job["download_zip_url"] == f"/api/v1/certificate-jobs/{job['id']}/download"
    response = client.get(job["download_zip_url"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    with ZipFile(BytesIO(response.content)) as archive:
        names = archive.namelist()
        assert len(names) == 1
        assert names[0].endswith("-certificate.pdf")
        assert archive.read(names[0]).startswith(b"%PDF")


def test_email_delivery_is_opt_in_and_reports_per_recipient_status(client, monkeypatch):
    monkeypatch.setattr(main, "SMTP_CONFIGURED", True)
    sent_to = []

    def capture_email(**kwargs):
        sent_to.append(kwargs["recipient_email"])

    monkeypatch.setattr(worker, "send_certificate_email", capture_email)
    request_payload = payload([
        {"name": "First Person", "course_name": "Python", "email": "first@example.com"},
        {"name": "Second Person", "course_name": "Python", "email": "second@example.com"},
    ])
    request_payload["send_email"] = True
    response = client.post("/api/v1/certificate-jobs", json=request_payload)
    assert response.status_code == 202
    job = client.get(f"/api/v1/certificate-jobs/{response.json()['id']}").json()
    assert job["email_requested"] is True
    assert job["email_sent"] == 2
    assert job["email_failed"] == 0
    assert sent_to == ["first@example.com", "second@example.com"]
    assert [item["email_status"] for item in job["certificates"]] == ["sent", "sent"]


def test_email_failure_does_not_lose_generated_certificate(client, monkeypatch):
    monkeypatch.setattr(main, "SMTP_CONFIGURED", True)

    def fail_email(**kwargs):
        raise RuntimeError("simulated SMTP failure")

    monkeypatch.setattr(worker, "send_certificate_email", fail_email)
    request_payload = payload()
    request_payload["send_email"] = True
    response = client.post("/api/v1/certificate-jobs", json=request_payload)
    job = client.get(f"/api/v1/certificate-jobs/{response.json()['id']}").json()
    assert job["status"] == "completed_with_errors"
    assert job["succeeded"] == 1
    assert job["email_failed"] == 1
    assert job["certificates"][0]["email_status"] == "failed"
    assert client.get(job["certificates"][0]["download_url"]).status_code == 200


def test_email_requested_without_smtp_configuration_is_rejected(client):
    request_payload = payload()
    request_payload["send_email"] = True
    response = client.post("/api/v1/certificate-jobs", json=request_payload)
    assert response.status_code == 503


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
    assert "Import CSV" in home.text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").json() == {"status": "ready"}
    assert client.post("/api/v1/certificate-jobs", json={"recipients": []}).status_code == 422
    assert client.get("/api/v1/certificate-jobs/missing").status_code == 404
    assert client.get("/api/v1/certificates/missing/download").status_code == 404


def test_csv_import_normalizes_headers_and_flags_invalid_rows(client):
    csv_data = (
        "Full Name,Course,Email Address\r\n"
        "Ada Lovelace,Python fundamentals,ada@example.com\r\n"
        "Grace Hopper,,invalid-email\r\n"
    )
    response = client.post("/api/v1/recipients/import-csv",
                           files={"file": ("recipients.csv", csv_data.encode(), "text/csv")})
    assert response.status_code == 200
    result = response.json()
    assert result["count"] == 2
    assert result["invalid_rows"] == 1
    assert result["recipients"][0] == {
        "name": "Ada Lovelace", "course_name": "Python fundamentals",
        "email": "ada@example.com", "row_number": 2, "errors": [],
    }
    assert result["recipients"][1]["row_number"] == 3
    assert result["recipients"][1]["errors"]


def test_csv_import_rejects_missing_headers_and_too_many_recipients(client, monkeypatch):
    missing_header = client.post("/api/v1/recipients/import-csv",
                                 files={"file": ("bad.csv", b"name,email\nAda,ada@example.com\n", "text/csv")})
    assert missing_header.status_code == 422

    monkeypatch.setattr(main, "MAX_RECIPIENTS_PER_JOB", 1)
    oversized = client.post("/api/v1/recipients/import-csv", files={
        "file": ("large.csv", b"name,course_name,email\nAda,Python,a@example.com\nGrace,Python,g@example.com\n", "text/csv")
    })
    assert oversized.status_code == 413


def test_csv_template_download(client):
    response = client.get("/api/v1/recipients/csv-template")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.content.startswith(b"name,course_name,email")


def test_authentication_is_not_required(client):
    response = client.post("/api/v1/certificate-jobs", json=payload())
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


def test_production_mode_uses_separate_worker_without_authentication(client, monkeypatch):
    monkeypatch.setattr(main, "APP_ENV", "production")
    response = client.post("/api/v1/certificate-jobs", json=payload())
    assert response.status_code == 202
    job_id = response.json()["id"]
    assert client.get(f"/api/v1/certificate-jobs/{job_id}").json()["status"] == "queued"
    assert worker.process_one_job() is True
    result = client.get(f"/api/v1/certificate-jobs/{job_id}").json()
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
