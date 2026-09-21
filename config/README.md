# Card style configuration

`card_style.json` is the user-facing source of truth for the PDF's physical
dimensions, responsive card geometry, colors, and remaining type-size limits.
The renderer converts physical measurements to ReportLab points internally.

## Unit conventions

- Fields ending in `_in` are physical inches.
- Fields ending in `_pt` are typographic/PostScript points. One point is 1/72
  inch. Points are retained for line weights and legacy typography settings.
- Fields ending in `_percent` are percentages, where `100` means the full
  reference dimension. The field name identifies whether that dimension is a
  height, width, or line height.
- Percentages describe layout relationships. They are not stored as decimal
  fractions: use `25`, not `0.25`, for 25 percent.

Text is measured before drawing. A configured height determines the preferred
font size, but text may become smaller to fit its available width. A minimum
text size is a lower bound; the renderer reports an error rather than knowingly
drawing text that cannot fit at that size.

## Physical page and card fields

### `page_width_in` and `page_height_in`

The physical PDF page dimensions. The defaults produce portrait US Letter
pages measuring 8.5 by 11 inches.

### `card_width_in` and `card_height_in`

The dimensions of one normal minisheet. The defaults are 4.25 by 5.5 inches,
so four normal minisheets exactly tile a Letter page.

### `large_card_width_in` and `large_card_height_in`

The logical portrait dimensions of one large minisheet. The defaults are 5.5
by 8.5 inches. The renderer rotates it into a complete 8.5-by-5.5-inch row.

### `margin_pt`

The artwork inset from every minisheet edge. The default 18 points is 0.25 inch.

## `layout`

The `layout` object contains physical sheet marks and responsive content regions.

### `layout.front_header`

Controls the header band at the top of a minisheet.

- `height_in`: physical height of the complete header band.
- `horizontal_padding_width_percent`: left and right padding, each measured as
  a percentage of printable card width (`card_width_in` minus both artwork
  insets).
- `vertical_padding_height_percent`: top and bottom padding, each measured as a
  percentage of the complete header height.
- `line_gap_height_percent`: gap between the name row and subtitle row, as a
  percentage of header height.
- `column_gap_width_percent`: horizontal gap between the monster name and
  challenge rating, as a percentage of printable card width.
- `name_height_percent`: the name row's share of the usable height left after
  vertical padding and the line gap. The subtitle row receives the remainder.
- `challenge_rating_height_percent`: preferred challenge-rating glyph height,
  as a percentage of the same usable header height. The CR is vertically
  centered in the name row.
- `name_min_size_in`: minimum permitted typographic size for the monster name,
  expressed as a physical inch value.
- `text_min_size_in`: minimum permitted typographic size for the subtitle and
  challenge rating.

The challenge rating is measured first. Its width and the configured column gap
are reserved before the monster name is fitted into the remaining space.

### `layout.primary_stats`

Controls the AC, HP, Speed, and Passive Perception icons beneath the header.

- `icon_height_in`: physical height shared by all four icons.
- `top_gap_height_percent`: space between the header and icon row, measured as
  a percentage of icon height.
- `horizontal_inset_width_percent`: distance from each printable side to the
  center of the first or last icon, as a percentage of printable card width.
  The four centers are distributed evenly between those endpoints.
- `label_row_height_percent`: height of the upper label region inside each
  icon, as a percentage of icon height. The value region occupies the rest.
- `label_height_percent`: preferred label glyph height as a percentage of icon
  height.
- `value_height_percent`: preferred value glyph height as a percentage of icon
  height.
- `text_horizontal_padding_percent`: horizontal text padding on each side as a
  percentage of that icon's width. For Speed, the available text region excludes
  the triangular arrowhead and is centered within the rectangular shaft.
- `line_width_in`: physical stroke width of each icon outline.
- `divider_line_width_in`: physical stroke width of the PP icon's internal
  divider.
- `text_min_size_in`: minimum permitted label or value typographic size.

The icon aspect ratios are locked by the renderer: AC is 46:42, HP is 43:42,
Speed is 52:42, and PP is 1:1. Changing `icon_height_in` scales both dimensions
and all internal vector coordinates without stretching a shape.

### `layout.abilities`

Controls the STR, DEX, CON, INT, WIS, and CHA band.

- `band_height_in`: physical height of the complete ability band.
- `vertical_padding_height_percent`: top and bottom padding, each measured as a
  percentage of the complete band height.
- `row_gap_height_percent`: each gap between the label, modifier, and raw-score
  rows, as a percentage of band height.
- `modifier_height_percent`: modifier row's share of the usable height remaining
  after padding and both row gaps.
- `text_horizontal_padding_percent`: left and right text padding inside each
  ability column, as a percentage of that column's width.
- `text_min_size_in`: minimum permitted ability typographic size.

The label and raw-score rows each receive half of the height not assigned to the
modifier. Their font sizes use cap-height measurement because these fields
contain uppercase labels, signs, and digits rather than descenders. Printable
card width is always divided into exactly six equal columns; band height never
affects column width.

### `layout.quick_facts`

Controls the ruled strip containing compact facts such as initiative, saves,
skills, and languages.

- `band_height_in`: physical height of the complete strip.
- `text_height_percent`: preferred measured text height as a percentage of band
  height.
- `horizontal_padding_width_percent`: left and right padding, each measured as
  a percentage of printable card width.
- `line_width_in`: physical width of the strip's top and bottom rules.
- `text_min_size_in`: minimum permitted quick-facts typographic size.

Quick facts are measured as one centered line. When the complete line cannot fit
at the minimum size, lower-priority facts are promoted into labeled rule blocks
before traits and actions. Text is never silently discarded.

### `layout.large_columns`

- `gutter_in`: space between the two rule-text columns used when a large
  minisheet still does not fit as one column.
- `body_min_size_pt`: smallest permitted body size for that measured large-sheet
  fallback. The renderer tries whole one-point decrements.

### Sheet cut field

- `trim_guide_width_pt`: stroke width of the solid cut guides.

The horizontal center guide is always drawn. Vertical center guides are drawn
only through rows containing normal minisheets.

## `colors`

Each value is either a hexadecimal RGB string (`#rrggbb`) or `none`. Setting a
value to `none` makes that fill, stroke, or text transparent. Color properties
are named for the one visual role they control, so changing one does not
recolor an unrelated part of the card.

- `front_background` and `front_border`: base fill and outer minisheet frame.
- `header_band_background` and `header_band_text`: header fill and all text in
  the header.
- `primary_stats_background`: background of the complete primary-stat region.
- `icon_background`, `icon_border`, and `icon_text`: fill, outline, and text of
  the AC, HP, Speed, and PP icons.
- `ability_band_background`, `ability_label_text`, `ability_modifier_text`, and
  `ability_score_text`: ability-band fill and its three text rows.
- `quick_facts_background`, `quick_facts_border`, and `quick_facts_text`:
  quick-facts strip fill, rules, and text.
- `rule_blocks_background`, `rule_block_title_text`,
  `rule_block_body_text`, and `rule_block_divider`: front rule-block area and
  its content.
- `source_note_text`: source attribution text.
- `trim_guide`: cutter-guide strokes.

## `fonts`

- `family`: documents the required font family.
- `name_weight`: weight assigned to monster names.
- `body_weight`: weight assigned to prose.
- `label_weight`: weight assigned to headings and labels.

The renderer requires the bundled Noto Sans roles and does not treat this object
as a general font-selection mechanism. The current values document that fixed
contract: Black for names, Bold for labels, and Regular for prose.

## `sizes`

These remaining values are typographic point sizes.

- `body`: preferred rule prose size. Normal minisheets always use this size;
  large sheets may reduce it according to `layout.large_columns`.
- `source_note`: source-note font size at the bottom of the minisheet.

## Editing guidance

Change one high-level physical dimension at a time, then regenerate a sample:

```sh
python3 cards.py sample --out output/sample.pdf
```

Responsive percentages usually do not need adjustment when their containing
band changes size. If a percentage does need tuning, its full reference is named
in the field so that the resulting physical distance can be calculated directly.
