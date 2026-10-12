#!/usr/bin/env python3
"""Download your full Warframe inventory to data/inventory.json.

The game must be running and logged in (Linux, native or Proton). The session
token is read straight from the game's memory, the same trick as Sainan's
warframe-api-helper (https://github.com/Sainan/warframe-api-helper): the game
keeps "?accountId=<24 hex>&nonce=<digits>" in memory, and a value seen 3 times
is taken as the real one.

Usage:
  python3 fetch_inventory.py                              # read token from the game
  python3 fetch_inventory.py --auth '?accountId=...&nonce=...'

If reading memory fails with "permission denied", your kernel only lets a
process read its own children (kernel.yama.ptrace_scope=1). Run once with sudo,
or temporarily: sudo sysctl kernel.yama.ptrace_scope=0
"""

import json
import re
import sys
import urllib.request
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
URL = "https://mobile.warframe.com/api/inventory.php"
PROCESS = "Warframe.x64.ex"  # /proc/<pid>/comm is cut to 15 characters
TOKEN = re.compile(rb"\?accountId=([0-9a-f]{24})&nonce=(\d+)")
CHUNK = 64 << 20
OVERLAP = 64  # so a token split across two chunks is still found


def find_pid():
    for comm in Path("/proc").glob("[0-9]*/comm"):
        try:
            if comm.read_text().strip() == PROCESS:
                return int(comm.parent.name)
        except OSError:
            continue
    sys.exit("Warframe is not running. Start the game, log in, and try again.")


def readable_regions(pid):
    for line in open(f"/proc/{pid}/maps"):
        parts = line.split()
        if "r" not in parts[1] or (len(parts) > 5 and parts[5] in ("[vvar]", "[vsyscall]")):
            continue
        start, end = (int(x, 16) for x in parts[0].split("-"))
        yield start, end


def token_from_game():
    pid = find_pid()
    seen = Counter()
    try:
        mem = open(f"/proc/{pid}/mem", "rb", buffering=0)
    except PermissionError:
        sys.exit("Permission denied reading game memory (ptrace_scope). Run with sudo, or:\n"
                 "  sudo sysctl kernel.yama.ptrace_scope=0")
    with mem:
        for start, end in readable_regions(pid):
            pos = start
            while pos < end:
                size = min(CHUNK, end - pos)
                try:
                    mem.seek(pos)
                    buf = mem.read(size + OVERLAP if pos + size < end else size)
                except (OSError, ValueError, OverflowError):
                    break  # region vanished or is unreadable
                for m in TOKEN.finditer(buf or b""):
                    auth = f"?accountId={m[1].decode()}&nonce={m[2].decode()}"
                    seen[auth] += 1
                    if seen[auth] == 3:
                        return auth
                pos += size
    if seen:
        return seen.most_common(1)[0][0]
    sys.exit("No session token found in game memory. Are you logged in past the login screen?")


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        sys.exit(__doc__)
    if args and (args[0] != "--auth" or len(args) != 2):
        sys.exit(__doc__)
    auth = args[1].replace("&amp;", "&") if args else token_from_game()
    print("got session token, downloading inventory...")

    DATA.mkdir(exist_ok=True)
    with urllib.request.urlopen(URL + auth, timeout=30) as r:
        inventory = json.load(r)
    (DATA / "inventory.json").write_text(json.dumps(inventory, indent=2))
    print(f"saved {DATA / 'inventory.json'}")


if __name__ == "__main__":
    main()
