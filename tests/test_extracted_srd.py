import json
from pathlib import Path
import tempfile
import unittest

from monster_minisheets.normalize import NormalizationError, monster_to_minisheet
from monster_minisheets.srd import SRDError, SRDRepository


class ExtractedSRDTests(unittest.TestCase):
    def test_custom_directory_loads_every_json_document(self):
        def document(name: str, section_id: str) -> dict:
            return {
                "sections": [{
                    "id": section_id,
                    "title": name,
                    "content": f"Small Humanoid AC 12 HP 5 (2d4) Speed 30 ft. CR 1",
                    "tables": [{
                        "headers": ["STR", "DEX", "CON", "INT", "WIS", "CHA"],
                        "rows": [["10", "10", "10", "10", "10", "10"]],
                    }],
                }],
            }

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            custom = root / "custom"
            monsters = custom / "monsters"
            monsters.mkdir(parents=True)
            (monsters / "zeta.json").write_text(json.dumps(document("Zeta Scout", "zeta")), encoding="utf-8")
            (monsters / "alpha.json").write_text(json.dumps(document("Alpha Scout", "alpha")), encoding="utf-8")

            repo = SRDRepository(root,custom)

            self.assertEqual(repo.monster("Alpha Scout")["name"],"Alpha Scout")
            self.assertEqual(repo.monster("Zeta Scout")["name"],"Zeta Scout")
            self.assertEqual(
                [path.name for path in repo.custom_monster_files], ["alpha.json", "zeta.json"]
            )

    def test_missing_srd_repository_explains_how_to_fix_the_path(self):
        missing = Path(tempfile.gettempdir()) / "missing-monster-minisheet-srd-repository"
        with self.assertRaisesRegex(
            SRDError,
            r"(?s)SRD repository was not found.*--srd PATH.*--srd ../dnd-srd-json",
        ):
            SRDRepository(missing)

    def test_custom_monsters_a_z_document_is_added_to_repository(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            root.mkdir(exist_ok=True)
            ability_rows = [["12 (+1)","14 (+2)","13 (+1)","8 (−1)","10 (+0)","6 (−2)"]]
            stat_section = {
                "id": "custom-clockwork-goblin",
                "documentId": "monsters-a-z",
                "title": "Clockwork Goblin",
                "parentId": "monsters-a-z",
                "content": (
                    "Small Construct, Unaligned Armor Class 16 Initiative +2 (12) Hit Points 18 (4d6 + 4) "
                    "Speed 30 ft., Climb 20 ft. Skills Stealth +4 Senses Darkvision 60 ft.; "
                    "Passive Perception 10 Languages Common Challenge 1 (XP 200; PB +2)"
                ),
                "tables": [{"headers": ["STR","DEX","CON","INT","WIS","CHA"],"rows": ability_rows}],
            }
            action_section = {
                "id": "custom-clockwork-goblin-actions",
                "documentId": "monsters-a-z",
                "title": "Actions",
                "parentId": "custom-clockwork-goblin",
                "content": "Gear Blade. Melee Attack Roll: +4, reach 5 ft. Hit: 6 Slashing damage.",
                "tables": [],
            }
            custom_file = root / "monsters-a-z.json"
            custom_file.write_text(json.dumps({"sections": [stat_section,action_section]}),encoding="utf-8")

            repo = SRDRepository(root,custom_file)
            minisheet = monster_to_minisheet(repo.monster("Clockwork Goblin"))

            self.assertEqual(minisheet.name,"Clockwork Goblin")
            self.assertEqual(minisheet.subtitle,"Small Construct, Unaligned")
            self.assertEqual(minisheet.ac,"16")
            self.assertEqual(minisheet.hp,"18")
            self.assertEqual(minisheet.speed,"30'")
            self.assertEqual(minisheet.abilities["STR"].score,12)
            self.assertIn("Climb 20'",minisheet.quick_facts)
            self.assertEqual(minisheet.blocks[0].title,"Gear Blade:")
            self.assertEqual(minisheet.source_note,"Generated from custom monster JSON.")

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

            minisheet = monster_to_minisheet(SRDRepository(root).monster("Goblin Warrior"))

            self.assertEqual(minisheet.subtitle, "Small Fey (Goblinoid), Chaotic Neutral")
            self.assertEqual(minisheet.cr, "1/4")
            self.assertEqual(minisheet.speed, "30'")
            self.assertIn("Fly 60'", minisheet.quick_facts)
            self.assertIn("Swim 20'", minisheet.quick_facts)
            self.assertEqual(minisheet.abilities["STR"].score, 8)
            self.assertEqual(minisheet.abilities["DEX"].modifier, 2)
            self.assertEqual(minisheet.passive_perception, "9")
            self.assertIn("Stealth +6", minisheet.quick_facts)
            self.assertEqual(
                [block.title for block in minisheet.blocks],
                [
                    "Sneaky:", "Escape Artist:", "Scimitar:", "Shortbow:",
                    "Bonus Action - Nimble Escape:", "Reaction - Parry:",
                    "Legendary Actions:", "Skitter:",
                    "Quick Slash (Costs 2 Actions):",
                ],
            )
            self.assertTrue(minisheet.blocks[2].text.startswith("Melee Attack Roll:"))
            self.assertTrue(minisheet.blocks[3].text.startswith("Ranged Attack Roll:"))

    def test_incomplete_schema_fails_instead_of_rendering_defaults(self):
        with self.assertRaisesRegex(NormalizationError, "schema may not be supported"):
            monster_to_minisheet({"name": "Mystery Creature"})


if __name__ == "__main__":
    unittest.main()
