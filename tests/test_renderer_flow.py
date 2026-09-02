from types import SimpleNamespace
import unittest

from monster_cards.model import RuleBlock
from monster_cards.renderer import CardRenderer
from reportlab.pdfbase.pdfmetrics import stringWidth


def _measurement_renderer() -> CardRenderer:
    renderer = CardRenderer.__new__(CardRenderer)
    renderer.sizes = {"body": 8.5}
    renderer.fonts = {
        "regular": "Helvetica",
        "bold": "Helvetica-Bold",
        "black": "Helvetica-Bold",
    }
    renderer.W = 4.25 * 72
    renderer.H = 5.5 * 72
    renderer.M = 12
    return renderer


class RendererFlowTests(unittest.TestCase):
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
