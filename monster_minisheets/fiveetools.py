from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
import ssl
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from .util import slugify


DEFAULT_BASE_URL = "https://5e.tools/data/bestiary/"
DEFAULT_MIRROR_BASE_URL = (
    "https://raw.githubusercontent.com/5etools-mirror-3/"
    "5etools-2014-src/main/data/bestiary/"
)


class FiveEToolsError(RuntimeError):
    pass


def _http_json(url: str) -> Any:
    request = Request(url, headers={"User-Agent": "monster-minisheet-generator/1.0"})
    context = ssl.create_default_context()
    verify_paths = ssl.get_default_verify_paths()
    if not verify_paths.cafile:
        for candidate in (Path("/etc/ssl/cert.pem"), Path("/etc/ssl/certs/ca-certificates.crt")):
            if candidate.is_file():
                context.load_verify_locations(cafile=str(candidate))
                break
    with urlopen(request, timeout=30, context=context) as response:
        return json.loads(response.read().decode("utf-8"))


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _replace_text(value: Any, pattern: str, replacement: str, flags: str = "") -> Any:
    regex_flags = re.I if "i" in flags.casefold() else 0
    if isinstance(value, str):
        return re.sub(pattern, lambda _: replacement, value, flags=regex_flags)
    if isinstance(value, list):
        return [_replace_text(item, pattern, replacement, flags) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_text(item, pattern, replacement, flags)
            for key, item in value.items()
        }
    return value


def _entry_name_matches(entry: Any, expected: str) -> bool:
    return isinstance(entry, dict) and str(entry.get("name", "")).casefold() == expected.casefold()


def _apply_array_mod(target: dict[str, Any], prop: str, mod: dict[str, Any]) -> None:
    mode = mod.get("mode")
    current = _as_list(target.get(prop))
    items = _as_list(mod.get("items"))
    if mode == "appendArr":
        target[prop] = current + deepcopy(items)
        return
    if mode == "insertArr":
        index = int(mod.get("index", len(current)))
        target[prop] = current[:index] + deepcopy(items) + current[index:]
        return
    if mode == "replaceArr":
        expected = str(mod.get("replace", ""))
        index = next((i for i, entry in enumerate(current) if _entry_name_matches(entry, expected)), None)
        if index is None:
            raise FiveEToolsError(f"Cannot replace missing {prop} entry {expected!r}.")
        target[prop] = current[:index] + deepcopy(items) + current[index + 1:]
        return
    if mode == "removeArr":
        names = _as_list(mod.get("names", mod.get("items")))
        folded = {str(name).casefold() for name in names}
        target[prop] = [
            entry for entry in current
            if not (isinstance(entry, str) and entry.casefold() in folded)
            and not (isinstance(entry, dict) and str(entry.get("name", "")).casefold() in folded)
        ]
        return
    raise FiveEToolsError(f"Unsupported 5etools copy mode {mode!r} for {prop!r}.")


def _apply_copy_mods(target: dict[str, Any], mods: dict[str, Any]) -> None:
    for prop, raw_mods in mods.items():
        for mod in _as_list(raw_mods):
            if mod == "remove":
                target.pop(prop, None)
                continue
            if not isinstance(mod, dict):
                raise FiveEToolsError(f"Unsupported 5etools copy modification: {mod!r}.")
            mode = mod.get("mode")
            if mode == "replaceTxt":
                keys = list(target) if prop == "*" else [prop]
                for key in keys:
                    if key in {"name", "source", "page", "_copy"} or key not in target:
                        continue
                    target[key] = _replace_text(
                        target[key], str(mod.get("replace", "")),
                        str(mod.get("with", "")), str(mod.get("flags", "")),
                    )
                continue
            if mode == "setProp" and prop == "_":
                nested_prop = str(mod.get("prop", ""))
                if mod.get("value") is None:
                    target.pop(nested_prop, None)
                else:
                    target[nested_prop] = deepcopy(mod.get("value"))
                continue
            if mode in {"appendArr", "insertArr", "replaceArr", "removeArr"}:
                _apply_array_mod(target, prop, mod)
                continue
            raise FiveEToolsError(f"Unsupported 5etools copy mode {mode!r} for {prop!r}.")


def _render_tag(match: re.Match[str]) -> str:
    body = match.group(1)
    tag, _, value = body.partition(" ")
    parts = value.split("|")
    visible = parts[2] if len(parts) > 2 and parts[2] else (parts[0] if parts else "")
    tag = tag.casefold()
    if tag == "atk":
        return {
            "mw": "Melee Weapon Attack:", "rw": "Ranged Weapon Attack:",
            "ms": "Melee Spell Attack:", "rs": "Ranged Spell Attack:",
            "m": "Melee Attack:", "r": "Ranged Attack:",
        }.get(visible.casefold(), "Attack:")
    if tag == "hit":
        return visible if visible.startswith(("+", "-")) else f"+{visible}"
    if tag == "h":
        return "Hit: "
    if tag == "dc":
        return f"DC {visible}"
    if tag in {"dice", "damage", "d20"}:
        return visible
    if tag == "recharge":
        return f"Recharge {visible or '6'}"
    return visible


def _clean_5etools_markup(value: str) -> str:
    previous = value
    while "{@" in previous:
        current = re.sub(r"\{@([^{}]+)\}", _render_tag, previous)
        if current == previous:
            break
        previous = current
    return re.sub(r"\s+", " ", previous).strip()


def _render_entries(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return _clean_5etools_markup(value)
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return " ".join(text for item in value if (text := _render_entries(item)))
    if not isinstance(value, dict):
        return str(value)

    body_parts: list[str] = []
    for key in ("entry", "entries", "items"):
        if key in value:
            text = _render_entries(value[key])
            if text:
                body_parts.append(text)
    if "rows" in value:
        for row in value["rows"]:
            text = _render_entries(row)
            if text:
                body_parts.append(text)
    body = " ".join(body_parts)
    name = _clean_5etools_markup(str(value.get("name", "")))
    return f"{name}. {body}".strip() if name and body else (name or body)


SIZE_NAMES = {
    "T": "Tiny", "S": "Small", "M": "Medium", "L": "Large",
    "H": "Huge", "G": "Gargantuan", "V": "Varies",
}
ALIGNMENT_NAMES = {
    "L": "Lawful", "N": "Neutral", "C": "Chaotic", "G": "Good",
    "E": "Evil", "U": "Unaligned", "A": "Any Alignment",
    "NX": "Neutral", "NY": "Neutral",
}


def _type_name(value: Any) -> str:
    if isinstance(value, dict):
        base = str(value.get("type", ""))
        tags = [str(tag.get("tag", "")) if isinstance(tag, dict) else str(tag) for tag in value.get("tags", [])]
        return f"{base} ({', '.join(tags)})" if tags else base
    return str(value or "")


def _alignment_name(value: Any) -> str:
    if isinstance(value, list):
        if len(value) == 1:
            return _alignment_name(value[0])
        return " ".join(_alignment_name(item) for item in value)
    if isinstance(value, dict):
        if value.get("special"):
            return str(value["special"])
        return _alignment_name(value.get("alignment", []))
    return ALIGNMENT_NAMES.get(str(value), str(value or ""))


def _speed_value(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    number = value.get("number")
    condition = _clean_5etools_markup(str(value.get("condition", "")))
    return f"{number} ft. {condition}".strip() if number is not None else condition


def _adapt_speed(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    if value and not any(speed for speed in value.values()):
        return "0 ft."
    return {
        mode: _speed_value(speed)
        for mode, speed in value.items()
        if mode not in {"canHover", "alternate"}
    }


def _defense_parts(value: Any, property_name: str) -> list[str]:
    parts: list[str] = []
    for item in _as_list(value):
        if isinstance(item, str):
            parts.append(_clean_5etools_markup(item))
            continue
        if not isinstance(item, dict):
            parts.append(str(item))
            continue
        nested = item.get(property_name, item.get("special", []))
        text = ", ".join(_defense_parts(nested, property_name))
        note = _clean_5etools_markup(str(item.get("note", "")))
        if text or note:
            parts.append(" ".join(part for part in (text, note) if part))
    return parts


def _named_entries(items: Any) -> list[dict[str, str]]:
    result = []
    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
        name = _clean_5etools_markup(str(item.get("name", "")))
        text = _render_entries(item.get("entries", item.get("entry", "")))
        if name and text:
            result.append({"name": name, "text": text})
    return result


def _spellcasting_entries(items: Any) -> list[dict[str, str]]:
    def render_spell_list(value: Any) -> str:
        return ", ".join(_render_entries(spell) for spell in _as_list(value))

    result = []
    for item in _as_list(items):
        if not isinstance(item, dict):
            continue
        parts = [_render_entries(item.get("headerEntries", []))]
        for level, spell_data in (item.get("spells") or {}).items():
            if not isinstance(spell_data, dict):
                continue
            slots = f" ({spell_data['slots']} slots)" if spell_data.get("slots") is not None else ""
            parts.append(f"Level {level}{slots}: {render_spell_list(spell_data.get('spells', []))}")
        if item.get("will"):
            parts.append(f"At will: {render_spell_list(item['will'])}")
        for uses, spells in (item.get("daily") or {}).items():
            parts.append(f"{uses} per day: {render_spell_list(spells)}")
        parts.append(_render_entries(item.get("footerEntries", [])))
        text = " ".join(part for part in parts if part)
        if text:
            result.append({"name": str(item.get("name", "Spellcasting")), "text": text})
    return result


def adapt_5etools_monster(monster: dict[str, Any]) -> dict[str, Any]:
    """Convert a fully dereferenced 5etools creature into the normalizer's schema."""
    hp = monster.get("hp")
    cr = monster.get("cr")
    ac = monster.get("ac")
    speed = _adapt_speed(monster.get("speed"))
    ac_value = (
        ac[0].get("ac", ac[0].get("special"))
        if isinstance(ac, list) and ac and isinstance(ac[0], dict)
        else ac[0] if isinstance(ac, list) and ac else ac
    )
    result: dict[str, Any] = {
        "name": monster.get("name"),
        "size": " or ".join(SIZE_NAMES.get(str(size), str(size)) for size in _as_list(monster.get("size"))),
        "type": _type_name(monster.get("type")),
        "alignment": _alignment_name(monster.get("alignment")),
        "armor_class": ac_value,
        "hit_points": hp.get("average", hp.get("special")) if isinstance(hp, dict) else hp,
        "speed": speed,
        "challenge_rating": cr.get("cr") if isinstance(cr, dict) else cr,
        "passive_perception": monster.get("passive"),
        "saving_throws": monster.get("save", {}),
        "skills": monster.get("skill", {}),
        "senses": monster.get("senses", []),
        "languages": monster.get("languages", []),
        "damage_vulnerabilities": _defense_parts(monster.get("vulnerable", []), "vulnerable"),
        "damage_resistances": _defense_parts(monster.get("resist", []), "resist"),
        "damage_immunities": _defense_parts(monster.get("immune", []), "immune"),
        "condition_immunities": _defense_parts(monster.get("conditionImmune", []), "conditionImmune"),
        "_source_note": f"Generated from 5etools bestiary data ({monster.get('source', 'unknown source')}).",
    }
    for short, long_name in (
        ("str", "strength"), ("dex", "dexterity"), ("con", "constitution"),
        ("int", "intelligence"), ("wis", "wisdom"), ("cha", "charisma"),
    ):
        result[long_name] = monster.get(short)

    traits = _spellcasting_entries(monster.get("spellcasting")) + _named_entries(monster.get("trait"))
    if traits:
        result["special_abilities"] = traits
    for source_key, target_key in (
        ("action", "actions"), ("bonus", "bonus_actions"),
        ("reaction", "reactions"), ("legendary", "legendary_actions"),
    ):
        entries = _named_entries(monster.get(source_key))
        if entries:
            result[target_key] = entries
    if not any(result.get(key) for key in (
        "special_abilities", "actions", "bonus_actions", "reactions", "legendary_actions",
    )):
        result["_allow_no_blocks"] = True
    return result


class FiveEToolsBestiary:
    """Lazy, cached reader for the public 5etools bestiary JSON files."""

    def __init__(
        self,
        *,
        sources: list[str] | None = None,
        base_url: str = DEFAULT_BASE_URL,
        mirror_base_url: str | None = DEFAULT_MIRROR_BASE_URL,
        cache_dir: str | Path | None = None,
        fetch_json: Callable[[str], Any] | None = None,
    ):
        self.sources = list(dict.fromkeys(sources)) if sources else None
        self.base_url = base_url.rstrip("/") + "/"
        self.mirror_base_url = mirror_base_url.rstrip("/") + "/" if mirror_base_url else None
        self.cache_dir = Path(cache_dir).expanduser().resolve() if cache_dir else None
        self.fetch_json = fetch_json or _http_json
        self._source_files: dict[str, tuple[str, str]] | None = None
        self._loaded_sources: set[str] = set()
        self._records: dict[tuple[str, str], dict[str, Any]] = {}
        self._names: dict[str, list[tuple[str, str]]] = {}

    def describe(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "sources": self.sources or "all (lazy search)",
            "cache_dir": str(self.cache_dir) if self.cache_dir else None,
        }

    def _get_json(self, filename: str) -> Any:
        cache_path = self.cache_dir / filename if self.cache_dir else None
        if cache_path and cache_path.is_file():
            try:
                return json.loads(cache_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                pass

        urls = [urljoin(self.base_url, filename)]
        if self.mirror_base_url:
            urls.append(urljoin(self.mirror_base_url, filename))
        errors = []
        for url in urls:
            try:
                payload = self.fetch_json(url)
                if cache_path:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
                    temporary.write_text(json.dumps(payload), encoding="utf-8")
                    temporary.replace(cache_path)
                return payload
            except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
                errors.append(f"{url}: {exc}")
        raise FiveEToolsError(
            f"Unable to fetch 5etools bestiary data file {filename!r}. " + " | ".join(errors)
        )

    def _sources_index(self) -> dict[str, tuple[str, str]]:
        if self._source_files is None:
            payload = self._get_json("index.json")
            if not isinstance(payload, dict):
                raise FiveEToolsError("The 5etools bestiary index is not a JSON object.")
            self._source_files = {
                str(source).casefold(): (str(source), str(filename))
                for source, filename in payload.items()
            }
        return self._source_files

    def _load_source(self, source: str) -> None:
        source_key = source.casefold()
        if source_key in self._loaded_sources:
            return
        source_info = self._sources_index().get(source_key)
        if not source_info:
            raise FiveEToolsError(f"Unknown 5etools bestiary source: {source!r}.")
        canonical_source, filename = source_info
        payload = self._get_json(filename)
        monsters = payload.get("monster") if isinstance(payload, dict) else None
        if not isinstance(monsters, list):
            raise FiveEToolsError(f"5etools data file {filename!r} has no monster list.")
        for monster in monsters:
            if not isinstance(monster, dict) or not monster.get("name"):
                continue
            actual_source = str(monster.get("source", canonical_source))
            key = (slugify(str(monster["name"])), actual_source.casefold())
            self._records[key] = monster
            self._names.setdefault(key[0], []).append(key)
        self._loaded_sources.add(source_key)

    def _find_raw(self, name: str) -> dict[str, Any]:
        name_key = slugify(name)
        preferred = self.sources or []
        for source in preferred:
            self._load_source(source)
        matches = self._names.get(name_key, [])
        if not matches and self.sources is None:
            for canonical_source, _ in self._sources_index().values():
                self._load_source(canonical_source)
                matches = self._names.get(name_key, [])
                if matches:
                    break
        if not matches:
            scope = ", ".join(preferred) if preferred else "the 5etools bestiary"
            raise FiveEToolsError(f"Monster not found in {scope}: {name}.")
        if preferred:
            rank = {source.casefold(): index for index, source in enumerate(preferred)}
            matches = sorted(matches, key=lambda key: rank.get(key[1], len(rank)))
        return self._records[matches[0]]

    def _resolve_copy(self, monster: dict[str, Any], stack: tuple[tuple[str, str], ...] = ()) -> dict[str, Any]:
        copy_meta = monster.get("_copy")
        if not isinstance(copy_meta, dict):
            return deepcopy(monster)
        parent_name = str(copy_meta.get("name", ""))
        parent_source = str(copy_meta.get("source", monster.get("source", "")))
        key = (slugify(parent_name), parent_source.casefold())
        if key in stack:
            raise FiveEToolsError(f"Circular 5etools _copy reference involving {parent_name!r}.")
        self._load_source(parent_source)
        parent = self._records.get(key)
        if parent is None:
            raise FiveEToolsError(
                f"Cannot resolve 5etools parent {parent_name!r} from source {parent_source!r}."
            )
        resolved = self._resolve_copy(parent, stack + (key,))
        child = deepcopy(monster)
        child_copy = child.pop("_copy")
        for prop, value in resolved.items():
            if prop not in child:
                child[prop] = deepcopy(value)
        mods = child_copy.get("_mod")
        if isinstance(mods, dict):
            _apply_copy_mods(child, mods)
        return child

    def monster(self, name: str) -> dict[str, Any]:
        return adapt_5etools_monster(self._resolve_copy(self._find_raw(name)))
