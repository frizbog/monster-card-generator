# Monster Card Generator

A small, local Python tool that turns D&D SRD monster JSON into fast-play, duplex monster cards.

The project deliberately keeps the **SRD data repository separate** from the **card generator**. The SRD clone is an upstream dependency; this repository contains only layout, normalization, heuristics, and your editorial overrides.

## What this version does

- Renders one card per PDF page at **4.25 x 5.5 inches**.
- Uses the v0.2/v0.3 visual grammar: teal identity header; AC/HP/Speed/PP dashboard; six abilities; flexible quick-facts strip; flowing rules section; mostly empty reverse with four edge labels.
- Uses **Noto Sans**. Ability modifiers are deliberately large; the old `MODIFIERS` and `Raw Scores` labels are gone.
- Corrects the reverse long-edge orientation: the left and right edge labels are rotated 180 degrees from the first prototype.
- Reads several common SRD-as-JSON layouts rather than hard-coding one repository schema.
- Automatically proposes a compact `quick_facts` strip from initiative, useful skills/saves, senses, resistances/immunities, etc.
- Supports editorial JSON overrides so a hand-tuned card stays hand-tuned.
- Supports simple kit files that generate several cards together.

## Philosophy

The source SRD is **facts**. The card generator is **presentation and editorial judgment**.

Do not try to reproduce the Monster Manual. Optimize for seconds-to-understand at the table. A rare lookup can still go to the book. The cards are for eliminating repetitive lookup.

## 1. Install Python

Python 3.11+ is recommended.

On macOS, check:

```bash
python3 --version
```

## 2. Create a virtual environment

From this folder:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

On Windows PowerShell the activation command is:

```powershell
.venv\Scripts\Activate.ps1
```

## 3. Install Noto Sans

The renderer **does not bundle font files**. Install the upright Noto Sans variable font on your computer (for example via Google Fonts / Font Book on macOS). The usual Google Fonts download is named `NotoSans-VariableFont_wdth,wght.ttf`; the renderer selects its Light, Regular, Bold, and Black weights. Separate static weight files are also supported.

The code searches common macOS, Linux, and Windows font directories. If needed, point it at the directory containing the `.ttf` files:

```bash
export NOTO_SANS_DIR="$HOME/Library/Fonts"
```

Variable-font instances are cached under `~/Library/Caches/monster-card-generator/fonts` on macOS. They use the distinct internal family name **Monster Card Noto Sans**, so installing one in Font Book will not replace the original Google Noto Sans family. Installing the cache files is not required for PDF generation.

## 4. Smoke test without an SRD clone

The package includes two tiny manual examples solely to prove the renderer works:

```bash
python cards.py sample
```

Output:

```text
output/sample-cards.pdf
```

This is the quickest way to verify ReportLab + Noto Sans + PDF rendering on your machine.

## 5. Keep an SRD JSON clone next to this repo

Recommended directory shape:

```text
dnd/
├── dnd-srd-json/             # upstream clone; never edit for card work
└── monster-card-generator/   # this project
```

The adapter supports, among other layouts:

```text
data/resources/monsters/*.json
data/resources/spells/*.json
```

and flat files such as:

```text
monsters.json
spells.json
```

A current SRD 5.2.1 JSON repository is preferable. Keep its license/attribution intact and `git pull` it independently of this project.

First verify that the adapter can see it:

```bash
python cards.py inspect-srd --srd ../dnd-srd-json
```

You should see counts for monsters and spells.

## 6. Generate one monster

```bash
python cards.py monster "Goblin Warrior" --srd ../dnd-srd-json
```

Or specify the output path:

```bash
python cards.py monster "Goblin Warrior" \
  --srd ../dnd-srd-json \
  --out output/goblin-warrior.pdf
```

To see the normalized card data without making a PDF:

```bash
python cards.py monster "Goblin Warrior" \
  --srd ../dnd-srd-json \
  --dump-normalized
```

That command is very useful while adapting to a particular upstream JSON schema.

## 7. Editorial overrides

Automatic normalization is intentionally not the final word. Dense monsters, casters, or creatures with awkward source text should get small override files.

Example:

```bash
python cards.py monster "Cultist Fanatic" \
  --srd ../dnd-srd-json \
  --override overrides/human-cultist-caster.example.json \
  --out output/human-cultist-caster.pdf
```

An override can change only what needs changing:

```json
{
  "name": "Human Cultist (Caster)",
  "quick_facts": ["Init +2", "WIS save +4", "Religion +2"],
  "overflow": [
    {
      "title": "COMMAND",
      "meta": "ACTION · 60 ft.",
      "text": "Your tested operational summary here."
    }
  ]
}
```

The important design rule is: **if an operational spell summary is good, save it rather than re-summarizing it every run.** A later version can factor shared spell summaries into their own library.

## 8. Quick-facts selection

`monster_cards/quickfacts.py` proposes facts using a simple priority heuristic:

1. Initiative.
2. High-value encounter skills such as Stealth and Perception.
3. Senses other than Passive Perception (which already has a dashboard home).
4. Damage/condition immunities, resistances, and vulnerabilities.
5. Saving throws and other compact skills.
6. Languages only when there is room; they are intentionally low priority.

It also limits the strip length. This is a **proposal**, not sacred truth. Put `quick_facts` in an override whenever your DM judgment is better.

## 9. Generate a kit

A kit file is collection management, not monster data:

```json
{
  "name": "Goblins",
  "monsters": [
    "Goblin Warrior"
  ]
}
```

Run:

```bash
python cards.py kit kits/example-goblins.json --srd ../dnd-srd-json
```

Entries can also name an override:

```json
{
  "name": "Humans",
  "monsters": [
    {
      "name": "Cultist Fanatic",
      "override": "../overrides/human-cultist-caster.example.json"
    }
  ]
}
```

## 10. Where to tweak things

### Easy visual tweaks

Edit:

```text
config/card_style.json
```

That contains card dimensions, colors, and most font sizes. For example:

```json
"ability_modifier": 16
```

is the new large ability-modifier size.

### Layout / geometry tweaks

Edit:

```text
monster_cards/renderer.py
```

This contains the actual coordinates and shapes for the header, dashboard, ability row, quick-facts strip, flow area, and reverse.

### SRD schema adaptation

Edit:

```text
monster_cards/srd.py
monster_cards/normalize.py
```

`srd.py` is responsible for finding resources in an upstream repository. `normalize.py` translates arbitrary-ish SRD JSON field names into our stable `MonsterCard` model.

### Quick-facts logic

Edit:

```text
monster_cards/quickfacts.py
```

### Creature-specific editorial decisions

Put them in:

```text
overrides/
```

Do not bake monster-specific exceptions into the renderer unless they genuinely reveal a general layout rule.

## Architecture

```text
local SRD clone
      |
      v
SRDRepository (srd.py)
      |
      v
normalizer (normalize.py)
      |
      +----> quick-facts heuristic
      |
      v
MonsterCard model
      |
      +----> editorial override JSON
      |
      v
CardRenderer (renderer.py)
      |
      v
PDF
```

The renderer knows nothing about the upstream SRD repository. If the upstream schema changes, ideally only the adapter/normalizer changes.

## Important current limitation

This is **v0.1 of the reusable code**, not a finished publishing engine. Generic source descriptions can be too verbose for a card. The renderer will move some late blocks to the reverse, but it does not yet perform perfect predictive pagination of a single giant block before drawing it.

That is intentional at this stage: use `--dump-normalized`, create overrides for the cards you actually care about, and let real monsters tell us what the next general rule should be.

The next valuable improvements are likely:

- better predictive front/back layout before any block is drawn;
- a reusable spell-summary library;
- smarter recognition of attack syntax from SRD action prose;
- printing/imposition helper for four cards per Letter sheet;
- card/kit batch manifests and validation.

## Printing

The canonical PDF is **one card per PDF page at actual finished size**. Keep it that way. Let Acrobat, Preview, Staples, or a later imposition helper do four-up printing. Avoid baking Letter-sheet imposition into the card renderer.

## Attribution

The tool itself is your local generator. SRD 5.2.1 material is licensed under Creative Commons Attribution 4.0. Keep appropriate Wizards of the Coast attribution with generated content and with the upstream dataset you choose.
