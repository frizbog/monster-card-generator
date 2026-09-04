from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest

from monster_cards.io import load_manual_cards
from monster_cards.layout import SheetLayout
from monster_cards.model import RuleBlock
from monster_cards.renderer import CardRenderer
from reportlab.pdfbase.pdfmetrics import getAscentDescent, getFont, stringWidth


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
    printable_width = renderer.W-2*renderer.M
    renderer.layout = {
        "front_header": {
            "height_in": 0.75,
            "horizontal_padding_width_percent": 6/printable_width*100,
            "vertical_padding_height_percent": 5/54*100,
            "line_gap_height_percent": 1/54*100,
            "column_gap_width_percent": 8/printable_width*100,
            "name_height_percent": 60,
            "challenge_rating_height_percent": 30,
            "name_min_size_in": 11/72,
            "text_min_size_in": 5/72,
        },
        "primary_stats": {
            "icon_height_in": 42/72,
            "top_gap_height_percent": 4/42*100,
            "horizontal_inset_width_percent": 26/printable_width*100,
            "label_row_height_percent": 40,
            "label_height_percent": 26,
            "value_height_percent": 52,
            "text_horizontal_padding_percent": 10,
            "line_width_in": 1/72,
            "divider_line_width_in": .7/72,
            "text_min_size_in": 5/72,
        },
        "abilities": {
            "band_height_in": 64/72,
            "vertical_padding_height_percent": 9/64*100,
            "row_gap_height_percent": 2/64*100,
            "modifier_height_percent": 53,
            "text_horizontal_padding_percent": 8,
            "text_min_size_in": 5/72,
        },
        "back_edge_band_in": 0.375,
        "back_frame_line_width_pt": 0.8,
        "back_text_top_padding_em": 1.0,
        "back_text_bottom_padding_pt": 8,
        "back_source_note_clearance_pt": 6,
        "back_source_note_leading_pt": 5.5,
    }
    renderer.front_header = renderer.layout["front_header"]
    renderer.front_header_height = .75*72
    renderer.primary_stats = renderer.layout["primary_stats"]
    renderer.primary_stat_height = 42
    renderer.abilities = renderer.layout["abilities"]
    renderer.ability_band_height = 64
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
    def test_front_header_height_percentages_control_text_and_dashboard(self):
        renderer = _measurement_renderer()
        card = SimpleNamespace(name="Ogre",subtitle="Large giant, chaotic evil",cr="2")

        header = renderer._front_header_layout(card)
        usable = .75*72-2*5-1
        name_ascent, name_descent = getAscentDescent(
            renderer.fonts["black"],header["name_size"]
        )
        cr_ascent, cr_descent = getAscentDescent(
            renderer.fonts["bold"],header["cr_size"]
        )

        self.assertAlmostEqual(name_ascent-name_descent,usable*.60)
        self.assertAlmostEqual(cr_ascent-cr_descent,usable*.30)
        self.assertEqual(renderer._dashboard_top(),renderer.H-renderer.M-.75*72-4)

    def test_primary_stat_icons_keep_their_aspect_ratios_and_scale_text(self):
        renderer = _measurement_renderer()
        original_sizes = renderer._primary_stat_text_layout("ac","AC","15",50,200)
        original_bottom = renderer._dashboard_bottom()

        for kind, ratio in renderer.PRIMARY_STAT_ASPECT_RATIOS.items():
            self.assertAlmostEqual(renderer._primary_stat_width(kind)/42,ratio)

        renderer.primary_stat_height = 63
        scaled_sizes = renderer._primary_stat_text_layout("ac","AC","15",50,200)
        for kind, ratio in renderer.PRIMARY_STAT_ASPECT_RATIOS.items():
            self.assertAlmostEqual(renderer._primary_stat_width(kind)/63,ratio)
        self.assertAlmostEqual(
            scaled_sizes["label_size"],original_sizes["label_size"]*1.5
        )
        self.assertAlmostEqual(
            scaled_sizes["value_size"],original_sizes["value_size"]*1.5
        )
        expected_shift = 21*(1+4/42)
        self.assertAlmostEqual(renderer._dashboard_bottom(),original_bottom-expected_shift)

    def test_speed_text_is_centered_in_the_shaft_without_the_arrowhead(self):
        renderer = _measurement_renderer()
        cx = 100
        layout = renderer._primary_stat_text_layout("speed","SPEED","30′",cx,200)
        width = renderer._primary_stat_width("speed")
        shaft_left = cx-width/2
        shaft_right = shaft_left+width*39/52

        self.assertAlmostEqual(layout["center"],(shaft_left+shaft_right)/2)
        self.assertLess(layout["center"],cx)

    def test_ability_band_uses_six_equal_columns_and_proportional_text(self):
        renderer = _measurement_renderer()
        ability = SimpleNamespace(modifier=-1,score=16)
        top = 200
        layouts = [
            renderer._ability_layout(index,abbr,ability,top)
            for index,abbr in enumerate(("STR","DEX","CON","INT","WIS","CHA"))
        ]
        expected_width = (renderer.W-2*renderer.M)/6
        for index,layout in enumerate(layouts):
            self.assertAlmostEqual(layout["right"]-layout["left"],expected_width)
            self.assertAlmostEqual(layout["left"],renderer.M+index*expected_width)
        self.assertAlmostEqual(layouts[0]["left"],renderer.M)
        self.assertAlmostEqual(layouts[-1]["right"],renderer.W-renderer.M)

        usable_height = 64-2*9-2*2
        def cap_height(font, size):
            face = getFont(font).face
            return getattr(face,"capHeight",face.ascent)*size/1000

        modifier_height = usable_height*.53
        self.assertAlmostEqual(
            cap_height(renderer.fonts["black"],layouts[0]["modifier_size"]),
            modifier_height,
        )
        self.assertAlmostEqual(
            cap_height(renderer.fonts["bold"],layouts[0]["label_size"]),
            (usable_height-modifier_height)/2,
        )
        self.assertAlmostEqual(
            cap_height(renderer.fonts["regular"],layouts[0]["score_size"]),
            (usable_height-modifier_height)/2,
        )
        self.assertAlmostEqual(
            layouts[0]["label_baseline"]
            -layouts[0]["modifier_baseline"]
            -cap_height(renderer.fonts["black"],layouts[0]["modifier_size"]),
            2,
        )
        self.assertAlmostEqual(
            layouts[0]["modifier_baseline"]
            -layouts[0]["score_baseline"]
            -cap_height(renderer.fonts["regular"],layouts[0]["score_size"]),
            2,
        )

        original_widths = [layout["right"]-layout["left"] for layout in layouts]
        renderer.ability_band_height = 80
        taller = renderer._ability_layout(0,"STR",ability,top)
        self.assertGreater(taller["modifier_size"],layouts[0]["modifier_size"])
        self.assertEqual(taller["right"]-taller["left"],original_widths[0])

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
