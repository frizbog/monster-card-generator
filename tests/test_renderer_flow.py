from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from monster_cards.io import load_manual_cards
from monster_cards.layout import SheetLayout
from monster_cards.model import RuleBlock
from monster_cards.renderer import CardRenderer
from reportlab.pdfbase.pdfmetrics import getAscentDescent, stringWidth


def _measurement_renderer() -> CardRenderer:
    renderer = CardRenderer.__new__(CardRenderer)
    renderer.sizes = {"body": 8.5, "source_note": 4.7, "edge_label_max": 24, "edge_label_min": 5}
    renderer.fonts = {
        "regular": "Helvetica",
        "bold": "Helvetica-Bold",
        "black": "Helvetica-Bold",
    }
    renderer.PAGE_W = 8.5 * 72
    renderer.PAGE_H = 11 * 72
    renderer.W = 4.0625 * 72
    renderer.H = 5.3125 * 72
    renderer.M = 18
    renderer.layout = {
        "back_edge_band_in": 0.375,
        "back_frame_line_width_pt": 0.8,
        "back_text_top_padding_em": 1.0,
        "back_text_bottom_padding_pt": 8,
        "back_source_note_clearance_pt": 6,
        "back_source_note_leading_pt": 5.5,
    }
    renderer.back_edge_band = 27
    renderer.sheet = SheetLayout(
        page_width=renderer.PAGE_W,
        page_height=renderer.PAGE_H,
        card_width=renderer.W,
        card_height=renderer.H,
        artwork_inset=renderer.M,
    )
    return renderer


class RendererFlowTests(unittest.TestCase):
    def test_back_edge_band_controls_the_inset_frame_width(self):
        renderer = _measurement_renderer()
        self.assertEqual(renderer._back_text_width(), renderer.W - 2*27 - 22)
        self.assertEqual(renderer._back_text_start(8.5), renderer.H - 27 - 8.5)
        size = renderer._back_edge_label_size("EDGE")
        ascent, descent = getAscentDescent(renderer.fonts["bold"], size)
        self.assertLessEqual(
            ascent-descent,
            renderer.back_edge_band-renderer.M-renderer.layout["back_frame_line_width_pt"]/2,
        )
        renderer.back_edge_band = 54
        self.assertGreater(renderer._back_edge_label_size("EDGE"), size)

    def test_back_divider_is_midway_between_adjacent_block_text(self):
        self.assertEqual(CardRenderer._back_divider_y(120,96),108)

    def test_renderer_emits_one_letter_page_per_pair_of_spreads(self):
        root = Path(__file__).resolve().parents[1]
        cards = load_manual_cards(root / "examples" / "manual_monsters.json")
        cards.append(deepcopy(cards[0]))

        with TemporaryDirectory() as directory:
            output = Path(directory) / "cards.pdf"
            CardRenderer(root / "config" / "card_style.json").render(cards,output)
            pdf = output.read_bytes()

        self.assertIn(b"/MediaBox [ 0 0 612 792 ]",pdf)
        self.assertEqual(pdf.count(b"/Type /Page\n"),2)

    def test_letter_sheet_spreads_and_trim_guides_use_physical_edges(self):
        renderer = _measurement_renderer()

        self.assertEqual(renderer._spread_origin(top=True),(0.0,5.6875*72))
        self.assertEqual(renderer._spread_origin(top=False),(0.0,0.0))
        self.assertEqual(renderer._trim_guide_segments(),[
            (8.125*72,0.0,8.125*72,11*72),
            (0.0,5.3125*72,8.5*72,5.3125*72),
            (0.0,5.6875*72,8.5*72,5.6875*72),
        ])
        self.assertEqual(renderer._discard_regions(),[
            (8.125*72,0.0,.375*72,11*72),
            (0.0,5.3125*72,8.125*72,.375*72),
        ])

    def test_middle_bar_overflow_becomes_labeled_blocks_before_traits(self):
        renderer = _measurement_renderer()
        card = SimpleNamespace(
            quick_facts=[
                "Stealth +3", "Cond Immune: blinded, deafened", "Vuln. fire",
                "Senses: blindsight 60 ft. (blind beyond this radius)",
                "Languages: understands Common but can’t speak",
            ],
            blocks=[RuleBlock("False Appearance:","The blight resembles a dead shrub.")],
        )

        renderer._prepare_fact_flow(card)

        self.assertIn("Vuln. fire"," · ".join(card.quick_facts))
        self.assertEqual([block.title for block in card.blocks[-3:]],[
            "Senses:","Languages:","False Appearance:",
        ])
        self.assertLessEqual(
            stringWidth(" · ".join(card.quick_facts),renderer.fonts["black"],5.8),
            renderer.W-2*renderer.M-10,
        )

    def test_large_block_splits_at_a_sentence_before_drawing(self):
        text = " ".join(
            f"Sentence {number} provides enough explanatory words to exercise semantic overflow handling."
            for number in range(1, 13)
        )
        card = SimpleNamespace(
            name="Flow Test",
            quick_facts=["Init +2"],
            blocks=[RuleBlock("Long Feature:", text)],
            overflow=[],
            source_note=None,
        )

        _measurement_renderer()._prepare_block_flow(card)

        self.assertEqual(len(card.blocks), 1)
        self.assertEqual(len(card.overflow), 1)
        self.assertEqual(card.overflow[0].title, "Long Feature (cont.):")
        self.assertTrue(card.blocks[0].text.endswith("."))
        self.assertEqual(f"{card.blocks[0].text} {card.overflow[0].text}", text)

    def test_long_back_title_wraps_before_explanatory_text(self):
        renderer = _measurement_renderer()
        block = RuleBlock(
            "Bonus Action - Trampling Charge (Recharge 5–6) (cont.):",
            "Each creature whose space the centaur enters must make a saving throw.",
        )

        title_lines, title_width, body_lines, inline = renderer._back_inline_layout(block)
        available_width = (renderer.W-62)-22
        body_size = renderer.sizes["body"]

        self.assertFalse(inline)
        self.assertEqual(title_width, 0)
        self.assertGreater(len(title_lines), 1)
        self.assertTrue(all(
            stringWidth(line,renderer.fonts["bold"],body_size) <= available_width
            for line in title_lines
        ))
        self.assertTrue(all(
            stringWidth(line,renderer.fonts["regular"],body_size) <= available_width
            for line, _ in body_lines
        ))

    def test_back_font_decreases_in_one_point_steps_until_all_text_fits(self):
        renderer = _measurement_renderer()
        card = SimpleNamespace(
            name="Adaptive Back Test",
            quick_facts=[],
            blocks=[],
            overflow=[RuleBlock("Feature:", "word "*275)],
            source_note=None,
        )

        self.assertFalse(renderer._back_fit(card,8.5)[0])
        self.assertTrue(renderer._back_fit(card,7.5)[0])

        renderer._prepare_block_flow(card)

        self.assertEqual(renderer._back_size_for(card),7.5)


if __name__ == "__main__":
    unittest.main()
