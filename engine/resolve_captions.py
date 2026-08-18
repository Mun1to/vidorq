"""Animated captions inside DaVinci Resolve, on the free edition.

Three walls stand between the scripting API and captions that look like the
paid plugins, and each one has a way round it that was measured, not assumed:

  the API cannot set keyframes          -> a .comp file carries its own splines,
                                           and ImportFusionComp keeps them
  the API cannot set a title's length   -> inserting the next title trims the
                                           previous one, so inserting in time
                                           order hands out exact durations
  a title always lands on V1, rippling  -> captions are built in their own
  whatever was already there               timeline and that timeline is nested
                                           on V2 of the real edit, which is a
                                           placement, not an insert

What comes out is a normal Resolve timeline: every caption is a Text+ the user
can open and edit by hand, which is the point of doing it this way instead of
burning pixels.
"""
from __future__ import annotations

from pathlib import Path

import captions as cap

# A title arrives 150 frames long, so anything inserted further ahead than that
# leaves the previous caption hanging on screen until it runs out.
TITLE_DEFAULT_FRAMES = 150


def frame_to_tc(frame, start_frame, start_tc, fps):
    """Timeline frame -> timecode string, which is all the bridge accepts.

    Timecode counts in whole frames (29.97 counts as 30), so the rate is
    rounded. Drop-frame timelines number differently and are left alone.
    """
    tc_fps = max(1, int(round(fps)))
    h0, m0, s0, f0 = (int(x) for x in start_tc.replace(";", ":").split(":"))
    base = ((h0 * 60 + m0) * 60 + s0) * tc_fps + f0
    total = base + (int(frame) - int(start_frame))
    total = max(0, total)
    f = total % tc_fps
    total //= tc_fps
    return "%02d:%02d:%02d:%02d" % (total // 3600, (total // 60) % 60, total % 60, f)


def switch_to(post, get, name):
    """Make `name` the current timeline.

    The bridge only switches by index and the project only reports how many
    timelines there are, so the name has to be found by walking them. Cheap: a
    project has a handful, not thousands.
    """
    if (get("/timeline") or {}).get("name") == name:
        return True
    total = int((get("/project") or {}).get("timelineCount", 0))
    for idx in range(1, total + 1):
        out = post("/timeline/switch", {"index": idx})
        if out.get("timeline") == name:
            return True
    return False


def _events(chunks, fps, start_frame):
    """The insert plan, in time order.

    Each caption needs a title at its start. A caption followed by silence also
    needs a throwaway title at its end, because that is the only thing that can
    cut it short; those get deleted once every duration is fixed.
    """
    plan = []
    for i, c in enumerate(chunks):
        s = start_frame + int(round(c["start"] * fps))
        e = start_frame + int(round(c["end"] * fps))
        if plan and s <= plan[-1]["frame"]:
            s = plan[-1]["frame"] + 1  # never insert twice on one frame
        if e <= s:
            e = s + 1
        plan.append({"frame": s, "chunk": c, "spacer": False})
        nxt = start_frame + int(round(chunks[i + 1]["start"] * fps)) if i + 1 < len(chunks) else None
        if nxt is None or nxt - e >= 2:
            plan.append({"frame": e, "chunk": None, "spacer": True})
    return plan


def build(post, get, timeline_name, chunks, preset_name, work_dir,
          width=1920, height=1080, fps=30.0, log=None, anim=""):
    """Build <timeline_name>_Subs and nest it over V2 of <timeline_name>.

    `post` and `get` are the engine's two bridge callers. Returns a summary dict.
    """
    def say(msg):
        if log:
            log(msg)

    tl = get("/timeline") or {}
    start_frame = int(tl.get("startFrame", 0))
    start_tc = tl.get("startTimecode") or "01:00:00:00"
    plan = _events(chunks, fps, start_frame)
    if not plan:
        return {"captions": 0, "timeline": None}

    # 1) A timeline that holds nothing but captions. Editing the same video
    #    twice must not fail on the name, so a taken one gets a number.
    base = "%s_Subs" % timeline_name[:40]
    subs = None
    for n in range(1, 20):
        candidate = base if n == 1 else "%s%d" % (base, n)
        if post("/timeline/create", {"name": candidate}).get("success"):
            subs = candidate
            break
    if not subs:
        raise RuntimeError("No pude crear el timeline de subtitulos '%s'" % base)

    # A new timeline is born with the project's shape, and this one ends up
    # NESTED inside the edit. Left at 16:9 inside a vertical edit, Resolve fits
    # it like any other clip: the captions come out at 56% of their size, parked
    # across the middle of the frame instead of near the bottom. Measured, not
    # guessed. One key per call, and useCustomSettings before the numbers.
    for key, value in (("useCustomSettings", "1"),
                       ("timelineResolutionWidth", str(int(width))),
                       ("timelineResolutionHeight", str(int(height)))):
        got = post("/timeline/setting", {"key": key, "value": value})
        if not got.get("success"):
            raise RuntimeError("Resolve no acepto %s=%s en '%s': %s"
                               % (key, value, subs, got.get("error", got)))

    # 2) One title per event, in time order, each trimming the one before it.
    for ev in plan:
        post("/playhead", {"timecode": frame_to_tc(ev["frame"], start_frame, start_tc, fps)})
        r = post("/title/insert", {"titleName": "Text+", "fusionTitle": True})
        if not r.get("success"):
            raise RuntimeError("Resolve no acepto un Text+: %s" % r)
    say("%d titulos colocados" % len(plan))

    # 3) Throw away the spacers and the tails the ripple left behind. Inserting
    #    in time order keeps the real ones at the front, so everything from
    #    len(plan) onwards is debris.
    junk = [i for i, ev in enumerate(plan) if ev["spacer"]]
    clips = (get("/timeline/clips?track_type=video&track_index=1") or {}).get("clips", [])
    junk += list(range(len(plan), len(clips)))
    if junk:
        post("/timeline/clips/delete", {
            "clips": [{"trackType": "video", "trackIndex": 1, "clipIndex": i} for i in junk],
            "ripple": False})

    # 4) Now every surviving clip has its final length, so the comps can be
    #    written against it and the entrance animation fits the caption.
    clips = (get("/timeline/clips?track_type=video&track_index=1") or {}).get("clips", [])
    real = [ev for ev in plan if not ev["spacer"]]
    if len(clips) != len(real):
        say("aviso: %d clips para %d subtitulos, uso los que hay" % (len(clips), len(real)))
    comp_dir = Path(work_dir) / "comps"
    comp_dir.mkdir(parents=True, exist_ok=True)
    done = 0
    for i, (ev, clip) in enumerate(zip(real, clips)):
        dur = max(2, int(clip.get("duration", TITLE_DEFAULT_FRAMES)))
        path = comp_dir / ("cap_%04d.comp" % i)
        cap.to_comp(path, ev["chunk"], width, height, dur, preset_name, anim or None)
        r = post("/clip/fusion/import", {"trackType": "video", "trackIndex": 1,
                                         "clipIndex": i,
                                         "path": str(path).replace("\\", "/")})
        if r.get("success"):
            done += 1
    say("%d subtitulos con estilo '%s'%s" % (done, preset_name,
                                          " y animacion '%s'" % anim if anim else ""))

    # 5) Back to the real edit, and drop the caption timeline on top of it.
    if not switch_to(post, get, timeline_name):
        raise RuntimeError("Los subtitulos estan en '%s' pero no encuentro el timeline '%s'"
                           % (subs, timeline_name))
    host = get("/timeline") or {}
    if int(host.get("trackCount", {}).get("video", 1)) < 2:
        post("/track/add", {"trackType": "video"})
    out = post("/media/insert", {"clipName": subs, "trackIndex": 2,
                                 "recordFrame": int(host.get("startFrame", start_frame))})
    if not out.get("success"):
        raise RuntimeError("Los subtitulos existen en '%s' pero no pude anidarlos: %s"
                           % (subs, out))
    return {"captions": done, "timeline": subs, "preset": preset_name,
            "anim": anim or "la del estilo"}
