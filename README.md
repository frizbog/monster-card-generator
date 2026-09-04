# Monster Card Generator

A small, local Python tool that turns D&D SRD monster JSON into fast-play, duplex monster cards.

The project deliberately keeps the **SRD data repository separate** from the **card generator**. The SRD clone is an upstream dependency; this repository contains only layout, normalization, heuristics, and your editorial overrides.

## What this version does

- Renders two foldable card spreads per standard portrait US Letter PDF page
  (**8.5 x 11 inches**), with no special printer-driver setup.
- Sizes each unfolded spread to **8 1/8 x 5 5/16 inches** so four folded cards
  fit in a 9 x 11.5 inch laminating pouch with laminate tolerance.
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

As of Thu Sep 3 2026, a good URL is https://fonts.google.com/noto/specimen/Noto+Sans

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

The recommended SRD JSON repo can be found at https://github.com/Cantilux/dnd-srd-json.
This is the repo the code was developed and tested against.

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
python cards.py inspect-srd
```

You should see counts for monsters and spells.

The default SRD location is `../dnd-srd-json`. If your clone is elsewhere, add
`--srd /path/to/dnd-srd-json` to any SRD-based command.

## 6. Generate one monster

```bash
python cards.py monster "Goblin Warrior"
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

You can also generate several monsters into one PDF directly from the command line:

```bash
python cards.py monster "Goblin Warrior" "Goblin Boss" "Worg" \
  --srd ../dnd-srd-json \
  --out output/goblins.pdf
```

Without `--out`, a multi-monster command writes to `output/monster-cards.pdf`.
Use a kit file instead when individual monsters need different override files.

### Custom monsters alongside the SRD

Every `*.json` document recursively under this project's `custom/` directory is
loaded by default alongside the SRD. Each document must use the same structure as the SRD
repository's `data/documents/monsters-a-z.json` file. See
[`custom/README.md`](custom/README.md) for authoring instructions.

```bash
python cards.py monster "Clockwork Goblin" --out output/clockwork-goblin.pdf
```

To use a different file or directory, pass `--custom-monsters PATH`. The custom
documents are additive: ordinary names still resolve from `--srd`.
If a custom monster has the same name as an SRD monster, the custom definition
takes precedence. The option also works with `kit` and `inspect-srd`.

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
python cards.py kit kits/example-goblins.json
```

If a kit names a monster that is not present in the SRD, the command prints a
warning, skips that entry, and continues rendering the remaining monsters.

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

The front header is sized from visible proportions rather than independent
coordinates. `layout.front_header.height_in` controls the teal band's physical
height. `name_height_percent` and `challenge_rating_height_percent` derive those
font sizes from the padded band height; the subtitle uses the portion of the
two-row stack not assigned to the name. Text is measured and reduced further
only when its available horizontal space requires it. The dashboard follows the
bottom of the header using `primary_stats.top_gap_height_percent`.

The AC, HP, Speed, and PP icons similarly derive from
`layout.primary_stats.icon_height_in`. Their original aspect ratios are locked,
their internal coordinates scale with the height, and their label and value
fonts use the configured height percentages. The icons remain centered in four
evenly spaced columns and report an error if the requested height makes their
locked widths overlap.

`layout.abilities.band_height_in` controls the complete ability-score band.
After its padding and row gaps, `modifier_height_percent` assigns the middle
modifier row's share; the label and raw-score rows divide the remainder equally.
Their fonts are calculated from cap height because these rows contain only
uppercase labels, signs, and digits—no descenders need to be reserved. The
printable width between the artwork insets is always divided into six equal
columns, independent of the band height.

The quick-facts strip uses `layout.quick_facts.band_height_in`; its text height
and horizontal padding are percentages of the strip height and printable width.
The default 0.30-inch strip has slightly less vertical whitespace than the
original fixed-height strip. Facts that cannot fit at the configured minimum
text size continue to move into labeled rule blocks.

Back-face layout settings are collected under `layout.back`, including its edge
band, frame line, text padding, and source-note spacing.
Vertical spacing uses percentages of the current body line height, while the
source note's line height is a percentage of its own font size. Horizontal body
and source-note padding use percentages of the back frame's inner width, keeping
them independent of the derived font sizes. Physical frame-line width remains
in points.

As a general style convention for these responsive bands, absolute physical
measurements use inches while internal geometry uses percentages of the named
height or width. Point values remain elsewhere where that migration has not yet
been useful; this is a design direction rather than a format-wide restriction.

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

This is **v0.1 of the reusable code**, not a finished publishing engine. Generic source descriptions can still be too verbose for a card. The renderer measures text before drawing, moves overflow predictively, and reduces back-side continuation text when needed; if the complete content still cannot fit, it reports an explicit overflow error.

That is intentional at this stage: use `--dump-normalized`, create overrides for the cards you actually care about, and let real monsters tell us what the next general rule should be.

The next valuable improvements are likely:

- a reusable spell-summary library;
- smarter recognition of attack syntax from SRD action prose;
- additional printer calibration guidance for the foldable Letter-sheet workflow;
- card/kit batch manifests and validation.

## Printing, cutting, folding, and laminating

Each PDF page is a normal portrait US Letter page: **8.5 x 11 inches**. It
contains two unfolded card spreads, one in the top half and one in the bottom
half. Each spread is **8 1/8 x 5 5/16 inches**, with the front on the left and
the back on the right; the panels touch at the vertical center fold. Card 1 is
flush with the top and left paper edges. Card 2 is flush with the bottom and
left paper edges.

This layout is intentional. It puts both sides of a card on the same printed
side of the paper, so the front and back cannot drift out of registration as
they can with duplex printing.

The PDF includes solid cutter guides at the right edge of the spreads and at
both edges of the narrow center band. After the first fold, the two center-band
guides coincide. There is deliberately no line at the sheet's 5.5-inch fold:
every solid guide is a line to cut, not a line to fold. A light, unlabeled
crosshatch fills the portions that will be discarded; the darker solid lines
remain the cutting guides.

```text
Portrait US Letter page (8.5 x 11 in.)

top paper edge
┌────────────────────────────────────────────────────────────┬───┐
│  Card 1 spread: FRONT          | BACK                      │   │
│                                 fold                       │   │
│                                |                           │   │
│                                                            │   │
│          3/16 in. reserved beside center fold              │   │
│════════ fold full sheet here, printed side out ════════════│═══│
│          3/16 in. reserved beside center fold              │   │
│                                                            │   │
│                                |                           │   │
│                                 fold                       │   │
│  Card 2 spread: FRONT          | BACK                      │   │
└────────────────────────────────────────────────────────────┴───┘
bottom paper edge                                           right paper edge
                                                             ↑
                                           Cut 1 after folding: 3/8 in.

The left, top, and bottom paper edges are retained.
```

For a practical batch workflow:

1. Print the PDF at **Actual Size** or **100%** on ordinary US Letter paper.
   Do not use “Fit,” “Shrink,” borderless scaling, duplex mode, or a custom
   paper size. The printer driver only needs to handle a vanilla Letter page.
   **Margins are already built into the PDF content.**
2. Fold the full Letter sheet across its horizontal centerline, printed side
   out. This produces one folded **8.5 x 5.5 inch** piece with both printed
   spreads visible and the two halves perfectly stacked.
3. Trim **3/8 inch** from the right paper edge, perpendicular to the fold. This
   trims both stacked spreads to **8 1/8 inches** wide in one cut. Cut on the
   visible vertical guide.
4. Trim **3/16 inch** from the folded edge, parallel to the fold. Discard the
   narrow strip containing the entire fold. This cut separates the two spreads
   and leaves each one **5 5/16 inches** tall. The two visible horizontal guides
   align after Step 2's fold, providing the cut line on both faces.
5. Fold each separated spread vertically along the shared long edge between the
   front and back panels. The folded paper card is **4 1/16 x 5 5/16 inches**.
6. Arrange four folded cards in a 2 x 2 grid in a 9 x 11.5 inch laminating
   pouch and laminate them.

```text
Cut and fold sequence

1. Fold full Letter sheet at 5.5 in., printed side OUT:

   open sheet                         folded stack: 8.5 x 5.5 in.
   ┌──────────────────────┐           ┌────────────────────────┐
   │ Card 1 spread        │           │ Cards 1&2 back to back │
   │======================│  fold →   └────────────────────────┘ ← folded edge
   │ Card 2 spread        │
   └──────────────────────┘

2. Cut 3/8 in. from the right edge, through both layers:

   ┌────────────────────┬─┐
   │ stacked spreads    │x│  x = 3/8 in. → discard
   └────────────────────┴─┘

3. Cut 3/16 in. from the folded edge, parallel to it:

   ┌────────────────────┐
   │ stacked spreads    │
   ├────────────────────┤  y = 3/16 in. folded strip → discard
   └────────────────────┘

   The two layers are now separate 8 1/8 x 5 5/16 in. card spreads.
```

```text
Finished pouch layout (9 x 11.5 in.)

              11.5" side
┌──────────────────────────────────┐
│  ┌────────────┐  ┌────────────┐  │
│  │ Card 1     │  │ Card 2     │  │
│  └────────────┘  └────────────┘  │
│                                  │   9" side
│  ┌────────────┐  ┌────────────┐  │
│  │ Card 3     │  │ Card 4     │  │
│  └────────────┘  └────────────┘  │
└──────────────────────────────────┘

Each folded card: 4 1/16 x 5 5/16 in.
```

The card dimensions leave 1/8 inch of total slack in each pouch direction,
above the required 3/16-inch laminate material around every card. Keep the two
panels adjacent at the fold; do not insert a gutter there, since the fold itself
is the registration hinge.

## Attribution

The tool itself is your local generator. SRD 5.2.1 material is licensed under Creative Commons Attribution 4.0. Keep appropriate Wizards of the Coast attribution with generated content and with the upstream dataset you choose.
