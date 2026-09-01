from types import SimpleNamespace
import unittest

from monster_cards.model import RuleBlock
from monster_cards.renderer import CardRenderer


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


if __name__ == "__main__":
    unittest.main()
