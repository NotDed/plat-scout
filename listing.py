"""Post sell orders to warframe.market (API v2).

Auth: your warframe.market session token, saved in data/wfm-token (git-ignored).
To get it: log in on warframe.market in your browser, open DevTools (F12) →
Application/Storage → Cookies → https://warframe.market → copy the value of
the "JWT" cookie.

Nothing here posts on its own: the TUI shows a review screen first.
"""

import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import extract

DATA = Path(__file__).resolve().parent / "data"
TOKEN_FILE = DATA / "wfm-token"
API = "https://api.warframe.market/v2"
PRICING = {  # key -> label
    "match": "match lowest online",
    "undercut": "undercut lowest by 1p",
    "average": "average online price",
}
# actions that can be listed as-is (everything else needs work first)
SELLABLE = re.compile(r"^(sell( as rank 0| it|$| \()|sell at rank \d+|complete! sell as a set)")


class WfmError(Exception):
    pass


# ---- token -----------------------------------------------------------------
def load_token():
    try:
        return TOKEN_FILE.read_text().strip() or None
    except OSError:
        return None


def save_token(token):
    token = token.strip().strip('"')
    token = re.sub(r"^(JWT|Bearer)\s+", "", token)  # cookie may carry a prefix
    DATA.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(token)
    TOKEN_FILE.chmod(0o600)
    return token


# ---- http ------------------------------------------------------------------
def call(method, path, body=None, token=None):
    token = token or load_token()
    if not token:
        raise WfmError("no warframe.market token saved")
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                 "Accept": "application/json", "Language": "en", "Platform": "pc",
                 "User-Agent": "plat-scout/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r).get("data")
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            try:
                err = json.load(e).get("error") or {}
            except ValueError:
                err = {}
            msg = ", ".join(err.get("request", [])) or json.dumps(err.get("inputs", {})) or str(e)
            if e.code == 401:
                msg = "token rejected (expired?). Copy a fresh JWT cookie."
            raise WfmError(msg) from None
    raise WfmError("rate limited, try again in a minute")


def me(token=None):
    return call("GET", "/me", token=token)


def my_orders():
    return call("GET", "/orders/my") or []


# ---- turning a candidate row into an order --------------------------------
def plan(rows, pricing="match"):
    """Rows from any ranking -> list of planned listings (nothing is sent)."""
    market = {i["slug"]: i for i in extract.load_market().values()}
    try:
        existing = {(o["itemId"], o.get("rank", 0), o.get("subtype")): o
                    for o in my_orders() if o.get("type") == "sell"}
    except WfmError:
        existing = {}
    plans = []
    for c in rows:
        slug = c.get("url", "").rstrip("/").rsplit("/", 1)[-1]
        item = market.get(slug)
        entry = {"name": c["name"], "action": c["action"]}
        if not SELLABLE.match(c["action"]) or not item:
            plans.append({**entry, "skip": "needs work first" if item else "unknown item"})
            continue
        m = re.search(r"rank (\d+)", c["action"])
        rank = int(m[1]) if m and "rank 0" not in c["action"] else 0
        subtype = c.get("refinement")
        if not subtype and item.get("subtypes"):
            refined = re.search(r"\((exceptional|flawless|radiant)\)$", c["name"])
            subtype = refined[1] if refined else item["subtypes"][0]
        low, avg = c.get("lowestPrice"), c.get("averagePrice")
        if "crackValue" in c:  # relic tab: averagePrice is crack value, not a price
            avg = None
        price = {"match": low, "undercut": (low - 1) if low else None,
                 "average": round(avg) if avg else low}[pricing]
        if not price or price < 1:
            plans.append({**entry, "skip": "no price"})
            continue
        qty = c.get("yourCopies")
        qty = qty if isinstance(qty, int) and qty > 0 else 1
        order = {"itemId": item["id"], "type": "sell", "platinum": int(price),
                 "quantity": qty, "visible": True}
        if item.get("maxRank") is not None and "set" not in item.get("tags", []):
            order["rank"] = rank
        if subtype:
            order["subtype"] = subtype
        if item.get("bulkTradable"):
            order["perTrade"] = 1  # required for bulk items: buyers can take any amount
        old = existing.get((item["id"], order.get("rank", 0), subtype))
        plans.append({**entry, "order": order, "slug": slug,
                      "existing": old and {"id": old["id"], "platinum": old["platinum"],
                                           "quantity": old.get("quantity")}})
    return plans


def log(p, error=None):
    """Append one line per post attempt to data/listing.log."""
    with open(DATA / "listing.log", "a") as f:
        f.write(json.dumps({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "name": p["name"],
                            "order": p.get("order"), "update": bool(p.get("existing")),
                            "error": error}) + "\n")


def post(p):
    """Create the order, or update the price/quantity of the one already listed."""
    if p.get("existing"):
        o = p["order"]
        return call("PATCH", f"/order/{p['existing']['id']}",
                    {"platinum": o["platinum"], "quantity": o["quantity"], "visible": True,
                     **({"perTrade": o["perTrade"]} if "perTrade" in o else {})})
    return call("POST", "/order", p["order"])
