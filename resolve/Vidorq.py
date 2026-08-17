"""Vidorq, the single entry in DaVinci Resolve's Scripts menu.

This file is deliberately tiny and is meant to NEVER change again. It holds no
logic: it finds the Vidorq install folder and hands over to the code that lives
there. Whatever updates the app also updates the behaviour of this menu entry,
so nobody has to reinstall a script into Resolve twice.

Everything real happens in the backend: the engine on 127.0.0.1:9877 and the
bridge this loader starts inside Resolve.
"""

import json
import os

CONF = os.path.join(os.environ.get("APPDATA", ""), "Vidorq", "resolve.json")


def fail(*lines):
    for line in lines:
        print("[Vidorq] " + line)


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
