"""Vidorq logo v4 (final combo picked by Munir): flat blue play (option A)
with a marked darker-blue border (option C), on the ring + symmetric
hexagonal spokes base. No gradients on the play - solid flat fill + outline
+ a soft drop shadow for a touch of lift.

Output: logo.png (transparent) + logo_dark.png (on brand dark background).
Run with the davinci-resolve-mcp venv (has Pillow).
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 4096
CX = CY = S // 2
R = int(S * 0.36)
OUT = Path(__file__).parent

VIOLET = (108, 92, 231)   # #6c5ce7 - ring/dots/spokes, flat
BLUE = (43, 130, 240)     # #2b82f0 - play, flat
BLUE_DARK = (18, 80, 170)  # marked border


def main():
    rng = random.Random(11)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    n = 22
    nodes = [(CX + R * math.cos(2 * math.pi * i / n), CY + R * math.sin(2 * math.pi * i / n))
             for i in range(n)]

    # Ring
    d.ellipse([CX - R, CY - R, CX + R, CY + R], outline=VIOLET + (255,), width=int(S * 0.006))

    # 6 symmetric spokes (evenly spaced sources), organic wobble, converge at center
    num_senders = 6
    senders = [round(i * n / num_senders) % n for i in range(num_senders)]
    for i in senders:
        x1, y1 = nodes[i]
        dx, dy = CX - x1, CY - y1
        dist = math.hypot(dx, dy)
        nx, ny = -dy / dist, dx / dist
        pts = [(x1, y1)]
        for s in range(1, 4):
            t = s / 4
            bx, by = x1 + dx * t, y1 + dy * t
            wobble = rng.uniform(-1, 1) * dist * 0.07 * math.sin(math.pi * t)
            pts.append((bx + nx * wobble, by + ny * wobble))
        pts.append((CX, CY))
        d.line(pts, fill=VIOLET + (255,), width=int(S * 0.0034), joint="curve")

    # Dots on the ring
    for i, (x, y) in enumerate(nodes):
        r = int(S * (0.022 if i % 4 == 0 else 0.015))
        d.ellipse([x - r, y - r, x + r, y + r], fill=VIOLET + (255,))

    # Play: flat blue, marked darker border, soft drop shadow behind
    pr = R * 0.5
    tri = [(CX - pr * 0.66, CY - pr * 0.8), (CX - pr * 0.66, CY + pr * 0.8), (CX + pr * 0.86, CY)]

    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).polygon(
        [(x + S * 0.010, y + S * 0.012) for x, y in tri], fill=(5, 15, 40, 140))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S * 0.010)))

    d.polygon(tri, fill=BLUE + (255,), outline=BLUE_DARK + (255,), width=int(S * 0.012))

    final = img.resize((1024, 1024), Image.LANCZOS)
    final.save(OUT / "logo.png")

    dark = Image.new("RGBA", (1024, 1024), (13, 15, 20, 255))
    dark.alpha_composite(final)
    dark.save(OUT / "logo_dark.png")
    print("OK:", OUT / "logo.png")


if __name__ == "__main__":
    main()
