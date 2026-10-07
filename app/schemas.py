from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .font_catalog import FONT_IDS
from .models import CertificateStatus, JobStatus

BUILTIN_DESIGNS = {"classic", "modern", "minimal"}
CERTIFICATE_FONTS = FONT_IDS


class JobCreate(BaseModel):
    event_name: str = Field(min_length=1, max_length=200)
    issued_on: date
    recipients: list[dict[str, Any]] = Field(min_length=1)
    design: str = "classic"
    template_id: str | None = None
    title_text: str = Field(default="CERTIFICATE OF COMPLETION", min_length=1, max_length=120)
    accent_color: str = "#B28B3D"
    signatory: str = Field(default="", max_length=120)
    font_family: str = "serif"

    @field_validator("event_name")
    @classmethod
    def trim_event(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("event_name cannot be blank")
        return value

    @field_validator("design")
    @classmethod
    def validate_design(cls, value: str) -> str:
        if value not in BUILTIN_DESIGNS:
            raise ValueError("design must be classic, modern, or minimal")
        return value

    @field_validator("font_family")
    @classmethod
    def validate_font_family(cls, value: str) -> str:
        if value not in CERTIFICATE_FONTS:
            raise ValueError("font_family must be a supported certificate font id")
        return value

    @field_validator("title_text", "signatory")
    @classmethod
    def trim_optional_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("accent_color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if len(value) != 7 or not value.startswith("#") or any(ch not in "0123456789abcdefABCDEF" for ch in value[1:]):
            raise ValueError("accent_color must be a six-digit hex color")
        return value.upper()


class RecipientInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=160)
    course_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def basic_email_format(cls, value: str) -> str:
        if value.count("@") != 1 or "." not in value.rsplit("@", 1)[1]:
            raise ValueError("email must be a valid email address")
        return value


class PreviewCreate(BaseModel):
    event_name: str = Field(min_length=1, max_length=200)
    issued_on: date
    recipient: RecipientInput
    design: str = "classic"
    template_id: str | None = None
    title_text: str = Field(default="CERTIFICATE OF COMPLETION", min_length=1, max_length=120)
    accent_color: str = "#B28B3D"
    signatory: str = Field(default="", max_length=120)
    font_family: str = "serif"

    @field_validator("design")
    @classmethod
    def validate_design(cls, value: str) -> str:
        if value not in BUILTIN_DESIGNS:
            raise ValueError("design must be classic, modern, or minimal")
        return value

    @field_validator("font_family")
    @classmethod
    def validate_font_family(cls, value: str) -> str:
        if value not in CERTIFICATE_FONTS:
            raise ValueError("font_family must be a supported certificate font id")
        return value

    @field_validator("accent_color")
    @classmethod
    def validate_color(cls, value: str) -> str:
        if len(value) != 7 or not value.startswith("#") or any(ch not in "0123456789abcdefABCDEF" for ch in value[1:]):
            raise ValueError("accent_color must be a six-digit hex color")
        return value.upper()


class CertificateResult(BaseModel):
    id: str
    recipient_name: str | None
    course_name: str | None
    email: str | None
    status: CertificateStatus
    error: str | None
    download_url: str | None


class JobResult(BaseModel):
    id: str
    event_name: str
    issued_on: str
    status: JobStatus
    total: int
    succeeded: int
    failed: int
    progress_percent: float
    created_at: str
    started_at: str | None
    finished_at: str | None
    certificates: list[CertificateResult]


