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
