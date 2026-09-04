from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import getAscentDescent, getFont, stringWidth
from reportlab.pdfgen import canvas

from .fonts import register_noto
from .layout import PT_PER_IN, SheetLayout
from .model import ABILITIES, MonsterCard, RuleBlock
from .util import signed


class CardRenderer:
    """Render measured monster cards onto foldable, physical PDF sheets.

    Coordinates use ReportLab points with (0, 0) at the lower-left of the
    current card panel. `render()` translates that local drawing twice per card
    spread, so front/back drawing stays independent of sheet placement.
    """

    # These are intrinsic properties of the four vector shapes. Their configured
    # height may change, but their width-to-height proportions never do.
    PRIMARY_STAT_REFERENCE_HEIGHT = 42
    BODY_LINE_HEIGHT_MULTIPLIER = 1.34
    PRIMARY_STAT_ASPECT_RATIOS = {
        "ac": 46/PRIMARY_STAT_REFERENCE_HEIGHT,
        "hp": 43/PRIMARY_STAT_REFERENCE_HEIGHT,
        "speed": 52/PRIMARY_STAT_REFERENCE_HEIGHT,
        "pp": 1.0,
    }

    def __init__(self, style_path: str | Path):
        # JSON is the authority for printable dimensions, colors, and type sizes.
        self.style = json.loads(Path(style_path).read_text(encoding="utf-8"))
        self.fonts = register_noto()
        self.sheet = SheetLayout.from_style(self.style)
        self.PAGE_W = self.sheet.page_width
        self.PAGE_H = self.sheet.page_height
        self.W = self.sheet.card_width
        self.H = self.sheet.card_height
        self.M = self.sheet.artwork_inset
        self.layout = self.style["layout"]
        self.front_header = self.layout["front_header"]
        self.front_header_height = float(self.front_header["height_in"]) * PT_PER_IN
        name_percent = float(self.front_header["name_height_percent"])
        cr_percent = float(self.front_header["challenge_rating_height_percent"])
        if not 0 < name_percent < 100:
            raise ValueError("layout.front_header.name_height_percent must be between 0 and 100")
        if not 0 < cr_percent <= 100:
            raise ValueError(
                "layout.front_header.challenge_rating_height_percent must be between 0 and 100"
            )
        if self._front_header_usable_height() <= 0:
            raise ValueError("layout.front_header padding and gap must leave usable height")
        self.primary_stats = self.layout["primary_stats"]
        self.primary_stat_height = float(self.primary_stats["icon_height_in"]) * PT_PER_IN
        if self.primary_stat_height <= 0:
            raise ValueError("layout.primary_stats.icon_height_in must be positive")
        for key in ("label_row_height_percent","label_height_percent","value_height_percent"):
            percent = float(self.primary_stats[key])
            if not 0 < percent < 100:
                raise ValueError(f"layout.primary_stats.{key} must be between 0 and 100")
        text_padding_percent = float(self.primary_stats["text_horizontal_padding_percent"])
        if not 0 <= text_padding_percent < 50:
            raise ValueError(
                "layout.primary_stats.text_horizontal_padding_percent must be between 0 and 50"
            )
        self.abilities = self.layout["abilities"]
        self.ability_band_height = float(self.abilities["band_height_in"]) * PT_PER_IN
        if self.ability_band_height <= 0:
            raise ValueError("layout.abilities.band_height_in must be positive")
        modifier_percent = float(self.abilities["modifier_height_percent"])
        if not 0 < modifier_percent < 100:
            raise ValueError(
                "layout.abilities.modifier_height_percent must be between 0 and 100"
            )
        ability_text_padding = float(self.abilities["text_horizontal_padding_percent"])
        if not 0 <= ability_text_padding < 50:
            raise ValueError(
                "layout.abilities.text_horizontal_padding_percent must be between 0 and 50"
            )
        if self._ability_usable_height() <= 0:
            raise ValueError("layout.abilities padding and gaps must leave usable height")
        self.quick_facts = self.layout["quick_facts"]
        self.quick_facts_band_height = float(self.quick_facts["band_height_in"]) * PT_PER_IN
        if self.quick_facts_band_height <= 0:
            raise ValueError("layout.quick_facts.band_height_in must be positive")
        quick_facts_text_percent = float(self.quick_facts["text_height_percent"])
        if not 0 < quick_facts_text_percent <= 100:
            raise ValueError(
                "layout.quick_facts.text_height_percent must be between 0 and 100"
            )
        quick_facts_padding = float(self.quick_facts["horizontal_padding_width_percent"])
        if not 0 <= quick_facts_padding < 50:
            raise ValueError(
                "layout.quick_facts.horizontal_padding_width_percent must be between 0 and 50"
            )
        self.back = self.layout["back"]
        self.back_edge_band = float(self.back["edge_band_in"]) * PT_PER_IN
        if self.back_edge_band <= self.M:
            raise ValueError("layout.back.edge_band_in must exceed margin_pt / 72")
        colors = self.style["colors"]
        self.TEAL = HexColor(colors["teal"])
        self.DARK = HexColor(colors["dark"])
        self.MID = HexColor(colors["mid"])
        self.GRID = HexColor(colors["grid"])
        self.GRAY = HexColor(colors["gray"])
        self.DIVIDER = HexColor(colors["divider"])
        self.DISCARD_HATCH = HexColor(colors["discard_hatch"])
        self.sizes = self.style["sizes"]
        self.c: canvas.Canvas | None = None
        self._back_body_sizes: dict[int, float] = {}
        self._fact_flow_prepared: set[int] = set()

    def render(self, cards: Iterable[MonsterCard], output: str | Path) -> Path:
        """Measure all text, then place up to two complete spreads on each sheet."""
        cards = list(cards)
        # Text flow mutates a card into front blocks and back overflow before any
        # ink is drawn. That avoids silent clipping caused by draw-as-you-go code.
        for card in cards:
            self._prepare_block_flow(card)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(output), pagesize=(self.PAGE_W, self.PAGE_H))
        self.c.setTitle("Monster Cards")
        # First card goes at the top, second at the bottom. An odd final card
        # deliberately leaves the bottom slot blank for the physical workflow.
        for index in range(0,len(cards),2):
            self._draw_spread(cards[index],top=True)
            if index+1 < len(cards):
                self._draw_spread(cards[index+1],top=False)
            self._draw_discard_hatching()
            self._draw_trim_guides()
            self.c.showPage()
        self.c.save()
        self.c = None
        return output

    def _spread_origin(self, top: bool) -> tuple[float,float]:
        return self.sheet.spread_origin(top)

    def _draw_spread(self, card: MonsterCard, top: bool) -> None:
        """Draw a front/back pair that shares its long-edge fold at `self.W`."""
        c = self.c; assert c
        x,y = self._spread_origin(top)
        c.saveState(); c.translate(x,y); self._draw_front(card); c.restoreState()
        c.saveState(); c.translate(x+self.W,y); self._draw_back(card); c.restoreState()

    def _trim_guide_segments(self) -> list[tuple[float,float,float,float]]:
        """Solid guides for the two physical cuts made after folding the sheet."""
        return self.sheet.trim_guide_segments()

    def _discard_regions(self) -> list[tuple[float,float,float,float]]:
        return self.sheet.discard_regions()

    def _crosshatch_rect(self, x: float, y: float, width: float, height: float) -> None:
        """Clip a light X-hatch to a discard region without touching card artwork."""
        c = self.c; assert c
        spacing = float(self.layout["discard_hatch_spacing_pt"])
        c.saveState()
        clip = c.beginPath(); clip.rect(x,y,width,height)
        c.clipPath(clip,stroke=0,fill=0)
        c.setStrokeColor(self.DISCARD_HATCH)
        c.setLineWidth(float(self.layout["discard_hatch_line_width_pt"]))
        start = x-height
        end = x+width+height
        position = start
        while position <= end:
            c.line(position,y,position+height,y+height)
            c.line(position,y+height,position+height,y)
            position += spacing
        c.restoreState()

    def _draw_discard_hatching(self) -> None:
        # Hatching is drawn before the darker cut guides, preserving their meaning.
        for region in self._discard_regions():
            self._crosshatch_rect(*region)

    def _draw_trim_guides(self) -> None:
        c = self.c; assert c
        c.saveState()
        c.setStrokeColor(self.DARK)
        c.setLineWidth(float(self.layout["trim_guide_width_pt"]))
        for x1,y1,x2,y2 in self._trim_guide_segments():
            c.line(x1,y1,x2,y2)
        c.restoreState()

    def _line(self, x1, y1, x2, y2, width=.7, color=None):
        c = self.c; assert c
        c.setStrokeColor(color or self.GRID); c.setLineWidth(width); c.line(x1, y1, x2, y2)

    def _center(self, text, x, y, font="bold", size=8, color=None):
        c = self.c; assert c
        c.setFillColor(color or self.DARK); c.setFont(self.fonts[font], size); c.drawCentredString(x, y, str(text))

    def _fit(self, text, maxw, start, minsize, font="regular"):
        s = float(start)
        f = self.fonts[font]
        while s > minsize and stringWidth(str(text), f, s) > maxw:
            s -= .25
        return s

    def _outer(self):
        c = self.c; assert c
        c.setStrokeColor(self.GRID); c.setLineWidth(1); c.rect(self.M, self.M, self.W - 2*self.M, self.H - 2*self.M, stroke=1, fill=0)

    def _front_header_usable_height(self) -> float:
        """Return header height available to the name and subtitle rows."""
        padding = self.front_header_height*float(
            self.front_header["vertical_padding_height_percent"]
        )/100
        gap = self.front_header_height*float(
            self.front_header["line_gap_height_percent"]
        )/100
        return self.front_header_height-2*padding-gap

    @staticmethod
    def _font_size_for_height(font: str, height: float) -> float:
        """Convert a desired glyph height into a size using the font's metrics."""
        ascent, descent = getAscentDescent(font,1)
        return height/(ascent-descent)

    @staticmethod
    def _baseline_for_row(font: str, size: float, bottom: float, top: float) -> float:
        """Center a font's actual ascent/descent bounds within a vertical row."""
        ascent, descent = getAscentDescent(font,size)
        return (bottom+top-ascent-descent)/2

    @staticmethod
    def _cap_height(font: str, size: float) -> float:
        """Return cap height for uppercase and numeric text with no descenders."""
        face = getFont(font).face
        return float(getattr(face,"capHeight",face.ascent))*size/1000

    @classmethod
    def _font_size_for_cap_height(cls, font: str, height: float) -> float:
        return height/cls._cap_height(font,1)

    @classmethod
    def _baseline_for_cap_row(
        cls, font: str, size: float, bottom: float, top: float
    ) -> float:
        """Center baseline-to-cap bounds in a row without descent allowance."""
        return (bottom+top-cls._cap_height(font,size))/2

    def _fit_text_to_height(
        self, text: str, font: str, target_height: float, max_width: float,
        minimum: float, context: str,
    ) -> float:
        size = self._font_size_for_height(self.fonts[font],target_height)
        if size < minimum:
            raise RuntimeError(
                f"The {context} is too short for {text!r} at the minimum font size"
            )
        size = self._fit(text,max_width,size,minimum,font)
        if stringWidth(text,self.fonts[font],size) > max_width:
            raise RuntimeError(
                f"{context.capitalize()} text {text!r} does not fit at the minimum font size"
            )
        return size

    def _fit_cap_text_to_height(
        self, text: str, font: str, target_height: float, max_width: float,
        minimum: float, context: str,
    ) -> float:
        """Fit known uppercase/numeric text without reserving descender space."""
        size = self._font_size_for_cap_height(self.fonts[font],target_height)
        if size < minimum:
            raise RuntimeError(
                f"The {context} is too short for {text!r} at the minimum font size"
            )
        size = self._fit(text,max_width,size,minimum,font)
        if stringWidth(text,self.fonts[font],size) > max_width:
            raise RuntimeError(
                f"{context.capitalize()} text {text!r} does not fit at the minimum font size"
            )
        return size

    def _front_header_layout(self, card: MonsterCard) -> dict[str, float | str]:
        """Measure the two-row header from its visible height and text percentages."""
        header_top = self.H-self.M
        header_width = self.W-2*self.M
        padding_x = header_width*float(
            self.front_header["horizontal_padding_width_percent"]
        )/100
        padding_y = self.front_header_height*float(
            self.front_header["vertical_padding_height_percent"]
        )/100
        line_gap = self.front_header_height*float(
            self.front_header["line_gap_height_percent"]
        )/100
        column_gap = header_width*float(
            self.front_header["column_gap_width_percent"]
        )/100
        usable_height = self._front_header_usable_height()
        name_row_height = usable_height*float(self.front_header["name_height_percent"])/100
        subtitle_row_height = usable_height-name_row_height
        subtitle_top = header_top-padding_y-name_row_height-line_gap
        subtitle_bottom = subtitle_top-subtitle_row_height
        name_bottom = subtitle_top+line_gap
        name_top = header_top-padding_y
        left = self.M+padding_x
        right = self.W-self.M-padding_x
        minimum = float(self.front_header["text_min_size_in"])*PT_PER_IN

        cr_text = f"CR {card.cr}"
        cr_height = usable_height*float(
            self.front_header["challenge_rating_height_percent"]
        )/100
        cr_size = self._fit_text_to_height(
            cr_text,"bold",cr_height,right-left,minimum,"front header"
        )
        cr_width = stringWidth(cr_text,self.fonts["bold"],cr_size)
        name_width = right-left-cr_width-column_gap
        if name_width <= 0:
            raise RuntimeError("Challenge rating leaves no room for the monster name")
        name_size = self._fit_text_to_height(
            card.name,"black",name_row_height,name_width,
            float(self.front_header["name_min_size_in"])*PT_PER_IN,"front header",
        )
        subtitle_size = self._fit_text_to_height(
            card.subtitle,"bold",subtitle_row_height,right-left,minimum,"front header"
        )
        return {
            "top": header_top,
            "left": left,
            "right": right,
            "name_size": name_size,
            "name_baseline": self._baseline_for_row(
                self.fonts["black"],name_size,name_bottom,name_top
            ),
            "subtitle_size": subtitle_size,
            "subtitle_baseline": self._baseline_for_row(
                self.fonts["bold"],subtitle_size,subtitle_bottom,subtitle_top
            ),
            "cr_text": cr_text,
            "cr_size": cr_size,
            "cr_baseline": self._baseline_for_row(
                self.fonts["bold"],cr_size,name_bottom,name_top
            ),
        }

    def _header(self, card: MonsterCard):
        c = self.c; assert c
        header = self._front_header_layout(card)
        c.setFillColor(self.TEAL)
        c.rect(
            self.M,self.H-self.M-self.front_header_height,
            self.W-2*self.M,self.front_header_height,fill=1,stroke=0,
        )
        c.setFillColor(white)
        c.setFont(self.fonts["black"],header["name_size"])
        c.drawString(header["left"],header["name_baseline"],card.name)
        c.setFont(self.fonts["bold"],header["subtitle_size"])
        c.drawString(header["left"],header["subtitle_baseline"],card.subtitle)
        c.setFont(self.fonts["bold"],header["cr_size"])
        c.drawRightString(header["right"],header["cr_baseline"],header["cr_text"])

    def _primary_stat_width(self, kind: str) -> float:
        return self.primary_stat_height*self.PRIMARY_STAT_ASPECT_RATIOS[kind]

    def _primary_stat_text_layout(
        self, kind: str, label: str, value: str, cx: float, top: float
    ) -> dict[str, float]:
        """Fit label and value text into proportional rows inside an icon."""
        height = self.primary_stat_height
        width = self._primary_stat_width(kind)
        bottom = top-height
        label_row_height = height*float(
            self.primary_stats["label_row_height_percent"]
        )/100
        boundary = top-label_row_height
        minimum = float(self.primary_stats["text_min_size_in"])*PT_PER_IN
        text_padding = width*float(
            self.primary_stats["text_horizontal_padding_percent"]
        )/100
        if kind == "speed":
            # Keep text in the arrow's rectangular shaft rather than its point.
            shaft_width = width*39/52
            text_width = shaft_width-2*text_padding
            text_center = cx-width/2+shaft_width/2
        else:
            text_width = width-2*text_padding
            text_center = cx
        label_size = self._fit_text_to_height(
            label,"bold",height*float(self.primary_stats["label_height_percent"])/100,
            text_width,minimum,"primary-stat icon",
        )
        value_size = self._fit_text_to_height(
            str(value),"black",height*float(self.primary_stats["value_height_percent"])/100,
            text_width,minimum,"primary-stat icon",
        )
        return {
            "center": text_center,
            "boundary": boundary,
            "label_size": label_size,
            "label_baseline": self._baseline_for_row(
                self.fonts["bold"],label_size,boundary,top
            ),
            "value_size": value_size,
            "value_baseline": self._baseline_for_row(
                self.fonts["black"],value_size,bottom,boundary
            ),
        }

    def _draw_primary_stat_text(self, kind, label, value, cx, top):
        text = self._primary_stat_text_layout(kind,label,str(value),cx,top)
        self._center(
            label,text["center"],text["label_baseline"],
            size=text["label_size"],
        )
        self._center(
            value,text["center"],text["value_baseline"],font="black",
            size=text["value_size"],
        )

    def _shield_ac(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; w = self._primary_stat_width("ac")
        scale = h/self.PRIMARY_STAT_REFERENCE_HEIGHT; x, y = cx-w/2, top-h
        p = c.beginPath(); p.moveTo(x,y+h); p.lineTo(x+w,y+h)
        p.lineTo(x+w-7*scale,y); p.lineTo(x+7*scale,y); p.close()
        c.setStrokeColor(self.TEAL); c.setLineWidth(float(self.primary_stats["line_width_in"])*PT_PER_IN); c.drawPath(p, stroke=1, fill=0)
        self._draw_primary_stat_text("ac","AC",value,cx,top)

    def _box_hp(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; w = self._primary_stat_width("hp")
        scale = h/self.PRIMARY_STAT_REFERENCE_HEIGHT; x, y = cx-w/2, top-h
        p = c.beginPath();
        p.moveTo(x+7*scale,y+h); p.lineTo(x+w-7*scale,y+h); p.lineTo(x+w-7*scale,y+h-6*scale); p.lineTo(x+w,y+h-6*scale)
        p.lineTo(x+w,y+6*scale); p.lineTo(x+w-7*scale,y+6*scale); p.lineTo(x+w-7*scale,y); p.lineTo(x+7*scale,y); p.lineTo(x+7*scale,y+6*scale)
        p.lineTo(x,y+6*scale); p.lineTo(x,y+h-6*scale); p.lineTo(x+7*scale,y+h-6*scale); p.close()
        c.setStrokeColor(self.TEAL); c.setLineWidth(float(self.primary_stats["line_width_in"])*PT_PER_IN); c.drawPath(p, stroke=1, fill=0)
        self._draw_primary_stat_text("hp","HP",value,cx,top)

    def _arrow_speed(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; w = self._primary_stat_width("speed")
        scale = h/self.PRIMARY_STAT_REFERENCE_HEIGHT; x, y = cx-w/2, top-h
        p = c.beginPath(); p.moveTo(x,y); p.lineTo(x+39*scale,y); p.lineTo(x+39*scale,y+8*scale); p.lineTo(x+w,y+h/2)
        p.lineTo(x+39*scale,y+h-8*scale); p.lineTo(x+39*scale,y+h); p.lineTo(x,y+h); p.close()
        c.setStrokeColor(self.TEAL); c.setLineWidth(float(self.primary_stats["line_width_in"])*PT_PER_IN); c.drawPath(p, stroke=1, fill=0)
        self._draw_primary_stat_text("speed","SPEED",value,cx,top)

    def _circle_pp(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; r = h/2; y = top-r
        text = self._primary_stat_text_layout("pp","PP",str(value),cx,top)
        c.setStrokeColor(self.TEAL); c.setLineWidth(float(self.primary_stats["line_width_in"])*PT_PER_IN); c.circle(cx,y,r,stroke=1,fill=0)
        self._line(
            cx-r,text["boundary"],cx+r,text["boundary"],
            width=float(self.primary_stats["divider_line_width_in"])*PT_PER_IN,
            color=self.TEAL,
        )
        self._draw_primary_stat_text("pp","PP",value,cx,top)

    def _dashboard(self, card: MonsterCard):
        top = self._dashboard_top()
        # AC and PP have matching frame insets; HP and Speed divide the span evenly.
        dashboard_inset = (self.W-2*self.M)*float(
            self.primary_stats["horizontal_inset_width_percent"]
        )/100
        dashboard_span = self.W-2*self.M-2*dashboard_inset
        xs = [self.M+dashboard_inset+i*dashboard_span/3 for i in range(4)]
        kinds = ("ac","hp","speed","pp")
        widths = [self._primary_stat_width(kind) for kind in kinds]
        bounds = [(x-width/2,x+width/2) for x,width in zip(xs,widths)]
        if bounds[0][0] < self.M or bounds[-1][1] > self.W-self.M or any(
            right > next_left for (_,right),(next_left,_) in zip(bounds,bounds[1:])
        ):
            raise RuntimeError("Primary-stat icons do not fit across the printable card width")
        self._shield_ac(xs[0],top,card.ac); self._box_hp(xs[1],top,card.hp); self._arrow_speed(xs[2],top,card.speed); self._circle_pp(xs[3],top,card.passive_perception)

        # Modifiers are deliberately large; raw scores are supporting information
        # beneath them. There are intentionally no "MODIFIERS" / "Raw Scores" labels.
        ability_top = top-self.primary_stat_height
        for index, abbr in enumerate(ABILITIES):
            self._draw_ability(index,abbr,card.abilities[abbr],ability_top)
        return ability_top-self.ability_band_height

    def _ability_usable_height(self) -> float:
        padding = self.ability_band_height*float(
            self.abilities["vertical_padding_height_percent"]
        )/100
        gap = self.ability_band_height*float(
            self.abilities["row_gap_height_percent"]
        )/100
        return self.ability_band_height-2*padding-2*gap

    def _ability_column_bounds(self, index: int) -> tuple[float,float]:
        """Return one of six equal columns across the printable card width."""
        column_width = (self.W-2*self.M)/len(ABILITIES)
        left = self.M+index*column_width
        return left,left+column_width

    def _ability_layout(self, index: int, abbr: str, ability, top: float) -> dict[str,float]:
        """Measure one ability using the shared three-row vertical proportions."""
        left,right = self._ability_column_bounds(index)
        width = right-left
        padding_y = self.ability_band_height*float(
            self.abilities["vertical_padding_height_percent"]
        )/100
        gap = self.ability_band_height*float(
            self.abilities["row_gap_height_percent"]
        )/100
        usable_height = self._ability_usable_height()
        modifier_height = usable_height*float(
            self.abilities["modifier_height_percent"]
        )/100
        outer_height = (usable_height-modifier_height)/2

        label_top = top-padding_y
        label_bottom = label_top-outer_height
        modifier_top = label_bottom-gap
        modifier_bottom = modifier_top-modifier_height
        score_top = modifier_bottom-gap
        score_bottom = score_top-outer_height
        text_padding = width*float(
            self.abilities["text_horizontal_padding_percent"]
        )/100
        text_width = width-2*text_padding
        minimum = float(self.abilities["text_min_size_in"])*PT_PER_IN
        modifier = signed(ability.modifier)
        score = str(ability.score)
        label_size = self._fit_cap_text_to_height(
            abbr,"bold",outer_height,text_width,minimum,"ability band"
        )
        modifier_size = self._fit_cap_text_to_height(
            modifier,"black",modifier_height,text_width,minimum,"ability band"
        )
        score_size = self._fit_cap_text_to_height(
            score,"regular",outer_height,text_width,minimum,"ability band"
        )
        return {
            "left": left,
            "right": right,
            "center": (left+right)/2,
            "label_size": label_size,
            "label_baseline": self._baseline_for_cap_row(
                self.fonts["bold"],label_size,label_bottom,label_top
            ),
            "modifier_size": modifier_size,
            "modifier_baseline": self._baseline_for_cap_row(
                self.fonts["black"],modifier_size,modifier_bottom,modifier_top
            ),
            "score_size": score_size,
            "score_baseline": self._baseline_for_cap_row(
                self.fonts["regular"],score_size,score_bottom,score_top
            ),
        }

    def _draw_ability(self, index: int, abbr: str, ability, top: float) -> None:
        layout = self._ability_layout(index,abbr,ability,top)
        center = layout["center"]
        self._center(
            abbr,center,layout["label_baseline"],font="bold",size=layout["label_size"]
        )
        self._center(
            signed(ability.modifier),center,layout["modifier_baseline"],
            font="black",size=layout["modifier_size"],
        )
        self._center(
            str(ability.score),center,layout["score_baseline"],font="regular",
            size=layout["score_size"],color=self.MID,
        )

    def _dashboard_top(self) -> float:
        return (
            self.H-self.M-self.front_header_height
            -self.primary_stat_height
            *float(self.primary_stats["top_gap_height_percent"])/100
        )

    def _dashboard_bottom(self) -> float:
        """Bottom of the dashboard, derived from its header-relative top."""
        return self._dashboard_top()-self.primary_stat_height-self.ability_band_height

    def _facts(self, y, facts: list[str]):
        if not facts:
            return y
        text = " · ".join(facts)
        height = self.quick_facts_band_height
        width = self.W-2*self.M
        horizontal_padding = width*float(
            self.quick_facts["horizontal_padding_width_percent"]
        )/100
        text_width = width-2*horizontal_padding
        minimum = float(self.quick_facts["text_min_size_in"])*PT_PER_IN
        size = self._fit_text_to_height(
            text,"black",height*float(self.quick_facts["text_height_percent"])/100,
            text_width,minimum,"quick-facts band",
        )
        line_width = float(self.quick_facts["line_width_in"])*PT_PER_IN
        self._line(self.M,y,self.W-self.M,y,width=line_width)
        self._line(self.M,y-height,self.W-self.M,y-height,width=line_width)
        baseline = self._baseline_for_row(self.fonts["black"],size,y-height,y)
        self._center(text,self.W/2,baseline,font="black",size=size,color=self.MID)
        return y-height

    def _block_layout(self, block: RuleBlock):
        """Wrap a front rule block, reserving first-line space for its bold title."""
        size = self.sizes["body"]
        x = self.M+7; right = self.W-self.M-7
        titlew = stringWidth(block.title,self.fonts["bold"],size)+4
        firstw = max(20,right-(x+titlew))
        words = block.text.split(); lines=[]; cur=""; first_line=True
        while words:
            word=words.pop(0); test=(cur+" "+word).strip(); limit=firstw if first_line else right-x
            if stringWidth(test,self.fonts["regular"],size)<=limit:
                cur=test
            else:
                if cur:
                    lines.append((cur,first_line)); first_line=False; cur=word
                else:
                    lines.append((word,first_line)); first_line=False; cur=""
        if cur: lines.append((cur,first_line))
        return titlew, lines

    def _block_height(self, block: RuleBlock) -> float:
        _, lines = self._block_layout(block)
        return 12 + len(lines) * self.sizes["body"] * 1.34

    def _block(self, y: float, block: RuleBlock, divider=True) -> float:
        c = self.c; assert c
        size = self.sizes["body"]
        x = self.M+7; right = self.W-self.M-7
        if divider:
            self._line(x,y+4,right,y+4,width=.45,color=self.DIVIDER)
        c.setFillColor(self.DARK); c.setFont(self.fonts["bold"],size); c.drawString(x,y-8,block.title)
        titlew, lines = self._block_layout(block)
        yy=y-8
        for text,is_first in lines:
            c.setFont(self.fonts["regular"],size); c.drawString(x+titlew if is_first else x,yy,text); yy-=size*1.34
        return yy-4

    def _front_block_top(self, card: MonsterCard) -> float:
        y = self._dashboard_bottom()
        if card.quick_facts:
            y -= self.quick_facts_band_height
        return y-7

    def _back_body_leading(self, body_size: float) -> float:
        return body_size*self.BODY_LINE_HEIGHT_MULTIPLIER

    def _back_frame_width(self) -> float:
        return self.W-2*self.back_edge_band

    def _back_body_horizontal_padding(self) -> float:
        return (
            self._back_frame_width()
            *float(self.back["body_horizontal_padding_width_percent"])/100
        )

    def _back_source_note_leading(self) -> float:
        return (
            float(self.sizes["source_note"])
            *float(self.back["source_note_line_height_percent"])/100
        )

    def _back_source_note_horizontal_padding(self) -> float:
        return (
            self._back_frame_width()
            *float(self.back["source_note_horizontal_padding_width_percent"])/100
        )

    def _back_text_width(self) -> float:
        """Return back body width after frame-relative horizontal padding."""
        return self._back_frame_width()-2*self._back_body_horizontal_padding()

    def _back_source_note_width(self) -> float:
        return (
            self._back_frame_width()-2*self._back_source_note_horizontal_padding()
        )

    def _back_text_start(self, body_size: float) -> float:
        """Anchor back text below the inset frame by a body-text-relative gap."""
        padding = (
            self._back_body_leading(body_size)
            *float(self.back["text_top_padding_line_percent"])/100
        )
        return self.H-self.back_edge_band-padding

    def _back_edge_label_size(self, edge: str) -> float:
        """Fit an edge label inside both the physical band and its long-side span."""
        band_capacity = self.back_edge_band-self.M-float(self.back["frame_line_width_pt"])/2
        minimum = float(self.sizes["edge_label_min"])
        if band_capacity < minimum:
            raise RuntimeError(
                "The back edge band is too narrow for the minimum edge-label font size"
            )
        # Start at a deliberately generous maximum and back off only when the
        # physical band or the label's long edge requires it. The label therefore
        # grows with a wider band instead of staying at a legacy fixed size.
        size = min(float(self.sizes["edge_label_max"]), band_capacity)
        while size > minimum:
            ascent, descent = getAscentDescent(self.fonts["bold"], size)
            if ascent-descent <= band_capacity:
                break
            size -= .25
        ascent, descent = getAscentDescent(self.fonts["bold"], size)
        if ascent-descent > band_capacity:
            raise RuntimeError(
                "The back edge band is too narrow for the minimum edge-label font size"
            )
        return self._fit(edge,self.W-2*self.back_edge_band,size,minimum,"bold")

    def _back_edge_label_baseline(self, size: float) -> float:
        """Center the actual glyph bounds in the safe portion of the edge band."""
        ascent, descent = getAscentDescent(self.fonts["bold"], size)
        label_floor = self.M
        label_ceiling = self.back_edge_band-float(self.back["frame_line_width_pt"])/2
        return (label_floor+label_ceiling-ascent-descent)/2

    def _back_text_floor(self, card: MonsterCard, body_size: float | None = None) -> float:
        size = float(self.sizes["body"] if body_size is None else body_size)
        bottom_padding = (
            self._back_body_leading(size)
            *float(self.back["text_bottom_padding_line_percent"])/100
        )
        if not card.source_note:
            return self.back_edge_band+bottom_padding
        note_size = self.sizes["source_note"]
        note_leading = self._back_source_note_leading()
        lines = simpleSplit(
            card.source_note,self.fonts["regular"],note_size,self._back_source_note_width()
        )
        top_baseline = self.back_edge_band+bottom_padding+note_leading*(len(lines)-1)
        clearance = (
            self._back_body_leading(size)
            *float(self.back["source_note_clearance_line_percent"])/100
        )
        return top_baseline+clearance

    def _back_block_height(self, block: RuleBlock, size: float | None = None) -> float:
        size = float(self.sizes["body"] if size is None else size)
        leading = self._back_body_leading(size)
        if block.meta:
            lines = simpleSplit(block.text,self.fonts["regular"],size,self._back_text_width())
            return 27 + len(lines)*leading
        title_lines, _, lines, inline = self._back_inline_layout(block,size)
        if inline:
            return 5 + max(1, len(lines))*leading
        return 5 + (len(title_lines)+len(lines))*leading

    def _back_inline_layout(self, block: RuleBlock, size: float | None = None):
        """Wrap a back block, moving unusually long titles onto their own lines."""
        size = float(self.sizes["body"] if size is None else size)
        width = self._back_text_width()
        titlew = stringWidth(block.title,self.fonts["bold"],size)+4
        if titlew > width-20:
            title_lines = simpleSplit(block.title,self.fonts["bold"],size,width)
            body_lines = [(line, False) for line in simpleSplit(block.text,self.fonts["regular"],size,width)]
            return title_lines, 0, body_lines, False

        firstw = max(20,width-titlew)
        words = block.text.split(); lines=[]; cur=""; first_line=True
        while words:
            word=words.pop(0); test=(cur+" "+word).strip(); limit=firstw if first_line else width
            if stringWidth(test,self.fonts["regular"],size)<=limit:
                cur=test
            else:
                if cur:
                    lines.append((cur,first_line)); first_line=False; cur=word
                else:
                    lines.append((word,first_line)); first_line=False; cur=""
        if cur:
            lines.append((cur,first_line))
        return [block.title], titlew, lines, True

    def _back_size_for(self, card: MonsterCard) -> float:
        return getattr(self,"_back_body_sizes",{}).get(id(card),float(self.sizes["body"]))

    def _back_fit(self, card: MonsterCard, size: float):
        y = self._back_text_start(size)
        floor = self._back_text_floor(card,size)
        for block in card.overflow:
            next_y = y-self._back_block_height(block,size)
            if next_y < floor:
                return False,block,floor-next_y
            y = next_y
        return True,None,0.0

    @staticmethod
    def _fact_rule_block(fact: str) -> RuleBlock:
        if fact.startswith("Languages: "):
            return RuleBlock("Languages:",fact.removeprefix("Languages: "))
        if fact.startswith("Vuln. "):
            return RuleBlock("Vuln.:",fact.removeprefix("Vuln. "))
        if ": " in fact:
            title,text = fact.split(": ",1)
            return RuleBlock(f"{title}:",text)
        return RuleBlock("Special Fact:",fact)

    def _prepare_fact_flow(self, card: MonsterCard) -> None:
        """Promote overflowing quick facts into normal, labeled front rule blocks."""
        prepared = getattr(self,"_fact_flow_prepared",None)
        if prepared is None:
            self._fact_flow_prepared = set()
            prepared = self._fact_flow_prepared
        if id(card) in prepared:
            return

        facts = list(card.quick_facts)
        moved: list[str] = []
        width = self.W-2*self.M
        horizontal_padding = width*float(
            self.quick_facts["horizontal_padding_width_percent"]
        )/100
        max_width = width-2*horizontal_padding
        minimum_size = float(self.quick_facts["text_min_size_in"])*PT_PER_IN
        while facts:
            text = " · ".join(facts)
            if stringWidth(text,self.fonts["black"],minimum_size) <= max_width:
                break
            moved.insert(0,facts.pop())
        card.quick_facts = facts
        if moved:
            card.blocks = [self._fact_rule_block(fact) for fact in moved]+card.blocks
        prepared.add(id(card))

    @staticmethod
    def _continuation_title(title: str) -> str:
        base = title.rstrip(":")
        if base.endswith(" (cont.)"):
            return f"{base}:"
        return f"{base} (cont.):" if base else "(cont.):"

    def _split_block_to_fit(self, block: RuleBlock, max_height: float):
        """Return the largest readable prefix that fits and its continuation."""
        text = block.text.strip()
        if not text:
            return None

        # Prefer complete sentences. If none fit, back off through word boundaries.
        sentence_boundaries = [
            match.end() for match in re.finditer(r"[.!?](?:['\"])?\s+(?=[A-Z])", text)
        ]
        word_boundaries = [match.start() for match in re.finditer(r"\s+", text)]
        for boundaries in (sentence_boundaries, word_boundaries):
            for boundary in reversed(boundaries):
                prefix_text = text[:boundary].strip()
                remainder_text = text[boundary:].strip()
                if not remainder_text or len(prefix_text.split()) < 3:
                    continue
                prefix = RuleBlock(block.title, prefix_text, block.kind, block.meta)
                if self._block_height(prefix) <= max_height:
                    remainder = RuleBlock(
                        self._continuation_title(block.title), remainder_text, block.kind, block.meta
                    )
                    return prefix, remainder
        return None

    def _prepare_block_flow(self, card: MonsterCard):
        """Measure before drawing; split/move front overflow and fit the back safely."""
        self._prepare_fact_flow(card)
        y = self._front_block_top(card)
        front: list[RuleBlock] = []
        carried: list[RuleBlock] = []
        for index, block in enumerate(card.blocks):
            next_y = y-self._block_height(block)
            if next_y < 24:
                split = self._split_block_to_fit(block, y-24)
                if split:
                    prefix, remainder = split
                    front.append(prefix)
                    carried.append(remainder)
                    carried.extend(card.blocks[index+1:])
                else:
                    carried.extend(card.blocks[index:])
                break
            front.append(block)
            y = next_y

        card.blocks = front
        card.overflow = carried+card.overflow

        # The back uses the front body size first, then only whole one-point
        # reductions. This preserves readability and makes a size change predictable.
        size = float(self.sizes["body"])
        while size >= .5:
            fits,block,excess = self._back_fit(card,size)
            if fits:
                if not hasattr(self,"_back_body_sizes"):
                    self._back_body_sizes = {}
                self._back_body_sizes[id(card)] = size
                return
            size -= 1

        title = (block.title if block else "untitled block") or "untitled block"
        raise RuntimeError(
            f"Text overflow for {card.name!r}: {title!r} does not fit on the back "
            f"even at 0.5 pt ({excess:.1f} pt too tall)"
        )

    def _draw_front(self, card: MonsterCard):
        self._outer(); self._header(card); y=self._dashboard(card); y=self._facts(y,card.quick_facts); y-=7
        drew_block = False
        for block in card.blocks:
            y = self._block(y,block,divider=drew_block)
            drew_block = True

    @staticmethod
    def _back_divider_y(previous_baseline: float, next_baseline: float) -> float:
        """Center a divider in the whitespace between adjacent rule blocks."""
        return (previous_baseline+next_baseline)/2

    def _draw_back(self, card: MonsterCard):
        c = self.c; assert c
        body_size = self._back_size_for(card)
        body_leading = self._back_body_leading(body_size)
        body_padding = self._back_body_horizontal_padding()
        top=self.H-self.back_edge_band; bot=self.back_edge_band
        left=self.back_edge_band; right=self.W-self.back_edge_band
        c.setStrokeColor(self.GRID); c.setLineWidth(float(self.back["frame_line_width_pt"])); c.rect(left,bot,right-left,top-bot,stroke=1,fill=0)
        edge=f"{card.name.upper()} · CR {card.cr}"
        # Font ascenders extend above a baseline, so center the glyph metrics—not
        # the baseline itself—in the usable band between margin and inner frame.
        edge_size = self._back_edge_label_size(edge)
        edge_inset = self._back_edge_label_baseline(edge_size)
        c.setFillColor(self.GRAY); c.setFont(self.fonts["bold"],edge_size)
        c.drawCentredString(self.W/2,edge_inset,edge)
        c.saveState(); c.translate(self.W/2,self.H-edge_inset); c.rotate(180); c.drawCentredString(0,0,edge); c.restoreState()
        # Corrected from the first prototype: both long-side labels rotated 180°.
        c.saveState(); c.translate(edge_inset,self.H/2); c.rotate(-90); c.drawCentredString(0,0,edge); c.restoreState()
        c.saveState(); c.translate(self.W-edge_inset,self.H/2); c.rotate(90); c.drawCentredString(0,0,edge); c.restoreState()

        y=self._back_text_start(body_size)
        previous_baseline: float | None = None
        for block in card.overflow:
            first_baseline = y-8 if block.meta else y-4
            if previous_baseline is not None:
                divider_y = self._back_divider_y(previous_baseline,first_baseline)
                self._line(
                    left+body_padding,divider_y,right-body_padding,divider_y,
                    width=.45,color=self.DIVIDER,
                )
            if block.meta:
                c.setFillColor(self.DARK); c.setFont(self.fonts["bold"],body_size)
                c.drawString(left+body_padding,y-8,block.title)
                c.setFont(self.fonts["bold"],6.4); c.setFillColor(self.MID); c.drawRightString(right-body_padding,y-8,block.meta)
                yy=y-21; c.setFillColor(self.DARK); c.setFont(self.fonts["regular"],body_size)
                last_baseline = y-8
                for ln in simpleSplit(block.text,self.fonts["regular"],body_size,self._back_text_width()):
                    c.drawString(left+body_padding,yy,ln); last_baseline=yy; yy-=body_leading
                y=yy-6
            else:
                title_lines, titlew, lines, inline = self._back_inline_layout(block,body_size)
                yy=y-4; c.setFillColor(self.DARK)
                last_baseline = yy
                if inline:
                    c.setFont(self.fonts["bold"],body_size); c.drawString(left+body_padding,yy,block.title)
                    c.setFont(self.fonts["regular"],body_size)
                    for text, is_first in lines:
                        c.drawString(left+body_padding+titlew if is_first else left+body_padding,yy,text); last_baseline=yy; yy-=body_leading
                else:
                    c.setFont(self.fonts["bold"],body_size)
                    for title_line in title_lines:
                        c.drawString(left+body_padding,yy,title_line); last_baseline=yy; yy-=body_leading
                    c.setFont(self.fonts["regular"],body_size)
                    for text, _ in lines:
                        c.drawString(left+body_padding,yy,text); last_baseline=yy; yy-=body_leading
                y=yy-1
            previous_baseline = last_baseline
        if card.source_note:
            note_size = self.sizes["source_note"]
            note_leading = self._back_source_note_leading()
            c.setFillColor(self.GRAY); c.setFont(self.fonts["regular"],note_size)
            lines=simpleSplit(
                card.source_note,self.fonts["regular"],note_size,self._back_source_note_width()
            )
            bottom_padding = (
                self._back_body_leading(body_size)
                *float(self.back["text_bottom_padding_line_percent"])/100
            )
            yy=bot+bottom_padding+note_leading*(len(lines)-1)
            for ln in lines:
                c.drawCentredString(self.W/2,yy,ln); yy-=note_leading
