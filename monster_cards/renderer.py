from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import getAscentDescent, getFont, stringWidth
from reportlab.pdfgen import canvas

from .fonts import register_noto
from .layout import PT_PER_IN, SheetLayout
from .model import ABILITIES, MonsterCard, RuleBlock
from .util import signed


@dataclass
class PreparedMinisheet:
    """A measured one-sided monster sheet and its selected physical size."""

    card: MonsterCard
    large: bool
    body_size: float
    column_split: int | None = None


class CardRenderer:
    """Render measured one-sided monster minisheets onto Letter pages.

    Coordinates use ReportLab points with (0, 0) at the lower-left of the
    logical portrait minisheet. Large sheets are rotated only during imposition.
    """

    # These are intrinsic properties of the four vector shapes. Their configured
    # height may change, but their width-to-height proportions never do.
    PRIMARY_STAT_REFERENCE_HEIGHT = 42
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
        self.NORMAL_W = self.sheet.card_width
        self.NORMAL_H = self.sheet.card_height
        self.LARGE_W = self.sheet.large_card_width
        self.LARGE_H = self.sheet.large_card_height
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
        self.colors = {
            name: self._parse_color(name,value)
            for name,value in self.style["colors"].items()
        }
        self.sizes = self.style["sizes"]
        self.body_size = float(self.sizes["body"])
        self.large_columns = self.layout["large_columns"]
        self.c: canvas.Canvas | None = None

    @staticmethod
    def _parse_color(name: str, value: object) -> Color | None:
        """Convert a configured #rrggbb color, with `none` meaning no ink."""
        if value == "none":
            return None
        if not isinstance(value,str) or re.fullmatch(r"#[0-9a-fA-F]{6}",value) is None:
            raise ValueError(f"colors.{name} must be #rrggbb or none")
        return HexColor(value)

    @staticmethod
    def _ordered_cards(cards: Iterable[MonsterCard]) -> list[MonsterCard]:
        """Return cards in stable, case-insensitive name order for PDF output."""
        return sorted(cards,key=lambda card: (card.name.casefold(),card.name))

    def render(self, cards: Iterable[MonsterCard], output: str | Path) -> Path:
        """Measure, size, pack, and render one-sided minisheets."""
        prepared = [self._prepare_minisheet(card) for card in self._ordered_cards(cards)]
        pages = self._pack_pages(prepared)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(output), pagesize=(self.PAGE_W, self.PAGE_H))
        self.c.setTitle("Monster Minisheets")
        for rows in pages:
            for index, row in enumerate(rows):
                self._draw_row(row, top=index == 0)
            top_is_normal = bool(rows and not rows[0][0].large)
            bottom_is_normal = bool(len(rows) > 1 and not rows[1][0].large)
            self._draw_trim_guides(
                top_is_normal=top_is_normal,
                bottom_is_normal=bottom_is_normal,
            )
            self.c.showPage()
        self.c.save()
        self.c = None
        return output

    @staticmethod
    def _pack_pages(
        minisheets: list[PreparedMinisheet],
    ) -> list[list[list[PreparedMinisheet]]]:
        """Fill normal rows with forward lookahead; large sheets own their rows.

        Cards arrive alphabetized. If a large sheet interrupts two normal
        sheets, the later normal sheet is pulled forward to avoid wasting the
        first normal row's second quadrant.
        """
        rows: list[list[PreparedMinisheet]] = []
        consumed: set[int] = set()
        for index,minisheet in enumerate(minisheets):
            if index in consumed:
                continue
            if minisheet.large:
                rows.append([minisheet])
                continue

            partner_index = next(
                (
                    candidate
                    for candidate in range(index+1,len(minisheets))
                    if candidate not in consumed and not minisheets[candidate].large
                ),
                None,
            )
            row = [minisheet]
            if partner_index is not None:
                row.append(minisheets[partner_index])
                consumed.add(partner_index)
            rows.append(row)
        return [rows[index:index + 2] for index in range(0, len(rows), 2)]

    def _use_size(self, *, large: bool) -> None:
        self.W = self.LARGE_W if large else self.NORMAL_W
        self.H = self.LARGE_H if large else self.NORMAL_H

    def _draw_row(self, row: list[PreparedMinisheet], top: bool) -> None:
        """Draw one full-width physical row with one large or up to two normals."""
        c = self.c; assert c
        y = self.sheet.row_origin_y(top)
        if row[0].large:
            self._use_size(large=True)
            # The logical 5.5 x 8.5 portrait sheet is rotated clockwise into an
            # 8.5 x 5.5 row. Its header therefore appears at the row's right edge.
            c.saveState()
            c.translate(0, y + self.sheet.row_height)
            c.rotate(-90)
            self._draw_minisheet(row[0])
            c.restoreState()
            return

        self._use_size(large=False)
        for column, minisheet in enumerate(row):
            c.saveState()
            c.translate(column * self.NORMAL_W, y)
            self._draw_minisheet(minisheet)
            c.restoreState()

    def _trim_guide_segments(
        self, *, top_is_normal: bool, bottom_is_normal: bool
    ) -> list[tuple[float,float,float,float]]:
        return self.sheet.trim_guide_segments(
            top_is_normal=top_is_normal,
            bottom_is_normal=bottom_is_normal,
        )

    def _draw_trim_guides(self, *, top_is_normal: bool, bottom_is_normal: bool) -> None:
        c = self.c; assert c
        c.saveState()
        color = self.colors["trim_guide"]
        if color is None:
            c.restoreState()
            return
        c.setStrokeColor(color)
        c.setLineWidth(float(self.layout["trim_guide_width_pt"]))
        for x1,y1,x2,y2 in self._trim_guide_segments(
            top_is_normal=top_is_normal,
            bottom_is_normal=bottom_is_normal,
        ):
            c.line(x1,y1,x2,y2)
        c.restoreState()

    def _line(self, x1, y1, x2, y2, width=.7, color=None):
        c = self.c; assert c
        if color is None:
            return
        c.setStrokeColor(color); c.setLineWidth(width); c.line(x1, y1, x2, y2)

    def _center(self, text, x, y, font="bold", size=8, color=None):
        c = self.c; assert c
        if color is None:
            return
        c.setFillColor(color); c.setFont(self.fonts[font], size); c.drawCentredString(x, y, str(text))

    def _fill_rect(self, x, y, width, height, color) -> None:
        c = self.c; assert c
        if color is None or width <= 0 or height <= 0:
            return
        c.setFillColor(color)
        c.rect(x,y,width,height,stroke=0,fill=1)

    def _fit(self, text, maxw, start, minsize, font="regular"):
        s = float(start)
        f = self.fonts[font]
        while s > minsize and stringWidth(str(text), f, s) > maxw:
            s -= .25
        return s

    def _outer(self):
        c = self.c; assert c
        color = self.colors["front_border"]
        if color is None:
            return
        c.setStrokeColor(color); c.setLineWidth(1); c.rect(self.M, self.M, self.W - 2*self.M, self.H - 2*self.M, stroke=1, fill=0)

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
        self._fill_rect(
            self.M,self.H-self.M-self.front_header_height,
            self.W-2*self.M,self.front_header_height,
            self.colors["header_band_background"],
        )
        text_color = self.colors["header_band_text"]
        if text_color is None:
            return
        c.setFillColor(text_color)
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
            size=text["label_size"],color=self.colors["icon_text"],
        )
        self._center(
            value,text["center"],text["value_baseline"],font="black",
            size=text["value_size"],color=self.colors["icon_text"],
        )

    def _draw_icon_path(self, path) -> None:
        c = self.c; assert c
        border = self.colors["icon_border"]
        background = self.colors["icon_background"]
        if border is not None:
            c.setStrokeColor(border)
            c.setLineWidth(float(self.primary_stats["line_width_in"])*PT_PER_IN)
        if background is not None:
            c.setFillColor(background)
        c.drawPath(path,stroke=border is not None,fill=background is not None)

    def _shield_ac(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; w = self._primary_stat_width("ac")
        scale = h/self.PRIMARY_STAT_REFERENCE_HEIGHT; x, y = cx-w/2, top-h
        p = c.beginPath(); p.moveTo(x,y+h); p.lineTo(x+w,y+h)
        p.lineTo(x+w-7*scale,y); p.lineTo(x+7*scale,y); p.close()
        self._draw_icon_path(p)
        self._draw_primary_stat_text("ac","AC",value,cx,top)

    def _box_hp(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; w = self._primary_stat_width("hp")
        scale = h/self.PRIMARY_STAT_REFERENCE_HEIGHT; x, y = cx-w/2, top-h
        p = c.beginPath();
        p.moveTo(x+7*scale,y+h); p.lineTo(x+w-7*scale,y+h); p.lineTo(x+w-7*scale,y+h-6*scale); p.lineTo(x+w,y+h-6*scale)
        p.lineTo(x+w,y+6*scale); p.lineTo(x+w-7*scale,y+6*scale); p.lineTo(x+w-7*scale,y); p.lineTo(x+7*scale,y); p.lineTo(x+7*scale,y+6*scale)
        p.lineTo(x,y+6*scale); p.lineTo(x,y+h-6*scale); p.lineTo(x+7*scale,y+h-6*scale); p.close()
        self._draw_icon_path(p)
        self._draw_primary_stat_text("hp","HP",value,cx,top)

    def _arrow_speed(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; w = self._primary_stat_width("speed")
        scale = h/self.PRIMARY_STAT_REFERENCE_HEIGHT; x, y = cx-w/2, top-h
        p = c.beginPath(); p.moveTo(x,y); p.lineTo(x+39*scale,y); p.lineTo(x+39*scale,y+8*scale); p.lineTo(x+w,y+h/2)
        p.lineTo(x+39*scale,y+h-8*scale); p.lineTo(x+39*scale,y+h); p.lineTo(x,y+h); p.close()
        self._draw_icon_path(p)
        self._draw_primary_stat_text("speed","SPEED",value,cx,top)

    def _circle_pp(self, cx, top, value):
        c = self.c; assert c
        h = self.primary_stat_height; r = h/2; y = top-r
        text = self._primary_stat_text_layout("pp","PP",str(value),cx,top)
        border = self.colors["icon_border"]
        background = self.colors["icon_background"]
        if border is not None:
            c.setStrokeColor(border)
            c.setLineWidth(float(self.primary_stats["line_width_in"])*PT_PER_IN)
        if background is not None:
            c.setFillColor(background)
        c.circle(cx,y,r,stroke=border is not None,fill=background is not None)
        self._line(
            cx-r,text["boundary"],cx+r,text["boundary"],
            width=float(self.primary_stats["divider_line_width_in"])*PT_PER_IN,
            color=self.colors["icon_border"],
        )
        self._draw_primary_stat_text("pp","PP",value,cx,top)

    def _dashboard(self, card: MonsterCard):
        top = self._dashboard_top()
        header_bottom = self.H-self.M-self.front_header_height
        ability_top = top-self.primary_stat_height
        self._fill_rect(
            self.M,ability_top,self.W-2*self.M,header_bottom-ability_top,
            self.colors["primary_stats_background"],
        )
        self._fill_rect(
            self.M,ability_top-self.ability_band_height,
            self.W-2*self.M,self.ability_band_height,
            self.colors["ability_band_background"],
        )
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
            abbr,center,layout["label_baseline"],font="bold",size=layout["label_size"],
            color=self.colors["ability_label_text"],
        )
        self._center(
            signed(ability.modifier),center,layout["modifier_baseline"],
            font="black",size=layout["modifier_size"],
            color=self.colors["ability_modifier_text"],
        )
        self._center(
            str(ability.score),center,layout["score_baseline"],font="regular",
            size=layout["score_size"],color=self.colors["ability_score_text"],
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
        self._fill_rect(
            self.M,y-height,width,height,self.colors["quick_facts_background"]
        )
        line_width = float(self.quick_facts["line_width_in"])*PT_PER_IN
        border = self.colors["quick_facts_border"]
        self._line(self.M,y,self.W-self.M,y,width=line_width,color=border)
        self._line(self.M,y-height,self.W-self.M,y-height,width=line_width,color=border)
        baseline = self._baseline_for_row(self.fonts["black"],size,y-height,y)
        self._center(
            text,self.W/2,baseline,font="black",size=size,
            color=self.colors["quick_facts_text"],
        )
        return y-height

    def _block_layout(self, block: RuleBlock, width: float | None = None):
        """Wrap a front rule block, reserving first-line space for its bold title."""
        size = self.body_size
        if width is None:
            width = self.W-2*self.M-14
        titlew = stringWidth(block.title,self.fonts["bold"],size)+4
        if titlew > width-20:
            title_lines = simpleSplit(block.title,self.fonts["bold"],size,width)
            body_lines = simpleSplit(block.text,self.fonts["regular"],size,width)
            self._require_lines_fit(title_lines,"bold",size,width,block.title)
            self._require_lines_fit(body_lines,"regular",size,width,block.title)
            return title_lines,0,[(line,False) for line in body_lines],False
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
                    if stringWidth(word,self.fonts["regular"],size) > width:
                        raise RuntimeError(
                            f"Rule text in {block.title!r} has a word wider than its column"
                        )
                    first_line=False; cur=word
        if cur: lines.append((cur,first_line))
        return [block.title],titlew,lines,True

    def _require_lines_fit(
        self, lines: list[str], font: str, size: float, width: float, context: str
    ) -> None:
        if any(stringWidth(line,self.fonts[font],size) > width for line in lines):
            raise RuntimeError(f"Text in {context!r} is wider than its column")

    def _block_height(self, block: RuleBlock, width: float | None = None) -> float:
        if width is None:
            width = self.W-2*self.M-14
        if block.meta:
            size = self.body_size
            title_lines = simpleSplit(block.title,self.fonts["bold"],size,width)
            meta_lines = simpleSplit(block.meta,self.fonts["bold"],size,width)
            body_lines = simpleSplit(block.text,self.fonts["regular"],size,width)
            self._require_lines_fit(title_lines,"bold",size,width,block.title)
            self._require_lines_fit(meta_lines,"bold",size,width,block.meta)
            self._require_lines_fit(body_lines,"regular",size,width,block.title)
            return 12 + (len(title_lines)+len(meta_lines)+len(body_lines))*size*1.34
        title_lines,_,lines,inline = self._block_layout(block,width)
        line_count = max(1,len(lines)) if inline else len(title_lines)+len(lines)
        return 12 + line_count * self.body_size * 1.34

    def _block(
        self, y: float, block: RuleBlock, divider=True,
        left: float | None = None, right: float | None = None,
    ) -> float:
        c = self.c; assert c
        size = self.body_size
        x = self.M+7 if left is None else left
        right = self.W-self.M-7 if right is None else right
        if divider:
            self._line(
                x,y+4,right,y+4,width=.45,
                color=self.colors["rule_block_divider"],
            )
        title_color = self.colors["rule_block_title_text"]
        body_color = self.colors["rule_block_body_text"]
        if block.meta:
            width = right-x
            leading = size*1.34
            yy = y-8
            for text in simpleSplit(block.title,self.fonts["bold"],size,width):
                if title_color is not None:
                    c.setFillColor(title_color); c.setFont(self.fonts["bold"],size)
                    c.drawString(x,yy,text)
                yy -= leading
            for text in simpleSplit(block.meta,self.fonts["bold"],size,width):
                if title_color is not None:
                    c.setFillColor(title_color); c.setFont(self.fonts["bold"],size)
                    c.drawString(x,yy,text)
                yy -= leading
            for text in simpleSplit(block.text,self.fonts["regular"],size,width):
                if body_color is not None:
                    c.setFillColor(body_color); c.setFont(self.fonts["regular"],size)
                    c.drawString(x,yy,text)
                yy -= leading
            return yy-4
        title_lines,titlew,lines,inline = self._block_layout(block,right-x)
        yy=y-8
        if inline:
            if title_color is not None:
                c.setFillColor(title_color); c.setFont(self.fonts["bold"],size)
                c.drawString(x,yy,block.title)
            for text,is_first in lines:
                if body_color is not None:
                    c.setFillColor(body_color); c.setFont(self.fonts["regular"],size)
                    c.drawString(x+titlew if is_first else x,yy,text)
                yy-=size*1.34
        else:
            for text in title_lines:
                if title_color is not None:
                    c.setFillColor(title_color); c.setFont(self.fonts["bold"],size)
                    c.drawString(x,yy,text)
                yy-=size*1.34
            for text,_ in lines:
                if body_color is not None:
                    c.setFillColor(body_color); c.setFont(self.fonts["regular"],size)
                    c.drawString(x,yy,text)
                yy-=size*1.34
        return yy-4

    def _front_block_top(self, card: MonsterCard) -> float:
        y = self._dashboard_bottom()
        if card.quick_facts:
            y -= self.quick_facts_band_height
        return y-7

    def _source_note_layout(self, card: MonsterCard) -> tuple[list[str], float]:
        """Return source-note lines and their baseline spacing on one face."""
        if not card.source_note:
            return [],0.0
        size = float(self.sizes["source_note"])
        width = self.W-2*self.M-14
        return simpleSplit(card.source_note,self.fonts["regular"],size,width),size*1.17

    def _content_floor(self, card: MonsterCard) -> float:
        lines,leading = self._source_note_layout(card)
        if not lines:
            return self.M
        return self.M+4+len(lines)*leading

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

    def _column_bounds(self) -> tuple[tuple[float,float],tuple[float,float]]:
        gutter = float(self.large_columns["gutter_in"])*PT_PER_IN
        center = self.W/2
        return (
            (self.M+7,center-gutter/2),
            (center+gutter/2,self.W-self.M-7),
        )

    def _prepare_for_current_size(
        self, card: MonsterCard, *, columns: int = 1
    ) -> tuple[bool, float, int | None]:
        """Measure a complete one-sided sheet at the currently selected size."""
        # Older inputs may explicitly place operational details in `overflow`.
        # On a one-sided minisheet they follow the ordinary blocks in full.
        card.blocks = list(card.blocks)+list(card.overflow)
        card.overflow = []
        self._prepare_fact_flow(card)
        self._front_header_layout(card)
        y = self._front_block_top(card)
        floor = self._content_floor(card)
        if columns == 1 or len(card.blocks) < 2:
            for block in card.blocks:
                y -= self._block_height(block)
            return y >= floor,max(0.0,floor-y),None

        bounds = self._column_bounds()
        widths = [right-left for left,right in bounds]
        heights = [
            [self._block_height(block,width) for block in card.blocks]
            for width in widths
        ]
        available = y-floor
        candidates = []
        for split in range(1,len(card.blocks)):
            left_height = sum(heights[0][:split])
            right_height = sum(heights[1][split:])
            candidates.append((max(left_height,right_height),split,left_height,right_height))
        used,split,left_height,right_height = min(candidates)
        return used <= available,max(0.0,used-available),split

    def _prepare_minisheet(self, source: MonsterCard) -> PreparedMinisheet:
        """Choose normal unless complete measured content requires large."""
        errors: list[str] = []
        preferred = float(self.sizes["body"])
        minimum = float(self.large_columns["body_min_size_pt"])
        attempts = [(False,preferred,1)]
        size = preferred
        while size >= minimum:
            attempts.extend(((True,size,1),(True,size,2)))
            size -= 1
        for large,body_size,columns in attempts:
            self._use_size(large=large)
            self.body_size = body_size
            card = deepcopy(source)
            try:
                fits,excess,split = self._prepare_for_current_size(card,columns=columns)
            except RuntimeError as exc:
                errors.append(str(exc))
                continue
            if fits:
                return PreparedMinisheet(
                    card=card,large=large,body_size=body_size,
                    column_split=split if columns == 2 else None,
                )
            errors.append(f"content is {excess:.1f} pt too tall")
        detail = errors[-1] if errors else "content does not fit"
        raise RuntimeError(
            f"Text overflow for {source.name!r}: {detail} on a 5.5 x 8.5 inch minisheet"
        )

    def _draw_source_note(self, card: MonsterCard) -> None:
        c = self.c; assert c
        lines,leading = self._source_note_layout(card)
        if not lines:
            return
        size = float(self.sizes["source_note"])
        color = self.colors["source_note_text"]
        if color is None:
            return
        c.setFillColor(color); c.setFont(self.fonts["regular"],size)
        yy = self.M+4+(len(lines)-1)*leading
        for line in lines:
            c.drawCentredString(self.W/2,yy,line)
            yy -= leading

    def _draw_minisheet(self, minisheet: PreparedMinisheet):
        card = minisheet.card
        self.body_size = minisheet.body_size
        self._fill_rect(
            self.M,self.M,self.W-2*self.M,self.H-2*self.M,
            self.colors["front_background"],
        )
        self._header(card); y=self._dashboard(card)
        rule_blocks_top = y-self.quick_facts_band_height if card.quick_facts else y
        self._fill_rect(
            self.M,self.M,self.W-2*self.M,rule_blocks_top-self.M,
            self.colors["rule_blocks_background"],
        )
        y=self._facts(y,card.quick_facts)-7
        if minisheet.column_split is None:
            for index,block in enumerate(card.blocks):
                y = self._block(y,block,divider=index > 0)
        else:
            bounds = self._column_bounds()
            groups = (
                card.blocks[:minisheet.column_split],
                card.blocks[minisheet.column_split:],
            )
            for (left,right),blocks in zip(bounds,groups):
                yy = y
                for index,block in enumerate(blocks):
                    yy = self._block(
                        yy,block,divider=index > 0,left=left,right=right,
                    )
        self._draw_source_note(card)
        self._outer()
