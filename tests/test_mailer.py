from pathlib import Path

from app import mailer


def test_gmail_mailer_uses_tls_and_attaches_certificate(tmp_path, monkeypatch):
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.test")
    monkeypatch.setattr(mailer, "SMTP_PORT", 587)
    monkeypatch.setattr(mailer, "SMTP_USERNAME", "sender@example.com")
    monkeypatch.setattr(mailer, "SMTP_APP_PASSWORD", "app-password")
    monkeypatch.setattr(mailer, "SMTP_FROM_EMAIL", "sender@example.com")
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            assert (host, port, timeout) == ("smtp.test", 587, 30)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def ehlo(self):
            pass

        def starttls(self, context):
            assert context is not None

        def login(self, username, password):
            assert (username, password) == ("sender@example.com", "app-password")

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    pdf_path = tmp_path / "certificate.pdf"
    pdf_path.write_bytes(b"%PDF-demo")
    mailer.send_certificate_email(
        recipient_email="person@example.com", recipient_name="Demo Person",
        course_name="Python", event_name="Demo", certificate_path=Path(pdf_path),
    )

    assert len(sent) == 1
    assert sent[0]["To"] == "person@example.com"
    assert sent[0].get_content_maintype() == "multipart"
    attachment = list(sent[0].iter_attachments())[0]
    assert attachment.get_content_type() == "application/pdf"
    assert attachment.get_payload(decode=True) == b"%PDF-demo"
