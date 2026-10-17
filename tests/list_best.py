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
        await pilot.press("L")
        await pilot.pause()
        scr = app.screen
        print("prompt:", type(scr).__name__, "| ticked:", scr.chosen(), "| default N:",
              scr.query_one("#count-n").value)
        print("info:", str(scr.query_one("#count-info").render()))
        await pilot.click("#src-relics")
        await pilot.pause()
        print("after ticking relics:", scr.chosen(), "|", str(scr.query_one("#count-info").render()))
        scr.query_one("#count-n").value = "8"
        scr.query_one("#count-n").focus()
        await pilot.press("enter")
        await until(pilot, lambda: getattr(app.screen, "plans", None))
        rev = app.screen
        print("review:", rev.title)
        for c in rev.rows:
            print(f"   {c['category']:<8} {c['listValue']:>5}p  {c['name']}")
        print("all postable:", all("order" in p for p in rev.plans), "| posted before y:", posted)
        await pilot.press("y")
        await until(pilot, lambda: len(posted) >= 8 and ingame)
        print("posted after y:", len(posted), "| set in game:", bool(ingame))
        await pilot.press("escape")
        await pilot.pause()
        print("remembered:", alerts.settings().get("listBest"), alerts.settings().get("listBestKinds"))
        print("LIST BEST OK")
    shutil.rmtree(TMP)


asyncio.run(main())
