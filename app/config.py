from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'certificates.db'}")
OUTPUT_DIR = Path(os.getenv("CERTIFICATE_OUTPUT_DIR", str(BASE_DIR / "data" / "certificates")))
TEMPLATE_DIR = Path(os.getenv("CERTIFICATE_TEMPLATE_DIR", str(BASE_DIR / "data" / "templates")))
if DATABASE_URL.startswith("sqlite"):
    (BASE_DIR / "data").mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
MAX_RECIPIENTS_PER_JOB = int(os.getenv("MAX_RECIPIENTS_PER_JOB", "1000"))
WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "1"))
WORKER_LEASE_SECONDS = int(os.getenv("WORKER_LEASE_SECONDS", "300"))
APP_ENV = os.getenv("APP_ENV", "development").lower()
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "").strip()
SMTP_APP_PASSWORD = os.getenv("SMTP_APP_PASSWORD", "").replace(" ", "").strip()
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USERNAME).strip()
SMTP_CONFIGURED = bool(SMTP_USERNAME and SMTP_APP_PASSWORD and SMTP_FROM_EMAIL)
