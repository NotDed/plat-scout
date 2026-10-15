"""Headless test of the BUY tab: add an item, cycle sellers, copy, bought, remove.
Sellers and the clipboard are stubbed and the cart is a throwaway file.

  ~/.local/share/uv/tools/plat-scout/bin/python tests/buy_flow.py
"""
import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import buying  # noqa: E402
import tui  # noqa: E402

TMP = ROOT / "data" / "test-tmp"
TMP.mkdir(parents=True, exist_ok=True)
buying.CART = TMP / "cart.json"
buying.CART.unlink(missing_ok=True)

FAKE = [{"name": "Alpha", "price": 30, "quantity": 2, "reputation": 50, "status": "ingame"},
        {"name": "Bravo", "price": 31, "quantity": 1, "reputation": 5, "status": "online"},
        {"name": "Charlie", "price": 45, "quantity": 1, "reputation": 90, "status": "ingame"}]
buying.sellers = lambda slug, rank=None, subtype=None: [dict(s) for s in FAKE]
copied = []
buying.copy = lambda text: copied.append(text) or True


def row(app):
    return app.rows[app.query_one("#table").cursor_row]


async def settle(pilot, app, cond, tries=40):
    for _ in range(tries):
        await asyncio.sleep(0.1)
        await pilot.pause()
        if cond():
            return True
    return False


async def main():
    app = tui.PlatScout()
    async with app.run_test(size=(170, 48)) as pilot:
        await pilot.pause()
        await pilot.press("6")
        await pilot.pause()
        print("empty cart rows:", len(app.rows))

        await pilot.press("a")
        await pilot.pause()
        await pilot.press(*"serr")
        await asyncio.sleep(0.3)
        await pilot.pause()
        box = app.screen.query_one("#add-q")
        print("typed 'serr' -> grey completion:", repr(box._suggestion))
        await pilot.press("tab")
        await pilot.pause()
        print("after Tab the box says:", repr(box.value))
        box.value = "nekros p"
        await asyncio.sleep(0.3)
        await pilot.pause()
        await pilot.press("right")
        await pilot.pause()
        print("'nekros p' + right arrow ->", repr(box.value), "| tab still:", app.kind)
        box.value = "serration"
        await pilot.pause()
        print("add screen:", type(app.screen).__name__, "| first hit:", app.screen.hits[0]["name"])
        await pilot.press("enter")          # pick Serration
        await pilot.pause()
        await pilot.press("up", "up")       # qty -> sub -> rank field
        rank = app.screen.query_one("#add-rank")
        rank.value = "10"
        await pilot.press("down", "down")   # back to qty
        qty = app.screen.query_one("#add-qty")
        qty.value = "2"
        await pilot.press("enter")
        await pilot.pause()
        ok = await settle(pilot, app, lambda: app.rows and app.rows[0].get("current"))
        r = row(app)
        print("cart row:", r["name"], "| qty", r["qty"], "| seller", r["seller"], r["sellerPos"],
              "| total", r["score"], "| sellers loaded:", ok)

        await pilot.press("enter")
        await pilot.pause()
        print("copied:", copied[-1] if copied else None)

        await pilot.press("greater_than_sign")
        await pilot.pause()
        print("after >:", row(app)["seller"], row(app)["sellerPos"])
        await pilot.click("#buy-next")
        await pilot.pause()
        print("after Next button:", row(app)["seller"], row(app)["sellerPos"])
        await pilot.press("less_than_sign")
        await pilot.pause()
        print("after <:", row(app)["seller"], row(app)["sellerPos"])

        await pilot.press("b")
        await pilot.pause()
        print("after bought: qty", row(app)["qty"], "| seller reset to", row(app)["seller"])
        await pilot.press("delete")
        await pilot.pause()
        print("after remove rows:", len(app.rows))
        print("BUY FLOW OK")
    shutil.rmtree(TMP)


asyncio.run(main())
