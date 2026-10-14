#!/usr/bin/env python3
"""Look up warframe.market prices for every mod in mods.json.

For each tradable mod: lowest and average sell price at rank 0 and at max rank,
plus average completed trades per day over the last 90 days at each rank.
Also works for arcanes: pass arcanes.json and every output file gets an
"arcane-" prefix instead (arcane-prices.json, arcane-sell-candidates.json, ...).

Writes mod-prices.json and mod-prices.csv next to the input file, and rewrites
sell-candidates.json after every mod so you can watch the ranking build up.

Usage:
  python3 prices.py [data/mods.json] [--all-sellers]
  python3 prices.py [data/mods.json] --from-prices   # re-rank only, no API calls

By default only sellers that are online or in game count, because offline
listings are often years old. --all-sellers counts every visible listing.
"""

import csv
import json
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.warframe.market/v2"
API_V1 = "https://api.warframe.market/v1"  # trade statistics only exist in v1
HEADERS = {"Language": "en", "Platform": "pc", "Crossplay": "true",
           "User-Agent": "plat-scout/1.0"}
DELAY = 0.35  # market allows ~3 requests/second


def get(path, base=API, key="data"):
    for attempt in range(5):
        req = urllib.request.Request(base + path, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)[key]
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            if e.code == 404:
                return None
            raise
        except urllib.error.URLError:
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"giving up on {path}")


def stats(prices):
    if not prices:
        return {"lowest": None, "average": None, "sellers": 0}
    return {"lowest": min(prices),
            "average": round(statistics.mean(prices), 1),
            "sellers": len(prices)}


def trades_per_day(slug, ranks, subtype=None):
    """Average closed trades per day over the 90-day window, keyed by rank."""
    data = get(f"/items/{slug}/statistics", base=API_V1, key="payload")
    days = (data or {}).get("statistics_closed", {}).get("90days", [])
    out = {r: 0 for r in ranks}
    for d in days:
        if subtype and d.get("subtype", subtype) != subtype:
            continue
        r = d.get("mod_rank", 0)
        if r in out:
            out[r] += d["volume"]
    return {r: round(v / 90, 2) for r, v in out.items()}


def progress(n, total, label, started):
    """One-line progress bar with percent and time left, redrawn in place."""
    width = 30
    filled = int(width * n / total)
    elapsed = time.monotonic() - started
    left = int(elapsed / n * (total - n)) if n else 0
    bar = "#" * filled + "-" * (width - filled)
    line = f"[{bar}] {n}/{total} {100 * n // total:3d}%  ~{left // 60}m{left % 60:02d}s left  {label}"
    print("\r" + line[:100].ljust(100), end="", flush=True)


MIN_PRICE = 5          # ignore candidates worth less than this (plat)
MIN_TRADES = 0.3       # ignore candidates trading less than this per day
TOP = 50               # how many candidates to keep in sell-candidates.json
WEEK = 7               # sell-candidates-owned.json: copies the market absorbs in this many days


def write_json(path, data):
    """Write via a temp file so a reader never sees a half-written file."""
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def arcane_copies_for(rank):
    """Arcanes rank up by fusing copies: rank r needs (r+1)(r+2)/2 copies."""
    return (rank + 1) * (rank + 2) // 2


def candidates(results):
    """Rank sell options by price x trades/day: plat the market moves per day."""
    return candidates_all(results)[:TOP]


def candidates_all(results):
    out = []
    for r in results:
        a, b = r["rank0"], r["maxRankPrice"]
        options = []
        if r["ownedRank0"]:
            options.append(("sell as rank 0" if r["maxRank"] else "sell", a, r["ownedRank0"]))
            if r["maxRank"] and b["lowest"] and a["lowest"] and b["lowest"] > a["lowest"]:
                if r.get("isArcane"):
                    need = arcane_copies_for(r["maxRank"])
                    if r["ownedRank0"] // need:
                        options.append((f"fuse {need} copies into rank {r['maxRank']}, then sell",
                                        b, r["ownedRank0"] // need))
                else:
                    options.append((f"rank to {r['maxRank']} first, then sell", b, r["ownedRank0"]))
        if r["ownedMax"] and r["maxRank"]:
            options.append((f"sell at rank {r['maxRank']} (already maxed)", b, r["ownedMax"]))
        for action, p, copies in options:
            if not p["lowest"] or p["lowest"] < MIN_PRICE or p["tradesPerDay"] < MIN_TRADES:
                continue
            out.append({"name": r["name"], "action": action, "lowestPrice": p["lowest"],
                        "averagePrice": p["average"], "tradesPerDay": p["tradesPerDay"],
                        "onlineSellers": p["sellers"], "yourCopies": copies,
                        "score": round(p["lowest"] * p["tradesPerDay"], 1),
                        "url": f"https://warframe.market/items/{r['slug']}"})
    out.sort(key=lambda c: -c["score"])
    return out


def owned_candidates(results):
    """Same options, ranked by plat you could make from YOUR copies in a week.

    Copies count only up to what the market trades in WEEK days, so 29 copies
    of a mod that sells once a day count as 7, not 29.
    """
    out = []
    for c in candidates_all(results):
        sellable = min(c["yourCopies"], c["tradesPerDay"] * WEEK)
        out.append({**c, "sellableIn7Days": round(sellable, 1),
                    "potentialPlat": round(c["lowestPrice"] * sellable)})
    out.sort(key=lambda c: -c["potentialPlat"])
    return out[:TOP]


def volume_candidates(results):
    """Ignore price: rank by copies you own x trades per day (easiest to dump)."""
    out = [{**c, "volumeScore": round(c["yourCopies"] * c["tradesPerDay"], 1)}
           for c in candidates_all(results)]
    out.sort(key=lambda c: -c["volumeScore"])
    return out[:TOP]


def write_candidates(out_dir, results, progress_text, prefix=""):
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    write_json(out_dir / f"{prefix}sell-candidates.json", {
        "updated": now, "progress": progress_text,
        "score": "lowest online price x trades per day (last 90 days)",
        "candidates": candidates(results)})
    write_json(out_dir / f"{prefix}sell-candidates-owned.json", {
        "updated": now, "progress": progress_text,
        "score": "lowest online price x copies you own, capped at what sells in 7 days",
        "candidates": owned_candidates(results)})
    write_json(out_dir / f"{prefix}sell-candidates-volume.json", {
        "updated": now, "progress": progress_text,
        "score": "copies you own x trades per day (price ignored, still >= 5p)",
        "candidates": volume_candidates(results)})


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    run(Path(args[0]) if args else Path(__file__).resolve().parent / "data" / "mods.json",
        all_sellers="--all-sellers" in sys.argv, from_prices="--from-prices" in sys.argv)


def run(mods_path, all_sellers=False, from_prices=False):
    mods_path = Path(mods_path).expanduser()
    out_dir = mods_path.parent
    # mods.json -> mod-prices.json + sell-candidates*.json (original names)
    # arcanes.json -> arcane-prices.json + arcane-sell-candidates*.json
    prefix = "" if mods_path.stem == "mods" else mods_path.stem.rstrip("s") + "-"
    prices_name = "mod-prices" if not prefix else f"{prefix}prices"

    if from_prices:
        # re-rank from a finished mod-prices.json without calling the API
        results = json.load(open(out_dir / f"{prices_name}.json"))
        write_candidates(out_dir, results, f"{len(results)}/{len(results)} checked", prefix)
        print(f"rewrote the sell-candidates*.json files in {out_dir}")
        return

    owned = {}
    for m in json.load(open(mods_path)):
        if "riven" in m:
            continue  # rivens are traded on the separate riven auction market
        # relics: one entry per refinement, priced separately
        o = owned.setdefault((m["uniqueName"], m.get("subtype")),
                             {"name": m["name"], "subtype": m.get("subtype"),
                              "owned": 0, "ranks": {}})
        o["owned"] += m["count"]
        o["ranks"][m["rank"]] = o["ranks"].get(m["rank"], 0) + m["count"]

    market = {i["gameRef"]: i for i in get("/items") if i.get("gameRef")}
    todo = [(ref, o, market[ref]) for (ref, _), o in owned.items() if ref in market]
    print(f"{len(owned)} owned, {len(todo)} tradable on warframe.market")
    print(f"live ranking: {out_dir / (prefix + 'sell-candidates.json')}")

    results = []
    started = time.monotonic()
    for n, (ref, o, item) in enumerate(sorted(todo, key=lambda t: t[1]["name"]), 1):
        progress(n, len(todo), o["name"], started)
        orders = get(f"/orders/item/{item['slug']}") or []
        time.sleep(DELAY)
        max_rank = item.get("maxRank", 0)
        # compare like with like: mods "regular" (not atragraph), relics "intact"...
        base = o["subtype"] or (item.get("subtypes") or [None])[0]
        sells = [x for x in orders
                 if x["type"] == "sell" and x.get("visible", True)
                 and x.get("subtype", base) == base
                 and (all_sellers or x["user"].get("status") in ("online", "ingame"))]
        r0 = [x["platinum"] for x in sells if x.get("rank", 0) == 0]
        rmax = [x["platinum"] for x in sells if x.get("rank", 0) == max_rank]
        volume = trades_per_day(item["slug"], {0, max_rank}, o["subtype"])
        time.sleep(DELAY)
        results.append({"name": o["name"], "slug": item["slug"], "owned": o["owned"],
                        "ownedRank0": o["ranks"].get(0, 0),
                        "ownedMax": o["ranks"].get(max_rank, 0) if max_rank else 0,
                        "maxRank": max_rank,
                        "isArcane": "arcane_enhancement" in item.get("tags", []),
                        "rank0": {**stats(r0), "tradesPerDay": volume[0]},
                        "maxRankPrice": {**stats(rmax), "tradesPerDay": volume[max_rank]}})
        write_candidates(out_dir, results, f"{n}/{len(todo)} checked", prefix)
    print()

    results.sort(key=lambda r: -(r["maxRankPrice"]["lowest"] or r["rank0"]["lowest"] or 0))
    write_json(out_dir / f"{prices_name}.json", results)
    with open(out_dir / f"{prices_name}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["name", "owned", "maxRank",
                    "r0_lowest", "r0_average", "r0_sellers", "r0_trades_per_day",
                    "max_lowest", "max_average", "max_sellers", "max_trades_per_day", "url"])
        for r in results:
            a, b = r["rank0"], r["maxRankPrice"]
            w.writerow([r["name"], r["owned"], r["maxRank"],
                        a["lowest"], a["average"], a["sellers"], a["tradesPerDay"],
                        b["lowest"], b["average"], b["sellers"], b["tradesPerDay"],
                        f"https://warframe.market/items/{r['slug']}"])
    print(f"saved {prefix}sell-candidates*.json, {prices_name}.json and .csv in {out_dir}")


if __name__ == "__main__":
    main()
