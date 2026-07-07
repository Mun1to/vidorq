"""Vidorq logo v3: a real ring (not just floating dots), symmetric spokes
converging to a centered play button, and the play rendered in blue with a
subtle embossed/raised look (soft shadow + gradient sheen) against the flat
violet ring. Everything else stays flat/simple as requested.

Output: logo.png (transparent) + logo_dark.png (on brand dark background).
Run with the davinci-resolve-mcp venv (has Pillow + numpy).
"""
import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

S = 4096  # supersample; final 1024
CX = CY = S // 2
R = int(S * 0.36)
OUT = Path(__file__).parent

VIOLET = (108, 92, 231)      # #6c5ce7 - ring/dots/spokes, flat
BLUE_LIGHT = (110, 190, 255)  # sheen highlight (top-left of the play)
BLUE_BASE = (43, 130, 240)    # #2b82f0 - play base blue
BLUE_DARK = (18, 80, 170)     # shaded side (bottom-right of the play)


def main():
    rng = random.Random(11)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    n = 22
    nodes = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        x = CX + R * math.cos(ang)
        y = CY + R * math.sin(ang)
        nodes.append((x, y))

    # 1) The ring itself - an actual circle, not just floating dots
    ring_w = int(S * 0.006)
    d.ellipse([CX - R, CY - R, CX + R, CY + R], outline=VIOLET + (255,), width=ring_w)

    # 2) Symmetric spokes: evenly-spaced source nodes (not a random scatter),
    # each with its own loosely organic wobble, all converging on true center.
    num_senders = 6
    senders = [round(i * n / num_senders) % n for i in range(num_senders)]
    for i in senders:
        x1, y1 = nodes[i]
        tx, ty = CX, CY
        dx, dy = tx - x1, ty - y1
        dist = math.hypot(dx, dy)
        nx, ny = -dy / dist, dx / dist
        pts = [(x1, y1)]
        steps = 4
        for s in range(1, steps):
            t = s / steps
            bx = x1 + dx * t
            by = y1 + dy * t
            wobble = rng.uniform(-1, 1) * dist * 0.07 * math.sin(math.pi * t)
            pts.append((bx + nx * wobble, by + ny * wobble))
        pts.append((tx, ty))
        d.line(pts, fill=VIOLET + (255,), width=int(S * 0.0034), joint="curve")

    # 3) Dots on the ring - flat, on top of the ring stroke and spoke lines
    for i, (x, y) in enumerate(nodes):
        r = int(S * (0.022 if i % 4 == 0 else 0.015))
        d.ellipse([x - r, y - r, x + r, y + r], fill=VIOLET + (255,))

    # 4) The play button: centered, blue, with a raised/embossed feel
    pr = R * 0.5
    tri = [(CX - pr * 0.66, CY - pr * 0.8),
           (CX - pr * 0.66, CY + pr * 0.8),
           (CX + pr * 0.86, CY)]

    tri_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(tri_mask).polygon(tri, fill=255)

    # Soft drop shadow (offset down-right, blurred) so the button lifts off the ring
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(
        [(x + S * 0.010, y + S * 0.014) for x, y in tri], fill=(5, 15, 40, 150))
    shadow = shadow.filter(ImageFilter.GaussianBlur(S * 0.010))
    img.alpha_composite(shadow)

    # Diagonal gradient sheen (light top-left -> dark bottom-right) masked to
    # the triangle: reads as a raised, slightly convex button, not flat paint.
    xs, ys = np.meshgrid(np.arange(S), np.arange(S))
    x0, y0, x1e, y1e = min(p[0] for p in tri), min(p[1] for p in tri), \
        max(p[0] for p in tri), max(p[1] for p in tri)
    t = ((xs - x0) / (x1e - x0) * 0.55 + (ys - y0) / (y1e - y0) * 0.45)
    t = np.clip(t, 0, 1)
    grad = np.zeros((S, S, 4), dtype=np.uint8)
    for c in range(3):
        lo, mid, hi = BLUE_LIGHT[c], BLUE_BASE[c], BLUE_DARK[c]
        # light -> base -> dark, so the top-left corner actually glows
        half = np.where(t < 0.5, lo + (mid - lo) * (t / 0.5), mid + (hi - mid) * ((t - 0.5) / 0.5))
        grad[:, :, c] = half.astype(np.uint8)
    grad[:, :, 3] = 255
    grad_img = Image.fromarray(grad, "RGBA")
    img.paste(grad_img, (0, 0), tri_mask)

    # Thin highlight rim along the top-left edge for extra bevel readability
    highlight = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(highlight).line(
        [tri[0], tri[2]], fill=(200, 230, 255, 130), width=int(S * 0.0055), joint="curve")
    hl_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(hl_mask).polygon(tri, fill=255)
    img.paste(highlight, (0, 0), Image.composite(highlight.split()[3], Image.new("L", (S, S), 0), hl_mask))

    final = img.resize((1024, 1024), Image.LANCZOS)
    final.save(OUT / "logo.png")

    dark = Image.new("RGBA", (1024, 1024), (13, 15, 20, 255))
    dark.alpha_composite(final)
    dark.save(OUT / "logo_dark.png")
    print("OK:", OUT / "logo.png")


if __name__ == "__main__":
    main()
