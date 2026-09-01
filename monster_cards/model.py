from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

ABILITIES = ("STR", "DEX", "CON", "INT", "WIS", "CHA")


@dataclass
class Ability:
    score: int
    modifier: int


@dataclass
class RuleBlock:
    title: str
    text: str
    kind: str = "full"  # full | action
    meta: str | None = None


@dataclass
class MonsterCard:
    name: str
    subtitle: str
    cr: str
    ac: str
    hp: str
    speed: str
    passive_perception: str
    abilities: dict[str, Ability]
    quick_facts: list[str] = field(default_factory=list)
    blocks: list[RuleBlock] = field(default_factory=list)
    overflow: list[RuleBlock] = field(default_factory=list)
    source_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d
