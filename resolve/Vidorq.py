"""Vidorq, the single entry in DaVinci Resolve's Scripts menu.

This file is deliberately tiny and almost never changes. It holds no logic: it
finds the Vidorq install folder and hands over to the code that lives there.
Whatever updates the app also updates the behaviour of this menu entry, so
nobody has to reinstall a script into Resolve for a new feature. The only thing
that can force a reinstall is a fix to this file itself, so it stays as close to
nothing as it can while still being able to say when it failed.

Everything real happens in the backend: the engine on 127.0.0.1:9877 and the
bridge this loader starts inside Resolve.
"""

import json
import os

CONF = os.path.join(os.environ.get("APPDATA", ""), "Vidorq", "resolve.json")


def fail(*lines):
    """Say it where the person who clicked will see it.

    The three ways this loader can fail - no config, broken config, folder moved
    - all used to end in print(), which in Resolve goes to the console behind F6.
    Nobody opens that, so clicking the menu entry looked exactly like clicking a
    menu entry that does nothing. Checked outside Resolve on all three paths: the
    lines came out, the exit code was 0, and there was nothing on screen.

    The box is the same plain Windows one that vidorq_resolve.py already uses,
    because Fusion's UIManager is not available on the Free edition. Here it runs
    on this thread on purpose, unlike there: after a failure this script is over,
    so there is nothing left behind for it to hold up, and a dialog nobody has to
    dismiss is a dialog that can disappear before it is read.
    """
    for line in lines:
        print("[Vidorq] " + line)
    if os.name != "nt":
        return
    try:
        import ctypes
        # 0x10 error icon, 0x10000 bring to front
        ctypes.windll.user32.MessageBoxW(0, "\n\n".join(lines), "Vidorq",
                                         0x10 | 0x10000)
    except Exception:
        pass    # sin caja, pero el mensaje ya esta impreso


if not os.path.isfile(CONF):
    fail("No encuentro la configuracion: %s" % CONF,
         "Abre Vidorq y vuelve a instalar la extension de Resolve.")
else:
    try:
        # utf-8-sig: PowerShell writes a BOM by default and json.load rejects it.
        with open(CONF, "r", encoding="utf-8-sig") as f:
            conf = json.load(f)
    except Exception as e:
        conf = None
        fail("La configuracion esta corrupta (%s): %s" % (e, CONF))

    if conf:
        payload = os.path.join(conf.get("home", ""), "resolve", "vidorq_resolve.py")
        if not os.path.isfile(payload):
            fail("No encuentro el codigo de Vidorq en: %s" % payload,
                 "La carpeta de instalacion ha cambiado de sitio o se ha borrado.")
        else:
            with open(payload, "r", encoding="utf-8") as f:
                code = f.read()
            # globals() carries the objects Resolve injects (bmd, fusion, resolve)
            # into the loaded code, which needs them to talk to the application.
            g = globals()
            g["VIDORQ_CONF"] = conf
            exec(compile(code, payload, "exec"), g)
