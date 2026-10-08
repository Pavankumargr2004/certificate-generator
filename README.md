# Bulk Certificate Generator

A Python backend API for generating PDF certificates in bulk. Submit one job containing many recipients, track each recipient’s result, and download the certificates individually or together as a ZIP. An optional responsive browser studio provides a visual way to build, review, and submit batches.

The project was built for a backend API assignment. Deployment to the public internet is not required by the assignment.

## Features

- Bulk certificate jobs with per-recipient input validation and isolated generation errors.
- CSV recipient import with a downloadable starter file, header aliases, and row validation feedback.
- Background processing with job status, progress, and recipient-level results.
- Individual PDF downloads and one ZIP containing all successful certificates in a completed job.
- Three built-in certificate designs, editable text and accent color, and first-recipient previews.
- Responsive browser studio layouts for desktop, tablet, and phone screens.
- PNG/JPEG certificate backgrounds, with image size limits.
- A certificate font catalog with built-in and bundled font options.
- Optional Gmail delivery of each generated PDF, enabled per job.
- PostgreSQL for the Docker stack; SQLite for local development.

## Technology

- Python 3.11 or newer
- FastAPI and Uvicorn
- SQLAlchemy and Alembic
- PostgreSQL in Docker Compose, or SQLite for local development
- ReportLab and Pillow for PDF and image handling
- Pytest for automated tests

## Run with Docker

Install and start Docker Desktop, then open a terminal in the project directory.

Copy the environment template and replace the PostgreSQL password with a strong alphanumeric value:

```powershell
Copy-Item .env.example .env
```

Start the services:

```powershell
docker compose up --build -d
docker compose ps
```

Compose starts PostgreSQL, applies database migrations, initializes persistent file storage, and starts the API and background worker. The first build may take a few minutes.

| Page | URL |
| --- | --- |
| Browser studio | <http://127.0.0.1:8000/> |
| Interactive API docs (Swagger) | <http://127.0.0.1:8000/docs> |
| OpenAPI schema | <http://127.0.0.1:8000/openapi.json> |
| Liveness check | <http://127.0.0.1:8000/health> |
| Readiness/database check | <http://127.0.0.1:8000/ready> |

To stop the services while keeping the database and generated files:

```powershell
docker compose down
```

The database, uploaded backgrounds, and certificates are stored in named Docker volumes and survive `docker compose down`.

## API reference

The full interactive request/response schemas are available in Swagger at `/docs`. Main endpoints:

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness check. |
| `GET` | `/ready` | Readiness and database connection check. |
| `GET` | `/api/v1/fonts` | List certificate font IDs and categories. |
| `GET` | `/api/v1/templates` | List built-in designs and uploaded templates. |
| `POST` | `/api/v1/templates` | Upload a PNG/JPEG background (`name` and `file` form fields). |
| `GET` | `/api/v1/recipients/csv-template` | Download a sample CSV with the required headers. |
| `POST` | `/api/v1/recipients/import-csv` | Parse and validate an uploaded recipient CSV without creating a job. |
| `POST` | `/api/v1/certificates/preview` | Generate a one-recipient PDF preview. |
| `POST` | `/api/v1/certificate-jobs` | Submit a bulk generation job. |
| `GET` | `/api/v1/certificate-jobs/{job_id}` | Read job progress and recipient results. |
| `GET` | `/api/v1/certificates/{certificate_id}/download` | Download one generated PDF. |
| `GET` | `/api/v1/certificate-jobs/{job_id}/download` | Download successful PDFs for a job as a ZIP. |

## Run locally without Docker

Local development uses SQLite and runs the job in the API process. From the project directory:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000/docs> for the API or <http://127.0.0.1:8000/> for the studio. The local database is created at `data/certificates.db`; generated PDFs and uploaded backgrounds are stored under `data/`.

## Generate a batch through the API

The simplest way to try the API is Swagger UI at <http://127.0.0.1:8000/docs>:

1. Expand **POST `/api/v1/certificate-jobs`** and choose **Try it out**.
2. Enter a JSON request and choose **Execute**.
3. Copy the returned job ID and use **GET `/api/v1/certificate-jobs/{job_id}`** to check progress and results.
4. Open a recipient’s `download_url` for one PDF, or use `download_zip_url` to download the successful certificates together.

### Import recipients from CSV

Download the starter file from **GET `/api/v1/recipients/csv-template`**. The required columns are `name`, `course_name`, and `email`. Common alternatives such as `full_name`, `recipient_name`, `course`, `achievement`, and `email_address` are also recognized. Headers are case-insensitive, and spaces or punctuation are normalized.

To preview an uploaded file in Swagger, use **POST `/api/v1/recipients/import-csv`**, choose **Try it out**, and upload the CSV. The response contains normalized recipient rows, their source row numbers, and validation errors. This endpoint does not create a generation job. In the studio, **Import CSV** fills the editable recipient list; review or correct flagged rows, then submit the batch as usual.

CSV uploads must be UTF-8, no larger than 5 MB, and contain at least one recipient row. The same configured per-job recipient limit applies. Invalid recipient values are returned with row-level errors so they can be fixed before generation.

Example request:

```json
{
  "event_name": "Spring training",
  "issued_on": "2026-10-08",
  "design": "classic",
  "font_family": "lora",
  "send_email": false,
  "recipients": [
    {
      "name": "Ada Lovelace",
      "course_name": "Python fundamentals",
      "email": "ada@example.com"
    },
    {
      "name": "Grace Hopper",
      "course_name": "Systems engineering",
      "email": "grace@example.com"
    }
  ]
}
```

`event_name`, `issued_on`, and a non-empty `recipients` list are required. Each recipient needs `name`, `course_name`, and `email`. `send_email` defaults to `false`. Optional design fields include `design` (`classic`, `modern`, or `minimal`), `template_id`, `title_text`, `accent_color`, `signatory`, and `font_family`. Check `GET /api/v1/fonts` for the valid font IDs and `GET /api/v1/templates` for the available designs and uploaded templates.

PowerShell example:

```powershell
$payload = @{
  event_name = "Spring training"
  issued_on = "2026-10-08"
  recipients = @(
    @{ name = "Ada Lovelace"; course_name = "Python fundamentals"; email = "ada@example.com" },
    @{ name = "Grace Hopper"; course_name = "Systems engineering"; email = "grace@example.com" }
  )
} | ConvertTo-Json -Depth 5

$job = Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/certificate-jobs" `
  -ContentType "application/json" `
  -Body $payload

$job.id
```

The API returns `202 Accepted` with a job ID. In the Docker stack, the separate worker processes jobs asynchronously. In local development, the API processes jobs in the background.

### Track job progress and downloads

Poll `GET /api/v1/certificate-jobs/{job_id}`. The response includes:

- `status`: `queued`, `processing`, `completed`, or `completed_with_errors`.
- `total`, `succeeded`, `failed`, and `progress_percent`.
- A result for each recipient, including validation or generation errors.
- A `download_url` for each successfully generated PDF.
- A `download_zip_url` for all successful PDFs in the completed job.
- Email delivery counts and statuses when email was requested.

Download one PDF with `GET /api/v1/certificates/{certificate_id}/download`.

Download all successful PDFs from a completed job with `GET /api/v1/certificate-jobs/{job_id}/download`. The response is a ZIP file. The endpoint returns `409` while the job is still processing or if there are no successful certificates.

For job-level invalid input, the API returns `422`; a batch above the configured recipient limit returns `413`. Invalid recipients are reported individually without preventing other valid recipients from being processed.

## Browser studio

The optional studio at `/` lets you import a CSV into an editable recipient list, choose a built-in design, upload a PNG/JPEG background, edit the heading, color, signatory, and font, and preview the first recipient before submitting a batch. Those design choices apply to the entire batch. The interface adapts to desktop, tablet, and phone screens, with form controls arranged for narrow viewports. The **Email each certificate to its recipient** checkbox opts the batch into email delivery when Gmail is configured. Completed batches also show a single ZIP download link.

Background uploads must be readable PNG or JPEG images, no larger than 12 MB and 20 million pixels. The PDF output uses landscape Letter pages and overlays the recipient and course details on the chosen design/background.

## Optional Gmail delivery

Email delivery is off by default. To enable it, add these values to `.env` for the Docker stack:

```dotenv
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-address@gmail.com
SMTP_APP_PASSWORD=your-google-app-password
SMTP_FROM_EMAIL=your-address@gmail.com
```

Use a Google App Password, not your regular Google account password. App Passwords require 2-Step Verification and may be unavailable for some managed accounts. Keep `.env` private and out of source control. After updating it, recreate the services so they receive the new environment:

```powershell
docker compose up -d --force-recreate api worker
```

Set `"send_email": true` in the batch request, or turn on the studio checkbox. The worker emails the generated PDF to each valid recipient. The API rejects an email-enabled job with `503` if SMTP is not configured. Email failures are recorded separately and do not discard generated PDFs; those PDFs remain downloadable.

Job responses include `email_requested`, `email_sent`, and `email_failed`. Each recipient includes `email_status` (`not_requested`, `queued`, `sent`, `failed`, or `not_sent`) and an `email_error` when applicable.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `POSTGRES_PASSWORD` | Required for Docker | Password for the Compose PostgreSQL user. |
| `DATABASE_URL` | Local SQLite path | SQLAlchemy database connection string. |
| `MAX_RECIPIENTS_PER_JOB` | `1000` | Maximum recipients accepted in a batch. |
| `WORKER_POLL_SECONDS` | `1` | Idle delay between worker polls. |
| `WORKER_LEASE_SECONDS` | `300` | Time before an interrupted processing job can be reclaimed. |
| `CERTIFICATE_OUTPUT_DIR` | `data/certificates` | Certificate output directory; set to persistent storage in deployments. |
| `CERTIFICATE_TEMPLATE_DIR` | `data/templates` | Uploaded template directory. |
| `SMTP_HOST` | `smtp.gmail.com` | Outgoing SMTP server when email delivery is enabled. |
| `SMTP_PORT` | `587` | SMTP STARTTLS port. |
| `SMTP_USERNAME` | Empty | Gmail account used to authenticate. |
| `SMTP_APP_PASSWORD` | Empty | Google App Password used by SMTP. |
| `SMTP_FROM_EMAIL` | `SMTP_USERNAME` | Sender address. |

## Tests

Run the automated test suite from the project directory:

```powershell
pytest -q
```

Tests cover job creation, recipient validation, PDF generation and downloads, ZIP downloads, progress, individual generation failures, template upload/preview, and optional email behavior. Email tests use a mocked SMTP transport; they do not send real messages.

## Design notes and limitations

- FastAPI provides request validation and an OpenAPI document; SQLAlchemy persists jobs, recipients, and templates.
- The API saves the complete recipient batch before processing. A separate database-backed worker is used in Docker; local development uses FastAPI background processing.
- Certificate creation and email sending are isolated per recipient so one failure does not stop the rest of the batch.
- PostgreSQL is used in Compose. SQLite is intended for local development and a single local process.
- The API currently has no authentication, as requested for this project. Compose binds it to `127.0.0.1`; do not expose it publicly without adding authentication/authorization and reviewing deployment security.
- Public deployment is outside the assignment requirements. A real deployment also needs HTTPS, persistent database and file storage, backups, monitoring, and a data-retention policy.

## Future scope

The following are possible future enhancements; they are **not implemented in the current project**.

### Verifiable digital credentials

Give each certificate a unique public verification page and QR code. The page could confirm that the credential was issued by the organization and show whether it is valid, expired, or revoked. Add signed credential data to make tampering easier to detect.

### Visual certificate designer

Replace fixed text positions with a drag-and-drop editor for names, course details, dates, logos, signatures, and QR codes. Support reusable brand kits, editable data placeholders, text-fit previews, and saved templates.

### Organization workspaces

Add sign-in, organization separation, and roles such as owner, editor, and viewer. Keep templates, batches, certificate records, and audit history scoped to each organization before offering the service to multiple customers.

### Live delivery operations

Add real-time job updates, retry controls for failed certificates and emails, delivery attempt history, configurable rate limits, and webhooks for job completion. Retries should avoid creating duplicate certificates or sending duplicate emails.

### Learning and HR integrations

Connect learning management and HR systems to import course completions and issue certificates automatically. Start with CSV/XLSX import and webhooks, then add specific platforms based on user needs.

### Credential analytics

Add dashboards for issued, delivered, downloaded, verified, expired, and revoked certificates, with filters for event, course, and date range. Define privacy and retention settings before collecting recipient activity.
