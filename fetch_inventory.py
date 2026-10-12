#!/usr/bin/env python3
"""Download your full Warframe inventory to data/inventory.json.

The game must be running and logged in. warframe-api-helper
(https://github.com/Sainan/warframe-api-helper) reads the session token from
the game; it may crash right after printing it, which is fine, since only the
printed "?accountId=...&nonce=..." line is needed.

Usage:
  python3 fetch_inventory.py --helper /path/to/warframe-api-helper
  python3 fetch_inventory.py --auth '?accountId=...&nonce=...'
"""

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
URL = "https://mobile.warframe.com/api/inventory.php"


def auth_from_helper(helper):
    run = subprocess.run([helper], capture_output=True, text=True, timeout=120, cwd=DATA)
    m = re.search(r"\?accountId=[0-9a-f]+&(?:amp;)?nonce=\d+", run.stdout + run.stderr)
    if not m:
        sys.exit("helper did not print a token; is the game running and logged in?")
    return m.group(0)


def main():
    args = sys.argv[1:]
    if len(args) != 2 or args[0] not in ("--helper", "--auth"):
        sys.exit(__doc__)
    auth = auth_from_helper(args[1]) if args[0] == "--helper" else args[1]
    auth = auth.replace("&amp;", "&")

    DATA.mkdir(exist_ok=True)
    with urllib.request.urlopen(URL + auth, timeout=30) as r:
        inventory = json.load(r)
    (DATA / "inventory.json").write_text(json.dumps(inventory, indent=2))
    print(f"saved {DATA / 'inventory.json'} "
          f"({len(inventory.get('RawUpgrades', []))} unranked mod/arcane stacks)")


if __name__ == "__main__":
    main()
