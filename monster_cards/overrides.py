from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .model import Ability, MonsterCard, RuleBlock


def load_override(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def apply_override(card: MonsterCard, data: dict[str, Any]) -> MonsterCard:
    if not data:
        return card
    for field in ("name", "subtitle", "cr", "ac", "hp", "speed", "passive_perception", "source_note"):
        if field in data:
            setattr(card, field, str(data[field]) if data[field] is not None else None)
    if "quick_facts" in data:
        card.quick_facts = [str(x) for x in data["quick_facts"]]
    if "abilities" in data:
        for abbr, payload in data["abilities"].items():
            card.abilities[abbr.upper()] = Ability(int(payload["score"]), int(payload["modifier"]))
    if "blocks" in data:
        card.blocks = [_rule_block(x) for x in data["blocks"]]
    if "append_blocks" in data:
        card.blocks.extend(_rule_block(x) for x in data["append_blocks"])
    if "overflow" in data:
        card.overflow = [_rule_block(x) for x in data["overflow"]]
    return card


def _rule_block(x: dict[str, Any]) -> RuleBlock:
    return RuleBlock(
        title=str(x.get("title", "")),
        text=str(x.get("text", "")),
        kind=str(x.get("kind", "full")),
        meta=x.get("meta"),
    )
