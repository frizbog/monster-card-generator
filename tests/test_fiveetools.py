import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import urlparse

from monster_minisheets.fiveetools import FiveEToolsBestiary, adapt_5etools_monster
from monster_minisheets.normalize import monster_to_minisheet
from monster_minisheets.srd import SRDRepository


def creature(name: str, source: str = "MM") -> dict:
    return {
        "name": name,
        "source": source,
        "size": ["M"],
        "type": {"type": "humanoid", "tags": ["human"]},
        "alignment": ["L", "G"],
        "ac": [12],
        "hp": {"average": 9, "formula": "2d8"},
        "speed": {"walk": 30},
        "str": 10,
        "dex": 12,
        "con": 10,
        "int": 11,
        "wis": 13,
        "cha": 10,
        "passive": 11,
        "cr": "1/4",
        "action": [{
            "name": "Longbow",
            "entries": ["{@atk rw} {@hit 3} to hit. {@h}4 ({@damage 1d8}) piercing damage."],
        }],
    }


class Fake5eTools:
    def __init__(self, payloads: dict[str, dict]):
        self.payloads = payloads
        self.calls: list[str] = []

    def __call__(self, url: str):
        filename = Path(urlparse(url).path).name
        self.calls.append(filename)
        return self.payloads[filename]


class FiveEToolsTests(unittest.TestCase):
    def payloads(self) -> dict[str, dict]:
        scout = creature("Scout")
        barovian = {
            "name": "Barovian Scout",
            "source": "CoS",
            "_copy": {
                "name": "Scout",
                "source": "MM",
                "_mod": {
                    "action": {
                        "mode": "replaceArr",
                        "replace": "Longbow",
                        "items": {
                            "name": "Light Crossbow",
                            "entries": [
                                "{@atk rw} {@hit 4} to hit. {@h}6 ({@damage 1d8 + 2}) piercing damage."
                            ],
                        },
                    },
                },
            },
        }
        return {
            "index.json": {"CoS": "bestiary-cos.json", "MM": "bestiary-mm.json"},
            "bestiary-cos.json": {"monster": [barovian]},
            "bestiary-mm.json": {"monster": [scout]},
        }

    def test_copy_is_resolved_and_5etools_markup_is_normalized(self):
        fake = Fake5eTools(self.payloads())
        source = FiveEToolsBestiary(sources=["CoS", "MM"], fetch_json=fake)

        minisheet = monster_to_minisheet(source.monster("Barovian Scout"))

        self.assertEqual(minisheet.name, "Barovian Scout")
        self.assertEqual(minisheet.subtitle, "Medium Humanoid (Human), Lawful Good")
        self.assertEqual(minisheet.hp, "9")
        self.assertEqual(minisheet.speed, "30'")
        self.assertEqual(minisheet.blocks[0].title, "Light Crossbow:")
        self.assertEqual(
            minisheet.blocks[0].text,
            "Ranged Weapon Attack: +4 to hit. Hit: 6 (1d8 + 2) piercing damage.",
        )
        self.assertEqual(
            minisheet.source_note, "Generated from 5etools bestiary data (CoS)."
        )

    def test_local_srd_remains_authoritative(self):
        payloads = self.payloads()
        payloads["bestiary-mm.json"]["monster"][0]["hp"]["average"] = 99
        fake = Fake5eTools(payloads)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            local = creature("Scout")
            local["hit_points"] = 7
            local["armor_class"] = 13
            local["challenge_rating"] = "1/4"
            local["actions"] = [{"name": "Local Bow", "desc": "A local action."}]
            (root / "monsters.json").write_text(json.dumps([local]), encoding="utf-8")
            source = FiveEToolsBestiary(sources=["MM"], fetch_json=fake)
            repo = SRDRepository(root, fiveetools=source)

            self.assertEqual(repo.monster("Scout")["hit_points"], 7)
            self.assertEqual(fake.calls, [])

    def test_downloads_are_reused_from_cache(self):
        fake = Fake5eTools(self.payloads())
        with tempfile.TemporaryDirectory() as directory:
            first = FiveEToolsBestiary(
                sources=["MM"], cache_dir=directory, fetch_json=fake,
            )
            self.assertEqual(first.monster("Scout")["name"], "Scout")
            calls_after_first_read = list(fake.calls)

            def fail_fetch(url: str):
                raise AssertionError(f"unexpected download: {url}")

            second = FiveEToolsBestiary(
                sources=["MM"], cache_dir=directory, fetch_json=fail_fetch,
            )
            self.assertEqual(second.monster("Scout")["name"], "Scout")
            self.assertEqual(fake.calls, calls_after_first_read)

    def test_stationary_creature_without_actions_is_preserved(self):
        raw = creature("Quiet Portrait", "CoS")
        raw["speed"] = {"walk": 0}
        raw.pop("action")

        minisheet = monster_to_minisheet(adapt_5etools_monster(raw))

        self.assertEqual(minisheet.speed, "0'")
        self.assertEqual(minisheet.blocks, [])

    def test_nested_defenses_and_conditional_speeds_are_readable(self):
        raw = creature("Flying Scout")
        raw["speed"] = {
            "walk": 30,
            "fly": {"number": 60, "condition": "(hover)"},
            "canHover": True,
        }
        raw["resist"] = [{
            "resist": ["bludgeoning", "piercing"],
            "note": "from nonmagical attacks",
        }]

        minisheet = monster_to_minisheet(adapt_5etools_monster(raw))

        self.assertIn("Fly 60' (hover)", minisheet.quick_facts)
        self.assertIn(
            "Resist: bludgeoning, piercing from nonmagical attacks",
            minisheet.quick_facts,
        )


if __name__ == "__main__":
    unittest.main()
