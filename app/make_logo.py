"""Vidorq logo v2: flat, simple. A circle of dots with a play button in the
center; a handful of dots send a thin, loosely-random line inward to the play.

No gradients, no glow, no shadows - pure flat design. Supersampled and
downscaled for crisp anti-aliased edges (no blur filters needed).
Output: logo.png (transparent) + logo_dark.png (on brand dark background).
Run with the davinci-resolve-mcp venv (has Pillow).
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw

S = 4096  # supersample; final 1024
CX = CY = S // 2
R = int(S * 0.36)
OUT = Path(__file__).parent

FLAT = (108, 92, 231)       # #6c5ce7 - the one flat brand color
WHITE = (255, 255, 255)


def main():
    rng = random.Random(7)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    n = 22
    nodes = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        x = CX + R * math.cos(ang)
        y = CY + R * math.sin(ang)
        nodes.append((x, y))

    # Play triangle geometry (drawn last, on top) - flat white, sharp edges
    pr = R * 0.5
    off = pr * 0.12
    tri = [(CX - pr * 0.6 + off, CY - pr * 0.78),
           (CX - pr * 0.6 + off, CY + pr * 0.78),
           (CX + pr * 0.82 + off, CY)]

    # A handful of dots send a thin, loosely-random line inward toward the play.
    # Not straight: nudge a couple of interior control points off-axis so each
    # line reads as an organic squiggle rather than a ruled line. Endpoints are
    # spread along the play's silhouette instead of one exact point, so the
    # lines read as separate wandering paths rather than a starburst.
    senders = sorted(rng.sample(range(n), 6))
    for k, i in enumerate(senders):
        x1, y1 = nodes[i]
        spread = (k / (len(senders) - 1) - 0.5) * pr * 0.9
        tx, ty = CX + off * 0.3 - pr * 0.15, CY + spread
        dx, dy = tx - x1, ty - y1
        dist = math.hypot(dx, dy)
        nx, ny = -dy / dist, dx / dist  # unit normal, for perpendicular jitter
        pts = [(x1, y1)]
        steps = 4
        for s in range(1, steps):
            t = s / steps
            bx = x1 + dx * t
            by = y1 + dy * t
            wobble = rng.uniform(-1, 1) * dist * 0.1 * math.sin(math.pi * t)
            pts.append((bx + nx * wobble, by + ny * wobble))
        pts.append((tx, ty))
        d.line(pts, fill=FLAT + (255,), width=int(S * 0.0036), joint="curve")

    # Dots on the circle - flat fill, two sizes for a bit of rhythm, no gradient
    for i, (x, y) in enumerate(nodes):
        r = int(S * (0.022 if i % 4 == 0 else 0.015))
        d.ellipse([x - r, y - r, x + r, y + r], fill=FLAT + (255,))

    d.polygon(tri, fill=WHITE + (255,))

    final = img.resize((1024, 1024), Image.LANCZOS)
    final.save(OUT / "logo.png")

    dark = Image.new("RGBA", (1024, 1024), (13, 15, 20, 255))
    dark.alpha_composite(final)
    dark.save(OUT / "logo_dark.png")
    print("OK:", OUT / "logo.png")


if __name__ == "__main__":
    main()
