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
plat-scout run                 # fetch + extract + prices, everything (~18 min)
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
| `plat-scout tui` | browse everything: `1`-`5` tabs (mods, arcanes, items, sets, relics), `v` ranking (relics also have "sell or crack"), `c`/`C` sort column / reverse (or click a header), `f` sell-now only, `/` search, `o` open on warframe.market, `space`/`l` select & list, `u` update inventory, `s`/`S` scan tab / all, `x` stop |
| `plat-scout top [mods\|arcanes]` | print the ranking (`--by market\|owned\|volume`, `-n`, `--quick`) |

`fetch` reads your session token from the game's memory (same method as
[warframe-api-helper](https://github.com/Sainan/warframe-api-helper), rewritten
in Python). If you get "permission denied", run it with `sudo` once.

The ranking files are rewritten after every item during `prices`, so you can
open them while the scan runs.

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

## Output (in `data/`)

| File | Ranked by |
|---|---|
| `sell-candidates.json` | lowest online price × trades per day |
| `sell-candidates-owned.json` | lowest price × your copies, capped at what sells in 7 days (bulk items: also what online buyers want right now) |
| `sell-candidates-volume.json` | your copies × trades per day (price ignored) |
| `mod-prices.json` / `.csv` | every tradable mod: lowest/average price and trades/day at rank 0 and max rank |

Arcanes, items and relics produce the same files with an `arcane-` / `item-` /
`relic-` prefix,
plus `ducat-candidates.json`: prime parts worth ≥10 ducats per plat at Baro.

| File | What |
|---|---|
| `set-candidates.json` | prime sets you own parts of: what's missing, its cost, and the gain vs selling parts |
| `relic-candidates.json` | per relic: sell price vs expected crack value at each refinement, best action |

Every price comes with the best online **buy order** too: what someone will pay
you right now.

`--all-sellers` on `prices`/`run` counts offline sellers too (default: only
online/in-game).

## Notes

- Trade volume comes from warframe.market's v1 statistics endpoint (90 days);
  everything else uses the v2 API.
- Relics are priced at every refinement (intact → radiant). If a refined level
  sells for more, you get a "refine to X (N traces), then sell" option. When no
  one is online selling a level, its price comes from the last 90 days of sales
  (shown with `~` in the TUI).
- Relic crack value = Σ drop chance × lowest online price of the drop (solo
  run, drop tables from WFCD). Refining is only suggested when it adds ≥5p.
- Rivens are skipped: they trade on the separate riven auction market.
- Built frames and weapons are skipped: only loose parts and blueprints can be
  traded. Resources (Ferrite, Rubedo...) aren't tradable either.
- "Already maxed" copies may be the ones you have equipped.
- `data/` is git-ignored: `inventory.json` contains your account ID.
- Reading the session token from game memory is a grey area under DE's terms
  of service. Use at your own risk.
