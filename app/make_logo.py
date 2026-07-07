"""Vidorq provisional logo: a circle of AI 'neurons' with a play button inside.

Draws at 4x and downsamples for crisp edges. Output: logo.png (1024x1024,
transparent) + logo_dark.png (on brand dark background, for previews).
Run with the davinci-resolve-mcp venv (has Pillow).
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 4096  # supersample; final 1024
CX = CY = S // 2
R = int(S * 0.36)          # neuron ring radius
OUT = Path(__file__).parent

C1 = (108, 92, 231)        # #6c5ce7
C2 = (176, 106, 179)       # #b06ab3


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def main():
    rng = random.Random(42)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # Neuron ring: nodes placed on the circle with slight jitter
    n = 28
    nodes = []
    for i in range(n):
        ang = 2 * math.pi * i / n
        rr = R + rng.randint(-int(S * 0.008), int(S * 0.008))
        x = CX + rr * math.cos(ang)
        y = CY + rr * math.sin(ang)
        nodes.append((x, y, ang))

    def col(ang):
        t = (math.sin(ang) + 1) / 2
        return lerp(C1, C2, t)

    # Connections: neighbours (strong) + a few skips (weak) = neural look
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(n):
        x1, y1, a1 = nodes[i]
        for step, alpha, w in ((1, 230, int(S * 0.006)), (2, 90, int(S * 0.0035))):
            x2, y2, a2 = nodes[(i + step) % n]
            gd.line([(x1, y1), (x2, y2)], fill=col((a1 + a2) / 2) + (alpha,), width=w)
    # soft outer glow
    blur = glow.filter(ImageFilter.GaussianBlur(S * 0.004))
    img.alpha_composite(blur)
    img.alpha_composite(glow)

    # Nodes on top (alternating sizes, brighter fill + tiny highlight)
    for i, (x, y, ang) in enumerate(nodes):
        r = int(S * (0.016 if i % 3 else 0.024))
        c = col(ang)
        d.ellipse([x - r * 1.9, y - r * 1.9, x + r * 1.9, y + r * 1.9], fill=c + (60,))
        d.ellipse([x - r, y - r, x + r, y + r], fill=lerp(c, (255, 255, 255), 0.25) + (255,))

    # Play triangle: white, rounded feel, optically centered (shifted right slightly)
    pr = R * 0.52
    off = pr * 0.14
    pts = [(CX - pr * 0.62 + off, CY - pr * 0.80),
           (CX - pr * 0.62 + off, CY + pr * 0.80),
           (CX + pr * 0.78 + off, CY)]
    tri = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    td = ImageDraw.Draw(tri)
    td.polygon(pts, fill=(255, 255, 255, 255))
    tri = tri.filter(ImageFilter.GaussianBlur(S * 0.0015))  # soften corners a touch
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.polygon([(p[0] + S * 0.004, p[1] + S * 0.006) for p in pts], fill=C1 + (140,))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(S * 0.01)))
    img.alpha_composite(tri)

    final = img.resize((1024, 1024), Image.LANCZOS)
    final.save(OUT / "logo.png")

    dark = Image.new("RGBA", (1024, 1024), (13, 15, 20, 255))
    dark.alpha_composite(final)
    dark.save(OUT / "logo_dark.png")
    print("OK:", OUT / "logo.png")


if __name__ == "__main__":
    main()
