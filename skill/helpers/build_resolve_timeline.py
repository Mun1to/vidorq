"""Vidorq: build an editable Resolve timeline from an EDL via the CursorBridge.

Talks HTTP to the bridge (127.0.0.1:9876) so cuts land in strict order:
  create timeline -> insert each keep-segment (source in/out) -> punch zoom
  on emphasis segments -> a marker per Q&A beat -> save.

This is the Resolve backend of Vidorq: same edl.json that the direct PyAV
render used, but here it produces a timeline you can still tweak by hand.
"""
import json
import sys
import urllib.request
from pathlib import Path

BRIDGE = "http://127.0.0.1:9876"
FPS = 30000 / 1001
CLIP = "Video SIN EDITAR de Luisito [W7VPKaDhBTs].mp4"
EDL = json.loads(Path(r"C:\Users\Muni\Downloads\edit\edl.json").read_text(encoding="utf-8"))["segments"]


def post(path, body):
    req = urllib.request.Request(
        BRIDGE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def main():
    tl_name = "Vidorq_Luisito_Edit"
    print("create timeline:", post("/timeline/create", {"name": tl_name}))

    record = 0
    marks = []
    for i, seg in enumerate(EDL):
        sf = round(seg["start"] * FPS)
        ef = round(seg["end"] * FPS) - 1
        dur = ef - sf + 1
        res = post("/media/insert", {"clipName": CLIP, "startFrame": sf, "endFrame": ef})
        ok = res.get("result", res).get("success")
        print(f"  insert {i:2d} sf={sf} ef={ef} -> {ok}")
        marks.append((record, seg))
        record += dur

    # Punch zooms on emphasis segments (static scale, no keyframes)
    for i, seg in enumerate(EDL):
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


if __name__ == "__main__":
    main()
