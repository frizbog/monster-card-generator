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

The dimensions of one folded card panel. A spread is exactly two panels wide:
the front is on the left and the back is on the right.

### `margin_pt`

The artwork inset from every card-panel edge. The default 18 points is 0.25
inch. Ordinary card artwork must remain inside this inset.

## `layout`

The `layout` object contains physical sheet marks and the responsive regions of
the front and back faces.

### `layout.front_header`

Controls the teal band at the top of the card front.

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

### Sheet trim and discard fields

- `trim_guide_width_pt`: stroke width of the solid cut guides.
- `discard_hatch_spacing_pt`: distance between repeated discard hatch lines.
- `discard_hatch_line_width_pt`: stroke width of discard hatch lines.

Trim guides are dark and drawn over the lighter discard hatching. These fields
affect mark styling, not the physical positions of the required cuts.

### `layout.back`

Controls the frame, edge labels, overflow text, and source note on the card back.

- `edge_band_in`: physical distance from each card edge to the inset back frame.
  It must be wider than the artwork inset so edge labels remain printable.
- `frame_line_width_pt`: stroke width of the inset frame.
- `body_horizontal_padding_width_percent`: left and right body-text padding,
  each measured as a percentage of the inner frame width (`card_width_in` minus
  two edge bands).
- `source_note_horizontal_padding_width_percent`: equivalent frame-width-based
  padding for the source note.
- `text_top_padding_line_percent`: space below the frame before body text begins,
  as a percentage of the current back body line height.
- `text_bottom_padding_line_percent`: space above the frame's bottom edge, as a
  percentage of the current back body line height.
- `source_note_clearance_line_percent`: vertical clearance between source-note
  content and body content, as a percentage of the current back body line
  height.
- `source_note_line_height_percent`: source-note line height as a percentage of
  the source-note font size.

Back body text starts at `sizes.body` and decreases only in whole one-point steps
when necessary. The proportional body spacing follows that selected size. If all
content still cannot fit, rendering ends with a clear overflow error.

## `colors`

All colors are hexadecimal RGB strings.

- `teal`: front header fill and primary-stat icon strokes.
- `dark`: primary text and solid trim guides.
- `mid`: supporting text such as raw ability scores and quick facts.
- `grid`: card frames and primary rules.
- `gray`: back edge labels and source notes.
- `divider`: subtle dividers between rule blocks.
- `discard_hatch`: light crosshatching in paper regions that will be discarded.

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

- `body`: front prose size and the initial back prose size. Back text may shrink
  from this value in whole one-point steps when necessary.
- `edge_label_max`: upper size limit for repeated labels around the card back.
- `edge_label_min`: lower size limit for those edge labels. Their actual size is
  also constrained by edge-band height and label width.
- `source_note`: source-note font size on the card back.

## Editing guidance

Change one high-level physical dimension at a time, then regenerate a sample:

```sh
python3 cards.py sample --out output/sample.pdf
```

Responsive percentages usually do not need adjustment when their containing
band changes size. If a percentage does need tuning, its full reference is named
in the field so that the resulting physical distance can be calculated directly.
