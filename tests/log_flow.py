"""The TUI following a (fake) game log: buying and selling, start to finish.
Sounds, warframe.market calls and sellers are stubbed; cart and log are temp files.

  ~/.local/share/uv/tools/plat-scout/bin/python tests/log_flow.py
"""
import asyncio
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import alerts  # noqa: E402
import buying  # noqa: E402
import gamelog  # noqa: E402
import listing  # noqa: E402
import tui  # noqa: E402

TMP = ROOT / "data" / "test-tmp"
TMP.mkdir(parents=True, exist_ok=True)
buying.CART = TMP / "cart.json"
buying.DATA = TMP  # purchases / sales records go here too
LOG = TMP / "EE.log"
LOG.write_text("")

heard = []
alerts.alert = lambda kind, title, body="": heard.append((kind, title)) or True
buying.sellers = lambda slug, rank=None, subtype=None: [
    {"name": "Gomhera", "price": 35, "quantity": 1, "reputation": 30, "status": "ingame"},
    {"name": "Other", "price": 36, "quantity": 1, "reputation": 3, "status": "online"}]
closed = []
listing.load_token = lambda: "x"
listing.sold_plan = lambda gave: [{"item": "Lethal Momentum", "qty": 2,
                                   "order": {"id": "o1", "quantity": 2, "platinum": 5}}]
listing.close_order = lambda oid, qty: closed.append((oid, qty))
listing.log = lambda *a, **k: None

items = {i["slug"]: i for i in buying.all_items()}
buying.add([], items["arcane_persistence"], 5, None, 1)

GLYPH = ""
LINES = {
    "whisper": [
        "41080.001 Script [Info]: ChatRedux.lua: ChatRedux::AddTab: Adding tab with channel name: FGomhera to index 7",
        '41082.652 Net [Info]: 41082.652 Net [Info]: IRC out: PRIVMSG Gomhera :Hi! I want to buy: '
        '"Arcane Persistence (rank 5)" for 35 platinum. (warframe.market)'],
    "invite": ["41090.000 Sys [Info]: LotusProfileData::GameInviteReceived from Gomhera to session 6ad0"],
    "bought": [
        "41158.000 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Are you sure you want to "
        "accept this trade? You are offering:", "Platinum x 35", "",
        f"and will receive from Gomhera{GLYPH} the following:",
        "Arcane Persistence , title= leftItem=/Menu/Confirm_Item_Ok)",
        "41159.000 Script [Info]: Dialog.lua: Dialog::CreateOk(description=The trade was successful!, title=)"],
    "buyer whispers": [
        "50000.000 Script [Info]: ChatRedux.lua: ChatRedux::AddTab: Adding tab with channel name: FBuyerGuy to index 8"],
    "sold": [
        "50100.000 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Are you sure you want to "
        "accept this trade? You are offering:", "Lethal Momentum x 2", "",
        "and will receive from BuyerGuy the following:", "Platinum x 10 , title= leftItem=)",
        "50101.000 Script [Info]: Dialog.lua: Dialog::CreateOk(description=The trade was successful!, title=)"],
}


def write(step):
    with open(LOG, "a") as f:
        f.write("\n".join(LINES[step]) + "\n")


async def wait(pilot, cond, seconds=8):
    for _ in range(int(seconds * 10)):
        await asyncio.sleep(0.1)
        await pilot.pause()
        if cond():
            return True
    return False


def row(app):
    return app.rows[0] if app.rows else {}


async def main():
    app = tui.PlatScout()
    async with app.run_test(size=(170, 48)) as pilot:
        app.game = gamelog.LogWatcher(LOG)
        await pilot.press("6")
        await wait(pilot, lambda: row(app).get("current"))
        print("cart:", row(app)["name"], "|", row(app)["action"])

        write("whisper")
        await wait(pilot, lambda: row(app).get("state") == "waiting")
        print("after whisper:", row(app)["action"])

        write("invite")
        await wait(pilot, lambda: row(app).get("state") == "answered")
        print("after invite:", row(app)["action"], "| alert:", heard[-1])

        write("bought")
        await wait(pilot, lambda: not app.rows)
        print("after trade: cart rows", len(app.rows), "| alert:", heard[-1],
              "| purchases logged:", (TMP / "purchases.jsonl").exists())

        # no answer: a whisper 6 minutes ago
        buying.add(buying.load_cart(), items["serration"], 10, "regular", 1)
        cart = buying.load_cart()
        cart[0].update(whisperedTo="Slowpoke", whisperedAt=time.time() - 360, answered=False)
        buying.save_cart(cart)
        app.load_if_buy()
        await wait(pilot, lambda: heard and heard[-1][0] == "bell")
        print("no answer:", row(app)["action"], "| alert:", heard[-1])
        await pilot.press("greater_than_sign")
        await pilot.pause()
        print("after >:", row(app)["seller"], "|", row(app)["action"])

        write("buyer whispers")
        await wait(pilot, lambda: app.whispers)
        print("someone whispered:", heard[-1], "| header:", app.game_line())

        write("sold")
        await wait(pilot, lambda: type(app.screen).__name__ == "CloseSoldScreen")
        await asyncio.sleep(0.5)
        await pilot.pause()
        print("sale alert:", heard[-1], "| screen:", type(app.screen).__name__)
        await pilot.press("y")
        await wait(pilot, lambda: closed)
        print("closed on warframe.market (stubbed):", closed)
        await pilot.press("escape")
        await pilot.pause()
        print("LOG FLOW OK")
    shutil.rmtree(TMP)


asyncio.run(main())
