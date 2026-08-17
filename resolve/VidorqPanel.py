"""Vidorq panel that lives inside DaVinci Resolve (Workspace > Scripts > VidorqPanel).

One brain, two faces: this panel is a thin client for the same local engine the
desktop app talks to (127.0.0.1:9877). It adds the one thing the external window
cannot do - it reads the clips straight out of the open Resolve project, so the
user never types a path.

Requires the Fusion UIManager API. That is the fragile part on the Free edition
(Blackmagic broke it in 19.1 without notice), so availability is checked up front
and reported in plain language instead of failing with a stack trace.
"""

import json
import locale
import urllib.request
import urllib.error

ENGINE = "http://127.0.0.1:9877"
POLL_MS = 700


def system_lang():
    """Spanish if the machine is Spanish, English otherwise. No setting to fiddle with."""
    try:
        code = (locale.getdefaultlocale()[0] or "").lower()
    except Exception:
        code = ""
    return "es" if code.startswith("es") else "en"


LANG = system_lang()

TEXT = {
    "es": {
        "sub": "Describe la edicion. El resto es nuestro.",
        "clip_label": "Video del proyecto",
        "reload": "Refrescar",
        "preset_label": "Que le hacemos",
        "caps": "Captions animados",
        "go": "EDITAR EN ESTE TIMELINE",
        "checking": "Comprobando el motor...",
        "engine_off": "Motor apagado",
        "engine_off_help": "Arrancalo con engine\\start_engine.bat y pulsa Refrescar.",
        "engine_ok": "Motor conectado. Elige un video y dale.",
        "engine_ok_n": "Motor conectado. %d videos.",
        "no_clips": "(no hay videos en esta carpeta del media pool)",
        "pick_first": "Elige un video del proyecto primero.",
        "working": "Editando...",
        "error": "Error",
        "done": "Listo. Timeline montado en Resolve.",
        "no_ui": "Esta version de Resolve no expone UIManager: %s",
        "no_ui_2": "El panel interno no puede dibujarse aqui.",
        "no_ui_3": "Usa la ventana externa de Vidorq (el motor es el mismo).",
        "no_resolve": "No se pudo obtener el objeto Resolve. Abre un proyecto primero.",
        "closed": "Cerrado.",
        "presets": [
            "Limpieza - corta silencios y muletillas",
            "Podcast Q&A - marca cada pregunta",
            "Montage (beta) - se queda la energia",
        ],
    },
    "en": {
        "sub": "Describe the edit. We handle the rest.",
        "clip_label": "Video from the project",
        "reload": "Refresh",
        "preset_label": "What we do to it",
        "caps": "Animated captions",
        "go": "EDIT INTO THIS TIMELINE",
        "checking": "Checking the engine...",
        "engine_off": "Engine off",
        "engine_off_help": "Start it with engine\\start_engine.bat, then hit Refresh.",
        "engine_ok": "Engine connected. Pick a video and go.",
        "engine_ok_n": "Engine connected. %d videos.",
        "no_clips": "(no videos in this media pool folder)",
        "pick_first": "Pick a video from the project first.",
        "working": "Editing...",
        "error": "Error",
        "done": "Done. Timeline built in Resolve.",
        "no_ui": "This Resolve build does not expose UIManager: %s",
        "no_ui_2": "The in-app panel cannot be drawn here.",
        "no_ui_3": "Use the Vidorq desktop window instead (same engine).",
        "no_resolve": "Could not get the Resolve object. Open a project first.",
        "closed": "Closed.",
        "presets": [
            "Cleanup - cuts silences and filler words",
            "Podcast Q&A - marks every question",
            "Montage (beta) - keeps the energy",
        ],
    },
}

T = TEXT[LANG]
PRESET_IDS = ["clean", "podcast", "montage"]

# --------------------------------------------------------------------------- #
# Engine client
# --------------------------------------------------------------------------- #
def engine_get(path, timeout=3):
    try:
        with urllib.request.urlopen(ENGINE + path, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def engine_post(path, payload, timeout=10):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(ENGINE + path, data=data,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"error": "El motor respondio %s" % e.code}
    except Exception:
        return {"error": "No se pudo hablar con el motor. Arrancalo con engine/start_engine.bat"}


# --------------------------------------------------------------------------- #
# Resolve project reading - the reason this panel exists
# --------------------------------------------------------------------------- #
def get_resolve():
    try:
        return bmd.scriptapp("Resolve")  # noqa: F821 - injected by Resolve
    except Exception:
        return None


def list_project_clips(resolve):
    """Video clips of the current media pool folder, as [(label, path), ...]."""
    out = []
    try:
        project = resolve.GetProjectManager().GetCurrentProject()
        folder = project.GetMediaPool().GetCurrentFolder()
        for clip in folder.GetClipList() or []:
            path = clip.GetClipProperty("File Path")
            if not path:
                continue
            if path.lower().endswith((".mp4", ".mov", ".mkv", ".webm", ".avi")):
                out.append((clip.GetName(), path))
    except Exception:
        pass
    return out


# --------------------------------------------------------------------------- #
# UI
# --------------------------------------------------------------------------- #
def bar(percent):
    filled = int(round(max(0, min(100, percent)) / 5.0))
    return "%s%s  %d%%" % ("#" * filled, "." * (20 - filled), percent)


def main():
    try:
        ui = fusion.UIManager          # noqa: F821 - injected by Resolve
        disp = bmd.UIDispatcher(ui)    # noqa: F821 - injected by Resolve
    except Exception as e:
        print("[VidorqPanel] " + T["no_ui"] % e)
        print("[VidorqPanel] " + T["no_ui_2"])
        print("[VidorqPanel] " + T["no_ui_3"])
        return

    resolve = get_resolve()
    if resolve is None:
        print("[VidorqPanel] " + T["no_resolve"])
        return

    clips = list_project_clips(resolve)
    clip_paths = [p for _, p in clips]

    win = disp.AddWindow({
        "ID": "VidorqWin",
        "WindowTitle": "Vidorq",
        "Geometry": [200, 150, 460, 430],
    }, [
        ui.VGroup({"Spacing": 8, "Weight": 0}, [
            ui.Label({"Text": "VIDORQ", "Weight": 0,
                      "StyleSheet": "font-size: 20px; font-weight: bold; color: #8f7bff;"}),
            ui.Label({"ID": "Sub", "Text": T["sub"],
                      "Weight": 0, "StyleSheet": "color: #8b95a8; font-size: 11px;"}),

            ui.VGap(6),
            ui.Label({"Text": T["clip_label"], "Weight": 0,
                      "StyleSheet": "color: #8b95a8; font-size: 11px;"}),
            ui.HGroup({"Weight": 0, "Spacing": 6}, [
                ui.ComboBox({"ID": "Clip", "Weight": 1}),
                ui.Button({"ID": "Reload", "Text": T["reload"], "Weight": 0}),
            ]),

            ui.VGap(6),
            ui.Label({"Text": T["preset_label"], "Weight": 0,
                      "StyleSheet": "color: #8b95a8; font-size: 11px;"}),
            ui.ComboBox({"ID": "Preset", "Weight": 0}),

            ui.VGap(4),
            ui.CheckBox({"ID": "Caps", "Text": T["caps"], "Checked": True, "Weight": 0}),

            ui.VGap(10),
            ui.Button({"ID": "Go", "Text": T["go"], "Weight": 0,
                       "StyleSheet": "font-weight: bold; padding: 8px;"}),

            ui.VGap(8),
            ui.Label({"ID": "Bar", "Text": "", "Weight": 0,
                      "StyleSheet": "font-family: Consolas, monospace; color: #6c5ce7;"}),
            ui.Label({"ID": "Status", "Text": T["checking"], "Weight": 0,
                      "StyleSheet": "color: #8b95a8; font-size: 11px;"}),
            ui.Label({"ID": "Detail", "Text": "", "Weight": 1, "WordWrap": True,
                      "StyleSheet": "color: #8b95a8; font-size: 10px;"}),
        ]),
    ])

    itm = win.GetItems()

    for label in T["presets"]:
        itm["Preset"].AddItem(label)
    for name, _ in clips:
        itm["Clip"].AddItem(name)
    if not clips:
        itm["Clip"].AddItem(T["no_clips"])

    state = {"running": False}

    def set_status(text, detail=""):
        itm["Status"].Text = text
        itm["Detail"].Text = detail

    if engine_get("/health") is None:
        set_status(T["engine_off"], T["engine_off_help"])
    else:
        set_status(T["engine_ok"])

    def on_close(ev):
        disp.ExitLoop()

    def on_reload(ev):
        new_clips = list_project_clips(resolve)
        itm["Clip"].Clear()
        del clip_paths[:]
        for name, path in new_clips:
            itm["Clip"].AddItem(name)
            clip_paths.append(path)
        if not new_clips:
            itm["Clip"].AddItem(T["no_clips"])
        ok = engine_get("/health") is not None
        if ok:
            set_status(T["engine_ok_n"] % len(new_clips))
        else:
            set_status(T["engine_off"], T["engine_off_help"])

    def on_go(ev):
        if state["running"]:
            return
        idx = itm["Clip"].CurrentIndex
        if idx < 0 or idx >= len(clip_paths):
            set_status(T["pick_first"])
            return
        payload = {
            "video": clip_paths[idx],
            "preset": PRESET_IDS[itm["Preset"].CurrentIndex],
            "captions": itm["Caps"].Checked,
            "output": "resolve",
            "prompt": "",
        }
        answer = engine_post("/edit", payload)
        if answer.get("error"):
            set_status(T["error"], answer["error"])
            return
        state["running"] = True
        itm["Go"].Enabled = False
        set_status(T["working"])

    def on_tick(ev):
        if not state["running"]:
            return
        p = engine_get("/progress", timeout=2)
        if p is None:
            return
        itm["Bar"].Text = bar(p.get("percent", 0))
        if p.get("error"):
            state["running"] = False
            itm["Go"].Enabled = True
            set_status(T["error"], p["error"])
        elif p.get("percent", 0) >= 100 and p.get("result"):
            state["running"] = False
            itm["Go"].Enabled = True
            set_status(T["done"], p["result"])
        else:
            set_status(p.get("step", T["working"]), p.get("detail", ""))

    win.On.VidorqWin.Close = on_close
    win.On.Reload.Clicked = on_reload
    win.On.Go.Clicked = on_go

    timer = ui.Timer({"ID": "Tick", "Interval": POLL_MS})
    win.On.Tick.Timeout = on_tick
    timer.Start()

    on_reload(None)
    win.Show()
    disp.RunLoop()
    timer.Stop()
    win.Hide()
    print("[VidorqPanel] " + T["closed"])


main()
