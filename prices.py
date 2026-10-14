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


def stats(prices, buys=()):
    """Sell-side summary plus the best buy order (instant-sale price)."""
    best_buy = max(buys) if buys else None
    if not prices:
        return {"lowest": None, "average": None, "sellers": 0, "bestBuy": best_buy}
    return {"lowest": min(prices),
            "average": round(statistics.mean(prices), 1),
            "sellers": len(prices), "bestBuy": best_buy}


# Void Traces to refine a relic from intact to each level.
REFINE_TRACES = {"intact": 0, "exceptional": 25, "flawless": 50, "radiant": 100}


def closed_days(slug):
    """Daily closed-trade statistics for the last 90 days."""
    data = get(f"/items/{slug}/statistics", base=API_V1, key="payload")
    return (data or {}).get("statistics_closed", {}).get("90days", [])


def sold_price(days, subtype):
    """Volume-weighted average price actually traded over 90 days, or None."""
    rows = [d for d in days if d.get("subtype") == subtype and d.get("volume")]
    total = sum(d["volume"] for d in rows)
    return round(sum(d["avg_price"] * d["volume"] for d in rows) / total, 1) if total else None


def trades_per_day(days, ranks, subtype=None):
    """Average closed trades per day over the 90-day window, keyed by rank."""
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
        refs = r.get("refinements")
        if refs and r["ownedRank0"] and r.get("subtype") in refs:
            # relics: is refining before selling worth the Void Traces?
            now = REFINE_TRACES[r["subtype"]]
            for sub, p in refs.items():
                if REFINE_TRACES[sub] > now and p["lowest"] and (not a["lowest"] or p["lowest"] > a["lowest"]):
                    options.append((f"refine to {sub} ({REFINE_TRACES[sub] - now} traces), then sell",
                                    p, r["ownedRank0"]))
        for action, p, copies in options:
            if not p["lowest"] or p["lowest"] < MIN_PRICE or p["tradesPerDay"] < MIN_TRADES:
                continue
            out.append({"name": r["name"], "action": action, "lowestPrice": p["lowest"],
                        "averagePrice": p["average"], "tradesPerDay": p["tradesPerDay"],
                        "onlineSellers": p["sellers"], "yourCopies": copies,
                        "bestBuy": p.get("bestBuy"), "ducats": r.get("ducats", 0),
                        "bulk": r.get("bulk", False), "buyDemand": p.get("buyDemand", 0),
                        "score": round(p["lowest"] * p["tradesPerDay"], 1),
                        "url": f"https://warframe.market/items/{r['slug']}",
                        **({"refinements": refs} if refs else {})})
    out.sort(key=lambda c: -c["score"])
    return out


SERIOUS_BUY = 0.5  # buy orders below half the lowest sell price are lowballs, not demand


def buyer_demand(buy_orders, lowest_sell):
    """Copies online buyers want at a price close to what sellers ask."""
    if lowest_sell is None:
        return 0
    return sum(x.get("quantity", 1) for x in buy_orders
               if x["platinum"] >= lowest_sell * SERIOUS_BUY)


def sellable_copies(trades_per_day, buy_demand=0, bulk=False):
    """How many copies the market should absorb in WEEK days."""
    by_history = trades_per_day * WEEK
    return max(by_history, buy_demand) if bulk else by_history


def owned_candidates(results):
    """Same options, ranked by plat you could make from YOUR copies in a week.

    Copies count only up to what the market trades in WEEK days, so 29 copies
    of a mod that sells once a day count as 7, not 29. Bulk-tradable items
    (one buyer can take many) also count what online buyers want right now.
    """
    out = []
    for c in candidates_all(results):
        sellable = min(c["yourCopies"], sellable_copies(c["tradesPerDay"], c.get("buyDemand", 0),
                                                        c.get("bulk", False)))
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


DUCAT_RATIO = 10  # Baro rule of thumb: ~10 ducats per plat is a fair trade


def ducat_candidates(results):
    """Prime parts worth more as ducats (Baro Ki'Teer) than as plat."""
    out = []
    for r in results:
        ducats, price = r.get("ducats", 0), r["rank0"]["lowest"]
        if not ducats or not r["ownedRank0"]:
            continue
        ratio = ducats / price if price else None
        if ratio is not None and ratio < DUCAT_RATIO:
            continue
        out.append({"name": r["name"],
                    "action": f"trade to Baro: {ducats} ducats each"
                              + (f" ({ratio:.0f} ducats per plat)" if ratio else " (no one selling)"),
                    "lowestPrice": price, "averagePrice": r["rank0"]["average"],
                    "bestBuy": r["rank0"].get("bestBuy"),
                    "tradesPerDay": r["rank0"]["tradesPerDay"],
                    "onlineSellers": r["rank0"]["sellers"], "yourCopies": r["ownedRank0"],
                    "ducats": ducats, "score": ducats * r["ownedRank0"],
                    "url": f"https://warframe.market/items/{r['slug']}"})
    out.sort(key=lambda c: -c["score"])
    return out


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
    write_json(out_dir / f"{prefix}ducat-candidates.json", {
        "updated": now, "progress": progress_text,
        "score": f"total ducats (parts worth >= {DUCAT_RATIO} ducats per plat)",
        "candidates": ducat_candidates(results)})


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
        live = [x for x in orders
                if x.get("visible", True) and x.get("subtype", base) == base
                and (all_sellers or x["user"].get("status") in ("online", "ingame"))]
        def plat(kind, rank):
            return [x["platinum"] for x in live if x["type"] == kind and x.get("rank", 0) == rank]
        def demand(rank):
            sells = plat("sell", rank)
            return buyer_demand([x for x in live if x["type"] == "buy" and x.get("rank", 0) == rank],
                                min(sells) if sells else None)
        r0, rmax = (plat("sell", 0), plat("buy", 0)), (plat("sell", max_rank), plat("buy", max_rank))
        days = closed_days(item["slug"])
        volume = trades_per_day(days, {0, max_rank}, o["subtype"])
        time.sleep(DELAY)
        refinements = None
        if o["subtype"] in REFINE_TRACES:  # relic: price every refinement level
            online = [x for x in orders if x.get("visible", True)
                      and (all_sellers or x["user"].get("status") in ("online", "ingame"))]
            refinements = {}
            for sub in item.get("subtypes", []):
                if sub not in REFINE_TRACES:
                    continue
                st = stats([x["platinum"] for x in online if x["type"] == "sell" and x.get("subtype") == sub],
                           [x["platinum"] for x in online if x["type"] == "buy" and x.get("subtype") == sub])
                st["buyDemand"] = buyer_demand([x for x in online
                                                if x["type"] == "buy" and x.get("subtype") == sub],
                                               st["lowest"])
                st["soldAvg"] = sold_price(days, sub)
                if st["lowest"] is None and st["soldAvg"]:
                    # nobody online selling this level: fall back to what it sold for
                    st["lowest"] = st["average"] = round(st["soldAvg"])
                    st["fromHistory"] = True
                st["tradesPerDay"] = trades_per_day(days, {0}, sub)[0]
                refinements[sub] = st
        results.append({"name": o["name"], "slug": item["slug"], "owned": o["owned"],
                        "ownedRank0": o["ranks"].get(0, 0),
                        "ownedMax": o["ranks"].get(max_rank, 0) if max_rank else 0,
                        "maxRank": max_rank,
                        "isArcane": "arcane_enhancement" in item.get("tags", []),
                        "bulk": bool(item.get("bulkTradable")),
                        "ducats": item.get("ducats", 0),
                        "rank0": {**stats(*r0), "tradesPerDay": volume[0], "buyDemand": demand(0)},
                        "maxRankPrice": {**stats(*rmax), "tradesPerDay": volume[max_rank],
                                         "buyDemand": demand(max_rank)},
                        **({"subtype": o["subtype"], "refinements": refinements}
                           if refinements else {})})
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
