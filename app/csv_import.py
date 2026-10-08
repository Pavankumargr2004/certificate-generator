"""CSV parsing helpers for importing certificate recipients."""
import csv
import re
from io import StringIO

MAX_CSV_BYTES = 5 * 1024 * 1024

_HEADER_ALIASES = {
    "name": "name",
    "full_name": "name",
    "recipient_name": "name",
    "course": "course_name",
    "course_name": "course_name",
    "achievement": "course_name",
    "email": "email",
    "email_address": "email",
}
_REQUIRED_FIELDS = ("name", "course_name", "email")


def parse_recipient_csv(contents: bytes, *, max_recipients: int) -> list[dict]:
    """Parse recipient rows; return canonical field names and source row numbers."""
    if len(contents) > MAX_CSV_BYTES:
        raise ValueError("CSV files must be 5 MB or smaller")
    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must use UTF-8 encoding") from exc
    if not text.strip():
        raise ValueError("CSV file is empty")

    try:
        reader = csv.DictReader(StringIO(text, newline=""), strict=True)
        if not reader.fieldnames:
            raise ValueError("CSV must include a header row")
        normalized_headers = [re.sub(r"[^a-z0-9]+", "_", (name or "").strip().lower()).strip("_")
                              for name in reader.fieldnames]
        if any(not name for name in normalized_headers):
            raise ValueError("CSV headers must not be blank")
        reader.fieldnames = normalized_headers

        field_map: dict[str, str] = {}
        for normalized in normalized_headers:
            canonical = _HEADER_ALIASES.get(normalized)
            if canonical:
                if canonical in field_map:
                    raise ValueError(f"CSV contains duplicate columns for '{canonical}'")
                field_map[canonical] = normalized
        missing = [field for field in _REQUIRED_FIELDS if field not in field_map]
        if missing:
            raise ValueError("CSV is missing required columns: " + ", ".join(missing))

        recipients = []
        for row_number, row in enumerate(reader, start=2):
            extras = row.get(None)
            if extras and any(str(value).strip() for value in extras):
                raise ValueError(f"CSV row {row_number} has more values than the header")
            recipient = {field: (row.get(header) or "").strip()
                         for field, header in field_map.items()}
            if not any(recipient.values()):
                continue
            if len(recipients) >= max_recipients:
                raise OverflowError(f"CSV may contain at most {max_recipients} recipients")
            recipients.append({**recipient, "row_number": row_number})
        if not recipients:
            raise ValueError("CSV contains no recipient rows")
        return recipients
    except csv.Error as exc:
        raise ValueError(f"CSV could not be parsed: {exc}") from exc
