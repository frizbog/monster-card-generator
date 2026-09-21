"""Physical Letter-sheet and minisheet geometry shared by PDF rendering code."""

from __future__ import annotations

from dataclasses import dataclass


# ReportLab measures all drawing positions in PostScript points, not inches.
# Keeping this conversion in one place prevents subtle physical-size errors.
PT_PER_IN = 72.0


@dataclass(frozen=True)
class SheetLayout:
    """Configured dimensions for a Letter sheet and both minisheet sizes.

    Normal minisheets occupy one quadrant. Large minisheets are authored in
    portrait orientation, then rotated into one complete half-sheet row.
    """

    page_width: float
    page_height: float
    card_width: float
    card_height: float
    large_card_width: float
    large_card_height: float
    artwork_inset: float

    @classmethod
    def from_style(cls, style: dict) -> "SheetLayout":
        """Read user-facing inches/points from the JSON style configuration."""
        layout = cls(
            page_width=float(style["page_width_in"]) * PT_PER_IN,
            page_height=float(style["page_height_in"]) * PT_PER_IN,
            card_width=float(style["card_width_in"]) * PT_PER_IN,
            card_height=float(style["card_height_in"]) * PT_PER_IN,
            large_card_width=float(style["large_card_width_in"]) * PT_PER_IN,
            large_card_height=float(style["large_card_height_in"]) * PT_PER_IN,
            artwork_inset=float(style["margin_pt"]),
        )
        layout.validate_imposition()
        return layout

    @property
    def row_height(self) -> float:
        return self.page_height / 2

    def validate_imposition(self) -> None:
        """Require dimensions that tile the page using the documented 2x2 grid."""
        tolerance = 0.01
        relationships = (
            (2 * self.card_width, self.page_width, "two normal minisheet widths"),
            (2 * self.card_height, self.page_height, "two normal minisheet heights"),
            (self.large_card_width, self.row_height, "rotated large minisheet width"),
            (self.large_card_height, self.page_width, "rotated large minisheet height"),
        )
        for actual, expected, label in relationships:
            if abs(actual - expected) > tolerance:
                raise ValueError(
                    f"{label} must exactly span its Letter-sheet region "
                    f"({actual / PT_PER_IN:g} in != {expected / PT_PER_IN:g} in)"
                )

    def row_origin_y(self, top: bool) -> float:
        return self.row_height if top else 0.0

    def trim_guide_segments(
        self, *, top_is_normal: bool, bottom_is_normal: bool
    ) -> list[tuple[float, float, float, float]]:
        """Return the center-row cut and only the applicable quadrant cuts."""
        segments = [(0.0, self.row_height, self.page_width, self.row_height)]
        center_x = self.page_width / 2
        if top_is_normal:
            segments.append((center_x, self.row_height, center_x, self.page_height))
        if bottom_is_normal:
            segments.append((center_x, 0.0, center_x, self.row_height))
        return segments
