"""Follow Warframe's EE.log and turn trade-related lines into events.

Read-only. What the log has (and what plat-scout uses):
  IRC out: PRIVMSG <name> :<text>              -> whisper_sent (your own whispers)
  ChatRedux::AddTab ... channel name: F<name>  -> whisper_received, when it isn't
                                                  followed by your own whisper
  GameInviteReceived from <name>               -> invite
  description=<name> wants to trade with you   -> trade_request
  You are offering: ... will receive from <name> the following: ...
                                               -> trade_offer (items both ways)
  The trade was successful!                    -> trade_done
Incoming whisper *text* is not in the log.

Override the log location with PLAT_SCOUT_EE_LOG.
"""

import os
import re
import time
from pathlib import Path

DEFAULT_LOG = (Path.home() / ".local/share/Steam/steamapps/compatdata/230410/pfx/drive_c/"
               "users/steamuser/AppData/Local/Warframe/EE.log")
SENT = re.compile(r"IRC out: PRIVMSG (\S+) :(.*)")
TAB = re.compile(r"channel name: F(\S+) to index")
INVITE = re.compile(r"GameInviteReceived from (\S+)")
TRADE_REQUEST = re.compile(r"description=(\S+) wants to trade with you")
OFFER_START = "You are offering:"
OFFER_END = ", title="
RECEIVE = re.compile(r"and will receive from (\S+) the following:")
DONE = "The trade was successful!"
QTY = re.compile(r"^(.*?)\s+x\s*(\d+)$")
ICONS = re.compile("[\ue000-\uf8ff]")  # in-game glyphs: platform icon after names, rank stars
OWN_WHISPER_WINDOW = 3.0  # a tab followed this fast by your whisper is yours, not incoming


def log_path():
    return Path(os.environ.get("PLAT_SCOUT_EE_LOG") or DEFAULT_LOG)


def clean(text):
    """Drop the game's private-use glyphs (platform icon, rank stars) and spaces."""
    return ICONS.sub("", text).strip()


def parse_items(lines):
    """['Platinum x 35', 'Arcane Persistence '] -> [('Platinum', 35), ('Arcane Persistence', 1)]"""
    items = []
    for line in lines:
        line = clean(line).rstrip(",").strip()
        if not line:
            continue
        m = QTY.match(line)
        items.append((m[1].strip(), int(m[2])) if m else (line, 1))
    return items


def platinum(items):
    return sum(q for name, q in items if name.lower() == "platinum")


def goods(items):
    return [(name, q) for name, q in items if name.lower() != "platinum"]


class LogWatcher:
    def __init__(self, path=None, from_start=False):
        self.path = Path(path) if path else log_path()
        try:
            self.pos = 0 if from_start else self.path.stat().st_size  # don't replay old sessions
        except OSError:
            self.pos = 0
        self.partial = ""
        self.block = None       # lines of a trade dialog being read
        self.offer = None       # last parsed trade_offer, for trade_done
        self.pending_tabs = {}  # name -> time the tab opened, until we know who wrote first
        self.whispered = set()  # names you whispered this session

    def exists(self):
        return self.path.exists()

    def poll(self, now=None):
        """New events since the last call."""
        now = now or time.time()
        events = []
        try:
            size = self.path.stat().st_size
        except OSError:
            return events
        if size < self.pos:  # game restarted: a new log
            self.pos, self.partial, self.block = 0, "", None
            self.pending_tabs.clear()
            self.whispered.clear()
        if size > self.pos:
            with open(self.path, "rb") as f:
                f.seek(self.pos)
                data = f.read(size - self.pos)
            self.pos = size
            lines = (self.partial + data.decode("utf-8", "replace")).split("\n")
            self.partial = lines.pop()  # keep an unfinished last line for next time
            for line in lines:
                events += self.feed(line.rstrip("\r"), now)
        # tabs nobody of yours followed: someone whispered you first
        for name, opened in list(self.pending_tabs.items()):
            if now - opened >= OWN_WHISPER_WINDOW:
                del self.pending_tabs[name]
                events.append(event("whisper_received", name, now))
        return events

    def feed(self, line, now):
        if self.block is not None:
            self.block.append(line)
            return self.finish_offer(now) if OFFER_END in line else []
        if OFFER_START in line:
            self.block = [line.split(OFFER_START, 1)[1]]
            return self.finish_offer(now) if OFFER_END in line else []
        m = SENT.search(line)
        if m:
            name = m[1]
            self.whispered.add(name.lower())
            self.pending_tabs.pop(name, None)
            return [event("whisper_sent", name, now, text=m[2].strip())]
        m = TAB.search(line)
        if m:
            if m[1].lower() not in self.whispered:
                self.pending_tabs.setdefault(m[1], now)
            return []
        m = INVITE.search(line)
        if m:
            return [event("invite", m[1], now)]
        m = TRADE_REQUEST.search(line)
        if m:
            return [event("trade_request", m[1], now)]
        if DONE in line:
            offer, self.offer = self.offer, None
            return [event("trade_done", offer["name"] if offer else None, now, offer=offer)]
        return []

    def finish_offer(self, now):
        text = "\n".join(self.block).split(OFFER_END, 1)[0]
        self.block = None
        m = RECEIVE.search(text)
        if not m:
            return []
        offered = parse_items(text[:m.start()].splitlines())
        received = parse_items(text[m.end():].splitlines())
        name = clean(m[1])
        self.offer = {"name": name, "offered": offered, "received": received}
        return [event("trade_offer", name, now, offered=offered, received=received)]


def event(kind, name, now, **extra):
    return {"kind": kind, "name": clean(name) if name else name, "time": now, **extra}
