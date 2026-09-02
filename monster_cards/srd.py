from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from .util import slugify, walk_json_files


class SRDError(RuntimeError):
    pass


class SRDRepository:
    """Schema-tolerant reader for local SRD-as-JSON repositories.

    Supported layouts include:
      * data/resources/monsters/*.json and data/resources/spells/*.json
      * monsters.json / spells.json anywhere near the repository root
      * a complete srd.json bundle, if its nested structures contain named resources

    The renderer deliberately depends on this adapter rather than on one upstream
    repository's exact schema.
    """

    def __init__(self, root: str | Path, custom_monsters: str | Path | None = None):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise SRDError(
                f"SRD repository was not found at: {self.root}\n"
                "Fix it by cloning/locating the SRD repository, then pass its directory with "
                "--srd PATH (for example: --srd ../dnd-srd-json)."
            )
        custom_path = Path(custom_monsters).expanduser().resolve() if custom_monsters else None
        if custom_path and custom_path.is_dir():
            self.custom_monster_files = sorted(custom_path.rglob("*.json"))
            if not self.custom_monster_files:
                raise SRDError(f"No custom monster JSON files found in directory: {custom_path}")
        elif custom_path and custom_path.is_file():
            self.custom_monster_files = [custom_path]
        elif custom_path:
            raise SRDError(f"Custom monster path does not exist: {custom_path}")
        else:
            self.custom_monster_files = []
        self._monster_index: dict[str, dict[str, Any]] | None = None
        self._spell_index: dict[str, dict[str, Any]] | None = None
        self._custom_monster_index: dict[str, dict[str, Any]] | None = None

    def describe(self) -> dict[str, Any]:
        monsters = self._monsters()
        spells = self._load_collection("spells")
        description = {
            "root": str(self.root),
            "monsters": len(monsters),
            "spells": len(spells),
        }
        if self.custom_monster_files:
            description["custom_monster_files"] = [str(path) for path in self.custom_monster_files]
            description["custom_monsters"] = len(self._custom_monsters())
        return description

    def monster(self, name: str) -> dict[str, Any]:
        monster_index = self._monsters()
        key = slugify(name)
        if key in monster_index:
            return monster_index[key]
        # Friendly fallback: exact case-insensitive name.
        for obj in monster_index.values():
            if str(obj.get("name", "")).casefold() == name.casefold():
                return obj
        available = sorted(str(x.get("name")) for x in monster_index.values() if x.get("name"))
        near = [x for x in available if name.casefold() in x.casefold() or x.casefold() in name.casefold()][:10]
        hint = f" Near matches: {', '.join(near)}" if near else ""
        raise SRDError(f"Monster not found: {name}.{hint}")

    def _monsters(self) -> dict[str, dict[str, Any]]:
        if self._monster_index is None:
            self._monster_index = self._load_collection("monsters")
            if self.custom_monster_files:
                self._monster_index.update(self._custom_monsters())
        return self._monster_index

    def _custom_monsters(self) -> dict[str, dict[str, Any]]:
        if self._custom_monster_index is not None:
            return self._custom_monster_index
        found: dict[str, dict[str, Any]] = {}
        for path in self.custom_monster_files:
            for key, monster in self._custom_monsters_from_file(path).items():
                if key in found:
                    raise SRDError(
                        f"Duplicate custom monster name {monster['name']!r} in {path}; "
                        "rename one of the custom monster entries."
                    )
                found[key] = monster
        self._custom_monster_index = found
        return found

    def _custom_monsters_from_file(self, path: Path) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SRDError(f"Cannot read custom monster file {path}: {exc}") from exc
        sections = payload.get("sections") if isinstance(payload, dict) else None
        if not isinstance(sections, list):
            raise SRDError(
                f"Custom monster file must use the monsters-a-z.json document format: {path}"
            )

        children: dict[str, list[dict[str, Any]]] = {}
        for section in sections:
            if isinstance(section, dict) and section.get("parentId"):
                children.setdefault(str(section["parentId"]), []).append(section)

        found: dict[str, dict[str, Any]] = {}
        for section in sections:
            if not isinstance(section, dict) or not self._is_monster_section(section):
                continue
            monster = self._monster_from_section(section,children.get(str(section.get("id")),[]))
            key = slugify(str(monster["name"]))
            if key in found:
                raise SRDError(
                    f"Duplicate custom monster name {monster['name']!r} in {path}; "
                    "rename one of the custom monster entries."
                )
            found[key] = monster
        if not found:
            raise SRDError(f"No monster stat blocks found in custom monster file: {path}")
        return found

    @staticmethod
    def _is_monster_section(section: dict[str, Any]) -> bool:
        content = str(section.get("content") or section.get("text") or "")
        tables = section.get("tables")
        ability_table = isinstance(tables,list) and any(
            isinstance(table,dict)
            and (
                "STR" in [str(header).upper() for header in table.get("headers",[])]
                or any("STR" in [str(cell).upper() for cell in row] for row in table.get("rows",[]) if isinstance(row,list))
            )
            for table in tables
        )
        return bool(
            section.get("title") and ability_table
            and re.search(r"\b(?:AC|Armor Class)\s+\d+",content,re.I)
            and re.search(r"\b(?:HP|Hit Points)\s+\d+",content,re.I)
            and re.search(r"\b(?:CR|Challenge)\s+\S+",content,re.I)
        )

    @staticmethod
    def _monster_from_section(
        section: dict[str, Any], child_sections: list[dict[str, Any]]
    ) -> dict[str, Any]:
        content = str(section.get("content") or section.get("text") or "")
        monster = dict(section)
        monster["name"] = str(section["title"])
        monster["_custom_monster"] = True

        type_match = re.match(r"(.+?)\s+(?:AC|Armor Class)\s+\d+",content,re.I)
        ac_match = re.search(r"\b(?:AC|Armor Class)\s+(\d+)",content,re.I)
        hp_match = re.search(r"\b(?:HP|Hit Points)\s+(\d+)",content,re.I)
        speed_match = re.search(
            r"\bSpeed\s+(.+?)(?=\s+(?:Saving Throws|Saves|Skills|Damage Vulnerabilities|"
            r"Damage Resistances|Damage Immunities|Condition Immunities|Gear|Senses|Languages|CR)\b)",
            content,
        )
        challenge_match = re.search(r"\b(?:CR|Challenge)\s+(.+?)(?=\s+(?:Traits|Actions|Bonus Actions|Reactions|Legendary Actions)\b|$)",content,re.I)
        if type_match:
            monster["type_line"] = type_match.group(1).strip()
        if ac_match:
            monster["armor_class"] = int(ac_match.group(1))
        if hp_match:
            monster["hit_points"] = int(hp_match.group(1))
        if speed_match:
            monster["speed"] = speed_match.group(1).strip()
        if challenge_match:
            monster["challenge"] = challenge_match.group(1).strip()

        key_for_title = {
            "traits": "special_abilities",
            "actions": "actions",
            "bonus actions": "bonus_actions",
            "reactions": "reactions",
            "legendary actions": "legendary_actions",
        }
        for child in child_sections:
            title = str(child.get("title") or "").strip()
            key = key_for_title.get(title.casefold())
            text = child.get("content") or child.get("text")
            if key and text:
                monster.setdefault(key,[]).append({"name": title,"text": str(text)})
        return monster

    def spell(self, name: str) -> dict[str, Any]:
        if self._spell_index is None:
            self._spell_index = self._load_collection("spells")
        key = slugify(name)
        if key in self._spell_index:
            return self._spell_index[key]
        for obj in self._spell_index.values():
            if str(obj.get("name", "")).casefold() == name.casefold():
                return obj
        raise SRDError(f"Spell not found: {name}")

    def _load_collection(self, collection: str) -> dict[str, dict[str, Any]]:
        # Best case: one resource per JSON file.
        resource_dir = self.root / "data" / "resources" / collection
        if resource_dir.exists():
            found = {}
            for path in resource_dir.glob("*.json"):
                try:
                    obj = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                obj = self._unwrap(obj)
                if isinstance(obj, dict) and obj.get("name"):
                    if collection == "monsters":
                        obj = self._with_monster_sections(obj)
                    found[slugify(str(obj["name"]))] = obj
            if found:
                return found

        # Look for an obvious flat collection file.
        candidates = [
            self.root / f"{collection}.json",
            self.root / "json" / f"{collection}.json",
            self.root / "data" / f"{collection}.json",
            self.root / "data" / "collections" / f"{collection}.json",
        ]
        for path in candidates:
            if path.exists():
                found = self._index_payload(json.loads(path.read_text(encoding="utf-8")), collection)
                if found:
                    return found

        # Last resort: inspect plausible JSON files. This is intentionally bounded
        # to avoid parsing huge unrelated indexes if a standard layout exists.
        for path in walk_json_files(self.root):
            if collection not in path.name.lower() and collection not in str(path.parent).lower():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            found = self._index_payload(payload, collection)
            if found:
                return found

        return {}

    def _with_monster_sections(self, monster: dict[str, Any]) -> dict[str, Any]:
        """Attach action/trait sections used by extracted SRD 5.2.1 data.

        That repository's resource files contain the stat-line and ability table,
        while operational text is stored in sibling section files.  Present those
        sections through the same keys consumed by the schema-tolerant normalizer.
        """
        source = monster.get("source")
        if not isinstance(source, dict):
            return monster
        document_id = source.get("documentId")
        section_id = source.get("sectionId")
        if not document_id or not section_id:
            return monster

        sections_dir = self.root / "data" / "sections"
        if not sections_dir.is_dir():
            return monster

        key_for_title = {
            "traits": "special_abilities",
            "actions": "actions",
            "bonus actions": "bonus_actions",
            "reactions": "reactions",
            "legendary actions": "legendary_actions",
        }
        attached: dict[str, list[dict[str, str]]] = {}
        pattern = f"{document_id}--{section_id}-*.json"
        for path in sections_dir.glob(pattern):
            try:
                section = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            # Only group sections immediately below this monster. Descendants are
            # already flattened into their parent group's content by the extractor.
            if section.get("parentId") != section_id:
                continue
            title = str(section.get("title", "")).strip()
            key = key_for_title.get(title.casefold())
            text = section.get("content") or section.get("text")
            if key and text:
                attached.setdefault(key, []).append({"name": title, "text": str(text)})

        if not attached:
            return monster
        result = dict(monster)
        result.update(attached)
        return result

    @staticmethod
    def _unwrap(obj: Any) -> Any:
        if isinstance(obj, dict) and set(obj.keys()) == {"data"}:
            return obj["data"]
        if isinstance(obj, dict) and "data" in obj and isinstance(obj["data"], dict) and obj["data"].get("name"):
            return obj["data"]
        return obj

    def _index_payload(self, payload: Any, collection: str) -> dict[str, dict[str, Any]]:
        payload = self._unwrap(payload)
        if isinstance(payload, dict):
            # Cantilux-style collections can have items.
            if isinstance(payload.get("items"), list):
                return self._index_list(payload["items"])
            if isinstance(payload.get("items"), dict):
                return self._index_dict(payload["items"])
            if isinstance(payload.get(collection), list):
                return self._index_list(payload[collection])
            if isinstance(payload.get(collection), dict):
                return self._index_dict(payload[collection])
            # Flat object keyed by slug.
            if any(isinstance(v, dict) and v.get("name") for v in payload.values()):
                return self._index_dict(payload)
        if isinstance(payload, list):
            return self._index_list(payload)
        return {}

    @staticmethod
    def _index_list(items: list[Any]) -> dict[str, dict[str, Any]]:
        found = {}
        for item in items:
            if isinstance(item, dict) and item.get("name"):
                found[slugify(str(item["name"]))] = item
        return found

    @staticmethod
    def _index_dict(items: dict[str, Any]) -> dict[str, dict[str, Any]]:
        found = {}
        for key, item in items.items():
            if isinstance(item, dict) and item.get("name"):
                found[slugify(str(item["name"]))] = item
            elif isinstance(item, dict):
                # Some resources omit name but are keyed by slug; not useful to us.
                continue
        return found
