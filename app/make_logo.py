"""Vidorq logo v5 - executed with actual craft this time.

Everything Munir asked across the whole conversation:
- a REAL ring (full circle) with dots on it
- from SOME dots, short lines with an organic-but-ORDERED shape run inward:
  circuit-board style traces (radial run + one clean 45-degree elbow + end pad),
  6 of them in hexagonal symmetry, elbow direction alternating for rhythm
- traces STOP before the play with breathing room (no ugly collisions)
- play button: flat blue (option A) with a marked darker border (option C),
  rounded corners, subtle drop shadow for a raised feel, optically centered
- flat and simple: exactly two colors + one shadow

Output: logo.png (transparent) + logo_dark.png (dark background preview).
"""
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 4096
CX = CY = S / 2
R = S * 0.36
OUT = Path(__file__).parent

VIOLET = (108, 92, 231)     # #6c5ce7 ring, dots, traces
BLUE = (43, 130, 240)       # #2b82f0 play fill (flat)
BLUE_DARK = (16, 72, 152)   # play border (marked)


def polar(radius, ang):
    return (CX + radius * math.cos(ang), CY + radius * math.sin(ang))


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # ---- ring ----
    ring_w = int(S * 0.005)
    d.ellipse([CX - R, CY - R, CX + R, CY + R], outline=VIOLET + (255,), width=ring_w)

    # ---- nodes: 24 dots, every 4th is an emitter (bigger). 15-degree offset
    # keeps emitters away from 0/180 degrees so no trace hits the play tip. ----
    n = 24
    offset = math.pi / 12
    angles = [2 * math.pi * i / n + offset for i in range(n)]
    emitters = [i for i in range(n) if i % 4 == 2]   # 6, hexagonal symmetry

    # ---- circuit traces: radial run -> one clean elbow -> end pad ----
    trace_w = int(S * 0.0036)
    for k, i in enumerate(emitters):
        a = angles[i]
        p0 = polar(R, a)
        p1 = polar(R * 0.80, a)                       # straight radial run
        bend = math.radians(38) * (1 if k % 2 == 0 else -1)  # alternate elbows
        toward_center = a + math.pi                   # direction pointing inward
        elbow_dir = toward_center + bend
        run2 = R * 0.19
        p2 = (p1[0] + run2 * math.cos(elbow_dir), p1[1] + run2 * math.sin(elbow_dir))
        d.line([p0, p1, p2], fill=VIOLET + (255,), width=trace_w, joint="curve")
        pad = S * 0.0085
        d.ellipse([p2[0] - pad, p2[1] - pad, p2[0] + pad, p2[1] + pad], fill=VIOLET + (255,))

    # ---- dots on the ring (uniform rhythm: emitters big, rest small) ----
    for i, a in enumerate(angles):
        x, y = polar(R, a)
        r = S * (0.019 if i in emitters else 0.0125)
        d.ellipse([x - r, y - r, x + r, y + r], fill=VIOLET + (255,))

    # ---- play button: optically centered, rounded, flat blue + marked border ----
    h = R * 0.40                                       # half height
    w = 2 * h * 0.866                                  # equilateral width
    x_left = CX - w / 2 + w * 0.06                     # optical shift right
    tri = [(x_left, CY - h), (x_left, CY + h), (x_left + w, CY)]

    def incenter(t):
        (ax, ay), (bx, by), (cx2, cy2) = t
        la = math.dist(t[1], t[2])
        lb = math.dist(t[0], t[2])
        lc = math.dist(t[0], t[1])
        p = la + lb + lc
        return ((la * ax + lb * bx + lc * cx2) / p, (la * ay + lb * by + lc * cy2) / p)

    def shrink(t, dist):
        ix, iy = incenter(t)
        (ax, ay) = t[0]
        la = math.dist(t[1], t[2])
        lb = math.dist(t[0], t[2])
        lc = math.dist(t[0], t[1])
        s_semi = (la + lb + lc) / 2
        area = abs((t[1][0] - ax) * (t[2][1] - ay) - (t[2][0] - ax) * (t[1][1] - ay)) / 2
        r_in = area / s_semi
        f = max(0.0, (r_in - dist) / r_in)
        return [(ix + (px - ix) * f, iy + (py - iy) * f) for px, py in t]

    def rounded_tri(draw, t, color, corner):
        draw.polygon(t, fill=color)
        draw.line(t + [t[0]], fill=color, width=int(corner * 2), joint="curve")

    corner = S * 0.012
    border = S * 0.0095

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sh = [(x + S * 0.007, y + S * 0.010) for x, y in tri]
    rounded_tri(ImageDraw.Draw(shadow), sh, (8, 20, 50, 130), corner)
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S * 0.008)))

    rounded_tri(d, tri, BLUE_DARK + (255,), corner)
    rounded_tri(d, shrink(tri, border), BLUE + (255,), max(corner - border, S * 0.003))

    final = img.resize((1024, 1024), Image.LANCZOS)
    final.save(OUT / "logo.png")
    dark = Image.new("RGBA", (1024, 1024), (13, 15, 20, 255))
    dark.alpha_composite(final)
    dark.save(OUT / "logo_dark.png")
    print("OK:", OUT / "logo.png")


if __name__ == "__main__":
    main()
