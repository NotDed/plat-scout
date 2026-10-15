"""Sample the platinum image into one color per ASCII-art character.

  uv run --with pillow python tools/color_art.py assets/plat.png assets/plat.txt assets/plat-colors.json

The image's transparent background is ignored; colors get a saturation and
brightness boost because shading characters (░▒▓) only show part of their color.
Delete assets/plat-colors.json to go back to the plain blue shades.
"""
import json, sys
from PIL import Image

img_path, art_path, out_path = sys.argv[1:4]
art = open(art_path, encoding="utf-8").read().splitlines()
rows, cols = len(art), max(map(len, art))

img = Image.open(img_path).convert("RGBA")
w, h = img.size
px = img.load()
# crop to the coin: bounding box of non-background (non-near-white) pixels
is_bg = lambda c: c[3] < 128  # transparent = background
xs = [x for x in range(w) for y in range(0, h, 4) if not is_bg(px[x, y])]
ys = [y for y in range(h) for x in range(0, w, 4) if not is_bg(px[x, y])]
x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
print("coin box", (x0, y0, x1, y1), "image", (w, h))

import colorsys
SAT, MIN_V, GAMMA = 2.6, 0.62, 0.8


def punch(rgb):
    """Brighter, more saturated: shading characters only show part of their color."""
    h, sat, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
    sat = min(1.0, sat * SAT)
    v = MIN_V + (1 - MIN_V) * (v ** GAMMA)
    return "#%02x%02x%02x" % tuple(round(c * 255) for c in colorsys.hsv_to_rgb(h, sat, v))


colors = []
for r in range(rows):
    line = []
    for c in range(cols):
        ch = art[r][c] if c < len(art[r]) else " "
        if ch == " ":
            line.append(None)
            continue
        cx0 = x0 + (x1 - x0) * c / cols
        cx1 = x0 + (x1 - x0) * (c + 1) / cols
        cy0 = y0 + (y1 - y0) * r / rows
        cy1 = y0 + (y1 - y0) * (r + 1) / rows
        samples = [px[x, y] for x in range(int(cx0), max(int(cx1), int(cx0) + 1))
                   for y in range(int(cy0), max(int(cy1), int(cy0) + 1)) if not is_bg(px[x, y])]
        if not samples:  # art pixel over background: nearest coin color fallback
            samples = [px[int((cx0 + cx1) / 2), int((cy0 + cy1) / 2)]]
        avg = tuple(sum(s[i] for s in samples) // len(samples) for i in range(3))  # RGB of RGBA
        line.append(punch(avg))
    colors.append(line)
json.dump(colors, open(out_path, "w"))
print("wrote", out_path, rows, "x", cols)
