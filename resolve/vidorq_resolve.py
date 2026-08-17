"""What the Vidorq menu entry actually does, loaded by the Vidorq.py stub.

One click has to be enough, so this brings up everything the user would
otherwise start by hand:

  1. the engine (127.0.0.1:9877), started hidden if it is not answering
  2. the Vidorq window, if a built app is installed
  3. the bridge (127.0.0.1:9876), which runs here inside Resolve and blocks,
     which is exactly right: it must stay alive for the whole session

Living in the install folder instead of Resolve's Scripts folder is the point.
The app updates this file; the menu entry never has to be touched again.
"""

import ctypes
import json
import locale
import os
import subprocess
import sys
import threading
import time
import urllib.request

ENGINE = "http://127.0.0.1:9877"
BRIDGE = "http://127.0.0.1:9876"
ENGINE_WAIT_S = 25

CONF = globals().get("VIDORQ_CONF", {})
HOME = CONF.get("home", "")
BRIDGE_SRC = CONF.get("bridge", "")

def spanish():
    """Spanish if the machine is Spanish. No setting to fiddle with.

    Windows answers this without locale.getdefaultlocale(), which is deprecated
    and prints a warning straight into Resolve's console.
    """
    if os.name == "nt":
        try:
            # Low 10 bits of the LCID are the primary language; 0x0A is Spanish.
            return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x0A
        except Exception:
            pass
    try:
        return (locale.getlocale()[0] or "").lower().startswith(("es", "spanish"))
    except Exception:
        return False


ES = spanish()

T = {
    "engine_up": ("Motor ya encendido.", "Engine already up."),
    "engine_start": ("Encendiendo el motor...", "Starting the engine..."),
    "engine_ok": ("Motor listo en %s" % ENGINE, "Engine ready at %s" % ENGINE),
    "engine_fail": ("El motor no arranca. Lanza engine\\start_engine.bat a mano y mira que dice.",
                    "The engine will not start. Run engine\\start_engine.bat by hand and read it."),
    "engine_missing": ("No encuentro el lanzador del motor: %s", "Cannot find the engine launcher: %s"),
    "app_open": ("Abriendo la ventana de Vidorq...", "Opening the Vidorq window..."),
    "app_none": ("Sin app instalada, usa la ventana de desarrollo.",
                 "No installed app, use the dev window."),
    "bridge_up": ("El puente ya estaba en marcha, lo reemplazo.",
                  "The bridge was already running, replacing it."),
    "bridge_start": ("Arrancando el puente dentro de Resolve...",
                     "Starting the bridge inside Resolve..."),
    "bridge_missing": ("No encuentro el puente: %s", "Cannot find the bridge: %s"),
    "not_in_resolve": ("Esto no se esta ejecutando dentro de Resolve, no arranco el puente.",
                       "This is not running inside Resolve, so the bridge stays off."),
    "ready": ("Todo listo. Deja Resolve abierto y edita desde la ventana de Vidorq.",
              "All set. Leave Resolve open and edit from the Vidorq window."),
    "box_title": ("Vidorq listo", "Vidorq is ready"),
}


LOG = os.path.join(os.environ.get("APPDATA", ""), "Vidorq", "ultimo_arranque.log")
_lines = []

try:
    # One run, one log. Reading it should never mean guessing which click it was.
    with open(LOG, "w", encoding="utf-8") as _f:
        _f.write("")
except Exception:
    pass


def say(key, *args):
    text = T[key][0] if ES else T[key][1]
    line = "[Vidorq] " + (text % args if args else text)
    print(line)
    _lines.append(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def notify(title, body):
    """Say something the user can actually see.

    A click that starts things silently reads as a click that did nothing, and
    Resolve's console is behind F6 where nobody looks. UIManager is out of reach
    on the Free edition, so this uses the plain Windows box, on its own thread so
    it never holds up the bridge behind it.
    """
    if os.name != "nt":
        return

    def show():
        try:
            # 0x40 information icon, 0x10000 bring to front
            ctypes.windll.user32.MessageBoxW(0, body, title, 0x40 | 0x10000)
        except Exception:
            pass

    threading.Thread(target=show, daemon=True).start()


def alive(url, timeout=1.5):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def spawn_hidden(*argv):
    """Launch and forget, with no console window.

    A visible console here is how people end up with a pile of dead windows they
    did not ask for, so the engine runs out of sight and reports through the app.
    DETACHED_PROCESS on its own: pairing it with CREATE_NO_WINDOW is an invalid
    combination on Windows and the launch simply fails.
    """
    flags = 0
    if os.name == "nt":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(list(argv), cwd=os.path.dirname(argv[0]),
                     creationflags=flags, close_fds=True)


# --------------------------------------------------------------------------- #
# 1. Engine
# --------------------------------------------------------------------------- #
if alive(ENGINE + "/health"):
    say("engine_up")
else:
    # pythonw, not the .bat: a GUI-subsystem interpreter cannot flash a console,
    # and the launcher is only a convenience wrapper around this same call.
    python = CONF.get("python", "")
    server = os.path.join(HOME, "engine", "server.py")
    if not (os.path.isfile(python) and os.path.isfile(server)):
        say("engine_missing", python or server)
    else:
        say("engine_start")
        try:
            spawn_hidden(python, server)
        except Exception as e:
            print("[Vidorq] %s" % e)
        deadline = time.time() + ENGINE_WAIT_S
        while time.time() < deadline and not alive(ENGINE + "/health"):
            time.sleep(1)
    say("engine_ok") if alive(ENGINE + "/health") else say("engine_fail")

# --------------------------------------------------------------------------- #
# 2. Window
# --------------------------------------------------------------------------- #
def find_app():
    """Where a built Vidorq window might be, best first.

    Searched at click time and not written down at install time, because the app
    usually gets built after the extension is already in the menu.
    """
    seen = [CONF.get("app", "")]
    target = os.environ.get("CARGO_TARGET_DIR", "")
    if target:
        seen.append(os.path.join(target, "release", "Vidorq.exe"))
    seen.append(os.path.join(HOME, "app", "src-tauri", "target", "release", "Vidorq.exe"))
    for base in (os.environ.get("LOCALAPPDATA", ""), os.environ.get("PROGRAMFILES", "")):
        if base:
            seen.append(os.path.join(base, "Vidorq", "Vidorq.exe"))
    for path in seen:
        if path and os.path.isfile(path):
            return path
    return ""


app_exe = find_app()
window_opened = False
if app_exe:
    say("app_open")
    try:
        spawn_hidden(app_exe)
        window_opened = True
    except Exception as e:
        print("[Vidorq] %s" % e)
else:
    say("app_none")

# --------------------------------------------------------------------------- #
# 3. Bridge, last because it blocks for the rest of the session
# --------------------------------------------------------------------------- #
if "bmd" not in globals():
    # Outside Resolve the bridge is useless, and worse: it would take port 9876
    # from the real one running inside Resolve and shut it down on the way in.
    say("not_in_resolve")
elif not os.path.isfile(BRIDGE_SRC):
    say("bridge_missing", BRIDGE_SRC)
else:
    if alive(BRIDGE + "/status"):
        say("bridge_up")
    say("bridge_start")
    say("ready")
    # The window appearing is feedback enough. Without one, a click that does
    # everything invisibly is indistinguishable from a click that failed.
    if not window_opened:
        notify(T["box_title"][0] if ES else T["box_title"][1], "\n".join(_lines))
    with open(BRIDGE_SRC, "r", encoding="utf-8") as f:
        src = f.read()
    # The bridge needs the objects Resolve injected into the stub, and it ends in
    # serve_forever(), so this call does not return until Resolve closes.
    exec(compile(src, BRIDGE_SRC, "exec"), globals())
