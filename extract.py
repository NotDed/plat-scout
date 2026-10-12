#!/usr/bin/env python3
"""Turn data/inventory.json into data/mods.json and data/arcanes.json.

Item names come from the community WFCD warframe-items database, downloaded
into data/cache/ on first run (delete that folder to refresh it).

Usage:
  python3 extract.py
"""

import json
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
CACHE = DATA / "cache"
DB_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/{}.json"


def load_db(name):
    path = CACHE / f"{name}.json"
    if not path.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(DB_URL.format(name), path)
    return {m["uniqueName"]: m for m in json.load(open(path))}


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

    for name, items in (("mods", mods), ("arcanes", arcanes)):
        items.sort(key=lambda e: (e["name"], -e["rank"]))
        (DATA / f"{name}.json").write_text(json.dumps(items, indent=2, ensure_ascii=False))
        print(f"{name}.json: {len(items)} entries, {sum(e['count'] for e in items)} copies")
    if unknown:
        print(f"skipped {len(unknown)} items not in the database (usually removed mods)")


if __name__ == "__main__":
    main()
