#!/usr/bin/env python3
"""Turn data/inventory.json into data/mods.json, data/arcanes.json,
data/relics.json and data/items.json (every other tradable thing: prime parts,
blueprints, Ayatan stars, fish...).

Mod and arcane names come from the community WFCD warframe-items database;
everything else is matched against warframe.market's item list. Both are
cached in data/cache/ (the market list is refreshed once a day).

Usage:
  python3 extract.py
"""

import json
import time
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CACHE = DATA / "cache"
DB_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/{}.json"
MARKET_URL = "https://api.warframe.market/v2/items"
# Inventory sections holding loose, tradable items. Built gear (Suits, LongGuns,
# ...) and mastery history (XPInfo) also match market "set" names but can't be
# traded, so they are left out on purpose.
ITEM_SECTIONS = ("MiscItems", "Recipes")
# Relics are stored per refinement ("...Bronze"); the market uses the base name
# plus a subtype.
RELIC_REFINEMENT = {"Bronze": "intact", "Silver": "exceptional",
                    "Gold": "flawless", "Platinum": "radiant"}


def market_ref(item_type, market):
    """Inventory ItemType -> (market gameRef, subtype), or (None, None)."""
    if item_type in market:
        return item_type, None
    for suffix, subtype in RELIC_REFINEMENT.items():
        if item_type.endswith(suffix) and item_type[:-len(suffix)] in market:
            return item_type[:-len(suffix)], subtype
    return None, None


def load_db(name):
    path = CACHE / f"{name}.json"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(DB_URL.format(name), path)
    return {m["uniqueName"]: m for m in json.load(open(path))}


def load_market():
    path = CACHE / "market-items.json"
    if not path.exists() or time.time() - path.stat().st_mtime > 86400:
        CACHE.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(MARKET_URL, headers={"Language": "en",
                                                          "User-Agent": "plat-scout/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            path.write_bytes(r.read())
    return {i["gameRef"]: i for i in json.load(open(path))["data"] if i.get("gameRef")}


def tradable_items(inv, market):
    items = {}
    for section in ITEM_SECTIONS:
        for x in inv.get(section, []):
            ref, subtype = market_ref(x.get("ItemType", ""), market)
            m = market.get(ref)
            if not m or "mod" in m.get("tags", []) or "arcane_enhancement" in m.get("tags", []):
                continue
            name = m["i18n"]["en"]["name"]
            if subtype and subtype != "intact":
                name += f" ({subtype})"
            e = items.setdefault((ref, subtype), {
                "name": name, "type": ", ".join(m.get("tags", [])),
                "rank": 0, "maxRank": m.get("maxRank", 0), "count": 0,
                "uniqueName": ref, "subtype": subtype})
            e["count"] += x.get("ItemCount", 1)
    return sorted(items.values(), key=lambda e: e["name"])


def fingerprint(entry):
    try:
        return json.loads(entry.get("UpgradeFingerprint") or "{}")
    except ValueError:
        return {}


def main():
    inv = json.load(open(DATA / "inventory.json"))
    entries = inv.get("RawUpgrades", []) + inv.get("Upgrades", [])
    mods_db, arcanes_db = load_db("Mods"), load_db("Arcanes")

    mods, arcanes, unknown = [], [], set()
    for x in entries:
        t = x["ItemType"]
        fp = fingerprint(x)
        count = x.get("ItemCount", 1)
        if t in arcanes_db:
            a = arcanes_db[t]
            arcanes.append({"name": a["name"], "type": a.get("type"), "rarity": a.get("rarity"),
                            "rank": fp.get("lvl", 0),
                            "maxRank": len(a["levelStats"]) - 1 if a.get("levelStats") else None,
                            "count": count, "uniqueName": t})
        elif t in mods_db and "Arcane" not in mods_db[t].get("type", ""):
            m = mods_db[t]
            e = {"name": m["name"], "type": m.get("type"), "rarity": m.get("rarity"),
                 "polarity": m.get("polarity"), "rank": fp.get("lvl", 0),
                 "maxRank": m.get("fusionLimit"), "count": count, "uniqueName": t}
            if "Randomized" in t and "UpgradeFingerprint" in x:
                e["riven"] = fp
            mods.append(e)
        else:
            unknown.add(t)

    tradable = tradable_items(inv, load_market())
    relics = [e for e in tradable if e.get("subtype")]  # relics carry a refinement
    items = [e for e in tradable if not e.get("subtype")]
    for name, items in (("mods", mods), ("arcanes", arcanes), ("items", items), ("relics", relics)):
        items.sort(key=lambda e: (e["name"], -e["rank"]))
        (DATA / f"{name}.json").write_text(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"{name}.json: {len(items)} entries, {sum(e['count'] for e in items)} copies")
    if unknown:
        print(f"skipped {len(unknown)} items not in the database (usually removed mods)")


if __name__ == "__main__":
    main()
