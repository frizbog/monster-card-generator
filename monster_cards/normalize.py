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


def _speed(monster: dict[str, Any]) -> str:
    speed = first(monster, "speed", "speeds", default="?")
    if isinstance(speed, dict):
        walk = first(speed, "walk", "walking", default=None)
        if walk is not None:
            return _distance(walk)
        # Pick first movement mode as a fallback.
        for value in speed.values():
            if value:
                return _distance(value)
    return _distance(speed)


def _distance(value: Any) -> str:
    text = strip_markup(value)
    if not text:
        return "?"
    if text.isdigit():
        return f"{text}'"
    text = re.sub(r"\bfeet\b", "ft.", text, flags=re.I)
    text = re.sub(r"\bfoot\b", "ft.", text, flags=re.I)
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


def _blocks(monster: dict[str, Any]) -> list[RuleBlock]:
    result: list[RuleBlock] = []
    traits = first(monster, "special_abilities", "traits", "features", default=[])
    actions = first(monster, "actions", default=[])
    bonus = first(monster, "bonus_actions", "bonusActions", default=[])
    reactions = first(monster, "reactions", default=[])

    # Traits before actions only when they are operationally relevant. This generic
    # importer cannot judge perfectly, so it preserves source order within groups.
    for name, desc in _iter_named_blocks(traits):
        result.append(RuleBlock(f"{name}:", desc, "full"))
    for name, desc in _iter_named_blocks(actions):
        result.append(RuleBlock(f"{name}:", desc, "full"))
    for name, desc in _iter_named_blocks(bonus):
        result.append(RuleBlock(f"Bonus Action - {name}:", desc, "full"))
    for name, desc in _iter_named_blocks(reactions):
        result.append(RuleBlock(f"Reaction - {name}:", desc, "full"))
    return result


def monster_to_card(monster: dict[str, Any]) -> MonsterCard:
    abilities = {abbr: _ability(monster, abbr) for abbr in ABILITIES}
    hp = first(monster, "hit_points", "hp", default="?")
    cr = first(monster, "challenge_rating", "cr", default="?")
    return MonsterCard(
        name=strip_markup(first(monster, "name", default="Unnamed Monster")),
        subtitle=_subtitle(monster),
        cr=str(cr),
        ac=_ac(monster),
        hp=str(hp),
        speed=_speed(monster),
        passive_perception=_passive_perception(monster),
        abilities=abilities,
        quick_facts=choose_quick_facts(monster),
        blocks=_blocks(monster),
        source_note="Generated from local D&D SRD JSON. SRD 5.2.1 content is CC BY 4.0, Wizards of the Coast LLC.",
    )
