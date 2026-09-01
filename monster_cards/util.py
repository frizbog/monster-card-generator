from __future__ import annotations

import html
import math
import re
from pathlib import Path
from typing import Any, Iterable


def ability_mod(score: int) -> int:
    return math.floor((int(score) - 10) / 2)


def signed(n: int | str) -> str:
    try:
        i = int(n)
    except (TypeError, ValueError):
        return str(n)
    return f"{i:+d}"


def first(obj: dict[str, Any], *keys: str, default=None):
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return default


def strip_markup(text: Any) -> str:
    if text is None:
        return ""
    if isinstance(text, list):
        text = " ".join(str(x) for x in text)
    text = str(text)
    text = html.unescape(text)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"</p\s*>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    # Common lightweight markdown cleanup.
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\[(.*?)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def walk_json_files(root: Path) -> Iterable[Path]:
    yield from root.rglob("*.json")
