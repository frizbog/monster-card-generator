from __future__ import annotations

import json
from pathlib import Path
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

    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        if not self.root.exists():
            raise SRDError(f"SRD path does not exist: {self.root}")
        self._monster_index: dict[str, dict[str, Any]] | None = None
        self._spell_index: dict[str, dict[str, Any]] | None = None

    def describe(self) -> dict[str, Any]:
        monsters = self._load_collection("monsters")
        spells = self._load_collection("spells")
        return {
            "root": str(self.root),
            "monsters": len(monsters),
            "spells": len(spells),
        }

    def monster(self, name: str) -> dict[str, Any]:
        if self._monster_index is None:
            self._monster_index = self._load_collection("monsters")
        key = slugify(name)
        if key in self._monster_index:
            return self._monster_index[key]
        # Friendly fallback: exact case-insensitive name.
        for obj in self._monster_index.values():
            if str(obj.get("name", "")).casefold() == name.casefold():
                return obj
        available = sorted(str(x.get("name")) for x in self._monster_index.values() if x.get("name"))
        near = [x for x in available if name.casefold() in x.casefold() or x.casefold() in name.casefold()][:10]
        hint = f" Near matches: {', '.join(near)}" if near else ""
        raise SRDError(f"Monster not found: {name}.{hint}")

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
