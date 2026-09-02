from __future__ import annotations

import re
from typing import Any

from .model import ABILITIES, Ability, MonsterCard, RuleBlock
from .quickfacts import choose_quick_facts
from .util import ability_mod, first, signed, strip_markup

ABILITY_KEYS = {
    "STR": ("strength", "str"),
    "DEX": ("dexterity", "dex"),
    "CON": ("constitution", "con"),
    "INT": ("intelligence", "int"),
    "WIS": ("wisdom", "wis"),
    "CHA": ("charisma", "cha"),
}


class NormalizationError(RuntimeError):
    pass


def _adapt_extracted_srd(monster: dict[str, Any]) -> dict[str, Any]:
    """Map the flattened/extracted SRD 5.2.1 resource shape to canonical keys."""
    result = dict(monster)

    type_line = strip_markup(monster.get("type_line"))
    if type_line and not any(key in result for key in ("size", "type", "creature_type")):
        # Preserve the source's exact type line; _subtitle knows to use it.
        result["_type_line"] = type_line

    challenge = monster.get("challenge")
    if challenge is not None and not any(key in result for key in ("challenge_rating", "cr")):
        result["challenge_rating"] = re.split(r"\s*\(", strip_markup(challenge), maxsplit=1)[0]

    # The extractor represents ability scores as repeating ABILITY, SCORE, MOD,
    # SAVE columns. Scan the rows rather than relying on generated column names.
    if not any(key in result for keys in ABILITY_KEYS.values() for key in keys):
        for table in monster.get("tables", []):
            if not isinstance(table, dict):
                continue
            headers = [str(header).upper() for header in table.get("headers", [])]
            rows = table.get("rows", [])
            if isinstance(rows, list) and rows and isinstance(rows[0], list):
                for index, abbr in enumerate(headers):
                    if abbr in ABILITY_KEYS and index < len(rows[0]):
                        score_match = re.match(r"\s*(\d+)", str(rows[0][index]))
                        if score_match:
                            result[ABILITY_KEYS[abbr][0]] = int(score_match.group(1))
            for row in table.get("rows", []):
                if not isinstance(row, list):
                    continue
                for index, cell in enumerate(row[:-1]):
                    abbr = str(cell).upper()
                    if abbr in ABILITY_KEYS:
                        score = str(row[index + 1]).strip()
                        if re.fullmatch(r"\d+", score):
                            result[ABILITY_KEYS[abbr][0]] = int(score)

    content = strip_markup(monster.get("content") or monster.get("text"))
    if content:
        simple_patterns = {
            "initiative": r"\bInitiative\s+([+\-\N{MINUS SIGN}]?\d+)",
            "passive_perception": r"\bPassive Perception\s+(\d+)",
        }
        for key, pattern in simple_patterns.items():
            if key not in result:
                match = re.search(pattern, content, flags=re.I)
                if match:
                    result[key] = match.group(1).replace("\N{MINUS SIGN}", "-")

        # These stat-line fields end at the next known label. Keeping them as
        # source text lets the existing quick-fact heuristic choose among them.
        labels = (
            "Saving Throws", "Saves", "Skills", "Damage Vulnerabilities",
            "Damage Resistances", "Damage Immunities", "Condition Immunities",
            "Gear", "Senses", "Languages", "CR", "Traits", "Actions",
            "Challenge", "Bonus Actions", "Reactions", "Legendary Actions",
        )
        label_pattern = "|".join(re.escape(label) for label in labels)
        field_keys = {
            "Senses": "senses",
            "Languages": "languages",
            "Damage Vulnerabilities": "damage_vulnerabilities",
            "Damage Resistances": "damage_resistances",
            "Damage Immunities": "damage_immunities",
            "Condition Immunities": "condition_immunities",
        }
        for label, key in field_keys.items():
            if key in result:
                continue
            match = re.search(
                rf"\b{re.escape(label)}\s+(.+?)(?=\s+(?:{label_pattern})\b|$)",
                content,
                flags=re.I,
            )
            if match:
                result[key] = match.group(1).strip(" ;,")

        for label, key in (("Skills", "skills"), ("Saving Throws", "saving_throws"), ("Saves", "saving_throws")):
            if key in result:
                continue
            match = re.search(
                rf"\b{label}\s+(.+?)(?=\s+(?:{label_pattern})\b|$)",
                content,
                flags=re.I,
            )
            if match:
                pairs = re.findall(r"([A-Za-z][A-Za-z ]*?)\s+([+\-\N{MINUS SIGN}]\d+)(?:,|;|$|\s+(?=[A-Z]))", match.group(1))
                if pairs:
                    result[key] = {name.strip(): value.replace("\N{MINUS SIGN}", "-") for name, value in pairs}

    return result


def _ability(monster: dict[str, Any], abbr: str) -> Ability:
    value = first(monster, *ABILITY_KEYS[abbr], default=10)
    if isinstance(value, dict):
        score = int(first(value, "score", "value", default=10))
        mod = first(value, "modifier", "mod", "bonus", default=None)
        return Ability(score, int(mod) if mod is not None else ability_mod(score))
    score = int(value)
    return Ability(score, ability_mod(score))


def _ac(monster: dict[str, Any]) -> str:
    ac = first(monster, "armor_class", "ac", default="?")
    if isinstance(ac, list) and ac:
        ac = ac[0]
    if isinstance(ac, dict):
        ac = first(ac, "value", "ac", default="?")
    return str(ac)


def _speeds(monster: dict[str, Any]) -> tuple[str, list[str]]:
    speed = first(monster, "speed", "speeds", default="?")
    if isinstance(speed, dict):
        modes = [(str(mode), value) for mode, value in speed.items() if value]
        if not modes:
            return "?", []
        primary_index = next(
            (index for index, (mode, _) in enumerate(modes) if mode.casefold() in {"walk", "walking"}),
            0,
        )
        primary_mode, primary_value = modes.pop(primary_index)
        extras = [f"{mode.title()} {_distance(value)}" for mode, value in modes]
        return _distance(primary_value), extras

    parts = [part.strip() for part in re.split(r"\s*[,;]\s*", strip_markup(speed)) if part.strip()]
    if not parts:
        return "?", []
    return _distance(parts[0]), [_distance(part) for part in parts[1:]]


def _distance(value: Any) -> str:
    text = strip_markup(value)
    if not text:
        return "?"
    if text.isdigit():
        return f"{text}'"
    text = re.sub(r"\s*(?:feet\b|foot\b|ft\.?)", "'", text, flags=re.I)
    return text


def _passive_perception(monster: dict[str, Any]) -> str:
    pp = first(monster, "passive_perception", "passivePerception", default=None)
    if pp is not None:
        return str(pp)
    senses = strip_markup(first(monster, "senses", default=""))
    m = re.search(r"passive perception\s*(\d+)", senses, flags=re.I)
    if m:
        return m.group(1)
    # Default to 10 + WIS modifier; does not include proficiency, so overrides
    # or source data are preferable when available.
    return str(10 + _ability(monster, "WIS").modifier)


def _subtitle(monster: dict[str, Any]) -> str:
    if monster.get("_type_line"):
        return strip_markup(monster["_type_line"])
    size = strip_markup(first(monster, "size", default=""))
    typ = first(monster, "type", "creature_type", default="")
    if isinstance(typ, dict):
        typ = first(typ, "type", "name", default="")
    typ = strip_markup(typ)
    alignment = strip_markup(first(monster, "alignment", default=""))
    base = " ".join(x for x in [size, typ.title() if typ else ""] if x).strip()
    return f"{base}, {alignment.title()}" if alignment else base


def _iter_named_blocks(value: Any):
    if isinstance(value, dict):
        for name, desc in value.items():
            if isinstance(desc, dict):
                desc = first(desc, "desc", "description", "text", default="")
            yield str(name), strip_markup(desc)
    elif isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            name = first(item, "name", "title", default="")
            desc = first(item, "desc", "description", "text", default="")
            if name:
                yield str(name), strip_markup(desc)


def _looks_like_action_title(value: str) -> bool:
    """Identify the short title sentence that starts an extracted SRD action."""
    value = value.strip()
    if not value or len(value) > 80 or ":" in value:
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", value)
    if not words:
        return False
    allowed_lowercase = {"a", "an", "and", "at", "for", "from", "in", "of", "on", "or", "the", "to", "with"}
    return all(word.casefold() in allowed_lowercase or word[0].isupper() for word in words)


def _split_grouped_entries(text: str, allow_preamble: bool = False) -> tuple[str, list[tuple[str, str]]]:
    """Recover named entries from an extractor-flattened rules section."""
    starts: list[tuple[int, int, str]] = []
    for match in re.finditer(r"(?:^|(?<=\. ))([^.!?]{1,80})\.\s+", text):
        title = match.group(1).strip()
        if _looks_like_action_title(title):
            starts.append((match.start(1), match.end(), title))
    if not starts or (starts[0][0] != 0 and not allow_preamble):
        return "", []

    preamble = text[:starts[0][0]].strip() if starts[0][0] else ""
    entries: list[tuple[str, str]] = []
    for index, (_, body_start, title) in enumerate(starts):
        body_end = starts[index + 1][0] if index + 1 < len(starts) else len(text)
        body = text[body_start:body_end].strip()
        if body:
            entries.append((title, body))
    return preamble, entries


def _append_grouped_blocks(
    result: list[RuleBlock],
    value: Any,
    group_name: str,
    title_prefix: str = "",
    allow_preamble: bool = False,
) -> None:
    for name, desc in _iter_named_blocks(value):
        if name.casefold() != group_name.casefold():
            result.append(RuleBlock(f"{title_prefix}{name}:", desc, "full"))
            continue
        preamble, entries = _split_grouped_entries(desc, allow_preamble=allow_preamble)
        if preamble:
            result.append(RuleBlock(f"{group_name}:", preamble, "full"))
        if entries:
            result.extend(RuleBlock(f"{title_prefix}{title}:", text, "full") for title, text in entries)
        elif not preamble:
            # Keep unfamiliar source text intact rather than risk a bad split.
            fallback_title = "" if group_name.casefold() == "actions" else f"{group_name}:"
            result.append(RuleBlock(fallback_title, desc, "full"))


def _blocks(monster: dict[str, Any]) -> list[RuleBlock]:
    result: list[RuleBlock] = []
    traits = first(monster, "special_abilities", "traits", "features", default=[])
    actions = first(monster, "actions", default=[])
    bonus = first(monster, "bonus_actions", "bonusActions", default=[])
    reactions = first(monster, "reactions", default=[])

    # Traits before actions only when they are operationally relevant. This generic
    # importer cannot judge perfectly, so it preserves source order within groups.
    _append_grouped_blocks(result, traits, "Traits")
    _append_grouped_blocks(result, actions, "Actions")
    _append_grouped_blocks(result, bonus, "Bonus Actions", "Bonus Action - ")
    _append_grouped_blocks(result, reactions, "Reactions", "Reaction - ")
    legendary = first(monster, "legendary_actions", "legendaryActions", default=[])
    _append_grouped_blocks(result, legendary, "Legendary Actions", allow_preamble=True)
    return result


def monster_to_card(monster: dict[str, Any]) -> MonsterCard:
    monster = _adapt_extracted_srd(monster)
    speed, additional_speeds = _speeds(monster)
    if additional_speeds:
        monster["_additional_speeds"] = additional_speeds
    abilities = {abbr: _ability(monster, abbr) for abbr in ABILITIES}
    hp = first(monster, "hit_points", "hp", default="?")
    cr = first(monster, "challenge_rating", "cr", default="?")
    card = MonsterCard(
        name=strip_markup(first(monster, "name", default="Unnamed Monster")),
        subtitle=_subtitle(monster),
        cr=str(cr),
        ac=_ac(monster),
        hp=str(hp),
        speed=speed,
        passive_perception=_passive_perception(monster),
        abilities=abilities,
        quick_facts=choose_quick_facts(monster),
        blocks=_blocks(monster),
        source_note=(
            "Generated from custom monster JSON."
            if monster.get("_custom_monster")
            else "Generated from local D&D SRD JSON. SRD 5.2.1 content is CC BY 4.0, Wizards of the Coast LLC."
        ),
    )
    missing = [
        label for label, value in (
            ("subtitle", card.subtitle), ("CR", card.cr), ("AC", card.ac),
            ("HP", card.hp), ("speed", card.speed),
        ) if not value or value == "?"
    ]
    missing_abilities = [abbr for abbr in ABILITIES if not any(key in monster for key in ABILITY_KEYS[abbr])]
    if missing or missing_abilities or not card.blocks:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if missing_abilities:
            details.append("missing ability scores: " + ", ".join(missing_abilities))
        if not card.blocks:
            details.append("no traits or actions found")
        raise NormalizationError(
            f"SRD data for {card.name!r} is incomplete ({'; '.join(details)}). "
            "The SRD JSON schema may not be supported."
        )
    return card
