from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


STATIC_WEIGHT_FILES = {
    "regular": "NotoSans-Regular.ttf",
    "bold": "NotoSans-Bold.ttf",
    "black": "NotoSans-Black.ttf",
    "light": "NotoSans-Light.ttf",
}

VARIABLE_FILES = (
    "NotoSans-VariableFont_wdth,wght.ttf",
    "NotoSans[wdth,wght].ttf",
)

WEIGHT_VALUES = {
    "regular": 400,
    "bold": 700,
    "black": 900,
    "light": 300,
}

WEIGHT_STYLES = {
    300: "Light",
    400: "Regular",
    700: "Bold",
    900: "Black",
}

DERIVED_FAMILY = "Monster Card Noto Sans"
CACHE_FORMAT_VERSION = 2


def _candidate_dirs() -> list[Path]:
    dirs = []
    env = os.environ.get("NOTO_SANS_DIR")
    if env:
        dirs.append(Path(env).expanduser())
    dirs += [
        Path.home() / "Library" / "Fonts",        # macOS user
        Path("/Library/Fonts"),                    # macOS system
        Path("/System/Library/Fonts"),             # macOS system
        Path("/usr/share/fonts/truetype/noto"),   # Debian/Ubuntu
        Path("/usr/local/share/fonts"),
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts",
    ]
    return dirs


def _find_font(filename: str) -> Path | None:
    for directory in _candidate_dirs():
        path = directory / filename
        if path.is_file():
            return path
    return None


def _find_variable_font() -> Path | None:
    for filename in VARIABLE_FILES:
        if path := _find_font(filename):
            return path
    return None


def _font_cache_dir() -> Path:
    if configured := os.environ.get("NOTO_SANS_CACHE_DIR"):
        return Path(configured).expanduser()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "monster-card-generator" / "fonts"
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        return root / "monster-card-generator" / "fonts"
    root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "monster-card-generator" / "fonts"


def _name_instance(font, weight: int) -> None:
    """Give a derived weight an identity distinct from installed Noto Sans."""
    style = WEIGHT_STYLES[weight]
    names = font["name"]
    name_values = {
        1: DERIVED_FAMILY,
        2: style,
        3: f"{DERIVED_FAMILY}; {style}",
        4: f"{DERIVED_FAMILY} {style}",
        6: f"MonsterCardNotoSans-{style}",
        16: DERIVED_FAMILY,
        17: style,
    }
    for name_id, value in name_values.items():
        names.setName(value, name_id, 3, 1, 0x409)

    # Keep the style-linking flags consistent with the new style names.
    os2 = font["OS/2"]
    os2.fsSelection &= ~((1 << 5) | (1 << 6))
    os2.fsSelection |= 1 << (5 if style == "Bold" else 6)
    font["head"].macStyle &= ~1
    if style == "Bold":
        font["head"].macStyle |= 1


def _variable_instance(path: Path, weight: int) -> Path | BytesIO:
    """Return a cached static instance that ReportLab can embed."""
    try:
        from fontTools.ttLib import TTFont as VariableTTFont
        from fontTools.varLib.instancer import instantiateVariableFont
    except ImportError as exc:
        raise RuntimeError(
            "Noto Sans is installed as a variable font, but fonttools is required "
            "to select its weights. Install the packages in requirements.txt."
        ) from exc

    stat = path.stat()
    cache_path = _font_cache_dir() / (
        f"MonsterCardNotoSans-v{CACHE_FORMAT_VERSION}-{stat.st_size}-"
        f"{stat.st_mtime_ns}-{WEIGHT_STYLES[weight]}.ttf"
    )
    if cache_path.is_file() and cache_path.stat().st_size:
        return cache_path

    font = VariableTTFont(path)
    try:
        axes = {axis.axisTag: axis.defaultValue for axis in font["fvar"].axes}
        if "wght" not in axes:
            raise RuntimeError(f"Noto Sans variable font has no wght axis: {path}")
        axes["wght"] = weight
        # IUP optimization makes no visual difference here and is unusually
        # expensive for Noto Sans; ReportLab will subset the result anyway.
        instantiateVariableFont(font, axes, inplace=True, optimize=False)
        _name_instance(font, weight)

        instance = BytesIO()
        font.save(instance)
        instance.seek(0)
        temporary_path = cache_path.with_name(f".{cache_path.name}.{os.getpid()}.tmp")
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path.write_bytes(instance.getbuffer())
            os.replace(temporary_path, cache_path)
            return cache_path
        except OSError:
            # A read-only home/cache directory should not prevent rendering.
            temporary_path.unlink(missing_ok=True)
            return instance
    finally:
        font.close()


def register_noto() -> dict[str, str]:
    found = {
        weight: path
        for weight, filename in STATIC_WEIGHT_FILES.items()
        if (path := _find_font(filename)) is not None
    }
    missing = [weight for weight in WEIGHT_VALUES if weight not in found]
    variable_font = _find_variable_font() if missing else None
    if missing:
        if variable_font is None:
            searched = "\n  ".join(str(x) for x in _candidate_dirs())
            raise RuntimeError(
                "Noto Sans is required but neither its variable font nor these "
                "static weights were found: "
                + ", ".join(missing)
                + "\nInstall Noto Sans Variable, or set NOTO_SANS_DIR."
                + "\nSearched:\n  " + searched
            )
    names = {}
    for weight in WEIGHT_VALUES:
        name = f"Noto-{weight}"
        if name not in pdfmetrics.getRegisteredFontNames():
            source: str | Path | BytesIO = (
                str(found[weight])
                if weight in found
                else _variable_instance(variable_font, WEIGHT_VALUES[weight])
            )
            pdfmetrics.registerFont(TTFont(name, str(source) if isinstance(source, Path) else source))
        names[weight] = name
    return names
