"""Set your warframe.market status to "in game" over its websocket.

The server is the source of truth: after signing in it tells us your current
status, and we only change it when you're not already in game for at least as
long. A status set with a duration stays even after we disconnect, until the
duration runs out (then the server sets you offline / invisible).

Uses the same JWT as listing.py (data/wfm-token).
"""

import asyncio
import json
import time
import uuid
from datetime import datetime

import alerts
import listing

URL = "wss://ws.warframe.market/socket"
DEFAULT_HOURS = 3  # change with "ingameHours" in data/settings.json (max 6)


def hours():
    return max(1 / 60, min(6, float(alerts.settings().get("ingameHours", DEFAULT_HOURS))))


def _msg(route, payload=None):
    m = {"route": route, "id": uuid.uuid4().hex}
    if payload is not None:
        m["payload"] = payload
    return json.dumps(m)


async def _recv_until(ws, routes, timeout):
    """Next message whose route is in routes (others are skipped), or None."""
    deadline = time.monotonic() + timeout
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            return None
        try:
            raw = await asyncio.wait_for(ws.recv(), left)
        except asyncio.TimeoutError:
            return None
        try:
            m = json.loads(raw)
        except ValueError:
            continue
        if m.get("route") in routes:
            return m


async def _set_ingame(token, seconds):
    from websockets.asyncio.client import connect  # only needed for this feature
    async with connect(URL, subprotocols=["wfm"], open_timeout=15,
                       additional_headers={"User-Agent": "plat-scout/1.0"}) as ws:
        await ws.send(_msg("@wfm|cmd/auth/signIn", {"token": token}))
        m = await _recv_until(ws, {"@wfm|cmd/auth/signIn:ok", "@wfm|cmd/auth/signIn:error"}, 15)
        if not m or m["route"].endswith(":error"):
            raise listing.WfmError(f"websocket sign-in failed: {(m or {}).get('payload', 'no answer')}")
        current = await _recv_until(ws, {"@wfm|event/status/set"}, 4)
        if current:
            p = current.get("payload") or {}
            until = p.get("statusUntil")
            left = (datetime.fromisoformat(until.replace("Z", "+00:00")).timestamp() - time.time()
                    if until else float("inf"))
            if p.get("status") == "ingame" and left >= seconds - 60:
                return "already in game"
        await ws.send(_msg("@wfm|cmd/status/set", {"status": "ingame", "duration": int(seconds)}))
        m = await _recv_until(ws, {"@wfm|cmd/status/set:ok", "@wfm|cmd/status/set:error"}, 15)
        if not m or m["route"].endswith(":error"):
            raise listing.WfmError(f"couldn't set status: {(m or {}).get('payload', 'no answer')}")
        return f"in game for {seconds / 3600:g} h"


def set_ingame(seconds=None):
    """Blocking: set 'in game' (default: hours() hours). Returns a short result text."""
    token = listing.load_token()
    if not token:
        raise listing.WfmError("no warframe.market token saved")
    return asyncio.run(_set_ingame(token, int(seconds or hours() * 3600)))
