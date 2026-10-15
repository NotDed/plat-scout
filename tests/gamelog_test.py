"""gamelog.LogWatcher against line formats copied from a real EE.log.

  python3 tests/gamelog_test.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import gamelog  # noqa: E402

TMP = ROOT / "data" / "test-tmp"
TMP.mkdir(parents=True, exist_ok=True)
LOG = TMP / "EE.log"

BUY = """41080.001 Script [Info]: ChatRedux.lua: ChatRedux::AddTab: Adding tab with channel name: FGomhera to index 7
41080.002 Script [Info]: ChatRedux.lua: Chat: Filters for FGomhera:
41080.010 Sys [Info]: LotusProfileData::GameInviteReceived from Gomhera to session 6ad04753486adf526f04d314
41082.652 Net [Info]: 41082.652 Net [Info]: IRC out: PRIVMSG Gomhera :Hi! I want to buy: "Arcane Persistence (rank 5)" for 35 platinum. (warframe.market)
41150.000 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Gomhera wants to trade with you. Would you like to join their trading session?, title= leftItem=/Menu/Confirm_Item_Ok, rightItem=/Menu/Confirm_Item_Cancel)
41158.000 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Are you sure you want to accept this trade? You are offering:
Platinum x 35

and will receive from Gomhera the following:
Arcane Persistence , title= leftItem=/Menu/Confirm_Item_Ok, rightItem=/Menu/Confirm_Item_Cancel)
41159.000 Script [Info]: Dialog.lua: Dialog::CreateOk(description=The trade was successful!, title= leftItem=/Menu/Confirm_Item_Ok)
"""

SELL = """50000.000 Script [Info]: ChatRedux.lua: ChatRedux::AddTab: Adding tab with channel name: FBuyerGuy to index 8
50100.000 Script [Info]: Dialog.lua: Dialog::CreateOkCancel(description=Are you sure you want to accept this trade? You are offering:
Lethal Momentum x 2

and will receive from BuyerGuy the following:
Platinum x 10 , title= leftItem=/Menu/Confirm_Item_Ok, rightItem=/Menu/Confirm_Item_Cancel)
50101.000 Script [Info]: Dialog.lua: Dialog::CreateOk(description=The trade was successful!, title= leftItem=/Menu/Confirm_Item_Ok)
"""


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        sys.exit(1)


LOG.write_text("old session line\n")
w = gamelog.LogWatcher(LOG)
check(w.poll(now=0) == [], "starts at the end: old lines are not replayed")

# buying, written in two chunks with a line split across them
half = len(BUY) // 2
with open(LOG, "a") as f:
    f.write(BUY[:half])
ev = w.poll(now=10)
with open(LOG, "a") as f:
    f.write(BUY[half:])
ev += w.poll(now=10.5)
kinds = [e["kind"] for e in ev]
check(kinds == ["invite", "whisper_sent", "trade_request", "trade_offer", "trade_done"],
      f"buy sequence {kinds}")
check(not any(e["kind"] == "whisper_received" for e in w.poll(now=20)),
      "our own whisper's tab is not reported as incoming")
sent = ev[1]
check(sent["name"] == "Gomhera" and '"Arcane Persistence (rank 5)"' in sent["text"], "whisper text parsed")
done = ev[-1]["offer"]
check(gamelog.platinum(done["offered"]) == 35 and gamelog.goods(done["received"]) == [("Arcane Persistence", 1)],
      f"trade contents {done}")

# selling: someone whispers first, then the trade
with open(LOG, "a") as f:
    f.write(SELL)
ev = w.poll(now=100) + w.poll(now=104)
kinds = [e["kind"] for e in ev]
check(kinds == ["trade_offer", "trade_done", "whisper_received"], f"sell sequence {kinds}")
offer = ev[1]["offer"]
check(gamelog.goods(offer["offered"]) == [("Lethal Momentum", 2)] and gamelog.platinum(offer["received"]) == 10,
      f"sale contents {offer}")

# game restart: a new, shorter log
LOG.write_text("41000.000 Net [Info]: IRC out: PRIVMSG Someone :hello\n")
ev = w.poll(now=200)
check([e["kind"] for e in ev] == ["whisper_sent"], "a new log after a restart is read from the start")

LOG.unlink()
print("GAMELOG OK")
