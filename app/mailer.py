"""Optional Gmail SMTP delivery for generated certificate PDFs."""
import smtplib
import ssl
from email.message import EmailMessage
from pathlib import Path

from .config import SMTP_APP_PASSWORD, SMTP_FROM_EMAIL, SMTP_HOST, SMTP_PORT, SMTP_USERNAME


def send_certificate_email(*, recipient_email: str, recipient_name: str, course_name: str,
                           event_name: str, certificate_path: Path) -> None:
    """Send one generated PDF using Gmail SMTP and an app password."""
    if not (SMTP_USERNAME and SMTP_APP_PASSWORD and SMTP_FROM_EMAIL):
        raise RuntimeError("Gmail SMTP is not configured")

    message = EmailMessage()
    message["Subject"] = f"Your certificate for {course_name}"
    message["From"] = SMTP_FROM_EMAIL
    message["To"] = recipient_email
    message.set_content(
        f"Hello {recipient_name},\n\n"
        f"Your certificate for {course_name} at {event_name} is attached.\n\n"
        "Congratulations!"
    )
    message.add_attachment(
        certificate_path.read_bytes(), maintype="application", subtype="pdf",
        filename=f"{recipient_name}-certificate.pdf",
    )

    tls_context = ssl.create_default_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        smtp.ehlo()
        smtp.starttls(context=tls_context)
        smtp.ehlo()
        smtp.login(SMTP_USERNAME, SMTP_APP_PASSWORD)
        smtp.send_message(message)
