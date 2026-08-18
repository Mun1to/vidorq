"""Where the faces are, so the vertical crop stops guessing.

Cropping a 16:9 video to 9:16 throws away two thirds of the width, so the only
question that matters is which third to keep. Two cheaper answers were measured
and both failed, and they are written up in docs/INTELIGENCIA.md:

  the centroid of detail and movement   3 frames right out of 6, one of them
                                        centred on a parked car
  asking a local vision model           answers "50" to every frame, including
                                        two that differ by 20% of the width

So this uses the thing built for the job: YuNet, a face detector of 227 KB that
runs on the CPU in milliseconds. It is not a language model and it does not
describe anything, it returns boxes.

No new dependency: the engine venv already carries onnxruntime, and the model
ships with the repo under its own MIT licence (skill/models/LICENSE.yunet.txt),
so this still works with the network unplugged.

The network is 640x640 with three output scales (80, 40 and 20 cells for
strides 8, 16 and 32). Everything below is the decoding of those cells into
boxes, which the ONNX file does not do for you.
"""
from __future__ import annotations

from pathlib import Path

MODEL = (Path(__file__).resolve().parent.parent / "models"
         / "face_detection_yunet_2023mar.onnx")
SIDE = 640
STRIDES = (8, 16, 32)
# Swept on real footage, seven frames with the answer known by eye. At 0.6 and
# 0.5 a face walking in the middle distance is missed; at 0.4 all seven are
# found and every one is right; at 0.2 a false positive grows bigger than the
# real face and steals the frame. So 0.4, and the margin either side is thin
# enough to be worth writing down.
CONF = 0.4
NMS_IOU = 0.3

_session = None


def available():
    """True when this machine can actually run the detector."""
    if not MODEL.exists():
        return False
    try:
        import onnxruntime  # noqa: F401
        import numpy  # noqa: F401
    except Exception:
        return False
    return True


def session():
    global _session
    if _session is None:
        import onnxruntime as ort
        opts = ort.SessionOptions()
        # Leave cores for ffmpeg, which is the part that actually takes minutes.
        opts.intra_op_num_threads = 4
        opts.log_severity_level = 3
        _session = ort.InferenceSession(str(MODEL), opts,
                                        providers=["CPUExecutionProvider"])
    return _session


def _letterbox(img):
    """PIL image to a (1,3,640,640) blob, plus how to undo the fit.

    Padded, not stretched: squashing a 16:9 frame into a square turns faces into
    something the detector was never trained on.
    """
    import numpy as np
    w, h = img.size
    scale = min(SIDE / w, SIDE / h)
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    small = img.convert("RGB").resize((nw, nh))
    canvas = np.zeros((SIDE, SIDE, 3), dtype="float32")
    px, py = (SIDE - nw) // 2, (SIDE - nh) // 2
    canvas[py:py + nh, px:px + nw] = np.asarray(small, dtype="float32")
    # BGR, 0-255, no normalisation: that is what this model was exported with.
    blob = canvas[:, :, ::-1].transpose(2, 0, 1)[None]
    return np.ascontiguousarray(blob), scale, px, py


def _decode(out, names, scale, px, py, w, h):
    import numpy as np
    boxes, scores = [], []
    for stride in STRIDES:
        cls = out[names.index("cls_%d" % stride)][0]
        obj = out[names.index("obj_%d" % stride)][0]
        box = out[names.index("bbox_%d" % stride)][0]
        cells = SIDE // stride
        # The confidence is the geometric mean of "there is an object here" and
        # "that object is a face". Either one alone lets through walls.
        conf = np.sqrt(np.clip(cls[:, 0], 0, 1) * np.clip(obj[:, 0], 0, 1))
        keep = np.where(conf >= CONF)[0]
        if not len(keep):
            continue
        rows, cols = keep // cells, keep % cells
        cx = (cols + box[keep, 0]) * stride
        cy = (rows + box[keep, 1]) * stride
        bw = np.exp(box[keep, 2]) * stride
        bh = np.exp(box[keep, 3]) * stride
        # Out of the letterbox, back into the original frame, then to 0-1 so the
        # rest of Vidorq never has to care what resolution anything was.
        x1 = (cx - bw / 2 - px) / scale / w
        y1 = (cy - bh / 2 - py) / scale / h
        boxes.append(np.stack([x1, y1, bw / scale / w, bh / scale / h], axis=1))
        scores.append(conf[keep])
    if not boxes:
        return []
    return _nms(np.concatenate(boxes), np.concatenate(scores))


def _nms(boxes, scores):
    """Plain greedy non-maximum suppression. A face fires on several cells."""
    import numpy as np
    order = np.argsort(-scores)
    x1, y1 = boxes[:, 0], boxes[:, 1]
    x2, y2 = x1 + boxes[:, 2], y1 + boxes[:, 3]
    area = np.maximum(0, boxes[:, 2]) * np.maximum(0, boxes[:, 3])
    out = []
    while len(order):
        i = order[0]
        out.append(i)
        if len(order) == 1:
            break
        rest = order[1:]
        ix1 = np.maximum(x1[i], x1[rest])
        iy1 = np.maximum(y1[i], y1[rest])
        ix2 = np.minimum(x2[i], x2[rest])
        iy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0, ix2 - ix1) * np.maximum(0, iy2 - iy1)
        iou = inter / np.maximum(1e-9, area[i] + area[rest] - inter)
        order = rest[iou <= NMS_IOU]
    return [{"x": float(boxes[i, 0]), "y": float(boxes[i, 1]),
             "w": float(boxes[i, 2]), "h": float(boxes[i, 3]),
             "score": float(scores[i])} for i in out]


def detect(img):
    """Faces in one PIL image, as boxes in 0-1 of the frame, best first."""
    blob, scale, px, py = _letterbox(img)
    s = session()
    names = [o.name for o in s.get_outputs()]
    out = s.run(names, {s.get_inputs()[0].name: blob})
    w, h = img.size
    return _decode(out, names, scale, px, py, w, h)


# How far below the best score in a frame a detection can be and still count as
# a real face. Measured: in a selfie shot the outstretched ARM holding the
# camera detects as a face at 0.60 to 0.71 while the actual face sits at 0.85 to
# 0.88, and the arm is BIGGER, so picking the biggest box framed the video on an
# elbow. Two genuine faces in one shot both score high and both survive this.
SAME_LEAGUE = 0.85


def main_face(faces):
    """The one to frame on.

    Not simply the biggest: size alone picks whichever mistake happens to be
    closest to the lens. So the weak detections are dropped first, relative to
    the best one in this frame, and only then does near beat far.
    """
    if not faces:
        return None
    best = max(f["score"] for f in faces)
    real = [f for f in faces if f["score"] >= best * SAME_LEAGUE]
    return max(real, key=lambda f: f["w"] * f["h"])


def at_times(video, times, log=None):
    """{second: horizontal centre of the main face, 0-1}. Missing = no face."""
    import io
    from PIL import Image
    import vision
    frames = vision.grab(video, times, width=SIDE)
    out = {}
    for n, (t, jpeg) in enumerate(sorted(frames.items()), 1):
        try:
            face = main_face(detect(Image.open(io.BytesIO(jpeg))))
        except Exception as e:
            if log:
                log("cara %.1fs: %s" % (t, str(e)[:80]))
            continue
        if face:
            out[t] = face["x"] + face["w"] / 2
        if log and n % 20 == 0:
            log("caras buscadas en %d/%d momentos" % (n, len(frames)))
    return out


# How many looks per cut. Three is the useful number: one can land on a frame
# where the person turned away, and more than three costs decoding without
# changing a median.
LOOKS = 3


def frame_edl(video, edl, default=0.5, log=None):
    """Fills every cut's frame_x with where the face actually is.

    Returns how many cuts got a real answer, because a caller that gets zero
    should say so rather than pretend the crop is tracked.
    """
    import numpy as np
    want = []
    for seg in edl:
        s, e = float(seg["start"]), float(seg["end"])
        want += [round(s + (e - s) * ((i + 0.5) / LOOKS), 2)
                 for i in range(LOOKS)]
    found = at_times(video, want, log=log)
    hits = 0
    for seg in edl:
        s, e = float(seg["start"]), float(seg["end"])
        xs = [x for t, x in found.items() if s - 0.05 <= t <= e + 0.05]
        if xs:
            # Median, so one frame where a hand crosses the lens cannot drag the
            # whole cut sideways.
            seg["frame_x"] = float(np.median(np.array(xs, dtype="float32")))
            hits += 1
        else:
            seg["frame_x"] = default
    return hits
