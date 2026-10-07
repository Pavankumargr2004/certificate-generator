"""Bundled PDF font catalog shared by the API, validation, and renderer."""
import json
from pathlib import Path

from .config import BASE_DIR

FONT_DIR = BASE_DIR / "app" / "fonts"
FONT_CATALOG = json.loads((FONT_DIR / "catalog.json").read_text(encoding="utf-8"))
FONT_BY_ID = {font["id"]: font for font in FONT_CATALOG}
FONT_IDS = set(FONT_BY_ID)


def get_font_paths(font_id: str) -> tuple[str, str] | None:
    font = FONT_BY_ID.get(font_id)
    if not font or font.get("builtin"):
        return None
    return str(FONT_DIR / font["regular"]), str(FONT_DIR / font["bold"])
