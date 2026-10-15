#!/usr/bin/env python3
"""plat-scout: find which of your Warframe items are worth selling."""

import argparse
import json
import sys
from pathlib import Path

import extract
import extras
import fetch_inventory
import prices

DATA = Path(__file__).resolve().parent / "data"
KINDS = {"mods": ("mods.json", ""), "arcanes": ("arcanes.json", "arcane-"),
         "items": ("items.json", "item-"), "relics": ("relics.json", "relic-")}
RANKINGS = {  # --by value -> (file suffix, field shown as "score")
    "market": ("sell-candidates.json", "score"),
    "owned": ("sell-candidates-owned.json", "potentialPlat"),
    "volume": ("sell-candidates-volume.json", "volumeScore"),
    "ducats": ("ducat-candidates.json", "score"),
    "crack": ("candidates.json", "score"),  # relics only: sell vs crack vs refine
}
SPECIAL = {"sets": "set-candidates.json"}


def kinds(which):
    return list(KINDS) if which == "all" else [which]


def need(path, hint):
    if not path.exists():
        sys.exit(f"{path.name} not found. Run first: plat-scout {hint}")


def cmd_fetch(a):
    fetch_inventory.fetch(a.auth)


def cmd_extract(a):
    need(DATA / "inventory.json", "fetch")
    extract.main()


def cmd_prices(a):
    for k in kinds(a.kind):
        path = DATA / KINDS[k][0]
        need(path, "extract")
        print(f"== {k}")
        prices.run(path, all_sellers=a.all_sellers)


def cmd_rank(a):
    for k in kinds(a.kind):
        prices.run(DATA / KINDS[k][0], from_prices=True)


def cmd_sets(a):
    need(DATA / "items.json", "extract")
    extras.sets()


def cmd_relics(a):
    need(DATA / "relics.json", "extract")
    extras.relics()


def cmd_top(a):
    if a.kind in SPECIAL:
        path, field = DATA / SPECIAL[a.kind], "score"
        need(path, a.kind)
    else:
        name, field = RANKINGS[a.by]
        path = DATA / (KINDS[a.kind][1] + name)
        need(path, f"prices {a.kind}")
    data = json.load(open(path))
    rows = data["candidates"]
    if a.quick:
        rows = [c for c in rows if not c["action"].startswith(("rank to", "fuse", "refine", "buy ", "missing"))]
    rows = rows[:a.n]

    print(f"{a.kind}{'' if a.kind in SPECIAL else ' by ' + a.by}: {data['score']}  ({data['progress']}, {data['updated']})")
    if not rows:
        print("nothing matches")
        return
    w = max(len(c["name"]) for c in rows)
    dash = lambda v: "-" if v is None else v
    def trend(c):
        t = c.get("trend") or {}
        if not t.get("signal"):
            return "-"
        return {"rising": "+", "falling": "-", "stable": "~"}[t["signal"]] + f"{abs(t['pricePct'])}%"
    print(f"{'#':>3}  {'name':<{w}}  {'score':>8}  {'price':>5}  {'buy':>5}  {'avg':>6}  {'/day':>6}  {'trend':>6}  {'own':>5}  action")
    for i, c in enumerate(rows, 1):
        print(f"{i:>3}  {c['name']:<{w}}  {c[field]:>8}  {dash(c.get('lowestPrice')):>5}  "
              f"{dash(c.get('bestBuy')):>5}  {dash(c.get('averagePrice')):>6}  "
              f"{c.get('tradesPerDay', 0):>6}  {trend(c):>6}  {c.get('yourCopies', ''):>5}  {c['action']}")


def cmd_tui(a):
    import tui  # textual is only needed for this command
    tui.run()


def cmd_run(a):
    cmd_fetch(a)
    cmd_extract(a)
    cmd_prices(a)
    cmd_sets(a)
    cmd_relics(a)
    print("\ndone. try: plat-scout tui")


def main():
    p = argparse.ArgumentParser(prog="plat-scout", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    s = sub.add_parser("fetch", help="download your inventory (game must be running)")
    s.add_argument("--auth", help="use this '?accountId=...&nonce=...' instead of reading the game")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("extract", help="split the inventory into mods.json, arcanes.json and items.json")
    s.set_defaults(func=cmd_extract)

    for name, func, text in (("prices", cmd_prices, "scan warframe.market (~15 min mods, ~3 min arcanes)"),
                             ("run", cmd_run, "fetch + extract + prices in one go")):
        s = sub.add_parser(name, help=text)
        s.add_argument("kind", nargs="?", default="all", choices=[*KINDS, "all"])
        s.add_argument("--all-sellers", action="store_true", help="count offline sellers too")
        s.set_defaults(func=func, auth=None)

    s = sub.add_parser("sets", help="prime sets you own parts of: complete them or not?")
    s.set_defaults(func=cmd_sets)

    s = sub.add_parser("relics", help="relic crack value vs selling (needs prices relics first)")
    s.set_defaults(func=cmd_relics)

    s = sub.add_parser("rank", help="rebuild the rankings from saved prices (no API calls)")
    s.add_argument("kind", nargs="?", default="all", choices=[*KINDS, "all"])
    s.set_defaults(func=cmd_rank)

    s = sub.add_parser("top", help="show the best sell candidates in the terminal")
    s.add_argument("kind", nargs="?", default="mods", choices=[*KINDS, *SPECIAL])
    s.add_argument("--by", choices=list(RANKINGS), default="owned",
                   help="market = price x trades/day, owned = plat from your copies (default), "
                        "volume = copies x trades/day, ducats = parts worth more at Baro, "
                        "crack = relics: sell vs crack vs refine")
    s.add_argument("-n", type=int, default=15, help="how many rows (default 15)")
    s.add_argument("--quick", action="store_true", help="hide options that need ranking up or fusing")
    s.set_defaults(func=cmd_top)

    s = sub.add_parser("tui", help="browse the rankings in an interactive terminal UI")
    s.set_defaults(func=cmd_tui)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
