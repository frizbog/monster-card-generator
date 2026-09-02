"""Physical sheet and folded-card geometry shared by PDF rendering code."""

from __future__ import annotations

from dataclasses import dataclass


# ReportLab measures all drawing positions in PostScript points, not inches.
# Keeping this conversion in one place prevents subtle physical-size errors.
PT_PER_IN = 72.0


@dataclass(frozen=True)
class SheetLayout:
    """Configured dimensions for one printed sheet and one card panel.

    All values stored here are points. A spread is two card panels wide: front
    on the left and back on the right. The renderer uses this model rather than
    repeating physical Letter-sheet arithmetic in drawing methods.
    """

    page_width: float
    page_height: float
    card_width: float
    card_height: float
    artwork_inset: float

    @classmethod
    def from_style(cls, style: dict) -> "SheetLayout":
        """Read user-facing inches/points from the JSON style configuration."""
        return cls(
            page_width=float(style["page_width_in"]) * PT_PER_IN,
            page_height=float(style["page_height_in"]) * PT_PER_IN,
            card_width=float(style["card_width_in"]) * PT_PER_IN,
            card_height=float(style["card_height_in"]) * PT_PER_IN,
            artwork_inset=float(style["margin_pt"]),
        )

    @property
    def spread_width(self) -> float:
        return 2 * self.card_width

    def spread_origin(self, top: bool) -> tuple[float, float]:
        """Return the lower-left origin of the top or bottom spread on a sheet."""
        return (0.0, self.page_height - self.card_height) if top else (0.0, 0.0)

    def trim_guide_segments(self) -> list[tuple[float, float, float, float]]:
        """Return the three visible cut guides, never the initial fold line."""
        return [
            (self.spread_width, 0.0, self.spread_width, self.page_height),
            (0.0, self.card_height, self.page_width, self.card_height),
            (0.0, self.page_height - self.card_height, self.page_width, self.page_height - self.card_height),
        ]

    def discard_regions(self) -> list[tuple[float, float, float, float]]:
        """Return the right and center paper regions removed during trimming."""
        return [
            (self.spread_width, 0.0, self.page_width - self.spread_width, self.page_height),
            (0.0, self.card_height, self.spread_width, self.page_height - 2 * self.card_height),
        ]
