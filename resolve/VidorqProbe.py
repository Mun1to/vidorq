"""Probe: how far can a script get inside DaVinci Resolve Free before it is stopped?

The panel dies somewhere between "there is a fusion object" and "a window is on
screen", and the Studio upsell dialog does not say where. This walks the same path
one call at a time and writes each result to a file the moment it happens, so the
last line of the log is the exact call that hit the wall.

Run it from Workspace > Scripts > VidorqProbe. It draws a tiny window and nothing
else; close it or let it be.
"""

import os
import sys
import traceback

LOG = os.path.join(os.environ.get("TEMP", "."), "vidorq_probe.log")


def w(line):
    """Write and flush now: if the next call freezes, this line still survives."""
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")
        f.flush()
    print("[VidorqProbe] " + line)


def step(name, fn):
    w("--> " + name)
    try:
        value = fn()
    except Exception:
        w("    FALLO: " + traceback.format_exc().strip().replace("\n", " | "))
        return None
    w("    OK: " + repr(value)[:300])
    return value


with open(LOG, "w", encoding="utf-8") as f:
    f.write("")

w("Python %s" % sys.version.split()[0])
w("Ejecutable: %s" % sys.executable)

g = globals()
w("Globales inyectados por Resolve: " + ", ".join(
    n for n in ("bmd", "fusion", "fu", "resolve", "app", "davinci") if n in g))

resolve_obj = step("bmd.scriptapp('Resolve')", lambda: bmd.scriptapp("Resolve"))  # noqa: F821
if resolve_obj:
    step("resolve.GetProductName()", resolve_obj.GetProductName)
    step("resolve.GetVersionString()", resolve_obj.GetVersionString)
    step("resolve.GetProjectManager()", resolve_obj.GetProjectManager)

fu_obj = step("objeto fusion", lambda: fusion)  # noqa: F821
ui = step("fusion.UIManager", lambda: fusion.UIManager)  # noqa: F821
disp = step("bmd.UIDispatcher(ui)", lambda: bmd.UIDispatcher(ui))  # noqa: F821

if ui and disp:
    win = step("disp.AddWindow(...)", lambda: disp.AddWindow(
        {"ID": "VidorqProbe", "WindowTitle": "Vidorq probe", "Geometry": [200, 200, 320, 120]},
        [ui.VGroup([ui.Label({"Text": "Si ves esto, UIManager funciona."})])],
    ))
    if win:
        # Without this the X button does nothing and RunLoop never returns.
        def close(ev):
            disp.ExitLoop()

        win.On.VidorqProbe.Close = close
        step("win.Show()", win.Show)
        step("disp.RunLoop()", disp.RunLoop)
        step("win.Hide()", win.Hide)

w("FIN. Log en: " + LOG)
