"""My listings screen: move, edit price/qty, hide/show, reprice; and posting sets
you in game. All warframe.market calls are stubbed.

  ~/.local/share/uv/tools/plat-scout/bin/python tests/listings_flow.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import listing  # noqa: E402
import status  # noqa: E402
import tui  # noqa: E402

ORDERS = [
    {"id": "o1", "name": "Lethal Momentum", "rank": 0, "subtype": None, "visible": True, "quantity": 2,
     "myPrice": 5, "lowestOther": 5, "undercutBy": 0, "status": "cheapest", "slug": "lethal_momentum"},
    {"id": "o2", "name": "Axi A22 Relic", "rank": None, "subtype": "intact", "visible": True, "quantity": 9,
     "myPrice": 8, "lowestOther": 5, "undercutBy": 3, "status": "undercut", "slug": "axi_a22_relic"},
    {"id": "o3", "name": "Chilling Claws", "rank": 5, "subtype": None, "visible": False, "quantity": 7,
     "myPrice": 8, "lowestOther": None, "undercutBy": 0, "status": "hidden", "slug": "chilling_claws"},
]
calls, ingame = [], []
listing.watch = lambda: [dict(o) for o in ORDERS]
listing.edit_order = lambda oid, **f: calls.append(("edit", oid, f))
listing.apply_reprice = lambda r, price: calls.append(("reprice", r["id"], price))
listing.log = lambda *a, **k: None
listing.load_token = lambda: "x"
listing.me = lambda token=None: {"ingameName": "Me", "id": "me"}
listing.my_orders = lambda: []
listing.post = lambda p: calls.append(("post", p["name"]))
status.set_ingame = lambda seconds=None: ingame.append(seconds) or "in game for 3 h"


async def until(pilot, cond, tries=40):
    for _ in range(tries):
        await asyncio.sleep(0.1)
        await pilot.pause()
        if cond():
            return


def note(app):
    return app.screen.note.replace("[#3ddc84]", "").replace("[/]", "").replace("[#8a93a6]", "")


async def main():
    app = tui.PlatScout()
    async with app.run_test(size=(170, 48)) as pilot:
        await pilot.pause()
        await pilot.press("w")
        await until(pilot, lambda: getattr(app.screen, "rows", None))
        scr = app.screen
        print("rows:", [r["name"] for r in scr.rows], "| picked:", scr.current()["name"])

        await pilot.press("e")
        await pilot.pause()
        print("edit form open, focus:", type(app.focused).__name__, "| prefilled:",
              scr.query_one("#edit-price").value, scr.query_one("#edit-qty").value)
        scr.query_one("#edit-price").value = "7"
        await pilot.press("tab")
        scr.query_one("#edit-qty").value = "1"
        await pilot.press("enter")
        await until(pilot, lambda: calls)
        print("edit ->", calls[-1], "|", note(app), "| ingame calls:", len(ingame))

        await pilot.press("down", "down", "h")
        await until(pilot, lambda: len(calls) >= 2)
        print("hide/show on", scr.current()["name"], "->", calls[-1], "| ingame calls:", len(ingame))

        await pilot.press("up", "h")
        await until(pilot, lambda: len(calls) >= 3)
        print("hide", calls[-1], "| ingame unchanged:", len(ingame) == 2)

        await pilot.press("y")
        await until(pilot, lambda: len(calls) >= 4)
        print("reprice ->", calls[-1], "| ingame calls:", len(ingame))

        await until(pilot, lambda: not scr.busy and len(ingame) >= 3)
        await pilot.press("e")
        await pilot.pause()
        print("form open:", scr.query_one("#edit-form").display)
        await pilot.press("escape")
        await pilot.pause()
        print("esc closes the form first, screen still:", type(app.screen).__name__)
        await pilot.press("escape")
        await pilot.pause()

        # posting from the review screen also goes in game
        await pilot.press("f", "l")
        await until(pilot, lambda: getattr(app.screen, "plans", None))
        await pilot.press("y")
        await until(pilot, lambda: any(c[0] == "post" for c in calls))
        await until(pilot, lambda: len(ingame) >= 4)
        print("post ->", [c for c in calls if c[0] == "post"], "| ingame calls:", len(ingame))
        print("LISTINGS FLOW OK")


asyncio.run(main())
