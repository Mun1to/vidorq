"""Animated captions inside DaVinci Resolve, on the free edition.

Three walls stand between the scripting API and captions that look like the
paid plugins, and each one has a way round it that was measured, not assumed:

  the API cannot set keyframes          -> a .comp file carries its own splines,
                                           and ImportFusionComp keeps them
  the API cannot set a title's length   -> a caption is not a title at all: it
                                           is any clip placed with an exact
                                           recordFrame and an exact length, and
                                           the .comp goes on top of that
  a title always lands on V1, rippling  -> captions are built in their own
  whatever was already there               timeline and that timeline is nested
                                           on V2 of the real edit, which is a
                                           placement, not an insert

What comes out is a normal Resolve timeline: every caption is a Text+ the user
can open and edit by hand, which is the point of doing it this way instead of
burning pixels.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import captions as cap

# A title arrives 150 frames long, so anything inserted further ahead than that
# leaves the previous caption hanging on screen until it runs out. Only the slow
# path cares; the fast one states every length outright.
TITLE_DEFAULT_FRAMES = 150

# --------------------------------------------------------------------------- #
# Why captions are not made of titles any more
# --------------------------------------------------------------------------- #
# Putting one caption on a Resolve timeline used to cost 518 ms, and 89% of that
# was a single call: moving the playhead. Measured on 21.0.4.5 Free, with the
# connection to the bridge already open:
#
#     transporte (una peticion que no hace nada)     13.7 ms
#     /title/insert                                  31.4 ms
#     escribir la .comp en disco                      0.6 ms
#     /clip/fusion/import                            32.3 ms
#     /playhead                                     501.9 ms   <-- todo esto
#
# SetCurrentTimecode costs half a second whatever you do. Same on the Edit, Cut
# and Media pages. Same on an empty timeline and on one holding 25 Fusion
# titles. Same when it does not move at all, which is what settles it: it is not
# seeking, and it is not rendering. It is what that call costs.
#
# It was there because a title has no length of its own: you insert the next one
# where the previous should end and the ripple trims it. So every caption paid
# 500 ms for a length.
#
# /media/insert takes a recordFrame AND a length, so a clip lands exactly where
# it should be, exactly as long as it should be, with the playhead untouched. It
# needs a media file rather than a title, and that turns out not to matter: the
# comps this program writes are Text+ -> optional Blur -> optional Glow ->
# Saver, with no MediaIn anywhere, so the clip underneath never enters the
# graph. Proved rather than assumed: with a bright red placeholder, the clip
# without a comp exports as (255, 24, 0) and the clip with one exports as
# (0, 0, 0). The red never arrives, which is also why the caption still nests
# with its transparency intact.
#
#     antes:  518 ms por subtitulo  ->  389 s para los 751 de un video de 10 min
#     ahora:   52 ms por subtitulo  ->   39 s
SUPPORT_SECONDS = 20


def support_clip(work_dir, fps):
    """A throwaway video for the captions to sit on, made once per frame rate.

    Its frame rate has to match the timeline's. Source frames and timeline
    frames are not the same unit, and a 30 fps placeholder on a 24 fps timeline
    hands out captions 20% short - measured, and it looks like a rounding bug
    everywhere except where it is.
    """
    import subprocess
    r = max(1, int(round(float(fps or 30))))
    path = Path(work_dir) / ("vidorq_soporte_%dfps.mp4" % r)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("hace falta ffmpeg para preparar los subtitulos")
    subprocess.run(
        [exe, "-hide_banner", "-loglevel", "error", "-f", "lavfi",
         "-i", "color=c=black:s=64x36:r=%d:d=%d" % (r, SUPPORT_SECONDS),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(path)],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        capture_output=True, timeout=120, check=True)
    return path


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


def timeline_fps(tl, fallback=30.0):
    """The frame rate of the timeline in front of us, worked out from itself.

    Not the video's. They are different numbers and using the wrong one bends
    every caption: a 29.97 source on a 24 fps timeline puts a caption meant for
    9:42 at 12:07, drifting a little more with every second, and the last third
    of them land past the end of the edit entirely. Measured on a ten minute
    video, against the .srt that carries the true times.

    The bridge does not report a frame rate, so it comes out of the two numbers
    that are always there: a timeline starts at a timecode and at a frame, and
    the frame count of that timecode is seconds x fps. Resolve's usual start is
    01:00:00:00, so 86400 frames is 24 fps and 107892 is 29.97.
    """
    try:
        start = int(tl.get("startFrame", 0))
        h, m, sec, f = (int(x) for x in
                        str(tl.get("startTimecode") or "01:00:00:00")
                        .replace(";", ":").split(":"))
        secs = h * 3600 + m * 60 + sec
        if secs > 0 and start > 0:
            got = (start - f) / float(secs)
            # Snapped to the rates a timeline can actually have, and to the
            # CLOSEST one rather than the first that is near: 24 and 23.976 sit
            # 0.024 apart, so "near enough" picks whichever happens to be
            # earlier in the list. Anything far from all of them means the
            # arithmetic did not apply here, and guessing is exactly how the
            # bug this function exists to fix got in.
            known = min((23.976, 24, 25, 29.97, 30, 47.952, 48, 50, 59.94, 60),
                        key=lambda r: abs(got - r))
            if abs(got - known) < 0.6:
                return float(known)
    except Exception:
        pass
    return float(fallback)


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


def _place_fast(post, get, real, work_dir, fps, start_frame, say):
    """Place every caption with /media/insert. Returns False if it is not there.

    Each caption states its own recordFrame and its own length, so nothing
    trims anything and the order does not matter. A caption is clamped so it
    cannot run into the next one: two clips fighting for a frame on V1 is how
    you get a caption that disappears for no visible reason.
    """
    try:
        support = support_clip(work_dir, fps)
    except Exception as e:
        say("sin clip de soporte (%s), voy por el camino lento" % str(e)[:60])
        return False
    got = post("/media/import", {"filePaths": [str(support)]})
    if not (got.get("success") or got.get("imported")):
        say("Resolve no acepto el clip de soporte, voy por el camino lento")
        return False

    limit = int(round(SUPPORT_SECONDS * float(fps or 30))) - 1
    placed = 0
    for i, ev in enumerate(real):
        end = real[i + 1]["frame"] if i + 1 < len(real) else None
        want = int(round((ev["chunk"]["end"] - ev["chunk"]["start"]) * fps))
        if end is not None:
            want = min(want, end - ev["frame"])
        dur = max(1, min(want, limit))
        r = post("/media/insert", {"clipName": support.name, "trackIndex": 1,
                                   "recordFrame": int(ev["frame"]),
                                   "startFrame": 0, "endFrame": dur})
        if not r.get("success"):
            if placed == 0:
                # Un puente sin /media/insert lo dice en la primera llamada, y
                # ahi todavia no hay nada que deshacer.
                say("este puente no coloca clips por frame, voy por el camino lento")
                return False
            raise RuntimeError("Resolve dejo de aceptar subtitulos en el %d: %s" % (i, r))
        placed += 1
    say("%d subtitulos colocados sin mover el cabezal" % placed)
    return True


def _place_slow(post, get, plan, start_frame, start_tc, fps, say):
    """El camino de antes: un Text+ por evento, cada uno recortando al anterior.

    Se queda como red para un puente viejo que no tenga /media/insert. Cuesta
    medio segundo por subtitulo, todo el en mover el cabezal.
    """
    for ev in plan:
        post("/playhead", {"timecode": frame_to_tc(ev["frame"], start_frame, start_tc, fps)})
        r = post("/title/insert", {"titleName": "Text+", "fusionTitle": True})
        if not r.get("success"):
            raise RuntimeError("Resolve no acepto un Text+: %s" % r)
    say("%d titulos colocados" % len(plan))
    junk = [i for i, ev in enumerate(plan) if ev["spacer"]]
    clips = (get("/timeline/clips?track_type=video&track_index=1") or {}).get("clips", [])
    junk += list(range(len(plan), len(clips)))
    if junk:
        post("/timeline/clips/delete", {
            "clips": [{"trackType": "video", "trackIndex": 1, "clipIndex": i} for i in junk],
            "ripple": False})


def build_subs(post, get, timeline_name, chunks, preset_name, work_dir,
               width=1920, height=1080, fps=30.0, log=None, anim=""):
    """Build <timeline_name>_Subs, full of captions, and leave it there.

    Split from the nesting so the caller decides when each half happens, which
    matters because this output exists to be WATCHED. Building the captions
    before the edit was tried and measured and it is worse: the user spends
    forty seconds on a timeline they do not recognise and then their edit
    appears fully formed in one second, which looks like nothing happened.
    Built after, it reads as three acts, and the middle one is the one that
    looks like a machine editing.

    `post` and `get` are the engine's two bridge callers.
    """
    def say(msg):
        if log:
            log(msg)

    plan = _events(chunks, fps, 0)
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

    # Now that the captions timeline exists and is current, its own start is the
    # clock the titles are placed against. Before the split this read whatever
    # timeline happened to be open, which was the host; now there is no host yet.
    tl = get("/timeline") or {}
    start_frame = int(tl.get("startFrame", 0))
    start_tc = tl.get("startTimecode") or "01:00:00:00"
    # From here on the only clock that matters is the timeline's own. What the
    # caller handed in is the VIDEO's rate, which is a different number and the
    # wrong one: see timeline_fps.
    real_fps = timeline_fps(tl, fps)
    if abs(real_fps - float(fps)) > 0.01:
        say("el timeline va a %g fps y el video a %g; mando el timeline"
            % (real_fps, float(fps)))
    fps = real_fps
    plan = _events(chunks, fps, start_frame)

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

    # 2) One clip per caption, placed outright: exact frame, exact length, and
    #    the playhead never moves. See the note at the top of this file for the
    #    measurements that made this the only sensible way round.
    real = [ev for ev in plan if not ev["spacer"]]
    fast = _place_fast(post, get, real, work_dir, fps, start_frame, say)
    if not fast:
        _place_slow(post, get, plan, start_frame, start_tc, fps, say)

    # 3) Now every clip has its final length, so the comps can be written
    #    against it and the entrance animation fits its own caption.
    clips = (get("/timeline/clips?track_type=video&track_index=1") or {}).get("clips", [])
    if not clips:
        # The titles are on the timeline; without this list there is no way to
        # know how long each one ended up, so the comps cannot be written and
        # every caption would keep Text+'s own "Custom Title". Stopping is the
        # honest outcome: a timeline full of placeholder text looks like the
        # program worked and is worse than an error.
        raise RuntimeError("Resolve no devolvio los %d titulos de '%s'; sin esa "
                           "lista los subtitulos saldrian en blanco"
                           % (len(real), subs))
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

    return {"captions": done, "timeline": subs, "preset": preset_name,
            "anim": anim or "la del estilo"}


def nest_subs(post, get, timeline_name, subs):
    """Drop the finished caption timeline over V2 of the real edit.

    The last thing that happens, so the captions land on a timeline the user is
    already looking at. Nested rather than copied because a nest stays editable:
    open it and every caption is still its own Text+.
    """
    if not switch_to(post, get, timeline_name):
        raise RuntimeError("Los subtitulos estan en '%s' pero no encuentro el timeline '%s'"
                           % (subs, timeline_name))
    host = get("/timeline") or {}
    if int(host.get("trackCount", {}).get("video", 1)) < 2:
        post("/track/add", {"trackType": "video"})
    out = post("/media/insert", {"clipName": subs, "trackIndex": 2,
                                 "recordFrame": int(host.get("startFrame", 0))})
    if not out.get("success"):
        raise RuntimeError("Los subtitulos existen en '%s' pero no pude anidarlos: %s"
                           % (subs, out))
    return out
