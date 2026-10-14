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
plat-scout relics              # crack value of each relic vs selling it
plat-scout run                 # fetch + extract + prices, everything (~18 min)
plat-scout top                 # best 15 mods to sell, by plat from your copies
plat-scout top --quick         # only ones you can sell right now (no ranking up)
plat-scout top arcanes --by market -n 30
```

Step by step:

| Command | What it does |
|---|---|
| `plat-scout fetch` | download your inventory (game running and logged in) |
| `plat-scout extract` | split it into `mods.json`, `arcanes.json` and `items.json` |
| `plat-scout prices [mods\|arcanes\|items]` | scan warframe.market (~2.3 s per item) |
| `plat-scout rank` | rebuild rankings from saved prices, no API calls |
| `plat-scout tui` | browse rankings: `m`/`a`/`i`/`p`/`r` mods/arcanes/items/sets/relics, `1`-`4` ranking, `f` sell-now only, `/` search, `o` open on warframe.market, `u` update inventory, `s` scan the current tab, `S` scan all tabs, `x` stop |
| `plat-scout top [mods\|arcanes]` | print the ranking (`--by market\|owned\|volume`, `-n`, `--quick`) |

`fetch` reads your session token from the game's memory (same method as
[warframe-api-helper](https://github.com/Sainan/warframe-api-helper), rewritten
in Python). If you get "permission denied", run it with `sudo` once.

The ranking files are rewritten after every item during `prices`, so you can
open them while the scan runs.

## Output (in `data/`)

| File | Ranked by |
|---|---|
| `sell-candidates.json` | lowest online price × trades per day |
| `sell-candidates-owned.json` | lowest price × your copies, capped at what sells in 7 days |
| `sell-candidates-volume.json` | your copies × trades per day (price ignored) |
| `mod-prices.json` / `.csv` | every tradable mod: lowest/average price and trades/day at rank 0 and max rank |

Arcanes and items produce the same files with an `arcane-` / `item-` prefix,
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
