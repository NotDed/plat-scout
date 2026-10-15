# plat-scout

Find which of your Warframe items are worth selling on
[warframe.market](https://warframe.market), based on price, trade volume and
how many copies you own. Covers mods, arcanes, and everything else tradable you
have lying around: prime parts and blueprints, relics (per refinement), Ayatan
stars, fish, scenes...

Python 3 standard library only, except the TUI which uses [Textual](https://textual.textualize.io).

## Install

```
uv tool install -e .      # or: pipx install -e .
```

This adds a `plat-scout` command. Data stays in this repo's `data/` folder.

## Usage

```
plat-scout tui                 # interactive browser: u = update inventory, s = scan tab, S = scan all
plat-scout sets                # prime sets you own parts of: complete them or not?
plat-scout relics              # crack value of each relic vs selling it (after prices relics)
plat-scout plan                # today's best trades within your MR trade limit and credit tax
plat-scout run                 # fetch + extract + prices + sets + relics + plan, everything (~30 min)
plat-scout top                 # best 15 mods to sell, by plat from your copies
plat-scout top --quick         # only ones you can sell right now (no ranking up)
plat-scout top arcanes --by market -n 30
```

Step by step:

| Command | What it does |
|---|---|
| `plat-scout fetch` | download your inventory (game running and logged in) |
| `plat-scout extract` | split it into `mods.json`, `arcanes.json`, `relics.json` and `items.json` |
| `plat-scout prices [mods\|arcanes\|items\|relics]` | scan warframe.market (~2.3 s per item) |
| `plat-scout rank` | rebuild rankings from saved prices, no API calls |
| `plat-scout tui` | browse everything: `1`-`6` or `←`/`→` tabs (mods, arcanes, items, sets, relics, buy), `w` my listings (undercut check), `v` ranking (relics also have "sell or crack"), multi-column sort (click headers to add a level, again to flip, a third time to remove; or `n` add level, `c` change its column, `C` flip, `Backspace` remove, `r` reset), `f` sell-now only, `/` search, `o` open on warframe.market, `space`/`l` select & list, `u` update inventory, `s`/`S` scan tab / all, `x` stop |
| `plat-scout plan` | day-by-day trade plan (see below), no new price scan |
| `plat-scout top [mods\|arcanes\|items\|relics\|sets\|trades]` | print a ranking (`--by market\|owned\|volume\|ducats`, `-n`, `--quick`) |

`fetch` reads your session token from the game's memory (same method as
[warframe-api-helper](https://github.com/Sainan/warframe-api-helper), rewritten
in Python). If you get "permission denied", run it with `sudo` once.

A scan first deletes the previous results for what it scans (`S` and
`plat-scout run`: every tab; `s`: that tab), so tables start empty and fill in
live. Inventory, item lists, caches, the worth history and your token are kept.

## Listing on warframe.market

In the TUI: `space` marks rows, `l` opens a review of exactly what would be
posted (item, rank, quantity, price, new listing or price update of one you
already have). `p` switches pricing between matching the lowest online seller,
undercutting it by 1p, or the online average. `y` posts, `esc` cancels.
Nothing is posted without that review.

Only rows you can sell as-is are listed (not "rank to…", "refine…", "buy…").

First time it asks for your warframe.market session token: log in on
warframe.market in your browser, F12 → Application/Storage → Cookies →
`https://warframe.market` → copy the `JWT` cookie value. It's saved in
`data/wfm-token` (git-ignored, readable only by you). Your account must be
verified on warframe.market to create orders.

Press `w` for **My listings**: each of your sell orders vs the cheapest *other*
online seller of the same item, rank and subtype. Undercut ones are flagged;
`y` reprices them (match the cheapest, or `p` for 1p under). Nothing changes
without `y`.

## Buying (BUY tab, `6`)

A cart for things you want to buy. `a` opens a search over every tradable item
(the closest name is completed in grey as you type: `Tab` or `→` accepts it,
`↑↓` picks from the matches); then set rank, refinement, how many and an
optional max price per copy. The cart is saved in `data/cart.json`.

For every cart item the tab finds the online sellers of that exact rank /
refinement, cheapest first, in-game before online, then by reputation:

- `Enter` (or **Copy whisper**) copies warframe.market's message for the current
  seller, ready to paste in Warframe chat
- `>` / `<` (or **Next** / **Prev**) when a seller doesn't answer
- `b` (**Bought**) takes one off the quantity, `Del` (**Remove**) drops the item
- `s` refreshes all sellers

The clipboard uses `wl-copy` (Wayland), `xclip`/`xsel` (X11), or your
terminal's clipboard as a fallback.

## Trade planner (`plat-scout plan`)

Warframe allows as many trades per day as your Mastery Rank, and every item
traded costs credits. `plat-scout plan` (then `plat-scout top trades`) takes every
sell-now option from the saved scans plus complete prime sets, treats each
buyer as one trade (bulk items like relics: up to 6 copies per trade), fetches
each item's credit tax once (cached in `data/cache/trading-tax.json`), and
fills today's remaining trades first, then MR trades per day, best plat per
trade first. Trades costing more than 2,000 credits per plat are skipped, as is
anything beyond your credits. It prints today's plat, tax and how many days it
takes to sell everything.

## Signals

- **Expected price**: scores and Potential use the cheapest ask *unless the item
  actually trades for less* (90-day median of real trades). Relics, for example,
  are often listed at 10-30p but trade at 1.5-3p in bulk.
- **Trend**: last 7 days vs 90 days of trades (↑ rising / → stable / ↓ falling,
  ±15 %); `-` when fewer than 3 trades this week. Vaulted items say so, since
  they tend to rise while vaulted.
- **Endo**: "rank to max" rows show the endo (rarity base 10/20/30/40 ×
  (2^max − 1)), credits, and plat gained per 1,000 endo.
- **Worth over time**: every scan logs each tab's sell-now worth to
  `data/history.jsonl`; the header shows a sparkline and the change vs a week ago.

## Output (in `data/`)

| File | Ranked by |
|---|---|
| `sell-candidates.json` | expected price × trades per day |
| `sell-candidates-owned.json` | expected price × your copies, capped at what sells in 7 days (bulk items: also what online buyers want right now) |
| `sell-candidates-volume.json` | your copies × trades per day (price ignored) |
| `mod-prices.json` / `.csv` | every tradable mod: lowest/average price and trades/day at rank 0 and max rank |

Arcanes, items and relics produce the same files with an `arcane-` / `item-` /
`relic-` prefix,
plus `ducat-candidates.json`: prime parts worth ≥10 ducats per plat at Baro.

| File | What |
|---|---|
| `set-candidates.json` | prime sets you own parts of: what's missing, its cost, and the gain vs selling parts |
| `relic-candidates.json` | per relic: sell price vs expected crack value at each refinement, best action |
| `trade-plan.json` | `plat-scout plan`: day, trades, tax and plat per item |
| `history.jsonl` | sell-now worth per tab after every scan |

Every price comes with the best online **buy order** too: what someone will pay
you right now. "Avg" is the *typical* asking price (median of the 5 cheapest
online sellers) and the detail panel adds what it actually **sold for** over the
last 90 days (median of real trades), so one wishful 300p listing on a
low-demand item can't inflate either.

`--all-sellers` on `prices`/`run` counts offline sellers too (default: only
online/in-game).

## Notes

- Trade volume comes from warframe.market's v1 statistics endpoint (90 days);
  everything else uses the v2 API.
- Relics are priced at every refinement (intact → radiant). If a refined level
  sells for more, you get a "refine to X (N traces), then sell" option. When no
  one is online selling a level, its price comes from the last 90 days of sales
  (shown with `~` in the TUI).
- Relic crack value = Σ drop chance × expected price of the drop (solo
  run, drop tables from WFCD). Refining is only suggested when it adds ≥5p.
- Rivens are skipped: they trade on the separate riven auction market.
- Built frames and weapons are skipped: only loose parts and blueprints can be
  traded. Resources (Ferrite, Rubedo...) aren't tradable either.
- Equipped mods and arcanes are never counted as sellable: extract.py reads
  every build (frames, weapons, companions, archwings…) and only spare copies
  show up. After re-equipping, `plat-scout extract && plat-scout rank`
  refreshes the rankings without a new scan.
- `data/` is git-ignored: `inventory.json` contains your account ID.
- Reading the session token from game memory is a grey area under DE's terms
  of service. Use at your own risk.
