#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from monster_cards.io import load_manual_cards
from monster_cards.normalize import monster_to_card
from monster_cards.overrides import apply_override, load_override
from monster_cards.renderer import CardRenderer
from monster_cards.srd import SRDError, SRDRepository

ROOT = Path(__file__).resolve().parent
DEFAULT_STYLE = ROOT / "config" / "card_style.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate fast-play D&D monster cards as PDFs.")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample", help="Render the bundled two-card smoke test; no SRD repo required.")
    p_sample.add_argument("--out", default=str(ROOT / "output" / "sample-cards.pdf"))
    p_sample.add_argument("--style", default=str(DEFAULT_STYLE))

    p_inspect = sub.add_parser("inspect-srd", help="Show whether the local SRD repository can be read.")
    p_inspect.add_argument("--srd", required=True)

    p_monster = sub.add_parser("monster", help="Render one or more monsters from the local SRD repository.")
    p_monster.add_argument("name", nargs="+", help="One or more monster names (quote names containing spaces).")
    p_monster.add_argument("--srd", required=True)
    p_monster.add_argument("--override", help="Optional JSON editorial override for display/card text.")
    p_monster.add_argument("--out")
    p_monster.add_argument("--style", default=str(DEFAULT_STYLE))
    p_monster.add_argument("--dump-normalized", action="store_true", help="Print normalized card JSON and exit.")

    p_kit = sub.add_parser("kit", help="Render every monster listed in a kit JSON file.")
    p_kit.add_argument("kit_file")
    p_kit.add_argument("--srd", required=True)
    p_kit.add_argument("--out")
    p_kit.add_argument("--style", default=str(DEFAULT_STYLE))

    args = parser.parse_args()
    try:
        if args.command == "sample":
            cards = load_manual_cards(ROOT / "examples" / "manual_monsters.json")
            path = CardRenderer(args.style).render(cards, args.out)
            print(path)
            return 0

        if args.command == "inspect-srd":
            print(json.dumps(SRDRepository(args.srd).describe(), indent=2))
            return 0

        if args.command == "monster":
            repo = SRDRepository(args.srd)
            if args.override and len(args.name) > 1:
                raise RuntimeError("--override can only be used when rendering one monster; use a kit for per-monster overrides")
            cards = []
            for name in args.name:
                card = monster_to_card(repo.monster(name))
                cards.append(apply_override(card, load_override(args.override)))
            if args.dump_normalized:
                payload = cards[0].to_dict() if len(cards) == 1 else [card.to_dict() for card in cards]
                print(json.dumps(payload, indent=2))
                return 0
            if args.out:
                out = args.out
            elif len(args.name) == 1:
                out = str(ROOT / "output" / f"{args.name[0].lower().replace(' ','-')}.pdf")
            else:
                out = str(ROOT / "output" / "monster-cards.pdf")
            path = CardRenderer(args.style).render(cards, out)
            print(path)
            return 0

        if args.command == "kit":
            repo = SRDRepository(args.srd)
            kit_path = Path(args.kit_file)
            data = json.loads(kit_path.read_text(encoding="utf-8"))
            cards = []
            for entry in data["monsters"]:
                if isinstance(entry, str):
                    name, override = entry, None
                else:
                    name = entry["name"]
                    override = entry.get("override")
                    if override:
                        override = str((kit_path.parent / override).resolve())
                try:
                    monster = repo.monster(name)
                except SRDError as exc:
                    print(f"WARNING: Skipping {name!r}: {exc}", file=sys.stderr)
                    continue
                card = monster_to_card(monster)
                cards.append(apply_override(card, load_override(override)))
            if not cards:
                print("WARNING: No kit monsters were found; no PDF was written.", file=sys.stderr)
                return 0
            out = args.out or str(ROOT / "output" / f"{kit_path.stem}.pdf")
            path = CardRenderer(args.style).render(cards, out)
            print(path)
            return 0
    except (SRDError, RuntimeError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
