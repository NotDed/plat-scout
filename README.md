# plat-scout

Find which of your Warframe mods and arcanes are worth selling on
[warframe.market](https://warframe.market), based on price, trade volume and
how many copies you own.

Python 3 standard library only, no dependencies.

## Install

```
uv tool install -e .      # or: pipx install -e .
```

This adds a `plat-scout` command. Data stays in this repo's `data/` folder.

## Usage

```
plat-scout run                 # fetch + extract + prices, everything (~18 min)
plat-scout top                 # best 15 mods to sell, by plat from your copies
plat-scout top --quick         # only ones you can sell right now (no ranking up)
plat-scout top arcanes --by market -n 30
```

Step by step:

| Command | What it does |
|---|---|
| `plat-scout fetch` | download your inventory (game running and logged in) |
| `plat-scout extract` | split it into `mods.json` and `arcanes.json` |
| `plat-scout prices [mods\|arcanes]` | scan warframe.market (~2.3 s per item) |
| `plat-scout rank` | rebuild rankings from saved prices, no API calls |
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

Arcanes produce the same files with an `arcane-` prefix.

`--all-sellers` on `prices`/`run` counts offline sellers too (default: only
online/in-game).

## Notes

- Trade volume comes from warframe.market's v1 statistics endpoint (90 days);
  everything else uses the v2 API.
- Rivens are skipped: they trade on the separate riven auction market.
- "Already maxed" copies may be the ones you have equipped.
- `data/` is git-ignored: `inventory.json` contains your account ID.
- Reading the session token from game memory is a grey area under DE's terms
  of service. Use at your own risk.
