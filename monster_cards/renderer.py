from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Iterable

from reportlab.lib.colors import HexColor, white
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase.pdfmetrics import stringWidth
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

    def _header(self, card: MonsterCard):
        c = self.c; assert c
        hh = 53
        c.setFillColor(self.TEAL); c.rect(self.M, self.H-self.M-hh, self.W-2*self.M, hh, fill=1, stroke=0)
        name_size = self._fit(card.name, self.W-2*self.M-62, self.sizes["monster_name"], 11, "black")
        c.setFillColor(white); c.setFont(self.fonts["black"], name_size); c.drawString(self.M+6, self.H-self.M-24, card.name)
        c.setFont(self.fonts["bold"], self.sizes["subtype"]); c.drawString(self.M+6, self.H-self.M-42, card.subtitle)
        c.setFont(self.fonts["bold"], self.sizes["cr"]); c.drawRightString(self.W-self.M-6, self.H-self.M-19, f"CR {card.cr}")

    def _shield_ac(self, cx, top, value):
        c = self.c; assert c
        w, h = 46, 42; x, y = cx-w/2, top-h
        p = c.beginPath(); p.moveTo(x,y+h); p.lineTo(x+w,y+h); p.lineTo(x+w-7,y); p.lineTo(x+7,y); p.close()
        c.setStrokeColor(self.TEAL); c.setLineWidth(1); c.drawPath(p, stroke=1, fill=0)
        self._center("AC", cx, y+h-12, size=self.sizes["dashboard_label"])
        self._center(value, cx, y+8, font="black", size=self.sizes["dashboard_value"])

    def _box_hp(self, cx, top, value):
        c = self.c; assert c
        w, h = 43, 42; x, y = cx-w/2, top-h
        p = c.beginPath();
        p.moveTo(x+7,y+h); p.lineTo(x+w-7,y+h); p.lineTo(x+w-7,y+h-6); p.lineTo(x+w,y+h-6)
        p.lineTo(x+w,y+6); p.lineTo(x+w-7,y+6); p.lineTo(x+w-7,y); p.lineTo(x+7,y); p.lineTo(x+7,y+6)
        p.lineTo(x,y+6); p.lineTo(x,y+h-6); p.lineTo(x+7,y+h-6); p.close()
        c.setStrokeColor(self.TEAL); c.setLineWidth(1); c.drawPath(p, stroke=1, fill=0)
        self._center("HP", cx, y+h-12, size=self.sizes["dashboard_label"])
        self._center(value, cx, y+8, font="black", size=self.sizes["dashboard_value"])

    def _arrow_speed(self, cx, top, value):
        c = self.c; assert c
        w, h = 52, 42; x, y = cx-w/2, top-h
        p = c.beginPath(); p.moveTo(x,y); p.lineTo(x+39,y); p.lineTo(x+39,y+8); p.lineTo(x+w,y+h/2)
        p.lineTo(x+39,y+h-8); p.lineTo(x+39,y+h); p.lineTo(x,y+h); p.close()
        c.setStrokeColor(self.TEAL); c.setLineWidth(1); c.drawPath(p, stroke=1, fill=0)
        self._center("SPEED", x+23, y+h-12, size=7.5)
        self._center(value, x+23, y+8, font="black", size=self.sizes["dashboard_value"]-1)

    def _circle_pp(self, cx, top, value):
        c = self.c; assert c
        r = 21; y = top-r
        c.setStrokeColor(self.TEAL); c.setLineWidth(1); c.circle(cx,y,r,stroke=1,fill=0)
        self._line(cx-r,y+6,cx+r,y+6,width=.7,color=self.TEAL)
        self._center("PP",cx,y+10,size=7.5); self._center(value,cx,y-r+7,font="black",size=self.sizes["dashboard_value"]-1)

    def _dashboard(self, card: MonsterCard):
        top = self.H-self.M-58
        # AC and PP have matching frame insets; HP and Speed divide the span evenly.
        dashboard_inset = 26
        dashboard_span = self.W-2*self.M-2*dashboard_inset
        xs = [self.M+dashboard_inset+i*dashboard_span/3 for i in range(4)]
        self._shield_ac(xs[0],top,card.ac); self._box_hp(xs[1],top,card.hp); self._arrow_speed(xs[2],top,card.speed); self._circle_pp(xs[3],top,card.passive_perception)

        # Modifiers are deliberately large; raw scores are supporting information
        # beneath them. There are intentionally no "MODIFIERS" / "Raw Scores" labels.
        y1 = self.H-self.M-116
        ability_inset = 24
        ability_span = self.W-2*self.M-2*ability_inset
        ax = [self.M+ability_inset+i*ability_span/5 for i in range(6)]
        for x, abbr in zip(ax, ABILITIES):
            ability = card.abilities[abbr]
            self._center(abbr, x, y1, font="bold", size=self.sizes["ability_label"])
            self._center(signed(ability.modifier), x, y1-19, font="black", size=self.sizes["ability_modifier"])
            self._center(str(ability.score), x, y1-37, font="regular", size=self.sizes["ability_score"], color=self.MID)
        return y1-48

    def _facts(self, y, facts: list[str]):
        if not facts:
            return y
        text = " · ".join(facts)
        h = 23
        self._line(self.M,y,self.W-self.M,y,width=.8); self._line(self.M,y-h,self.W-self.M,y-h,width=.8)
        size = self._fit(text,self.W-2*self.M-10,self.sizes["quick_facts"],5.8,"black")
        self._center(text,self.W/2,y-15,font="black",size=size,color=self.MID)
        return y-h

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
        y = self.H-self.M-164
        if card.quick_facts:
            y -= 23
        return y-7

    def _back_text_floor(self, card: MonsterCard) -> float:
        bot = 27
        if not card.source_note:
            return bot+8
        lines = simpleSplit(card.source_note,self.fonts["regular"],4.7,(self.W-62)-20)
        top_baseline = bot+8+5.5*(len(lines)-1)
        return top_baseline+6

    def _back_block_height(self, block: RuleBlock, size: float | None = None) -> float:
        size = float(self.sizes["body"] if size is None else size)
        leading = size*1.34
        if block.meta:
            lines = simpleSplit(block.text,self.fonts["regular"],size,(self.W-62)-22)
            return 27 + len(lines)*leading
        title_lines, _, lines, inline = self._back_inline_layout(block,size)
        if inline:
            return 5 + max(1, len(lines))*leading
        return 5 + (len(title_lines)+len(lines))*leading

    def _back_inline_layout(self, block: RuleBlock, size: float | None = None):
        """Wrap a back block, moving unusually long titles onto their own lines."""
        size = float(self.sizes["body"] if size is None else size)
        width = (self.W-62)-22
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
        y = self.H-58
        floor = self._back_text_floor(card)
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
        max_width = self.W-2*self.M-10
        minimum_size = 5.8
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
        body_leading = body_size*1.34
        inset=31; top=self.H-27; bot=27; left=31; right=self.W-31
        c.setStrokeColor(self.GRID); c.setLineWidth(.8); c.rect(left,bot,right-left,top-bot,stroke=1,fill=0)
        edge=f"{card.name.upper()} · CR {card.cr}"
        edge_inset = float(self.layout["edge_label_inset_pt"])
        c.setFillColor(self.GRAY); c.setFont(self.fonts["bold"],self.sizes["edge_label"])
        c.drawCentredString(self.W/2,edge_inset,edge)
        c.saveState(); c.translate(self.W/2,self.H-edge_inset); c.rotate(180); c.drawCentredString(0,0,edge); c.restoreState()
        # Corrected from the first prototype: both long-side labels rotated 180°.
        c.saveState(); c.translate(edge_inset,self.H/2); c.rotate(-90); c.drawCentredString(0,0,edge); c.restoreState()
        c.saveState(); c.translate(self.W-edge_inset,self.H/2); c.rotate(90); c.drawCentredString(0,0,edge); c.restoreState()

        y=self.H-58
        previous_baseline: float | None = None
        for block in card.overflow:
            first_baseline = y-8 if block.meta else y-4
            if previous_baseline is not None:
                divider_y = self._back_divider_y(previous_baseline,first_baseline)
                self._line(left+10,divider_y,right-10,divider_y,width=.45,color=self.DIVIDER)
            if block.meta:
                c.setFillColor(self.DARK); c.setFont(self.fonts["bold"],body_size)
                c.drawString(left+11,y-8,block.title)
                c.setFont(self.fonts["bold"],6.4); c.setFillColor(self.MID); c.drawRightString(right-11,y-8,block.meta)
                yy=y-21; c.setFillColor(self.DARK); c.setFont(self.fonts["regular"],body_size)
                last_baseline = y-8
                for ln in simpleSplit(block.text,self.fonts["regular"],body_size,(right-left)-22):
                    c.drawString(left+11,yy,ln); last_baseline=yy; yy-=body_leading
                y=yy-6
            else:
                title_lines, titlew, lines, inline = self._back_inline_layout(block,body_size)
                yy=y-4; c.setFillColor(self.DARK)
                last_baseline = yy
                if inline:
                    c.setFont(self.fonts["bold"],body_size); c.drawString(left+11,yy,block.title)
                    c.setFont(self.fonts["regular"],body_size)
                    for text, is_first in lines:
                        c.drawString(left+11+titlew if is_first else left+11,yy,text); last_baseline=yy; yy-=body_leading
                else:
                    c.setFont(self.fonts["bold"],body_size)
                    for title_line in title_lines:
                        c.drawString(left+11,yy,title_line); last_baseline=yy; yy-=body_leading
                    c.setFont(self.fonts["regular"],body_size)
                    for text, _ in lines:
                        c.drawString(left+11,yy,text); last_baseline=yy; yy-=body_leading
                y=yy-1
            previous_baseline = last_baseline
        if card.source_note:
            c.setFillColor(self.GRAY); c.setFont(self.fonts["regular"],4.7)
            lines=simpleSplit(card.source_note,self.fonts["regular"],4.7,right-left-20)
            yy=bot+8+5.5*(len(lines)-1)
            for ln in lines:
                c.drawCentredString(self.W/2,yy,ln); yy-=5.5
