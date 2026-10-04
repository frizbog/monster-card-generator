from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

from monster_minisheets.io import load_manual_minisheets
from monster_minisheets.layout import SheetLayout
from monster_minisheets.model import RuleBlock
from monster_minisheets.renderer import MinisheetRenderer
from reportlab.pdfbase.pdfmetrics import getAscentDescent, getFont, stringWidth


def _measurement_minisheet_renderer() -> MinisheetRenderer:
    renderer = MinisheetRenderer.__new__(MinisheetRenderer)
    renderer.sizes = {"body": 8.5,"source_note": 4.7}
    renderer.body_size = 8.5
    renderer.fonts = {
        "regular": "Helvetica",
        "bold": "Helvetica-Bold",
        "black": "Helvetica-Bold",
    }
    renderer.PAGE_W = 8.5 * 72
    renderer.PAGE_H = 11 * 72
    renderer.W = 4.25 * 72
    renderer.H = 5.5 * 72
    renderer.NORMAL_W = renderer.W
    renderer.NORMAL_H = renderer.H
    renderer.LARGE_W = 5.5 * 72
    renderer.LARGE_H = 8.5 * 72
    renderer.M = 18
    printable_width = renderer.W-2*renderer.M
    renderer.layout = {
        "header": {
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
        "quick_facts": {
            "band_height_in": .3,
            "text_height_percent": 55,
            "horizontal_padding_width_percent": 5/printable_width*100,
            "line_width_in": .8/72,
            "text_min_size_in": 5.8/72,
        },
    }
    renderer.header = renderer.layout["header"]
    renderer.header_height = .75*72
    renderer.primary_stats = renderer.layout["primary_stats"]
    renderer.primary_stat_height = 42
    renderer.abilities = renderer.layout["abilities"]
    renderer.ability_band_height = 64
    renderer.quick_facts = renderer.layout["quick_facts"]
    renderer.quick_facts_band_height = .3*72
    renderer.large_columns = {"gutter_in": .14,"body_min_size_pt": 6.5}
    renderer.sheet = SheetLayout(
        page_width=renderer.PAGE_W,
        page_height=renderer.PAGE_H,
        minisheet_width=renderer.W,
        minisheet_height=renderer.H,
        large_minisheet_width=renderer.LARGE_W,
        large_minisheet_height=renderer.LARGE_H,
        artwork_inset=renderer.M,
    )
    return renderer


class MinisheetRendererFlowTests(unittest.TestCase):
    def test_minisheet_renderer_orders_multiple_minisheets_alphabetically_by_name(self):
        minisheets = [
            SimpleNamespace(name="Zombie"),
            SimpleNamespace(name="acolyte"),
            SimpleNamespace(name="Bandit"),
            SimpleNamespace(name="Acolyte"),
        ]

        ordered = MinisheetRenderer._ordered_minisheets(minisheets)

        self.assertEqual(
            [minisheet.name for minisheet in ordered],
            ["Acolyte","acolyte","Bandit","Zombie"],
        )

    def test_color_configuration_is_semantic_and_accepts_none(self):
        root = Path(__file__).resolve().parents[1]
        style_path = root / "config" / "minisheet_style.json"
        style = json.loads(style_path.read_text(encoding="utf-8"))

        self.assertNotIn("teal",style["colors"])
        self.assertNotIn("dark",style["colors"])
        self.assertEqual(style["colors"]["header_band_background"],"#17657f")
        self.assertEqual(style["colors"]["icon_border"],"#17657f")
        self.assertEqual(style["colors"]["header_band_text"],"#ffffff")
        self.assertIsNone(MinisheetRenderer(style_path).colors["icon_background"])

    def test_every_color_role_can_be_none_when_rendering(self):
        root = Path(__file__).resolve().parents[1]
        style = json.loads(
            (root / "config" / "minisheet_style.json").read_text(encoding="utf-8")
        )
        style["colors"] = {name: "none" for name in style["colors"]}
        minisheets = load_manual_minisheets(root / "examples" / "manual_monsters.json")[:1]

        with TemporaryDirectory() as directory:
            style_path = Path(directory) / "style.json"
            output = Path(directory) / "minisheets.pdf"
            style_path.write_text(json.dumps(style),encoding="utf-8")
            MinisheetRenderer(style_path).render(minisheets,output)

            self.assertTrue(output.read_bytes().startswith(b"%PDF"))

    def test_color_configuration_rejects_non_hex_values(self):
        with self.assertRaisesRegex(
            ValueError,r"colors\.header_band_text must be #rrggbb or none"
        ):
            MinisheetRenderer._parse_color("header_band_text","white")

    def test_quick_facts_band_uses_physical_height_and_proportional_text(self):
        renderer = _measurement_minisheet_renderer()
        target_height = renderer.quick_facts_band_height*.55
        size = renderer._fit_text_to_height(
            "Init +2 · Speed 30′","black",target_height,
            renderer.W-2*renderer.M-10,5.8,"quick-facts band",
        )
        ascent,descent = getAscentDescent(renderer.fonts["black"],size)

        self.assertAlmostEqual(renderer.quick_facts_band_height,.3*72)
        self.assertAlmostEqual(ascent-descent,target_height)

    def test_header_height_percentages_control_text_and_dashboard(self):
        renderer = _measurement_minisheet_renderer()
        minisheet = SimpleNamespace(name="Ogre",subtitle="Large giant, chaotic evil",cr="2")

        header = renderer._header_layout(minisheet)
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
        renderer = _measurement_minisheet_renderer()
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
        renderer = _measurement_minisheet_renderer()
        cx = 100
        layout = renderer._primary_stat_text_layout("speed","SPEED","30′",cx,200)
        width = renderer._primary_stat_width("speed")
        shaft_left = cx-width/2
        shaft_right = shaft_left+width*39/52

        self.assertAlmostEqual(layout["center"],(shaft_left+shaft_right)/2)
        self.assertLess(layout["center"],cx)

    def test_ability_band_uses_six_equal_columns_and_proportional_text(self):
        renderer = _measurement_minisheet_renderer()
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

    def test_minisheet_renderer_emits_letter_page_with_four_normal_minisheets(self):
        root = Path(__file__).resolve().parents[1]
        minisheet = load_manual_minisheets(root / "examples" / "manual_monsters.json")[0]
        minisheets = [deepcopy(minisheet) for _ in range(4)]

        with TemporaryDirectory() as directory:
            output = Path(directory) / "minisheets.pdf"
            MinisheetRenderer(root / "config" / "minisheet_style.json").render(minisheets,output)
            pdf = output.read_bytes()

        self.assertIn(b"/MediaBox [ 0 0 612 792 ]",pdf)
        self.assertEqual(pdf.count(b"/Type /Page\n"),1)

    def test_letter_sheet_rows_and_cut_guides_use_correct_physical_edges(self):
        renderer = _measurement_minisheet_renderer()

        self.assertEqual(renderer.sheet.row_origin_y(top=True),5.5*72)
        self.assertEqual(renderer.sheet.row_origin_y(top=False),0.0)
        self.assertEqual(renderer._trim_guide_segments(
            top_is_normal=True,bottom_is_normal=False,
        ),[
            (0.0,5.5*72,8.5*72,5.5*72),
            (4.25*72,5.5*72,4.25*72,11*72),
        ])
        self.assertEqual(renderer._trim_guide_segments(
            top_is_normal=True,bottom_is_normal=True,
        ),[
            (0.0,5.5*72,8.5*72,5.5*72),
            (4.25*72,5.5*72,4.25*72,11*72),
            (4.25*72,0.0,4.25*72,5.5*72),
        ])

    def test_large_minisheet_is_rotated_clockwise_into_a_complete_row(self):
        renderer = _measurement_minisheet_renderer()
        renderer.c = MagicMock()
        minisheet = SimpleNamespace(large=True,minisheet=SimpleNamespace(name="Large"))

        with patch.object(renderer,"_draw_minisheet") as draw:
            renderer._draw_row([minisheet],top=False)

        renderer.c.translate.assert_called_once_with(0,5.5*72)
        renderer.c.rotate.assert_called_once_with(-90)
        draw.assert_called_once_with(minisheet)

    def test_configured_dimensions_exactly_tile_letter_rows(self):
        root = Path(__file__).resolve().parents[1]
        style = json.loads((root / "config" / "minisheet_style.json").read_text())

        layout = SheetLayout.from_style(style)

        self.assertEqual((layout.minisheet_width,layout.minisheet_height),(4.25*72,5.5*72))
        self.assertEqual(
            (layout.large_minisheet_width,layout.large_minisheet_height),(5.5*72,8.5*72)
        )

    def test_middle_bar_overflow_becomes_labeled_blocks_before_traits(self):
        renderer = _measurement_minisheet_renderer()
        minisheet = SimpleNamespace(
            quick_facts=[
                "Stealth +3", "Cond Immune: blinded, deafened", "Vuln. fire",
                "Senses: blindsight 60 ft. (blind beyond this radius)",
                "Languages: understands Common but can’t speak",
            ],
            blocks=[RuleBlock("False Appearance:","The blight resembles a dead shrub.")],
        )

        renderer._prepare_fact_flow(minisheet)

        self.assertIn("Vuln. fire"," · ".join(minisheet.quick_facts))
        self.assertEqual([block.title for block in minisheet.blocks[-3:]],[
            "Senses:","Languages:","False Appearance:",
        ])
        self.assertLessEqual(
            stringWidth(" · ".join(minisheet.quick_facts),renderer.fonts["black"],5.8),
            renderer.W-2*renderer.M-10,
        )

    def test_overflow_content_promotes_to_large_without_disappearing(self):
        root = Path(__file__).resolve().parents[1]
        normal, complex_minisheet = load_manual_minisheets(root / "examples" / "manual_monsters.json")
        renderer = MinisheetRenderer(root / "config" / "minisheet_style.json")

        normal_sheet = renderer._prepare_minisheet(normal)
        large_sheet = renderer._prepare_minisheet(complex_minisheet)

        self.assertFalse(normal_sheet.large)
        self.assertTrue(large_sheet.large)
        self.assertEqual(len(large_sheet.minisheet.blocks),6)
        self.assertEqual(large_sheet.minisheet.overflow,[])

    def test_content_that_exceeds_large_minisheet_reports_overflow(self):
        root = Path(__file__).resolve().parents[1]
        minisheet = load_manual_minisheets(root / "examples" / "manual_monsters.json")[0]
        minisheet.blocks = [RuleBlock("Unbounded Feature:","word "*2500)]
        minisheet.quick_facts = []
        minisheet.source_note = None

        with self.assertRaisesRegex(RuntimeError,"Text overflow for 'Goblin Warrior'"):
            MinisheetRenderer(root / "config" / "minisheet_style.json")._prepare_minisheet(minisheet)

    def test_row_packing_supports_all_required_combinations(self):
        small = lambda name: SimpleNamespace(minisheet=SimpleNamespace(name=name),large=False)
        large = lambda name: SimpleNamespace(minisheet=SimpleNamespace(name=name),large=True)

        four_normal = MinisheetRenderer._pack_pages([small(str(i)) for i in range(4)])
        mixed = MinisheetRenderer._pack_pages([small("a"),small("b"),large("c")])
        two_large = MinisheetRenderer._pack_pages([large("a"),large("b")])

        self.assertEqual([len(row) for row in four_normal[0]],[2,2])
        self.assertEqual([len(row) for row in mixed[0]],[2,1])
        self.assertEqual([len(row) for row in two_large[0]],[1,1])

    def test_row_packing_pulls_forward_next_normal_to_fill_open_quadrant(self):
        small = lambda name: SimpleNamespace(minisheet=SimpleNamespace(name=name),large=False)
        large = lambda name: SimpleNamespace(minisheet=SimpleNamespace(name=name),large=True)

        pages = MinisheetRenderer._pack_pages([
            small("Acolyte"),large("Banshee"),small("Bandit"),large("Revenant")
        ])

        self.assertEqual(
            [[[item.minisheet.name for item in row] for row in page] for page in pages],
            [[
                ["Acolyte","Bandit"],
                ["Banshee"],
            ],[
                ["Revenant"],
            ]],
        )

    def test_two_large_minisheets_share_one_page_without_vertical_cuts(self):
        large = lambda name: SimpleNamespace(minisheet=SimpleNamespace(name=name),large=True)
        pages = MinisheetRenderer._pack_pages([large("Banshee"),large("Revenant")])
        renderer = _measurement_minisheet_renderer()

        self.assertEqual(len(pages),1)
        self.assertEqual(len(pages[0]),2)
        self.assertEqual(renderer._trim_guide_segments(
            top_is_normal=False,bottom_is_normal=False,
        ),[
            (0.0,5.5*72,8.5*72,5.5*72),
        ])


if __name__ == "__main__":
    unittest.main()
