"""Buying on warframe.market: a cart, the best sellers per item, whisper text.

The cart lives in data/cart.json. Sellers come from the public order book:
online or in-game sellers of the same rank / refinement, cheapest first, in-game
before online, then by reputation.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import extract
import prices

DATA = Path(__file__).resolve().parent / "data"
CART = DATA / "cart.json"


# ---- cart -----------------------------------------------------------------
def load_cart():
    try:
        return json.loads(CART.read_text())
    except (OSError, ValueError):
        return []


def save_cart(cart):
    DATA.mkdir(exist_ok=True)
    CART.write_text(json.dumps(cart, indent=2, ensure_ascii=False))


def add(cart, item, rank=None, subtype=None, qty=1, max_price=None):
    """Add an item (from search()) to the cart, merging with an identical entry."""
    for e in cart:
        if (e["slug"], e.get("rank"), e.get("subtype")) == (item["slug"], rank, subtype):
            e["qty"] += qty
            e["maxPrice"] = max_price or e.get("maxPrice")
            break
    else:
        cart.append({"slug": item["slug"], "name": item["name"], "rank": rank,
                     "subtype": subtype, "qty": qty, "maxPrice": max_price, "sellerIndex": 0})
    save_cart(cart)
    return cart


# ---- items ----------------------------------------------------------------
_items = None


def all_items():
    global _items
    if _items is None:
        _items = sorted(({"slug": i["slug"], "name": i["i18n"]["en"]["name"],
                          "maxRank": i.get("maxRank"), "subtypes": i.get("subtypes", []),
                          "tags": i.get("tags", [])}
                         for i in extract.load_market().values()), key=lambda i: i["name"])
    return _items


def search(text, limit=12):
    """Items whose name contains every word typed; names starting with it first."""
    words = text.lower().split()
    if not words:
        return []
    hits = [i for i in all_items() if all(w in i["name"].lower() for w in words)]
    hits.sort(key=lambda i: (not i["name"].lower().startswith(text.lower().strip()), len(i["name"])))
    return hits[:limit]


def complete(text):
    """Closest item name that starts with what's typed (for inline completion)."""
    t = text.lower()
    if not t.strip():
        return None
    starts = [i["name"] for i in all_items() if i["name"].lower().startswith(t)]
    return min(starts, key=len) if starts else None


# ---- sellers --------------------------------------------------------------
STATUS_ORDER = {"ingame": 0, "online": 1}


def sellers(slug, rank=None, subtype=None):
    """Online sellers of this item / rank / refinement, best first."""
    book = prices.get(f"/orders/item/{slug}") or []
    out = []
    for x in book:
        user = x.get("user", {})
        if x["type"] != "sell" or not x.get("visible", True) or user.get("status") not in STATUS_ORDER:
            continue
        if rank is not None and x.get("rank", 0) != rank:
            continue
        if subtype is not None and x.get("subtype") != subtype:
            continue
        out.append({"name": user.get("ingameName", "?"), "price": x["platinum"],
                    "quantity": x.get("quantity", 1), "reputation": user.get("reputation", 0),
                    "status": user.get("status")})
    out.sort(key=lambda s: (s["price"], STATUS_ORDER[s["status"]], -s["reputation"]))
    return out


def item_label(entry):
    """How warframe.market names the item in whispers."""
    label = entry["name"]
    if entry.get("rank") is not None:
        label += f" (rank {entry['rank']})"
    if entry.get("subtype") and entry["subtype"] not in ("intact", "regular"):
        label += f" ({entry['subtype']})"
    return label


def whisper(seller, entry):
    """The message warframe.market itself copies when you click Buy."""
    qty = min(entry.get("qty", 1), seller.get("quantity", 1))
    if qty > 1:
        what = f'{qty} x "{item_label(entry)}" for {seller["price"]} platinum each'
    else:
        what = f'"{item_label(entry)}" for {seller["price"]} platinum'
    return f"/w {seller['name']} Hi! I want to buy: {what}. (warframe.market)"


# ---- clipboard ------------------------------------------------------------
def copy(text):
    """Copy with the system clipboard tool; False if none worked (caller falls
    back to the terminal clipboard)."""
    tools = []
    if os.environ.get("WAYLAND_DISPLAY") and shutil.which("wl-copy"):
        tools.append(["wl-copy"])
    if os.environ.get("DISPLAY"):
        if shutil.which("xclip"):
            tools.append(["xclip", "-selection", "clipboard"])
        if shutil.which("xsel"):
            tools.append(["xsel", "--clipboard", "--input"])
    for cmd in tools:
        try:
            subprocess.run(cmd, input=text.encode(), check=True, timeout=5)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False
