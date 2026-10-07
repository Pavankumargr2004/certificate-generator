from io import BytesIO
from pathlib import Path
from threading import Lock

from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .font_catalog import get_font_paths


BUILTIN_DESIGNS = [
    {"id": "classic", "name": "Heritage", "description": "A timeless double-border award", "accent": "#B28B3D"},
    {"id": "modern", "name": "Modern", "description": "Bold blocks and contemporary type", "accent": "#137B70"},
    {"id": "minimal", "name": "Minimal", "description": "Quiet, refined and spacious", "accent": "#354C61"},
]
_FONT_LOCK = Lock()
_BUILTIN_FONTS = {
    "sans": ("Helvetica", "Helvetica-Bold"),
    "serif": ("Times-Roman", "Times-Bold"),
    "mono": ("Courier", "Courier-Bold"),
}


def _font_faces(font_family: str) -> tuple[str, str]:
    builtin = _BUILTIN_FONTS.get(font_family)
    if builtin:
        return builtin
    paths = get_font_paths(font_family)
    if not paths:
        return _BUILTIN_FONTS["serif"]
    regular_path, bold_path = paths
    regular_name = f"Certflow-{font_family}-Regular"
    bold_name = f"Certflow-{font_family}-Bold"
    with _FONT_LOCK:
        registered = set(pdfmetrics.getRegisteredFontNames())
        if regular_name not in registered:
            pdfmetrics.registerFont(TTFont(regular_name, regular_path))
        if bold_name not in registered:
            pdfmetrics.registerFont(TTFont(bold_name, bold_path))
        family_name = f"Certflow-{font_family}"
        pdfmetrics.registerFontFamily(family_name, normal=regular_name, bold=bold_name,
                                      italic=regular_name, boldItalic=bold_name)
    return regular_name, bold_name


def _fit_size(pdf: canvas.Canvas, text: str, font: str, size: int, max_width: float) -> int:
    while size > 12 and pdf.stringWidth(text, font, size) > max_width:
        size -= 1
    return size


def create_certificate(*, recipient_name: str, course_name: str, event_name: str,
                       issued_on: str, destination: Path | None = None,
                       design: str = "classic", template_path: Path | None = None,
                       title_text: str = "CERTIFICATE OF COMPLETION",
                       accent_color: str = "#B28B3D", signatory: str = "",
                       font_family: str = "serif") -> bytes | None:
    """Render a certificate PDF, optionally using an uploaded image background."""
    page = landscape(letter)
    output = BytesIO() if destination is None else str(destination)
    if destination:
        destination.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(output, pagesize=page)
    width, height = page
    accent = colors.HexColor(accent_color)

    if template_path:
        pdf.drawImage(str(template_path), 0, 0, width=width, height=height,
                      preserveAspectRatio=True, anchor="c", mask="auto")
        pdf.setFillColor(colors.HexColor("#26364A"))
    elif design == "modern":
        pdf.setFillColor(colors.HexColor("#F7FAF9"))
        pdf.rect(0, 0, width, height, fill=1, stroke=0)
        pdf.setFillColor(accent)
        pdf.rect(0, height - 32, width, 32, fill=1, stroke=0)
        pdf.rect(0, 0, 14, height - 32, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#17353B"))
    elif design == "minimal":
        pdf.setStrokeColor(accent)
        pdf.setLineWidth(1.5)
        pdf.line(82, 83, width - 82, 83)
        pdf.circle(width / 2, height - 74, 5, fill=1, stroke=0)
        pdf.setFillColor(colors.HexColor("#293943"))
    else:
        pdf.setStrokeColor(accent)
        pdf.setLineWidth(3)
        pdf.rect(28, 28, width - 56, height - 56)
        pdf.setStrokeColor(colors.Color(accent.red, accent.green, accent.blue, alpha=.48))
        pdf.setLineWidth(1)
        pdf.rect(38, 38, width - 76, height - 76)
        pdf.setFillColor(colors.HexColor("#26364A"))

    regular_font, bold_font = _font_faces(font_family)
    title_font = bold_font
    title_size = _fit_size(pdf, title_text, title_font, 28, width - 130)
    pdf.setFont(title_font, title_size)
    pdf.drawCentredString(width / 2, height - 145, title_text)

    pdf.setFillColor(colors.HexColor("#59666A"))
    pdf.setFont(regular_font, 14)
    pdf.drawCentredString(width / 2, height - 205, "This certificate is proudly presented to")

    name_font = bold_font
    name_size = _fit_size(pdf, recipient_name, name_font, 28, width - 150)
    pdf.setFillColor(colors.HexColor("#203844"))
    pdf.setFont(name_font, name_size)
    pdf.drawCentredString(width / 2, height - 252, recipient_name)
    pdf.setStrokeColor(accent)
    pdf.setLineWidth(1.5 if design != "classic" else 1)
    pdf.line(width * .25, height - 265, width * .75, height - 265)

    pdf.setFillColor(colors.HexColor("#59666A"))
    pdf.setFont(regular_font, 14)
    course_line = f"for successfully completing {course_name}"
    event_line = f"as part of {event_name}"
    pdf.drawCentredString(width / 2, height - 305, course_line)
    pdf.drawCentredString(width / 2, height - 335, event_line)
    if signatory:
        pdf.setFillColor(colors.HexColor("#344951"))
        pdf.setFont(bold_font, 11)
        pdf.drawCentredString(width / 2, 108, signatory)
        pdf.setStrokeColor(colors.HexColor("#9BA9A5"))
        pdf.line(width / 2 - 85, 125, width / 2 + 85, 125)
    pdf.setFillColor(colors.HexColor("#59666A"))
    pdf.setFont(regular_font, 11)
    pdf.drawCentredString(width / 2, 78 if signatory else 85, f"Issued {issued_on}")
    pdf.save()
    return output.getvalue() if isinstance(output, BytesIO) else None
