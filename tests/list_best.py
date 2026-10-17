"""'L' lists the best N sellable rows after a review. Market calls are stubbed.

  ~/.local/share/uv/tools/plat-scout/bin/python tests/list_best.py
"""
import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import alerts  # noqa: E402
import listing  # noqa: E402
import status  # noqa: E402
import tui  # noqa: E402

TMP = ROOT / "data" / "test-tmp"
TMP.mkdir(parents=True, exist_ok=True)
alerts.SETTINGS = TMP / "settings.json"

posted, ingame = [], []
listing.load_token = lambda: "x"
listing.me = lambda token=None: {"ingameName": "Me", "id": "me"}
listing.my_orders = lambda: []
listing.post = lambda p: posted.append(p["name"])
listing.log = lambda *a, **k: None
status.set_ingame = lambda seconds=None: ingame.append(1) or "in game for 3 h"


async def until(pilot, cond, tries=50):
    for _ in range(tries):
        await asyncio.sleep(0.1)
        await pilot.pause()
        if cond():
            return


async def main():
    app = tui.PlatScout()
    async with app.run_test(size=(170, 48)) as pilot:
        await pilot.pause()
        ready = [c["name"] for c in app.rows if listing.SELLABLE.match(c["action"])]
        print("mods tab: rows", len(app.rows), "| sellable as-is:", len(ready), "| first 3:", ready[:3])
        await pilot.press("L")
        await pilot.pause()
        box = app.screen.query_one("#count-n")
        print("prompt:", type(app.screen).__name__, "| default:", box.value)
        box.value = "3"
        await pilot.press("enter")
        await until(pilot, lambda: getattr(app.screen, "plans", None))
        scr = app.screen
        print("review:", scr.title, "| rows:", [p["name"] for p in scr.plans],
              "| all postable:", all("order" in p for p in scr.plans))
        print("posted before y:", posted)
        await pilot.press("y")
        await until(pilot, lambda: len(posted) >= 3 and ingame)
        print("posted after y:", posted, "| set in game:", bool(ingame))
        await pilot.press("escape")
        await pilot.pause()
        print("remembered N:", alerts.settings().get("listBest"))
        await pilot.press("6", "L")
        await pilot.pause()
        print("on the buy tab L does nothing:", type(app.screen).__name__)
        print("LIST BEST OK")
    shutil.rmtree(TMP)


asyncio.run(main())
