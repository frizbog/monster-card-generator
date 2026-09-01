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
            trait_section = {
                "title": "Traits",
                "parentId": "goblin-warrior",
                "content": "Sneaky. The goblin has Advantage on stealthy tests. Escape Artist. The goblin slips away.",
            }
            reaction_section = {
                "title": "Reactions",
                "parentId": "goblin-warrior",
                "content": "Parry. Trigger: The goblin is hit. Response: The goblin gains 2 AC against the attack.",
            }
            bonus_section = {
                "title": "Bonus Actions",
                "parentId": "goblin-warrior",
                "content": "Nimble Escape. The goblin takes the Disengage or Hide action.",
            }
            legendary_section = {
                "title": "Legendary Actions",
                "parentId": "goblin-warrior",
                "content": (
                    "Legendary Action Uses: 2. Immediately after another creature's turn, the goblin can act. "
                    "The goblin regains all uses at the start of its turn. Skitter. The goblin moves 10 feet. "
                    "Quick Slash (Costs 2 Actions). The goblin makes one Scimitar attack."
                ),
            }
            (resources / "goblin-warrior.json").write_text(json.dumps(resource), encoding="utf-8")
            (sections / "monsters-a-z--goblin-warrior-actions.json").write_text(
                json.dumps(action_section), encoding="utf-8"
            )
            (sections / "monsters-a-z--goblin-warrior-traits.json").write_text(
                json.dumps(trait_section), encoding="utf-8"
            )
            (sections / "monsters-a-z--goblin-warrior-reactions.json").write_text(
                json.dumps(reaction_section), encoding="utf-8"
            )
            (sections / "monsters-a-z--goblin-warrior-bonus-actions.json").write_text(
                json.dumps(bonus_section), encoding="utf-8"
            )
            (sections / "monsters-a-z--goblin-warrior-legendary-actions.json").write_text(
                json.dumps(legendary_section), encoding="utf-8"
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
            self.assertEqual(
                [block.title for block in card.blocks],
                [
                    "Sneaky:", "Escape Artist:", "Scimitar:", "Shortbow:",
                    "Bonus Action - Nimble Escape:", "Reaction - Parry:",
                    "Legendary Actions:", "Skitter:",
                    "Quick Slash (Costs 2 Actions):",
                ],
            )
            self.assertTrue(card.blocks[2].text.startswith("Melee Attack Roll:"))
            self.assertTrue(card.blocks[3].text.startswith("Ranged Attack Roll:"))

    def test_incomplete_schema_fails_instead_of_rendering_defaults(self):
        with self.assertRaisesRegex(NormalizationError, "schema may not be supported"):
            monster_to_card({"name": "Mystery Creature"})


if __name__ == "__main__":
    unittest.main()
