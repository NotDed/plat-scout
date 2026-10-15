#!/usr/bin/env python3
"""Plan which trades to make, day by day.

Warframe allows as many trades per day as your Mastery Rank, and every item you
trade costs a credit tax. This builds data/trade-plan.json from the saved price
scans (no new price scan): every sell-now option (no ranking up, refining or
buying parts) plus complete prime sets, one buyer per trade, best plat per
trade first, spread over days.

Usage:
  python3 planner.py
"""

import json
import math
import time
from pathlib import Path

import prices
from prices import (DELAY, candidates_all, expected_price, get, owned_copies, progress,
                    refresh_counts, sellable_copies, write_json)

DATA = Path(__file__).resolve().parent / "data"
TAX_CACHE = DATA / "cache" / "trading-tax.json"
SOURCES = {"mod-prices.json": "mods.json", "arcane-prices.json": "arcanes.json",  # prices -> copies
           "item-prices.json": "items.json", "relic-prices.json": "relics.json"}
SELL_NOW = ("sell", "complete!")          # actions that need no work first
WORK_FIRST = ("rank to", "fuse", "refine", "buy ", "missing")
BULK_PER_TRADE = 6          # copies one buyer takes of a bulk item (relics, mods...)
MAX_CREDITS_PER_PLAT = 2000  # worse than this, the trade isn't worth the tax


def trading_tax(slugs):
    """Credit tax per item copy, from /v2/item/{slug}, cached on disk."""
    try:
        cache = json.loads(TAX_CACHE.read_text())
    except (OSError, ValueError):
        cache = {}
    missing = [s for s in slugs if s not in cache]
    started = time.monotonic()
    for n, slug in enumerate(missing, 1):
        progress(n, len(missing), f"trade tax: {slug.replace('_', ' ')}", started)
        item = get(f"/item/{slug}") or {}
        cache[slug] = item.get("tradingTax", 0)
        time.sleep(DELAY)
    if missing:
        print()
        TAX_CACHE.parent.mkdir(parents=True, exist_ok=True)
        TAX_CACHE.write_text(json.dumps(cache))
    return cache


def sell_options():
    """Every sell-now option across the saved scans, plus complete sets."""
    opts = []
    for name, source in SOURCES.items():
        try:
            results = json.load(open(DATA / name))
            refresh_counts(results, owned_copies(DATA / source))  # spare copies only
        except OSError:
            continue
        for c in candidates_all(results):
            if c["action"].startswith(SELL_NOW) and not c["action"].startswith(WORK_FIRST):
                opts.append(c)
    try:
        for s in json.load(open(DATA / "set-candidates.json"))["candidates"]:
            if s.get("complete") and s.get("lowestPrice"):
                opts.append({**s, "expectedPrice": s["lowestPrice"], "bulk": False,
                             "yourCopies": 1})
    except OSError:
        pass
    return opts


def main():
    inv = json.load(open(DATA / "inventory.json"))
    mr = inv.get("PlayerLevel", 0)
    left_today = inv.get("TradesRemaining", mr)
    credits = inv.get("RegularCredits", 0)

    opts = sell_options()
    slug = lambda c: c["url"].rstrip("/").rsplit("/", 1)[-1]
    tax = trading_tax(sorted({slug(c) for c in opts}))

    # break every option into trades: one buyer each
    units = []
    for c in opts:
        price = c.get("expectedPrice") or expected_price({"lowest": c.get("lowestPrice")})
        copies = c["yourCopies"] if isinstance(c["yourCopies"], int) else 1
        can = min(copies, math.floor(sellable_copies(c.get("tradesPerDay", 0),
                                                     c.get("buyDemand", 0), c.get("bulk", False))))
        per_trade = BULK_PER_TRADE if c.get("bulk") else 1
        while can > 0:
            qty = min(per_trade, can)
            units.append((price * qty, qty, tax.get(slug(c), 0) * qty, c))
            can -= qty
    units.sort(key=lambda u: -u[0])

    # fill days: what's left today first, then MR trades per day; stop when credits run out
    plan, day, used, spent, skipped = {}, 1, 0, 0, {}
    cap = left_today or mr
    for plat, qty, cost, c in units:
        key = (c["name"], c["action"])
        if plat <= 0 or cost / plat > MAX_CREDITS_PER_PLAT:
            skipped.setdefault(key, [c, 0, 0])[1] += qty
            continue
        if spent + cost > credits:
            skipped.setdefault(key, [c, 0, 0])[2] += qty
            continue
        if used >= cap:
            day, used, cap = day + 1, 0, mr
        used += 1
        spent += cost
        row = plan.setdefault(key, {"c": c, "plat": 0, "qty": 0, "tax": 0, "trades": 0,
                                    "days": []})
        row["plat"] += plat
        row["qty"] += qty
        row["tax"] += cost
        row["trades"] += 1
        row["days"].append(day)

    rows = []
    for (name, action), r in plan.items():
        c, first, last = r["c"], min(r["days"]), max(r["days"])
        rows.append({"name": name, "action": action, "score": round(r["plat"]),
                     "dayFirst": first, "dayLabel": str(first) if first == last else f"{first}-{last}",
                     "trades": r["trades"], "tax": r["tax"],
                     "lowestPrice": c.get("lowestPrice"), "expectedPrice": c.get("expectedPrice"),
                     "bestBuy": c.get("bestBuy"), "tradesPerDay": c.get("tradesPerDay", 0),
                     "yourCopies": r["qty"], "trend": c.get("trend"), "vaulted": c.get("vaulted"),
                     "soldAvg": c.get("soldAvg"), "refinement": c.get("refinement"),
                     "url": c["url"]})
    rows.sort(key=lambda r: (r["dayFirst"], -r["score"]))
    for (name, action), (c, too_taxed, no_credits) in skipped.items():
        why = "not worth the tax" if too_taxed else "not enough credits"
        rows.append({"name": name, "action": f"skip: {why}", "score": 0, "dayFirst": 999,
                     "dayLabel": "-", "trades": 0, "tax": 0, "lowestPrice": c.get("lowestPrice"),
                     "bestBuy": c.get("bestBuy"), "tradesPerDay": c.get("tradesPerDay", 0),
                     "yourCopies": too_taxed or no_credits, "url": c["url"]})

    today = [r for r in rows if r["dayFirst"] == 1]
    days_needed = max((int(r["dayLabel"].split("-")[-1]) for r in rows if r["dayLabel"] != "-"),
                      default=0)
    write_json(DATA / "trade-plan.json", {
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"), "progress": f"{len(units)} possible trades",
        "score": "plat per day, best trades first", "mr": mr, "tradesPerDay": mr,
        "tradesLeftToday": left_today, "credits": credits,
        "todayPlat": round(sum(r["score"] for r in today)), "todayTax": sum(r["tax"] for r in today),
        "daysNeeded": days_needed, "candidates": rows})
    print(f"MR {mr}: {mr} trades/day ({left_today} left today) · {len(rows)} items over "
          f"{days_needed} days · saved {DATA / 'trade-plan.json'}")


if __name__ == "__main__":
    main()
