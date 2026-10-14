#!/usr/bin/env python3
"""Prime set completion and relic crack value.

Usage:
  python3 extras.py sets     # -> data/set-candidates.json
  python3 extras.py relics   # -> data/relic-candidates.json

Both read data/items.json (from extract.py). relics also reads
data/item-prices.json, when present, for each relic's own sell price.
Prices are the lowest online sell order; "Buy" is the best online buy order.
"""

import json
import sys
import time
from pathlib import Path

import extract
from prices import (DELAY, REFINE_TRACES, closed_days, get, progress, sellable_copies,
                    sold_price, stats, trades_per_day, write_json)

DATA = Path(__file__).resolve().parent / "data"
SUFFIX = {"intact": "Bronze", "exceptional": "Silver", "flawless": "Gold", "radiant": "Platinum"}
REFINE_MIN_GAIN = 5  # plat per relic refining must add to be worth the Void Traces
RELICS_URL = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json/Relics.json"

_orders, _days = {}, {}


def orders_for(slug):
    if slug not in _orders:
        _orders[slug] = get(f"/orders/item/{slug}") or []
        time.sleep(DELAY)
    return _orders[slug]


def days_for(slug):
    if slug not in _days:
        _days[slug] = closed_days(slug)
        time.sleep(DELAY)
    return _days[slug]


def price(slug, subtype=None):
    """Online sell/buy summary for one item (optionally one relic refinement)."""
    live = [x for x in orders_for(slug)
            if x.get("visible", True) and x["user"].get("status") in ("online", "ingame")
            and (subtype is None or x.get("subtype", subtype) == subtype)]
    return stats([x["platinum"] for x in live if x["type"] == "sell"],
                 [x["platinum"] for x in live if x["type"] == "buy"])


def save(name, label, rows, done, total):
    write_json(DATA / name, {"updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                             "progress": f"{done}/{total} checked", "score": label,
                             "candidates": rows})


# ---- prime sets ------------------------------------------------------------
def sets():
    market = extract.load_market()
    owned = {e["uniqueName"]: e["count"] for e in json.load(open(DATA / "items.json"))
             if not e.get("subtype")}
    parts = [market[ref] for ref in owned if ref in market
             and "prime" in market[ref]["tags"]
             and {"component", "blueprint"} & set(market[ref]["tags"])
             and "set" not in market[ref]["tags"]]

    # one /set call per set, skipping parts of a set we already have
    defs, seen = [], set()
    for part in parts:
        if part["id"] in seen:
            continue
        data = get(f"/item/{part['slug']}/set")
        time.sleep(DELAY)
        members = (data or {}).get("items", [])
        seen.update(m["id"] for m in members)
        root = next((m for m in members if m.get("setRoot")), None)
        if root:
            defs.append((root, [m for m in members if not m.get("setRoot")]))
    print(f"{len(parts)} prime parts owned, part of {len(defs)} sets")

    rows, started = [], time.monotonic()
    for n, (root, members) in enumerate(defs, 1):
        name = root["i18n"]["en"]["name"]
        progress(n, len(defs), name, started)
        sp = price(root["slug"])
        volume = trades_per_day(days_for(root["slug"]), {0})[0]
        part_rows, missing_cost, owned_value, have_n, need_n = [], 0, 0, 0, 0
        for m in members:
            qty, have = m.get("quantityInSet", 1), owned.get(m["gameRef"], 0)
            pp = price(m["slug"])
            missing = max(qty - have, 0)
            part_rows.append({"name": m["i18n"]["en"]["name"], "need": qty, "have": have,
                              "lowest": pp["lowest"], "bestBuy": pp["bestBuy"]})
            need_n += qty
            have_n += min(have, qty)
            if missing:
                missing_cost = None if missing_cost is None or pp["lowest"] is None \
                    else missing_cost + missing * pp["lowest"]
            owned_value += min(have, qty) * (pp["lowest"] or 0)
        complete = have_n == need_n
        gain = None
        if sp["lowest"] is not None and missing_cost is not None:
            gain = sp["lowest"] - missing_cost - owned_value
        missing_names = [p["name"].replace(name.replace(" Set", "") + " ", "")
                         for p in part_rows if p["have"] < p["need"]]
        action = ("complete! sell as a set" if complete
                  else f"buy {', '.join(missing_names)} (~{missing_cost}p), then sell set"
                  if missing_cost is not None else f"missing {', '.join(missing_names)}")
        rows.append({"name": name, "action": action, "complete": complete,
                     "score": gain if gain is not None else 0,
                     "lowestPrice": sp["lowest"], "averagePrice": sp["average"],
                     "bestBuy": sp["bestBuy"], "tradesPerDay": volume,
                     "onlineSellers": sp["sellers"], "yourCopies": f"{have_n}/{need_n}",
                     "missingCost": missing_cost, "ownedPartsValue": owned_value,
                     "ducats": root.get("ducats", 0), "parts": part_rows,
                     "url": f"https://warframe.market/items/{root['slug']}"})
        rows.sort(key=lambda r: (not r["complete"], -r["score"]))
        save("set-candidates.json",
             "set price - cost of missing parts - value of your parts sold separately",
             rows, n, len(defs))
    print()
    print(f"saved {DATA / 'set-candidates.json'}")


# ---- relic crack value -----------------------------------------------------
def relic_drops():
    path = extract.CACHE / "Relics.json"
    if not path.exists() or time.time() - path.stat().st_mtime > 7 * 86400:
        extract.CACHE.mkdir(parents=True, exist_ok=True)
        import urllib.request
        urllib.request.urlretrieve(RELICS_URL, path)
    return {r["uniqueName"]: r.get("rewards", []) for r in json.load(open(path))}


def relics():
    market = extract.load_market()
    drops = relic_drops()
    relics = [e for e in json.load(open(DATA / "items.json")) if e.get("subtype") in SUFFIX]
    sell = {}
    try:
        for r in json.load(open(DATA / "item-prices.json")):
            for sub, p in (r.get("refinements") or {}).items():
                sell[(r["slug"], sub)] = p
    except OSError:
        pass

    # every reward slug across all refinements of every owned relic
    slugs = sorted({d["item"]["warframeMarket"]["urlName"]
                    for e in relics for sub in SUFFIX
                    for d in drops.get(e["uniqueName"] + SUFFIX[sub], [])
                    if (d.get("item") or {}).get("warframeMarket")})
    print(f"{len(relics)} relic stacks owned, {len(slugs)} different rewards to price")

    value, started = {}, time.monotonic()
    for n, slug in enumerate(slugs, 1):
        progress(n, len(slugs), slug.replace("_", " "), started)
        p = price(slug)
        value[slug] = p["lowest"] if p["lowest"] is not None else sold_price(days_for(slug), None)

    rows = []
    for e in relics:
        slug = market[e["uniqueName"]]["slug"]
        cur = e["subtype"]
        ev, top = {}, []
        for sub in SUFFIX:
            total = 0.0
            for d in drops.get(e["uniqueName"] + SUFFIX[sub], []):
                wm = (d.get("item") or {}).get("warframeMarket")
                v = value.get(wm["urlName"]) if wm else None
                total += d["chance"] / 100 * (v or 0)
                if sub == cur:
                    top.append({"name": d["item"]["name"], "chance": d["chance"], "price": v})
            ev[sub] = round(total, 1)
        own_sell = sell.get((slug, cur)) or price(slug, cur)
        sell_price = own_sell.get("lowest")

        options = [(sell_price or 0, f"sell it ({sell_price}p)" if sell_price else None),
                   (ev[cur], f"crack it (expected {ev[cur]}p)")]
        base_best = max(sell_price or 0, ev[cur])
        for sub in SUFFIX:
            if REFINE_TRACES[sub] > REFINE_TRACES[cur] and ev[sub] - base_best >= REFINE_MIN_GAIN:
                options.append((ev[sub], f"refine to {sub} ({REFINE_TRACES[sub] - REFINE_TRACES[cur]}"
                                         f" traces) & crack (expected {ev[sub]}p)"))
        # selling is limited by demand (relics are bulk: count buyers' quantities too);
        # cracking isn't, you can open every copy yourself
        can_sell = min(e["count"], sellable_copies(own_sell.get("tradesPerDay", 0),
                                                   own_sell.get("buyDemand", 0), bulk=True))
        totals = [(v * (can_sell if a and a.startswith("sell") else e["count"]), v, a)
                  for v, a in options if a]
        total, best, action = max(totals)
        top.sort(key=lambda d: -(d["chance"] / 100 * (d["price"] or 0)))
        rows.append({"name": e["name"], "action": action, "score": round(total),
                     "sellableIn7Days": round(can_sell, 1), "buyDemand": own_sell.get("buyDemand", 0),
                     "lowestPrice": sell_price, "averagePrice": ev[cur],
                     "bestBuy": own_sell.get("bestBuy"),
                     "tradesPerDay": own_sell.get("tradesPerDay", 0),
                     "onlineSellers": own_sell.get("sellers", 0), "yourCopies": e["count"],
                     "refinement": cur, "crackValue": ev, "topDrops": top[:4],
                     "url": f"https://warframe.market/items/{slug}"})
    rows.sort(key=lambda r: -r["score"])
    save("relic-candidates.json", "best of sell / crack / refine & crack, x your copies",
         rows, len(slugs), len(slugs))
    print()
    print(f"saved {DATA / 'relic-candidates.json'}")


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "sets":
        sets()
    elif what == "relics":
        relics()
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
