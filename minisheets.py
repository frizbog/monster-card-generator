#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from monster_minisheets.io import load_manual_minisheets
from monster_minisheets.normalize import monster_to_minisheet
from monster_minisheets.overrides import apply_override, load_override
from monster_minisheets.renderer import MinisheetRenderer
from monster_minisheets.srd import SRDError, SRDRepository

ROOT = Path(__file__).resolve().parent
DEFAULT_STYLE = ROOT / "config" / "minisheet_style.json"
DEFAULT_SRD = "../dnd-srd-json"
DEFAULT_CUSTOM_MONSTERS = ROOT / "custom"

SOURCE_OPTIONS_HELP = (
    "Custom monster JSON file or directory (default: project's custom/ directory; "
    "all nested *.json files are loaded)."
)


def add_source_options(command: argparse.ArgumentParser) -> None:
    """Add the common local-SRD and custom-document options to a command."""
    command.add_argument(
        "--srd", default=DEFAULT_SRD, metavar="SRD_REPO",
        help="Path to the SRD repository directory (default: %(default)s).",
    )
    command.add_argument(
        "--custom-monsters", default=str(DEFAULT_CUSTOM_MONSTERS), metavar="CUSTOM_PATH",
        help=SOURCE_OPTIONS_HELP,
    )


def repository_from_args(args: argparse.Namespace) -> SRDRepository:
    """Build the shared data source used by the inspect, monster, and roster commands."""
    return SRDRepository(args.srd, args.custom_monsters)


def normalized_minisheets(repo: SRDRepository, names: list[str], override: str | None = None):
    """Turn SRD/custom records into renderable minisheets, applying one optional edit file."""
    return [
        apply_override(monster_to_minisheet(repo.monster(name)), load_override(override))
        for name in names
    ]


def main() -> int:
    # This text is repeated in subcommand help so a missing SRD is easy to fix
    # without consulting the README.
    location_help = """location examples:
  --srd /path/to/dnd-srd-json
  --custom-monsters /path/to/custom-folder

The SRD repository defaults to ../dnd-srd-json. Use --srd to select a different
repository directory. By default, every .json file under this project's custom/
directory is loaded alongside the SRD. Use --custom-monsters to select a
different JSON file or directory.
"""
    parser = argparse.ArgumentParser(
        description="Generate fast-play D&D monster minisheets as PDFs.",
        epilog="""examples:
  minisheets.py monster "Goblin Warrior"
  minisheets.py monster "Clockwork Goblin" \\
    --custom-monsters custom
  minisheets.py roster rosters/example-goblins.json --srd /path/to/dnd-srd-json \\
    --custom-monsters /path/to/custom-folder
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Commands only define input/output choices here. The dispatch below does
    # the work, which keeps `--help` quick and side-effect free.
    sub = parser.add_subparsers(dest="command", required=True)

    p_sample = sub.add_parser("sample", help="Render the bundled two-monster smoke test; no SRD repo required.")
    p_sample.add_argument("--out", default=str(ROOT / "output" / "sample-minisheets.pdf"))
    p_sample.add_argument("--style", default=str(DEFAULT_STYLE))

    p_inspect = sub.add_parser(
        "inspect-srd", help="Show whether the local SRD repository can be read.",
        epilog=location_help, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_source_options(p_inspect)

    p_monster = sub.add_parser(
        "monster", help="Render one or more monsters from the local SRD repository.",
        epilog=location_help, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_monster.add_argument("name", nargs="+", help="One or more monster names (quote names containing spaces).")
    add_source_options(p_monster)
    p_monster.add_argument("--override", help="Optional JSON editorial override for display/minisheet text.")
    p_monster.add_argument("--out")
    p_monster.add_argument("--style", default=str(DEFAULT_STYLE))
    p_monster.add_argument("--dump-normalized", action="store_true", help="Print normalized minisheet JSON and exit.")

    p_roster = sub.add_parser(
        "roster", help="Render every monster listed in a roster JSON file.",
        epilog=location_help, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p_roster.add_argument("roster_file")
    add_source_options(p_roster)
    p_roster.add_argument("--out")
    p_roster.add_argument("--style", default=str(DEFAULT_STYLE))

    args = parser.parse_args()
    try:
        # `sample` is intentionally self-contained; every other command starts
        # from the local SRD plus the project's custom-document directory.
        if args.command == "sample":
            minisheets = load_manual_minisheets(ROOT / "examples" / "manual_monsters.json")
            path = MinisheetRenderer(args.style).render(minisheets, args.out)
            print(path)
            return 0

        if args.command == "inspect-srd":
            print(json.dumps(repository_from_args(args).describe(), indent=2))
            return 0

        if args.command == "monster":
            repo = repository_from_args(args)
            if args.override and len(args.name) > 1:
                raise RuntimeError("--override can only be used when rendering one monster; use a roster for per-monster overrides")
            minisheets = normalized_minisheets(repo, args.name, args.override)
            if args.dump_normalized:
                payload = minisheets[0].to_dict() if len(minisheets) == 1 else [minisheet.to_dict() for minisheet in minisheets]
                print(json.dumps(payload, indent=2))
                return 0
            if args.out:
                out = args.out
            elif len(args.name) == 1:
                out = str(ROOT / "output" / f"{args.name[0].lower().replace(' ','-')}.pdf")
            else:
                out = str(ROOT / "output" / "monster-minisheets.pdf")
            path = MinisheetRenderer(args.style).render(minisheets, out)
            print(path)
            return 0

        if args.command == "roster":
            repo = repository_from_args(args)
            roster_path = Path(args.roster_file)
            data = json.loads(roster_path.read_text(encoding="utf-8"))
            minisheets = []
            for entry in data["monsters"]:
                if isinstance(entry, str):
                    name, override = entry, None
                else:
                    name = entry["name"]
                    override = entry.get("override")
                    if override:
                        override = str((roster_path.parent / override).resolve())
                try:
                    monster = repo.monster(name)
                except SRDError as exc:
                    print(f"WARNING: Skipping {name!r}: {exc}", file=sys.stderr)
                    continue
                minisheet = monster_to_minisheet(monster)
                minisheets.append(apply_override(minisheet, load_override(override)))
            if not minisheets:
                print("WARNING: No roster monsters were found; no PDF was written.", file=sys.stderr)
                return 0
            out = args.out or str(ROOT / "output" / f"{roster_path.stem}.pdf")
            path = MinisheetRenderer(args.style).render(minisheets, out)
            print(path)
            return 0
    except (SRDError, RuntimeError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
