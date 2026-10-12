"""plat-scout TUI: browse the sell rankings, live-reloading while a scan runs."""

import json
import webbrowser
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Input, Static

DATA = Path(__file__).resolve().parent / "data"
KINDS = {"mods": "", "arcanes": "arcane-"}
RANKINGS = {  # key -> (file, score field, label)
    "owned": ("sell-candidates-owned.json", "potentialPlat", "plat from your copies (7 days)"),
    "market": ("sell-candidates.json", "score", "price × trades per day"),
    "volume": ("sell-candidates-volume.json", "volumeScore", "your copies × trades per day"),
}

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


def build_logo():
    """The platinum artwork from assets/plat.txt with the green arrow
    overlapping its bottom-right edge."""
    try:
        plat = (ASSETS / "plat.txt").read_text(encoding="utf-8").splitlines()
    except OSError:
        plat = []
    plat_w = max((len(line) for line in plat), default=0)
    ox = max(plat_w - ARROW_OVERLAP, 0)  # arrow column offset
    oy = max(len(plat) - len(ARROW), 0)  # arrow sits at the bottom
    width = max(plat_w, ox + len(ARROW[0]))
    height = max(len(plat), oy + len(ARROW))

    # canvas of (char, style): plat first, then the arrow painted over it
    cells = [[(" ", "")] * width for _ in range(height)]
    for y, line in enumerate(plat):
        for x, ch in enumerate(line):
            cells[y][x] = (ch, SHADES.get(ch, ""))
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
    """
    BINDINGS = [
        Binding("m", "kind('mods')", "Mods"),
        Binding("a", "kind('arcanes')", "Arcanes"),
        Binding("1", "rank('owned')", "Your plat"),
        Binding("2", "rank('market')", "Market"),
        Binding("3", "rank('volume')", "Volume"),
        Binding("f", "toggle_quick", "Sell-now only"),
        Binding("slash", "search", "Search"),
        Binding("o", "open", "Open market"),
        Binding("escape", "clear_search", "Clear", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.kind, self.ranking, self.quick, self.search_text = "mods", "owned", False, ""
        self.rows, self.meta, self.mtime = [], {}, None

    def compose(self) -> ComposeResult:
        with Horizontal(id="top"):
            yield Static(build_logo(), id="art")
            yield Static(id="headline")
        yield Input(placeholder="filter by name…  (esc to clear)", id="search")
        with Horizontal(id="body"):
            yield DataTable(id="table", cursor_type="row", zebra_stripes=True)
            with Vertical(id="side"):
                yield Static(id="detail")
        yield Footer()

    def on_mount(self):
        self.query_one(DataTable).add_columns(
            "#", "Name", "Score", "Price", "Avg", "/day", "Own", "Action")
        self.load()
        self.query_one(DataTable).focus()  # otherwise the hidden search box grabs keys
        self.set_interval(3, self.reload_if_changed)  # follows a running scan

    # ---- data -------------------------------------------------------------
    def path(self):
        return DATA / (KINDS[self.kind] + RANKINGS[self.ranking][0])

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
            rows = [c for c in rows if not c["action"].startswith(("rank to", "fuse"))]
        if self.search_text:
            rows = [c for c in rows if self.search_text.lower() in c["name"].lower()]
        return rows

    # ---- drawing ----------------------------------------------------------
    def refresh_view(self):
        field = RANKINGS[self.ranking][1]
        self.rows = self.visible()
        table = self.query_one(DataTable)
        table.clear()
        top = max((c[field] for c in self.rows), default=1) or 1
        for i, c in enumerate(self.rows, 1):
            heat = c[field] / top
            color = "#3ddc84" if heat > 0.5 else "#e3c75b" if heat > 0.15 else "#8a93a6"
            action_color = "#ff9f5a" if c["action"].startswith(("rank to", "fuse")) else "#3ddc84"
            table.add_row(
                Text(str(i), style="#5b6680"),
                Text(c["name"], style="bold #e8eefc"),
                Text(f"{c[field]:,}", style=f"bold {color}", justify="right"),
                Text(f"{c['lowestPrice']}p", style="#9fd8ff", justify="right"),
                Text(f"{c['averagePrice']}p", style="#6f87a8", justify="right"),
                Text(f"{c['tradesPerDay']}", justify="right"),
                Text(f"{c['yourCopies']}", justify="right"),
                Text(c["action"], style=action_color),
                key=str(i))
        self.draw_headline()
        self.draw_detail(self.rows[0] if self.rows else None)

    def draw_headline(self):
        label = RANKINGS[self.ranking][2]
        tab = lambda k, name: f"[reverse b #9fd8ff] {name} [/]" if k == self.kind else f" [#5b6680]{name}[/] "
        if not self.meta:
            status = f"[#ff6b6b]no data yet[/] — run [b]plat-scout prices {self.kind}[/]"
        else:
            status = f"[#5b6680]{self.meta.get('progress', '')} · updated {self.meta.get('updated', '')}[/]"
        total = sum(c.get("potentialPlat", 0) for c in self.rows) if self.ranking == "owned" else None
        lines = [TITLE, "",
                 tab("mods", "MODS") + " " + tab("arcanes", "ARCANES")
                 + f"   ranked by [b #e3c75b]{label}[/]"
                 + ("   [b #3ddc84]● sell-now only[/]" if self.quick else ""),
                 status]
        if total is not None:
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
        box.update(markup(
            f"[b #e8eefc]{c['name']}[/]\n"
            f"[#ff9f5a]{c['action']}[/]\n\n"
            f"[#8a93a6]lowest online[/]       [b #9fd8ff]{c['lowestPrice']}p[/]\n"
            f"[#8a93a6]average online[/]      {c['averagePrice']}p\n"
            f"[#8a93a6]online sellers[/]      {c['onlineSellers']}\n"
            f"[#8a93a6]trades per day[/]      {c['tradesPerDay']}\n"
            f"[#8a93a6]your copies[/]         {c['yourCopies']}"
            f"{extra}\n\n"
            f"[#5b6680]press [b]o[/b] to open on warframe.market[/]"))

    # ---- events -----------------------------------------------------------
    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted):
        if event.row_key is not None and event.row_key.value:
            i = int(event.row_key.value) - 1
            if 0 <= i < len(self.rows):
                self.draw_detail(self.rows[i])

    def on_input_changed(self, event: Input.Changed):
        self.search_text = event.value
        self.refresh_view()

    def on_input_submitted(self, event: Input.Submitted):
        self.query_one(DataTable).focus()

    # ---- actions ----------------------------------------------------------
    def action_kind(self, kind):
        self.kind = kind
        self.load()

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

    def action_open(self):
        table = self.query_one(DataTable)
        if self.rows and 0 <= table.cursor_row < len(self.rows):
            webbrowser.open(self.rows[table.cursor_row]["url"])


def run():
    PlatScout().run()


if __name__ == "__main__":
    run()
