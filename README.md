# Bulk Certificate Generator

A FastAPI application that accepts a batch of recipients, validates each independently, generates a PDF certificate for every valid recipient, and reports job progress and per-recipient results. The browser studio offers three built-in designs, 20 bundled PDF font families across sans serif, serif, display, handwriting, and monospace categories, editable certificate text and color, first-recipient PDF previews, and uploaded PNG/JPG background templates.

## Requirements

- Python 3.11 or newer
- pip

## Set up and run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API creates a local SQLite database at `data/certificates.db` and PDFs under `data/certificates/`. Interactive API docs are available at `http://127.0.0.1:8000/docs`; liveness and readiness checks are `GET /health` and `GET /ready`.

## Run the production stack locally with Docker

Copy `.env.example` to `.env` and set a unique database password. Use a random alphanumeric value (for example, `openssl rand -hex 24`) so it can safely appear in the PostgreSQL connection URL. Then run:

```sh
docker compose up --build -d
docker compose ps
```

Compose starts PostgreSQL, applies Alembic migrations once, then starts the API and a separate polling worker. PostgreSQL data and generated certificates use persistent Docker volumes. The API binds to localhost so it is not directly exposed to the internet; place it behind a TLS reverse proxy or managed HTTPS load balancer before external use. Keep `.env` out of source control.

For a non-Docker deployment, set `APP_ENV=production`, `DATABASE_URL` to `postgresql+psycopg://user:password@host:5432/database`, and `CERTIFICATE_OUTPUT_DIR` to persistent shared storage. Run `alembic upgrade head` once as a release step before starting API or worker processes. Then run Uvicorn for the API and `python -m app.worker` as a separate service. The UI and API do not require sign-in. The API binds to localhost by default; place it behind a TLS reverse proxy or managed HTTPS load balancer before external use.

The worker uses a database lease to reclaim jobs if it stops unexpectedly. PostgreSQL workers coordinate job claims; use PostgreSQL for multiple workers and API replicas. Back up the database and certificate storage together. Schedule and rehearse restore procedures.

Set `MAX_RECIPIENTS_PER_JOB` (default `1000`) and `WORKER_POLL_SECONDS` (default `1`) to tune limits and polling.

## Tests

```powershell
pytest -q
```

The suite covers job submission and completion, input validation, PDF generation/download, progress, and isolated generation failures.

## Create a bulk job

`POST /api/v1/certificate-jobs` accepts an ISO date and a list of recipients. Each recipient requires `name`, `course_name`, and `email`.

```json
{
  "event_name": "Spring training",
  "issued_on": "2026-10-07",
  "recipients": [
    {"name": "Ada Lovelace", "course_name": "Python fundamentals", "email": "ada@example.com"},
    {"name": "Grace Hopper", "course_name": "Python fundamentals", "email": "grace@example.com"}
  ]
}
```

Example request:

```powershell
$body = Get-Content .\request.json -Raw
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/api/v1/certificate-jobs -ContentType 'application/json' -Body $body
```

The API returns `202 Accepted` and a job ID. Malformed job-level input (such as a missing date or an empty batch) returns `422`; batches over the configured limit return `413`. Recipient-level errors are recorded against that recipient and do not reject valid entries in the same batch.

## Track a job and retrieve certificates

Poll `GET /api/v1/certificate-jobs/{job_id}`. The response includes `queued`, `processing`, `completed`, or `completed_with_errors`, total/succeeded/failed counts, a progress percentage, per-recipient status and validation/generation errors. A successful result includes a `download_url`.

Download one PDF with `GET /api/v1/certificates/{certificate_id}/download`. Downloads return `409` while the certificate is not ready and `404` for unknown records or missing files.

## Use the browser studio

Open `/` to select Heritage, Modern, or Minimal; upload a PNG/JPG certificate background; edit the heading, accent color, and optional signatory; and preview the first recipient before submitting the batch. The saved template choice and edits are applied consistently to every certificate in that batch. Uploaded backgrounds are stored with the application data volume. Uploaded image backgrounds support PNG/JPEG up to 12 MB; the generated certificate stays landscape letter size and overlays the recipient, course, event, heading, date, and optional signatory in the built-in text positions.

## Design decisions

- FastAPI provides typed request handling, OpenAPI documentation, and straightforward deployment with Uvicorn.
- SQLAlchemy stores jobs and recipient results in a relational database. Individual recipient rows preserve validation failures and partial successes.
- The API persists the complete batch before returning. Local development uses an in-process task; production uses a separate database polling worker with expiring leases, so interrupted jobs can be reclaimed.
- PDF generation is isolated per recipient. Errors are logged server-side and represented with a safe per-record failure message.
- A maximum batch size bounds memory, database, and storage impact. Database and generated files must use persistent storage in deployment.

## Production deployment notes

Terminate TLS at a trusted reverse proxy or load balancer and configure its request-size limits and rate limiting. Restrict database network access to application services. Configure PostgreSQL and shared persistent certificate storage for multiple API/worker instances. Monitor worker logs, queue age, disk use, database capacity, and failed counts; alert on sustained queue growth and low storage. The included email check is intentionally lightweight; deployments needing strict address validation can replace it with a dedicated validation library and policy. Review data retention and privacy requirements for recipient names and email addresses before launch.
