"""Vidorq: build an editable Resolve timeline from an EDL via the CursorBridge.

Talks HTTP to the bridge (127.0.0.1:9876) so cuts land in strict order:
  create timeline -> insert each keep-segment (source in/out) -> punch zoom
  on emphasis segments -> a marker per Q&A beat -> save.

This is the FIRST Resolve backend of Vidorq, from July, and it stays because it
is the smallest thing that proves the bridge works end to end. What the product
runs today is engine/server.py (output_resolve), which does all of this plus
native captions, transitions, overlays and a punch zoom that moves.

    python build_resolve_timeline.py edl.json "my video.mp4" [timeline name]
"""
import json
import sys
import urllib.request
from pathlib import Path

BRIDGE = "http://127.0.0.1:9876"
FPS = 30000 / 1001


def post(path, body):
    req = urllib.request.Request(
        BRIDGE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    # El EDL y el nombre del clip se pasan por la linea de comandos. Antes
    # estaban escritos aqui dentro, con la carpeta de Descargas de una persona
    # concreta y el nombre de su video, asi que en cualquier otro ordenador este
    # archivo reventaba al IMPORTARLO, antes siquiera de llegar a main(); y en
    # el suyo, ejecutarlo sin querer montaba un timeline entero.
    if len(sys.argv) < 3:
        print("uso: build_resolve_timeline.py <edl.json> <nombre del clip en el "
              "media pool> [nombre del timeline]")
        return 1
    edl = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))["segments"]
    clip = sys.argv[2]
    tl_name = sys.argv[3] if len(sys.argv) > 3 else "Vidorq_Edit"
    print("create timeline:", post("/timeline/create", {"name": tl_name}))

    record = 0
    marks = []
    for i, seg in enumerate(edl):
        sf = round(seg["start"] * FPS)
        ef = round(seg["end"] * FPS) - 1
        dur = ef - sf + 1
        res = post("/media/insert", {"clipName": clip, "startFrame": sf, "endFrame": ef})
        ok = res.get("result", res).get("success")
        print(f"  insert {i:2d} sf={sf} ef={ef} -> {ok}")
        marks.append((record, seg))
        record += dur

    # Punch zooms on emphasis segments (static scale, no keyframes)
    for i, seg in enumerate(edl):
        z = float(seg.get("zoom", 1.0))
        if z > 1.001:
            res = post("/clip/properties", {
                "trackType": "video", "trackIndex": 1, "clipIndex": i,
                "properties": {"ZoomX": z, "ZoomY": z}})
            print(f"  zoom  {i:2d} = {z} -> {res.get('result', res)}")

    # A marker per beat
    for rec, seg in marks:
        note = seg["note"]
        color = "Yellow" if ("Q" in note or "pregunta" in note.lower() or ":" in note) else "Green"
        res = post("/marker/add", {"frameId": rec, "color": color,
                                    "name": note[:40], "note": note})
        print(f"  marker@{rec} ({color}) -> {res.get('result', res).get('success')}")

    print("save:", post("/project/save", {}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
