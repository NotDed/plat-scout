"""Turn the platinum image into square pixels for the TUI logo.

  uv run --with pillow python tools/pixel_art.py assets/plat.png assets/plat-pixels.json [width]

Writes a grid of colors (or null for transparent) with twice as many rows as
the logo has text rows: the TUI draws two pixels per cell with the half block
"▀" (top = text color, bottom = background), which makes each pixel square.
"""

import json
import sys

from PIL import Image

img_path, out_path = sys.argv[1:3]
width = int(sys.argv[3]) if len(sys.argv) > 3 else 30

img = Image.open(img_path).convert("RGBA")
img = img.crop(img.getchannel("A").getbbox())  # just the coin
w, h = img.size
height = round(width * h / w)
height += height % 2  # whole text rows
small = img.resize((width, height), Image.LANCZOS)

grid = []
for y in range(height):
    row = []
    for x in range(width):
        r, g, b, a = small.getpixel((x, y))
        row.append("#%02x%02x%02x" % (r, g, b) if a >= 128 else None)
    grid.append(row)
json.dump(grid, open(out_path, "w"))
print(f"wrote {out_path}: {width} x {height} pixels = {width} x {height // 2} text cells")
