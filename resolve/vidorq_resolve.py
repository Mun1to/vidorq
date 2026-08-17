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

import json
import locale
import os
import subprocess
import sys
import time
import urllib.request

ENGINE = "http://127.0.0.1:9877"
BRIDGE = "http://127.0.0.1:9876"
ENGINE_WAIT_S = 25

CONF = globals().get("VIDORQ_CONF", {})
HOME = CONF.get("home", "")
BRIDGE_SRC = CONF.get("bridge", "")

ES = (locale.getdefaultlocale()[0] or "").lower().startswith("es")

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
}


def say(key, *args):
    text = T[key][0] if ES else T[key][1]
    print("[Vidorq] " + (text % args if args else text))


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
app_exe = CONF.get("app", "")
if app_exe and os.path.isfile(app_exe):
    say("app_open")
    try:
        spawn_hidden(app_exe)
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
    with open(BRIDGE_SRC, "r", encoding="utf-8") as f:
        src = f.read()
    # The bridge needs the objects Resolve injected into the stub, and it ends in
    # serve_forever(), so this call does not return until Resolve closes.
    exec(compile(src, BRIDGE_SRC, "exec"), globals())
