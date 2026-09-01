from __future__ import annotations

import json
from pathlib import Path

from .model import Ability, MonsterCard, RuleBlock


def load_manual_cards(path: str | Path) -> list[MonsterCard]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return [_card(x) for x in payload]


def _card(x) -> MonsterCard:
    return MonsterCard(
        name=x["name"], subtitle=x["subtitle"], cr=str(x["cr"]), ac=str(x["ac"]), hp=str(x["hp"]),
        speed=str(x["speed"]), passive_perception=str(x["passive_perception"]),
        abilities={k: Ability(int(v["score"]),int(v["modifier"])) for k,v in x["abilities"].items()},
        quick_facts=list(x.get("quick_facts",[])),
        blocks=[RuleBlock(**b) for b in x.get("blocks",[])],
        overflow=[RuleBlock(**b) for b in x.get("overflow",[])],
        source_note=x.get("source_note"),
    )
