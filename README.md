# plat-scout

Find which of your Warframe mods and arcanes are worth selling on
[warframe.market](https://warframe.market), based on price, trade volume and
how many copies you own.

Python 3 standard library only, no dependencies.

## Steps

1. **Get your inventory** (game running and logged in). Download
   [warframe-api-helper](https://github.com/Sainan/warframe-api-helper/releases)
   (there is a Linux build), then:
   ```
   python3 fetch_inventory.py --helper /path/to/warframe-api-helper
   ```
2. **Split it into mods and arcanes:**
   ```
   python3 extract.py
   ```
3. **Price them** (about 2.3 s per item: ~15 min for mods, ~2.5 min for arcanes):
   ```
   python3 prices.py data/mods.json
   python3 prices.py data/arcanes.json
   ```
   The ranking files are rewritten after every item, so you can open them while
   the scan runs.

## Output (in `data/`)

| File | Ranked by |
|---|---|
| `sell-candidates.json` | lowest online price × trades per day |
| `sell-candidates-owned.json` | lowest price × your copies, capped at what sells in 7 days |
| `sell-candidates-volume.json` | your copies × trades per day (price ignored) |
| `mod-prices.json` / `.csv` | every tradable mod: lowest/average price and trades/day at rank 0 and max rank |

Arcanes produce the same files with an `arcane-` prefix.

## Options

- `--all-sellers`: count offline sellers too (default: only online/in-game).
- `--from-prices`: re-rank from an existing prices file without calling the API.

## Notes

- Trade volume comes from warframe.market's v1 statistics endpoint (90 days);
  everything else uses the v2 API.
- Rivens are skipped: they trade on the separate riven auction market.
- "Already maxed" copies may be the ones you have equipped.
- `data/` is git-ignored: `inventory.json` contains your account ID.
- Reading the session token from game memory is a grey area under DE's terms
  of service. Use at your own risk.
