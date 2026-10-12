#!/usr/bin/env python3
"""plat-scout: find which Warframe mods and arcanes are worth selling."""

import argparse
import json
import sys
from pathlib import Path

import extract
import fetch_inventory
import prices

DATA = Path(__file__).resolve().parent / "data"
KINDS = {"mods": ("mods.json", ""), "arcanes": ("arcanes.json", "arcane-")}
RANKINGS = {  # --by value -> (file suffix, field shown as "score")
    "market": ("sell-candidates.json", "score"),
    "owned": ("sell-candidates-owned.json", "potentialPlat"),
    "volume": ("sell-candidates-volume.json", "volumeScore"),
}


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


def cmd_top(a):
    name, field = RANKINGS[a.by]
    path = DATA / (KINDS[a.kind][1] + name)
    need(path, f"prices {a.kind}")
    data = json.load(open(path))
    rows = data["candidates"]
    if a.quick:
        rows = [c for c in rows if not c["action"].startswith(("rank to", "fuse"))]
    rows = rows[:a.n]

    print(f"{a.kind} by {a.by}: {data['score']}  ({data['progress']}, {data['updated']})")
    if not rows:
        print("nothing matches")
        return
    w = max(len(c["name"]) for c in rows)
    print(f"{'#':>3}  {'name':<{w}}  {'score':>8}  {'price':>5}  {'avg':>6}  {'/day':>6}  {'own':>4}  action")
    for i, c in enumerate(rows, 1):
        print(f"{i:>3}  {c['name']:<{w}}  {c[field]:>8}  {c['lowestPrice']:>5}  "
              f"{c['averagePrice']:>6}  {c['tradesPerDay']:>6}  {c['yourCopies']:>4}  {c['action']}")


def cmd_tui(a):
    import tui  # textual is only needed for this command
    tui.run()


def cmd_run(a):
    cmd_fetch(a)
    cmd_extract(a)
    cmd_prices(a)
    print("\ndone. try: plat-scout top --quick")


def main():
    p = argparse.ArgumentParser(prog="plat-scout", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="command")

    s = sub.add_parser("fetch", help="download your inventory (game must be running)")
    s.add_argument("--auth", help="use this '?accountId=...&nonce=...' instead of reading the game")
    s.set_defaults(func=cmd_fetch)

    s = sub.add_parser("extract", help="split the inventory into mods.json and arcanes.json")
    s.set_defaults(func=cmd_extract)

    for name, func, text in (("prices", cmd_prices, "scan warframe.market (~15 min mods, ~3 min arcanes)"),
                             ("run", cmd_run, "fetch + extract + prices in one go")):
        s = sub.add_parser(name, help=text)
        s.add_argument("kind", nargs="?", default="all", choices=["mods", "arcanes", "all"])
        s.add_argument("--all-sellers", action="store_true", help="count offline sellers too")
        s.set_defaults(func=func, auth=None)

    s = sub.add_parser("rank", help="rebuild the rankings from saved prices (no API calls)")
    s.add_argument("kind", nargs="?", default="all", choices=["mods", "arcanes", "all"])
    s.set_defaults(func=cmd_rank)

    s = sub.add_parser("top", help="show the best sell candidates in the terminal")
    s.add_argument("kind", nargs="?", default="mods", choices=["mods", "arcanes"])
    s.add_argument("--by", choices=list(RANKINGS), default="owned",
                   help="market = price x trades/day, owned = plat from your copies (default), "
                        "volume = copies x trades/day")
    s.add_argument("-n", type=int, default=15, help="how many rows (default 15)")
    s.add_argument("--quick", action="store_true", help="hide options that need ranking up or fusing")
    s.set_defaults(func=cmd_top)

    s = sub.add_parser("tui", help="browse the rankings in an interactive terminal UI")
    s.set_defaults(func=cmd_tui)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
