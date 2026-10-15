"""plat-scout TUI: browse the sell rankings, live-reloading while a scan runs."""

import asyncio
import json
import re
import sys
import time
import webbrowser
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual import work
from textual.widgets import DataTable, Footer, Input, ProgressBar, Static

import listing

REPO = Path(__file__).resolve().parent
DATA = REPO / "data"
# matches the progress line prices.py redraws: "[###---] 120/433  27%  ~9m12s left  Serration"
PROGRESS = re.compile(r"(\d+)/(\d+)\s+\d+%\s+~(\S+) left\s+(.*)")
KINDS = {"mods": "", "arcanes": "arcane-", "items": "item-", "relics": "relic-"}  # tab -> file prefix
RANKINGS = {  # key -> (file, score field, label)
    "owned": ("sell-candidates-owned.json", "potentialPlat", "plat from your copies (7 days)"),
    "market": ("sell-candidates.json", "score", "price × trades per day"),
    "volume": ("sell-candidates-volume.json", "volumeScore", "your copies × trades per day"),
    "ducats": ("ducat-candidates.json", "score", "ducats at Baro (worth ≥10 ducats per plat)"),
    "crack": ("candidates.json", "score", "best of sell / crack / refine, × copies"),
}
# tabs with a single ranking of their own, made by extras.py
SPECIAL = {"sets": ("set-candidates.json", "gain from completing the set"),
           "mastery": ("mastery-candidates.json", "unmastered prime sets, lowest true cost per MR point")}
TABS = [("1", "mods"), ("2", "arcanes"), ("3", "items"), ("4", "sets"), ("5", "relics"),
        ("6", "mastery")]
RANK_ORDER = [("owned", "your plat"), ("market", "market"), ("volume", "volume"), ("ducats", "ducats")]
RELIC_RANK_ORDER = [("crack", "sell or crack"), ("owned", "your plat"), ("market", "market"),
                    ("volume", "volume")]
SORT_NONE = 0  # column index 0 ("#") = the ranking's own order
COLUMNS = {  # header row per tab; the 6th column's field differs
    "default": ("#", "Name", "Score", "Price", "Buy", "Avg", "/day", "Own", "Action"),
    "sets": ("#", "Set", "Gain", "Set", "Buy", "Missing", "/day", "Parts", "Action"),
    "relics": ("#", "Relic", "Total", "Sell", "Buy", "Crack", "/day", "Own", "Best action"),
    "mastery": ("#", "Set", "MR pts", "True cost", "Cash", "Full set", "/day", "Parts", "What to do"),
}
NEEDS_WORK = ("rank to", "fuse", "refine", "buy ", "missing")

ASSETS = Path(__file__).resolve().parent / "assets"
SHADES = {"░": "#2b4a6b", "▒": "#5f8fbf", "▓": "#a8d8ff", "█": "#ffffff"}
ARROW = ["     ▄     ",
         "    ▄█▄    ",
         "   ▄███▄   ",
         "  ▄█████▄  ",
         " ▀▀▀███▀▀▀ ",
         "    ███    ",
         "    ███    "]
ARROW_SHADES = ["#b8ffd6", "#7cf0ac", "#5ae896", "#3ddc84", "#2fb36b", "#26935a", "#1f7a4b"]
ARROW_OVERLAP = 6  # columns of the arrow that sit on top of the plat


def plat_cells():
    """The plat as rows of (char, style) cells.

    Preferred: assets/plat-pixels.json (made from assets/plat.png), drawn with
    half blocks so each cell holds two square pixels. Fallback: the shaded
    ASCII art in assets/plat.txt.
    """
    try:
        pixels = json.loads((ASSETS / "plat-pixels.json").read_text())
    except (OSError, ValueError):
        pixels = None
    if pixels:
        rows = []
        for y in range(0, len(pixels) - 1, 2):
            row = []
            for top, bottom in zip(pixels[y], pixels[y + 1]):
                if top and bottom:
                    row.append(("▀", f"{top} on {bottom}"))
                elif top:
                    row.append(("▀", top))
                elif bottom:
                    row.append(("▄", bottom))
                else:
                    row.append((" ", ""))
            rows.append(row)
        return rows
    try:
        plat = (ASSETS / "plat.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    return [[(ch, SHADES.get(ch, "")) for ch in line] for line in plat]


def build_logo():
    """The plat with the green arrow overlapping its bottom-right edge."""
    plat = plat_cells()
    plat_w = max((len(row) for row in plat), default=0)
    ox = max(plat_w - ARROW_OVERLAP, 0)  # arrow column offset
    oy = max(len(plat) - len(ARROW), 0)  # arrow sits at the bottom
    width = max(plat_w, ox + len(ARROW[0]))
    height = max(len(plat), oy + len(ARROW))

    # canvas of (char, style): plat first, then the arrow painted over it
    cells = [[(" ", "")] * width for _ in range(height)]
    for y, row in enumerate(plat):
        for x, cell in enumerate(row):
            cells[y][x] = cell
    for y, line in enumerate(ARROW):
        for x, ch in enumerate(line):
            if ch != " ":
                cells[oy + y][ox + x] = (ch, f"bold {ARROW_SHADES[y]}")

    art = Text(no_wrap=True, overflow="crop")
    for y, row in enumerate(cells):
        for ch, style in row:
            art.append(ch, style=style)
        if y < height - 1:
            art.append("\n")
    return art


TITLE = """[b #9fd8ff]█▀█ █   ▄▀█ ▀█▀[/]   [b #3ddc84]█▀ █▀▀ █▀█ █ █ ▀█▀[/]
[b #9fd8ff]█▀▀ █▄▄ █▀█  █ [/]   [b #3ddc84]▄█ █▄▄ █▄█ █▄█  █ [/]"""


def markup(s):
    """Rich markup -> Text, so Textual keeps the spacing exactly."""
    return Text.from_markup(s, overflow="crop")


class ReviewScreen(ModalScreen):
    """Shows exactly what would be listed on warframe.market; posts only on y."""
    CSS = """
    ReviewScreen { align: center middle; background: #0b0f17 70%; }
    #review { width: 110; height: auto; max-height: 90%; border: round #3ddc84;
              background: #0f1522; padding: 1 2; }
    #review-body { height: auto; }
    #token { margin: 1 0 0 0; border: tall #e3c75b; }
    """
    BINDINGS = [Binding("y", "post", "Post"), Binding("p", "pricing", "Pricing"),
                Binding("escape", "dismiss", "Cancel")]

    def __init__(self, rows):
        super().__init__()
        self.rows, self.pricing, self.plans, self.user, self.busy = rows, "match", [], None, False

    def compose(self) -> ComposeResult:
        with Vertical(id="review"):
            yield Static(id="review-body")
            yield Input(placeholder="paste your warframe.market JWT cookie here, then Enter",
                        password=True, id="token")

    def on_mount(self):
        self.query_one("#token").display = False
        self.refresh_plan()

    @work(exclusive=True, thread=True)
    def refresh_plan(self):
        body = self.query_one("#review-body", Static)
        self.app.call_from_thread(body.update, markup("[#8a93a6]checking your account…[/]"))
        try:
            self.user = listing.me() if listing.load_token() else None
        except listing.WfmError as e:
            self.user = None
            self.app.call_from_thread(self.notify, str(e), severity="error")
        self.plans = listing.plan(self.rows, self.pricing)
        self.app.call_from_thread(self.draw)

    def draw(self):
        token_box = self.query_one("#token")
        token_box.display = not self.user
        if not self.user:
            token_box.focus()
        else:
            self.set_focus(None)  # so y / p / esc reach this screen, not a text box
        who = (f"[b #3ddc84]{self.user.get('ingameName', '?')}[/]" if self.user
               else "[#ff6b6b]not logged in[/] [#8a93a6]- paste your token below[/]")
        lines = [f"[b #e8eefc]Post to warframe.market[/]   as {who}",
                 f"[#8a93a6]pricing:[/] [b #e3c75b]{listing.PRICING[self.pricing]}[/]"
                 f" [#5b6680](p to change)[/]",
                 "", f"[b #9fd8ff]{'item':<34} {'rank':>4} {'qty':>4} {'price':>7}  what happens[/]"]
        ready = 0
        for p in self.plans:
            if "skip" in p:
                lines.append(f"[#5b6680]{p['name'][:34]:<34} {'':>4} {'':>4} {'':>7}"
                             f"  skipped: {p['skip']}[/]")
                continue
            o, old = p["order"], p.get("existing")
            what = (f"[#e3c75b]update {old['platinum']}p -> {o['platinum']}p[/]" if old
                    else "[#3ddc84]new listing[/]")
            if "already maxed" in p["action"] and "spare copy" not in p["action"]:
                what += " [#ff9f5a](not equipped; still yours to keep?)[/]"
            sub = o.get("subtype")
            name = p["name"] + (f" ({sub})" if sub and sub not in ("intact", "regular")
                                and sub not in p["name"] else "")
            lines.append(f"{name[:34]:<34} {o.get('rank', '')!s:>4} {o['quantity']:>4}"
                         f" {o['platinum']:>6}p  {what}")
            ready += 1
        lines += ["", f"[b #3ddc84]y[/] post {ready} listing(s)   [b]p[/] pricing   [b]esc[/] cancel"
                  if self.user and ready else "[b]esc[/] close"]
        self.query_one("#review-body", Static).update(markup("\n".join(lines)))

    def on_input_changed(self, event: Input.Changed):
        event.stop()  # the token must never reach the main screen's search

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        listing.save_token(event.value)
        event.input.value = ""
        self.refresh_plan()

    def action_pricing(self):
        keys = list(listing.PRICING)
        self.pricing = keys[(keys.index(self.pricing) + 1) % len(keys)]
        self.refresh_plan()

    def action_post(self):
        if self.busy:
            return
        if not self.user:
            self.notify("not logged in: paste your JWT token first", severity="error")
        elif not any("order" in p for p in self.plans):
            self.notify("nothing to post: every row here is skipped (see the reason on each row)",
                        severity="warning", timeout=8)
        else:
            self.busy = True
            self.post_all()

    @work(exclusive=True, thread=True)
    def post_all(self):
        results = []
        todo = [p for p in self.plans if "order" in p]
        body = self.query_one("#review-body", Static)
        for n, p in enumerate(todo, 1):
            self.app.call_from_thread(body.update,
                                      markup(f"[#3ddc84]posting {n}/{len(todo)}[/]  {p['name']}"))
            try:
                listing.post(p)
                results.append((p["name"], None))
            except Exception as e:  # show anything that goes wrong, never fail silently
                results.append((p["name"], str(e) or type(e).__name__))
            listing.log(p, results[-1][1])
            time.sleep(0.4)  # stay under the market's rate limit
        ok = sum(1 for _, err in results if err is None)
        lines = [f"[b #e8eefc]Posted {ok} of {len(results)}[/]", ""]
        for name, err in results:
            lines.append(f"[#3ddc84]✓[/] {name}" if err is None else f"[#ff6b6b]✗ {name}: {err}[/]")
        lines += ["", "[#8a93a6]check them at warframe.market → your profile · details in data/listing.log[/]",
                  "[b]esc[/] close"]
        self.app.call_from_thread(body.update, markup("\n".join(lines)))
        self.app.call_from_thread(self.app.notify, f"posted {ok} of {len(results)} listing(s)",
                                  severity="information" if ok == len(results) else "error",
                                  timeout=12)


class PlatScout(App):
    TITLE = "plat-scout"
    CSS = """
    Screen { background: #0b0f17; }
    #top { height: 17; padding: 1 2 0 2; }
    #art { width: 36; }
    #headline { width: 1fr; padding: 4 0 0 2; }
    #search { display: none; margin: 0 2; border: tall #3ddc84; }
    #search.shown { display: block; }
    #body { height: 1fr; padding: 0 1; }
    DataTable { width: 3fr; border: round #2a3550; background: #0b0f17; }
    DataTable:focus { border: round #9fd8ff; }
    DataTable > .datatable--header { background: #141b2b; color: #9fd8ff; text-style: bold; }
    DataTable > .datatable--cursor { background: #1f6f4a; color: #ffffff; }
    #side { width: 44; }
    #detail { height: 1fr; border: round #2a3550; padding: 1 2; }
    #scan { display: none; height: 3; margin: 0 2; padding: 0 1; border: round #3ddc84; }
    #scan.running { display: block; }
    #scan Horizontal { height: 1; }
    #scan ProgressBar { width: 52; }
    #scan Bar > .bar--bar { color: #3ddc84; }
    #scan Bar > .bar--indeterminate { color: #3ddc84; }
    #scan-label { width: 1fr; padding: 0 0 0 2; }
    """
    BINDINGS = [
        *[Binding(key, f"kind('{kind}')", kind.title(), show=False) for key, kind in TABS],
        # priority: the table would otherwise use left/right to scroll sideways
        Binding("left", "step_tab(-1)", "Prev tab", show=False, priority=True),
        Binding("right", "step_tab(1)", "Next tab", show=False, priority=True),
        Binding("v", "next_ranking", "Ranking"),
        Binding("c", "next_sort", "Sort"),
        Binding("C", "flip_sort", "Reverse sort", show=False),
        Binding("f", "toggle_quick", "Sell-now only"),
        Binding("slash", "search", "Search"),
        Binding("o", "open", "Open market"),
        Binding("space", "toggle_select", "Select", show=False),
        Binding("l", "list_selected", "List on market"),
        Binding("s", "scan", "Scan tab"),
        Binding("S", "scan_all", "Scan all", show=False),
        Binding("u", "update_inventory", "Update inventory"),
        Binding("x", "stop_scan", "Stop scan", show=False),
        Binding("escape", "clear_search", "Clear", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.kind, self.ranking, self.quick, self.search_text = "mods", "owned", False, ""
        self.rows, self.meta, self.mtime = [], {}, None
        self.proc = None  # running scan / fetch subprocess
        self.selected = set()  # (name, action) of rows marked with space
        self.sort_col, self.sort_desc = SORT_NONE, True

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            yield Static(build_logo(), id="art")
            yield Static(id="headline")
        with Vertical(id="scan"):
            with Horizontal():
                yield ProgressBar(id="scan-bar", show_eta=False)
                yield Static(id="scan-label")
        yield Input(placeholder="filter by name…  (esc to clear)", id="search")
        with Horizontal(id="body"):
            yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="side"):
                yield Static(id="detail")
        yield Footer()

    def on_mount(self):
        self.columns_for = None
        self.load()
        self.query_one(DataTable).focus()  # otherwise the hidden search box grabs keys
        self.set_interval(3, self.reload_if_changed)  # follows a running scan

    # ---- data -------------------------------------------------------------
    def path(self):
        if self.kind in SPECIAL:
            return DATA / SPECIAL[self.kind][0]
        return DATA / (KINDS[self.kind] + RANKINGS[self.ranking][0])

    def field(self):
        return "score" if self.kind in SPECIAL else RANKINGS[self.ranking][1]

    def load(self):
        p = self.path()
        try:
            self.meta = json.loads(p.read_text())
            self.mtime = p.stat().st_mtime
        except (OSError, ValueError):
            self.meta, self.mtime = {}, None
        self.refresh_view()

    def reload_if_changed(self):
        try:
            if self.path().stat().st_mtime != self.mtime:
                self.load()
        except OSError:
            pass

    def visible(self):
        rows = self.meta.get("candidates", [])
        if self.quick:
            rows = [c for c in rows if not c["action"].startswith(NEEDS_WORK)]
        if self.search_text:
            rows = [c for c in rows if self.search_text.lower() in c["name"].lower()]
        return rows

    # ---- drawing ----------------------------------------------------------
    def refresh_view(self):
        field = self.field()
        ranked = self.visible()
        self.rank_of = {id(c): n for n, c in enumerate(ranked, 1)}
        self.rows = self.sorted_rows(ranked)
        table = self.query_one(DataTable)
        layout = self.layout()
        if self.columns_for != layout:
            table.clear(columns=True)
            table.add_columns(*COLUMNS[layout])
            self.columns_for = layout
        else:
            table.clear()
        sixth = "missingCost" if self.kind == "sets" else "averagePrice"
        plat = lambda v: f"{v}p" if v is not None else "-"
        top = max((c[field] or 0 for c in self.rows), default=1) or 1
        for i, c in enumerate(self.rows, 1):
            heat = (c[field] or 0) / top
            color = "#3ddc84" if heat > 0.5 else "#e3c75b" if heat > 0.15 else "#8a93a6"
            action_color = "#ff9f5a" if c["action"].startswith(NEEDS_WORK) else "#3ddc84"
            table.add_row(
                Text("●" if (c["name"], c["action"]) in self.selected else str(self.rank_of[id(c)]),
                     style="bold #3ddc84" if (c["name"], c["action"]) in self.selected
                     else "#5b6680"),
                Text(c["name"], style="bold #e8eefc"),
                Text(f"{c[field] or 0:,}", style=f"bold {color}", justify="right"),
                Text(plat(c.get("lowestPrice")), style="#9fd8ff", justify="right"),
                Text(plat(c.get("bestBuy")), style="#c39bff", justify="right"),
                Text(plat(c.get(sixth)), style="#6f87a8", justify="right"),
                Text(f"{c.get('tradesPerDay', 0)}", justify="right"),
                Text(f"{c.get('yourCopies', '')}", justify="right"),
                Text(c["action"], style=action_color),
                key=str(i))
        self.draw_headline()
        self.draw_detail(self.rows[0] if self.rows else None)

    def sort_value(self, c, col):
        """Value of row c in table column col, for sorting."""
        sixth = "missingCost" if self.kind == "sets" else "averagePrice"
        field = [None, "name", self.field(), "lowestPrice", "bestBuy", sixth,
                 "tradesPerDay", "yourCopies", "action"][col]
        v = c.get(field)
        if isinstance(v, str) and "/" in v and field == "yourCopies":  # sets: "2/4"
            have, need = v.split("/")
            v = int(have) / int(need)
        return v

    def sorted_rows(self, rows):
        if self.sort_col == SORT_NONE:
            return rows if self.sort_desc else rows[::-1]
        present = [c for c in rows if self.sort_value(c, self.sort_col) is not None]
        missing = [c for c in rows if self.sort_value(c, self.sort_col) is None]
        present.sort(key=lambda c: (self.sort_value(c, self.sort_col).lower()
                                    if isinstance(self.sort_value(c, self.sort_col), str)
                                    else self.sort_value(c, self.sort_col)),
                     reverse=self.sort_desc)
        return present + missing  # rows without a value always go last

    def sort_label(self):
        layout = self.layout()
        if self.sort_col == SORT_NONE:
            return "ranking order" + ("" if self.sort_desc else " (reversed)")
        name = COLUMNS[layout][self.sort_col]
        return f"{name} {'↓' if self.sort_desc else '↑'}"

    def draw_headline(self):
        special = self.kind in SPECIAL
        label = SPECIAL[self.kind][1] if special else RANKINGS[self.ranking][2]
        tabs = "  ".join(f"[reverse b #9fd8ff] {key} {kind.upper()} [/]" if kind == self.kind
                         else f"[#e3c75b]{key}[/] [#5b6680]{kind.upper()}[/]" for key, kind in TABS)
        ranks = "[#e3c75b]v[/] " + "  ".join(
            f"[b #e3c75b]{name}[/]" if key == self.ranking else f"[#5b6680]{name}[/]"
            for key, name in self.rank_order())
        if not self.meta:
            status = f"[#ff6b6b]no data yet[/] — press [b]s[/] to scan {self.kind}"
        else:
            status = f"[#5b6680]{self.meta.get('progress', '')} · updated {self.meta.get('updated', '')}[/]"
        lines = [TITLE, "", tabs,
                 (f"[#5b6680]ranked by[/] [b #e3c75b]{label}[/]" if special else ranks)
                 + f"   [#e3c75b]c[/] [#5b6680]sort:[/] [b #9fd8ff]{self.sort_label()}[/]"
                 + ("   [b #3ddc84]● sell-now only[/]" if self.quick else ""),
                 status]
        if self.kind == "relics" and self.ranking == "crack":
            total = sum(c["score"] for c in self.rows)
            lines.append(f"[b #3ddc84]▲ ~{total:,}p[/] [#8a93a6]following the best action for every relic[/]")
        elif self.kind == "mastery":
            pts = sum(c["masteryPoints"] for c in self.rows)
            cash = sum(c.get("cash") or 0 for c in self.rows)
            true = sum(c.get("trueCost") or 0 for c in self.rows)
            lines.append(f"[b #3ddc84]▲ {pts:,} mastery points[/] [#8a93a6]from {len(self.rows)} sets:"
                         f" ~{cash:,}p to spend, ~{true:,}p true cost[/]")
        elif self.kind == "sets":
            done = sum(1 for c in self.rows if c.get("complete"))
            lines.append(f"[b #3ddc84]▲ {done}[/] [#8a93a6]complete set(s) ready to sell[/]")
        elif self.ranking == "ducats":
            total = sum(c["score"] for c in self.rows)
            lines.append(f"[b #e3c75b]◆ {total:,} ducats[/] [#8a93a6]from {len(self.rows)} parts[/]")
        elif self.ranking == "owned":
            total = sum(c.get("potentialPlat", 0) for c in self.rows)
            lines.append(f"[b #3ddc84]▲ ~{total:,}p[/] [#8a93a6]you could make from the {len(self.rows)} listed[/]")
        self.query_one("#headline", Static).update(markup("\n".join(lines)))

    def draw_detail(self, c):
        box = self.query_one("#detail", Static)
        if not c:
            box.update(markup("[#5b6680]nothing to show[/]"))
            return
        extra = ""
        if "potentialPlat" in c:
            extra = (f"\n[#8a93a6]sellable in 7 days[/]  {c['sellableIn7Days']}"
                     f"\n[#8a93a6]potential[/]           [b #3ddc84]{c['potentialPlat']:,}p[/]")
        refs = c.get("refinements")
        if refs:
            extra += "\n\n[b #9fd8ff]refinement   price    avg   /day[/]"
            for sub, p in refs.items():
                low = f"{p['lowest']}p" if p["lowest"] else "-"
                if p.get("fromHistory"):
                    low = "~" + low  # no one online: price from past sales
                avg = f"{p['average']}p" if p["average"] else "-"
                extra += f"\n[#8a93a6]{sub:<12}[/] {low:>6} {avg:>6} {p['tradesPerDay']:>6}"
        if "affinityNeeded" in c:
            extra += (f"\n[#8a93a6]affinity[/]            {c['affinity']:,} / {c['affinityNeeded']:,}"
                      f"\n[#8a93a6]mastery points[/]      [b #3ddc84]+{c['masteryPoints']:,}[/]"
                      f"\n[#5b6680]true cost = plat you end up without vs selling instead ·"
                      f" cash = plat you spend · full set = buying it whole[/]")
        if c.get("buyDemand"):
            extra += f"\n[#8a93a6]buyers want now[/]     [#c39bff]{c['buyDemand']}[/]"
        if "sellableIn7Days" in c and "potentialPlat" not in c:
            extra += f"\n[#8a93a6]sellable in 7 days[/]  {c['sellableIn7Days']}"
        if c.get("ducats"):
            extra += f"\n[#8a93a6]ducats (Baro)[/]       [#e3c75b]{c['ducats']}[/]"
        if c.get("parts"):  # sets
            extra += "\n\n[b #9fd8ff]part                 have  price[/]"
            for p in c["parts"]:
                mark = "[#3ddc84]✓[/]" if p["have"] >= p["need"] else "[#ff6b6b]✗[/]"
                short = p["name"].replace(c["name"].replace(" Set", "") + " ", "")[:18]
                low = f"{p['lowest']}p" if p["lowest"] is not None else "-"
                extra += f"\n{mark} {short:<18} {p['have']}/{p['need']:<3} {low:>5}"
        if c.get("crackValue"):  # relics
            extra += "\n\n[b #9fd8ff]crack value per relic[/]"
            for sub, v in c["crackValue"].items():
                here = " [#3ddc84]← yours[/]" if sub == c.get("refinement") else ""
                extra += f"\n[#8a93a6]{sub:<12}[/] {v:>6}p{here}"
            extra += "\n\n[b #9fd8ff]best drops[/]"
            for d in c.get("topDrops", []):
                low = f"{d['price']}p" if d["price"] is not None else "-"
                extra += f"\n{d['name'][:22]:<22} {d['chance']:>5}% {low:>5}"
        plat = lambda v: f"{v}p" if v is not None else "-"
        is_relic = "crackValue" in c
        box.update(markup(
            f"[b #e8eefc]{c['name']}[/]\n"
            f"[#ff9f5a]{c['action']}[/]\n\n"
            f"[#8a93a6]lowest online[/]       [b #9fd8ff]{plat(c.get('lowestPrice'))}[/]\n"
            f"[#8a93a6]best buy order[/]      [b #c39bff]{plat(c.get('bestBuy'))}[/]\n"
            + (f"[#8a93a6]crack value[/]         {plat(c.get('averagePrice'))}\n" if is_relic else
               f"[#8a93a6]average online[/]      {plat(c.get('averagePrice'))}\n") +
            f"[#8a93a6]online sellers[/]      {c.get('onlineSellers', 0)}\n"
            f"[#8a93a6]trades per day[/]      {c.get('tradesPerDay', 0)}\n"
            f"[#8a93a6]your copies[/]         {c['yourCopies']}"
            f"{extra}"
            + ("\n[#5b6680]~ = no one online, price from past 90 days of sales[/]"
               if refs and any(p.get("fromHistory") for p in refs.values()) else "")
            + f"\n\n[#5b6680][b]o[/b] open on warframe.market · [b]space[/b] select · [b]l[/b] list it[/]"))

    # ---- events -----------------------------------------------------------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if event.row_key is not None and event.row_key.value:
            i = int(event.row_key.value) - 1
            if 0 <= i < len(self.rows):
                self.draw_detail(self.rows[i])

    def on_input_changed(self, event: Input.Changed):
        if event.input.id != "search":
            return
        self.search_text = event.value
        self.refresh_view()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search":
            self.query_one(DataTable).focus()

    # ---- actions ----------------------------------------------------------
    def action_step_tab(self, step):
        kinds = [k for _, k in TABS]
        self.action_kind(kinds[(kinds.index(self.kind) + step) % len(kinds)])

    def check_action(self, action, parameters):
        # while typing in a text box, left/right move the text cursor instead
        if action == "step_tab" and (isinstance(self.focused, Input) or self.screen is not self.screen_stack[0]):
            return False
        return True

    def rank_order(self):
        return RELIC_RANK_ORDER if self.kind == "relics" else RANK_ORDER

    def layout(self):
        """Which header row the table uses."""
        if self.kind in ("sets", "mastery"):
            return self.kind
        return "relics" if self.kind == "relics" and self.ranking == "crack" else "default"

    def action_kind(self, kind):
        self.kind = kind
        keys = [k for k, _ in self.rank_order()]
        if self.ranking not in keys:  # e.g. ducats doesn't exist for relics
            self.ranking = keys[0]
        self.load()

    def action_next_ranking(self):
        if self.kind in SPECIAL:
            self.notify("this tab has a single ranking")
            return
        keys = [k for k, _ in self.rank_order()]
        self.action_rank(keys[(keys.index(self.ranking) + 1) % len(keys)])

    def action_next_sort(self):
        self.sort_col = (self.sort_col + 1) % 9
        self.sort_desc = self.sort_col not in (1, 8)  # text columns start A→Z
        self.refresh_view()

    def action_flip_sort(self):
        self.sort_desc = not self.sort_desc
        self.refresh_view()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected):
        # click a header: sort by it; click again: reverse
        if event.column_index == self.sort_col:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_col = event.column_index
            self.sort_desc = self.sort_col not in (1, 8)
        self.refresh_view()

    def action_rank(self, ranking):
        self.ranking = ranking
        self.load()

    def action_toggle_quick(self):
        self.quick = not self.quick
        self.refresh_view()

    def action_search(self):
        box = self.query_one("#search", Input)
        box.add_class("shown")
        box.focus()

    def action_clear_search(self):
        box = self.query_one("#search", Input)
        box.value = ""
        box.remove_class("shown")
        self.query_one(DataTable).focus()

    def action_toggle_select(self):
        table = self.query_one(DataTable)
        if self.rows and 0 <= table.cursor_row < len(self.rows):
            c = self.rows[table.cursor_row]
            self.selected ^= {(c["name"], c["action"])}
            row = table.cursor_row
            self.refresh_view()
            table.move_cursor(row=min(row + 1, len(self.rows) - 1))

    def action_list_selected(self):
        table = self.query_one(DataTable)
        rows = [c for c in self.rows if (c["name"], c["action"]) in self.selected]
        if not rows and self.rows and 0 <= table.cursor_row < len(self.rows):
            rows = [self.rows[table.cursor_row]]
        if rows:
            self.push_screen(ReviewScreen(rows), lambda _: self.reset_selection())

    def reset_selection(self):
        self.selected.clear()
        self.refresh_view()

    def action_open(self):
        table = self.query_one(DataTable)
        if self.rows and 0 <= table.cursor_row < len(self.rows):
            webbrowser.open(self.rows[table.cursor_row]["url"])


    # ---- scanning ---------------------------------------------------------
    def scan_steps(self, kind):
        if kind in ("sets", "mastery"):
            return [("checking sets & mastery", ["extras.py", "sets"])]
        steps = [(f"scanning {kind}", ["prices.py", str(DATA / f"{kind}.json")])]
        if kind == "relics":  # crack values need the relic prices just scanned
            steps.append(("working out crack values", ["extras.py", "relics"]))
        return steps

    @staticmethod
    def source(kind):
        return DATA / ("items.json" if kind in ("sets", "mastery") else f"{kind}.json")

    def action_scan(self):
        if not self.source(self.kind).exists():
            self.notify(f"{self.source(self.kind).name} not found. Press u to update your "
                        "inventory first.", severity="error")
            return
        self.run_steps(self.scan_steps(self.kind))

    def action_scan_all(self):
        steps = [step for _, k in TABS if k != "mastery" and self.source(k).exists()
                 for step in self.scan_steps(k)]  # mastery comes from the sets step
        if not steps:
            self.notify("nothing to scan. Press u to update your inventory first.", severity="error")
            return
        self.run_steps(steps)

    def action_update_inventory(self):
        self.run_steps([("reading game & downloading inventory", ["cli.py", "fetch"]),
                        ("sorting into mods, arcanes and items", ["cli.py", "extract"])])

    def action_stop_scan(self):
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            self.notify("scan stopped. Rankings keep what was checked so far.")

    def run_steps(self, steps):
        if self.proc and self.proc.returncode is None:
            self.notify("already running, press x to stop it first", severity="warning")
            return
        self.steps_worker(steps)

    @work(exclusive=True)
    async def steps_worker(self, steps):
        box, bar = self.query_one("#scan"), self.query_one("#scan-bar", ProgressBar)
        label = self.query_one("#scan-label", Static)
        box.add_class("running")
        try:
            for title, cmd in steps:
                bar.update(total=None, progress=0)  # indeterminate until we see a count
                label.update(markup(f"[b #3ddc84]{title}[/] [#5b6680]starting…[/]"))
                ok, last = await self.run_one(cmd, title, bar, label)
                if not ok:
                    self.notify(last or f"{title} failed", severity="error", timeout=10)
                    return
            self.notify(f"done: {steps[-1][0]}")
        finally:
            box.remove_class("running")
            self.proc = None
            self.load()

    async def run_one(self, cmd, title, bar, label):
        self.proc = await asyncio.create_subprocess_exec(
            sys.executable, "-u", *cmd, cwd=REPO,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        last, buf = "", b""
        while chunk := await self.proc.stdout.read(512):
            buf += chunk
            *parts, buf = re.split(rb"[\r\n]", buf)
            for part in parts:
                line = part.decode(errors="replace").strip()
                if not line:
                    continue
                m = PROGRESS.search(line)
                if m:
                    done, total, left, name = int(m[1]), int(m[2]), m[3], m[4].strip()
                    bar.update(total=total, progress=done)
                    label.update(markup(f"[b #3ddc84]{title}[/]  {done}/{total}  "
                                        f"[#e3c75b]~{left} left[/]  [#8a93a6]{name}[/]"
                                        f"   [#5b6680]x to stop[/]"))
                else:
                    last = line
                    label.update(markup(f"[b #3ddc84]{title}[/]  [#8a93a6]{line}[/]"))
        await self.proc.wait()
        return self.proc.returncode == 0, last

    def on_unmount(self):
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()


def run():
    PlatScout().run()


if __name__ == "__main__":
    run()
