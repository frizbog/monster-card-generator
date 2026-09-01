from __future__ import annotations

from typing import Any

from .util import first, signed, strip_markup


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        out = {}
        for item in value:
            if isinstance(item, dict):
                name = item.get("name") or item.get("skill") or item.get("ability")
                val = item.get("value") or item.get("bonus") or item.get("modifier")
                if name is not None and val is not None:
                    out[str(name)] = val
        return out
    return {}


def choose_quick_facts(monster: dict[str, Any], max_items: int = 4) -> list[str]:
    """Pick compact, high-runtime-value facts.

    This is intentionally heuristic. Overrides should replace the result when a
    creature has a better hand-curated status line.
    """
    candidates: list[tuple[int, str]] = []

    initiative = first(monster, "initiative", "initiative_bonus")
    if initiative is not None:
        candidates.append((100, f"Init {signed(initiative)}"))

    skills = _as_mapping(first(monster, "skills", "skill_proficiencies", default={}))
    # Commonly useful encounter skills get a slight preference.
    skill_priority = {"stealth": 95, "perception": 90, "deception": 75, "persuasion": 70, "religion": 60, "athletics": 60, "acrobatics": 60}
    for name, val in skills.items():
        p = skill_priority.get(str(name).casefold(), 45)
        candidates.append((p, f"{name.title()} {signed(val)}"))

    saves = _as_mapping(first(monster, "saving_throws", "saves", default={}))
    for name, val in saves.items():
        candidates.append((65, f"{str(name).upper()[:3]} save {signed(val)}"))

    senses = strip_markup(first(monster, "senses", default=""))
    if senses:
        # Passive Perception already has a dedicated dashboard field.
        bits = [x.strip() for x in senses.replace(";", ",").split(",")]
        for bit in bits:
            if bit and "passive perception" not in bit.casefold():
                candidates.append((85, bit))

    for keys, label, priority in [
        (("damage_immunities",), "Immune", 92),
        (("condition_immunities",), "Cond Immune", 90),
        (("damage_resistances",), "Resist", 88),
        (("damage_vulnerabilities",), "Vulnerable", 88),
    ]:
        value = first(monster, *keys, default=None)
        if value:
            if isinstance(value, list):
                text = ", ".join(strip_markup(x) for x in value)
            else:
                text = strip_markup(value)
            if text:
                candidates.append((priority, f"{label}: {text}"))

    # Languages are useful occasionally but deliberately low priority.
    languages = strip_markup(first(monster, "languages", default=""))
    if languages and languages.casefold() not in {"none", "-", "--"}:
        candidates.append((20, languages))

    candidates.sort(key=lambda x: x[0], reverse=True)
    facts: list[str] = []
    chars = 0
    for _, text in candidates:
        # Keep the strip compact; renderer can still shrink a bit if needed.
        projected = chars + len(text) + (3 if facts else 0)
        if projected > 105 and facts:
            continue
        facts.append(text)
        chars = projected
        if len(facts) >= max_items:
            break
    return facts
