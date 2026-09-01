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
from .model import ABILITIES, MonsterCard, RuleBlock
from .util import signed

PT_PER_IN = 72.0


class CardRenderer:
    def __init__(self, style_path: str | Path):
        self.style = json.loads(Path(style_path).read_text(encoding="utf-8"))
        self.fonts = register_noto()
        self.W = self.style["page_width_in"] * PT_PER_IN
        self.H = self.style["page_height_in"] * PT_PER_IN
        self.M = float(self.style.get("margin_pt", 12))
        colors = self.style["colors"]
        self.TEAL = HexColor(colors["teal"])
        self.DARK = HexColor(colors["dark"])
        self.MID = HexColor(colors["mid"])
        self.GRID = HexColor(colors["grid"])
        self.GRAY = HexColor(colors["gray"])
        self.DIVIDER = HexColor(colors["divider"])
        self.sizes = self.style["sizes"]
        self.c: canvas.Canvas | None = None

    def render(self, cards: Iterable[MonsterCard], output: str | Path) -> Path:
        cards = list(cards)
        for card in cards:
            self._prepare_block_flow(card)
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        self.c = canvas.Canvas(str(output), pagesize=(self.W, self.H))
        self.c.setTitle("Monster Cards")
        for card in cards:
            self._draw_front(card)
            self.c.showPage()
            self._draw_back(card)
            self.c.showPage()
        self.c.save()
        self.c = None
        return output

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
        xs = [43, 116.333, 189.667, 263]
        self._shield_ac(xs[0],top,card.ac); self._box_hp(xs[1],top,card.hp); self._arrow_speed(xs[2],top,card.speed); self._circle_pp(xs[3],top,card.passive_perception)

        # v0.3: no MODIFIERS / Raw Scores labels. Modifiers are deliberately large;
        # raw scores are supporting information beneath them.
        y1 = self.H-self.M-116
        ax = [42,86,130,174,218,262]
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

    def _back_block_height(self, block: RuleBlock) -> float:
        if block.meta:
            lines = simpleSplit(block.text,self.fonts["regular"],6.7,(self.W-62)-22)
            return 27 + len(lines)*8.8
        _, lines = self._back_inline_layout(block)
        return 5 + len(lines)*8.8

    def _back_inline_layout(self, block: RuleBlock):
        size = 6.7
        width = (self.W-62)-22
        titlew = stringWidth(block.title,self.fonts["black"],8.3)+4
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
        return titlew, lines

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
        """Measure blocks before drawing and move front overflow to the back."""
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

        y = self.H-58
        floor = self._back_text_floor(card)
        for block in card.overflow:
            next_y = y-self._back_block_height(block)
            if next_y < floor:
                title = block.title or "untitled block"
                raise RuntimeError(
                    f"Text overflow for {card.name!r}: {title!r} does not fit on the back "
                    f"({floor-next_y:.1f} pt too tall)"
                )
            y = next_y

    def _draw_front(self, card: MonsterCard):
        self._outer(); self._header(card); y=self._dashboard(card); y=self._facts(y,card.quick_facts); y-=7
        drew_block = False
        for block in card.blocks:
            y = self._block(y,block,divider=drew_block)
            drew_block = True

    def _draw_back(self, card: MonsterCard):
        c = self.c; assert c
        inset=31; top=self.H-27; bot=27; left=31; right=self.W-31
        c.setStrokeColor(self.GRID); c.setLineWidth(.8); c.rect(left,bot,right-left,top-bot,stroke=1,fill=0)
        edge=f"{card.name.upper()} · CR {card.cr}"
        c.setFillColor(self.GRAY); c.setFont(self.fonts["bold"],self.sizes["edge_label"])
        c.drawCentredString(self.W/2,11,edge)
        c.saveState(); c.translate(self.W/2,self.H-11); c.rotate(180); c.drawCentredString(0,0,edge); c.restoreState()
        # Corrected from the first prototype: both long-side labels rotated 180°.
        c.saveState(); c.translate(11,self.H/2); c.rotate(-90); c.drawCentredString(0,0,edge); c.restoreState()
        c.saveState(); c.translate(self.W-11,self.H/2); c.rotate(90); c.drawCentredString(0,0,edge); c.restoreState()

        y=self.H-58
        for index, block in enumerate(card.overflow):
            if index:
                self._line(left+10,y+2,right-10,y+2,width=.45,color=self.DIVIDER)
            title_y = y-8 if block.meta else y-4
            c.setFillColor(self.DARK); c.setFont(self.fonts["black"],8.3); c.drawString(left+11,title_y,block.title)
            if block.meta:
                c.setFont(self.fonts["bold"],6.4); c.setFillColor(self.MID); c.drawRightString(right-11,y-8,block.meta)
                yy=y-21; c.setFillColor(self.DARK); c.setFont(self.fonts["regular"],6.7)
                for ln in simpleSplit(block.text,self.fonts["regular"],6.7,(right-left)-22):
                    c.drawString(left+11,yy,ln); yy-=8.8
                y=yy-6
            else:
                titlew, lines = self._back_inline_layout(block)
                yy=y-4; c.setFillColor(self.DARK); c.setFont(self.fonts["regular"],6.7)
                for text, is_first in lines:
                    c.drawString(left+11+titlew if is_first else left+11,yy,text); yy-=8.8
                y=yy-1
        if card.source_note:
            c.setFillColor(self.GRAY); c.setFont(self.fonts["regular"],4.7)
            lines=simpleSplit(card.source_note,self.fonts["regular"],4.7,right-left-20)
            yy=bot+8+5.5*(len(lines)-1)
            for ln in lines:
                c.drawCentredString(self.W/2,yy,ln); yy-=5.5
