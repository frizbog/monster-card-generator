import json
from pathlib import Path
import tempfile
import unittest

from monster_cards.normalize import NormalizationError, monster_to_card
from monster_cards.srd import SRDRepository


class ExtractedSRDTests(unittest.TestCase):
    def test_extracted_resource_is_hydrated_and_normalized(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            resources = root / "data" / "resources" / "monsters"
            sections = root / "data" / "sections"
            resources.mkdir(parents=True)
            sections.mkdir(parents=True)
            resource = {
                "name": "Goblin Warrior",
                "source": {"documentId": "monsters-a-z", "sectionId": "goblin-warrior"},
                "type_line": "Small Fey (Goblinoid), Chaotic Neutral",
                "armor_class": 15,
                "hit_points": 10,
                "speed": "30 ft., Fly 60 ft., Swim 20 ft.",
                "challenge": "1/4 (XP 50; PB +2)",
                "content": (
                    "Small Fey (Goblinoid), Chaotic Neutral AC 15 Initiative +2 (12) "
                    "HP 10 (3d6) Speed 30 ft. Skills Stealth +6 Senses Darkvision 60 ft.; "
                    "Passive Perception 9 Languages Common, Goblin CR 1/4 (XP 50; PB +2)"
                ),
                "tables": [{"rows": [
                    ["STR", "8", "−1", "−1", "DEX", "15", "+2", "+2", "CON", "10", "+0", "+0"],
                    ["INT", "10", "+0", "+0", "WIS", "8", "−1", "−1", "CHA", "8", "−1", "−1"],
                ]}],
            }
            action_section = {
                "title": "Actions",
                "parentId": "goblin-warrior",
                "content": (
                    "Scimitar. Melee Attack Roll: +4, reach 5 ft. Hit: 5 Slashing damage. "
                    "Shortbow. Ranged Attack Roll: +4, range 80/320 ft. Hit: 5 Piercing damage."
                ),
            }
            (resources / "goblin-warrior.json").write_text(json.dumps(resource), encoding="utf-8")
            (sections / "monsters-a-z--goblin-warrior-actions.json").write_text(
                json.dumps(action_section), encoding="utf-8"
            )

            card = monster_to_card(SRDRepository(root).monster("Goblin Warrior"))

            self.assertEqual(card.subtitle, "Small Fey (Goblinoid), Chaotic Neutral")
            self.assertEqual(card.cr, "1/4")
            self.assertEqual(card.speed, "30'")
            self.assertIn("Fly 60'", card.quick_facts)
            self.assertIn("Swim 20'", card.quick_facts)
            self.assertEqual(card.abilities["STR"].score, 8)
            self.assertEqual(card.abilities["DEX"].modifier, 2)
            self.assertEqual(card.passive_perception, "9")
            self.assertIn("Stealth +6", card.quick_facts)
            self.assertEqual([block.title for block in card.blocks], ["Scimitar:", "Shortbow:"])
            self.assertTrue(card.blocks[0].text.startswith("Melee Attack Roll:"))
            self.assertTrue(card.blocks[1].text.startswith("Ranged Attack Roll:"))

    def test_incomplete_schema_fails_instead_of_rendering_defaults(self):
        with self.assertRaisesRegex(NormalizationError, "schema may not be supported"):
            monster_to_card({"name": "Mystery Creature"})


if __name__ == "__main__":
    unittest.main()
