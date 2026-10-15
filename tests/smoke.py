"""Headless smoke test of the TUI: every tab, every ranking, cursor moves,
the detail panel, and the review / listings screens. No network writes.

  ~/.local/share/uv/tools/plat-scout/bin/python tests/smoke.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import buying  # noqa: E402
import listing  # noqa: E402
import tui  # noqa: E402

# never touch the network or real orders from the smoke test
listing.load_token = lambda: "x"
listing.me = lambda token=None: {"ingameName": "Smoke", "id": "me"}
listing.my_orders = lambda: []
listing.post = lambda p: None
listing.watch = lambda: []
buying.sellers = lambda slug, rank=None, subtype=None: []


async def main():
    app = tui.PlatScout()
    async with app.run_test(size=(170, 48)) as pilot:
        await pilot.pause()
        for key, kind in tui.TABS:
            await pilot.press(key)
            await pilot.pause()
            n = len(app.rank_order()) if kind not in tui.SPECIAL and kind != "buy" else 1
            for _ in range(n):
                for _ in range(3):
                    await pilot.press("down")
                await pilot.pause()
                detail = str(app.query_one("#detail").render())
                cols = [str(c.label).strip() for c in app.query_one("#table").columns.values()]
                print(f"{key} {kind:<8} {app.ranking:<7} rows {len(app.rows):>3} cols {len(cols):>2} "
                      f"detail {len(detail.splitlines()):>2} lines | {' '.join(cols[2:6])}")
                if kind not in tui.SPECIAL and kind != "buy":
                    await pilot.press("v")
                    await pilot.pause()
        await pilot.press("1")
        await pilot.pause()
        await pilot.press("l")
        await asyncio.sleep(0.5)
        await pilot.pause()
        print("review screen:", type(app.screen).__name__)
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("w")
        await asyncio.sleep(0.5)
        await pilot.pause()
        print("watch screen:", type(app.screen).__name__)
        await pilot.press("escape")
        await pilot.pause()
        print("SMOKE OK")


asyncio.run(main())
