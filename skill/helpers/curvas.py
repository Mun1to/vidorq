"""Curvas de movimiento: lo que separa una animacion de calidad de una robotica.

## El problema que arregla, medido el 2026-09-21

Las entradas de los subtitulos se escribian como tramos `\\t(inicio, fin, valor)`
sin curva, y en el formato de subtitulos eso es VELOCIDAD CONSTANTE. Medido
contando pixeles del texto fotograma a fotograma, a 60 fps, sobre el camino real
del MP4 (libass):

    pop     tamaño  0.62 0.72 0.83 0.93 1.03 1.03 1.00
            vel.    +0.10 +0.11 +0.10 +0.10 +0.00 -0.03   <- ritmo fijo, frenazo seco
    bounce  tamaño  0.35 0.59 0.85 1.11 1.06 0.95 0.96
            vel.    +0.24 +0.26 +0.26 -0.06 -0.10 +0.00   <- de +0.26 a -0.06 de golpe

Eso es exactamente lo que se ve como "animacion barata": crece a velocidad fija y
se para de golpe en cada punto. Un movimiento de verdad (una mano, un objeto que
cae, la interfaz de un movil) arranca rapido y FRENA poco a poco.

## Que hay aqui

Funciones puras de `t` en [0, 1] a progreso. El progreso puede pasar de 1 en las
que rebotan (atras, elastica, muelle): eso ES el rebote, no un error.

Las formulas no se inventan. Las de facilidad son las de Robert Penner, que es de
donde salen las de CSS, After Effects y practicamente cualquier libreria de
animacion; el muelle es la solucion exacta del oscilador amortiguado, la misma
que usan SwiftUI y Framer Motion. Usar las de siempre tiene una ventaja que no es
de gusto: el ojo del espectador ya esta hecho a ellas, porque las ve todo el dia
en su movil.

## Por que se MUESTREA en vez de pasarle la curva al renderizador

libass solo sabe una curva, una potencia (`\\t(t1,t2,accel,...)`), y con una
potencia no se puede hacer un rebote: sube y baja, y una potencia solo sube. Asi
que la curva se evalua en Python, fotograma a fotograma, y se escribe como tramos
cortos. Con un tramo por fotograma a 60, cada fotograma que se ve tiene el valor
EXACTO de la curva; entre tramo y tramo no hay nada que ver. Es el mismo truco que
ya hacia el zoom del camino de Resolve con siete claves.
"""
from __future__ import annotations

import math


def lineal(t):
    """La de antes: velocidad constante. Solo para comparar y para `none`."""
    return t


def suave(t):
    """Ease-out cubico. Arranca rapido y frena suave. La que vale para todo.

    `1 - (1 - t)^3`, la misma curva que ya usaba el zoom de Resolve.
    """
    return 1.0 - (1.0 - t) ** 3


def rapida(t):
    """Ease-out quintico. Llega casi entera en el primer tercio y remata despacio.

    Es el "snap" de los shorts: la palabra ya esta ahi antes de que la mires.
    """
    return 1.0 - (1.0 - t) ** 5


def exponencial(t):
    """Ease-out exponencial. Aun mas seca que la rapida al principio."""
    return 1.0 if t >= 1.0 else 1.0 - 2.0 ** (-10.0 * t)


def atras(t, fuerza=1.70158):
    """Ease-out back: se pasa del final y vuelve. Un solo rebote, limpio.

    `fuerza` 1.70158 es la constante de Penner, que da un 10% de pasada. Mas
    alta, mas se pasa. Es la curva de un boton que "salta" al aparecer.
    """
    c3 = fuerza + 1.0
    u = t - 1.0
    return 1.0 + c3 * u ** 3 + fuerza * u ** 2


def elastica(t):
    """Ease-out elastic: varios rebotes que se apagan, como una goma.

    Es la mas llamativa, y por eso la que menos se debe usar: en un subtitulo
    que dura un segundo, tres rebotes se comen la mitad de lo que dura.
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    c4 = (2.0 * math.pi) / 3.0
    return 2.0 ** (-10.0 * t) * math.sin((t * 10.0 - 0.75) * c4) + 1.0


def rebote(t):
    """Ease-out bounce: cae y rebota contra el suelo, como una pelota.

    Distinta de la elastica: aqui el valor NUNCA pasa de 1, rebota hacia atras
    desde el final. Es la de una cosa que cae y toca fondo.
    """
    n1, d1 = 7.5625, 2.75
    if t < 1.0 / d1:
        return n1 * t * t
    if t < 2.0 / d1:
        t -= 1.5 / d1
        return n1 * t * t + 0.75
    if t < 2.5 / d1:
        t -= 2.25 / d1
        return n1 * t * t + 0.9375
    t -= 2.625 / d1
    return n1 * t * t + 0.984375


def muelle(t, rebote_=0.3):
    """Un muelle fisico amortiguado. La curva de mas calidad para un "pop".

    Es la solucion exacta del oscilador armonico amortiguado, parametrizada como
    la de SwiftUI y Framer Motion: `rebote_` de 0 (llega sin pasarse, amortiguado
    critico) a casi 1 (rebota mucho). Se nota distinta de `atras` porque el
    rebote sale de la FISICA y no de una formula de forma: la pasada y la vuelta
    tienen la proporcion que tiene un objeto de verdad, y por eso se lee natural.

    El tiempo se reescala para que en t=1 el muelle este practicamente quieto
    (menos del 0,5% de error), que es lo que hace que una duracion elegida
    signifique "cuanto tarda en asentarse" y no "cuanto dura la formula".
    """
    if t <= 0.0:
        return 0.0
    if t >= 1.0:
        return 1.0
    rebote_ = max(0.0, min(0.95, rebote_))
    zeta = 1.0 - rebote_                    # amortiguacion: 1 = critico, sin pasarse
    w0 = _rigidez(zeta)
    if zeta >= 0.999:
        # Critico: sube sin pasarse. e^(-w t) (1 + w t)
        return 1.0 - math.exp(-w0 * t) * (1.0 + w0 * t)
    wd = w0 * math.sqrt(1.0 - zeta * zeta)
    env = math.exp(-zeta * w0 * t)
    return 1.0 - env * (math.cos(wd * t) + (zeta * w0 / wd) * math.sin(wd * t))


# Error maximo que se tolera en el ultimo 10% del tiempo. Por encima, al acabar la
# entrada el texto da un salto hasta su tamaño final, porque el ultimo punto se
# fija exacto y el anterior no lo estaba. 0,4% de 1080 son cuatro pixeles, que es
# lo que ya no se ve.
ASENTADO = 0.004


def _rigidez(zeta):
    """La frecuencia natural para que el muelle YA este quieto al acabar.

    La primera version la calculaba con una formula cerrada (`5.3 / zeta`) y se
    MIDIO que no bastaba: sin rebote, en el 95% del tiempo aun le faltaba un 4%,
    asi que al final daba un salto visible, justo en la curva que iba por
    defecto. La formula ignora que la amortiguacion critica tiene otra forma, y
    que la envolvente no es todo el error.

    Asi que se busca: la rigidez mas baja con la que el ultimo 10% ya no se
    aparta mas de `ASENTADO`. La mas baja, porque mas rigido tambien es mas
    brusco: se quiere que use toda la duracion, no que llegue en la mitad y se
    quede quieto el resto.
    """
    clave = round(zeta, 3)
    if clave in _cache:
        return _cache[clave]
    w = 2.0
    while w < 80.0:
        if _error_final(zeta, w) < ASENTADO:
            break
        w *= 1.03
    _cache[clave] = w
    return w


def _error_final(zeta, w0):
    peor = 0.0
    for i in range(21):
        t = 0.9 + 0.1 * i / 20.0
        if zeta >= 0.999:
            x = 1.0 - math.exp(-w0 * t) * (1.0 + w0 * t)
        else:
            wd = w0 * math.sqrt(1.0 - zeta * zeta)
            x = 1.0 - math.exp(-zeta * w0 * t) * (
                math.cos(wd * t) + (zeta * w0 / wd) * math.sin(wd * t))
        peor = max(peor, abs(x - 1.0))
    return peor


_cache = {}


# Los presets de curva con nombre, que es lo que ve el usuario. El orden importa:
# es el del selector, y la primera es la de por defecto.
CURVAS = {
    "suave": {
        "f": suave,
        "es": ("Suave", "Arranca rápido y frena despacio. Vale para todo."),
        "en": ("Smooth", "Starts fast and eases in. Works for anything."),
    },
    "rapida": {
        "f": rapida,
        "es": ("Rápida", "La palabra ya está ahí antes de que la mires. Para shorts."),
        "en": ("Snappy", "The word is there before you look. For shorts."),
    },
    "muelle": {
        "f": lambda t: muelle(t, 0.35),
        "es": ("Muelle", "Se pasa un poco y vuelve, como algo de verdad. La de más calidad."),
        "en": ("Spring", "Overshoots a little and settles, like a real object. The finest."),
    },
    "atras": {
        "f": atras,
        "es": ("Salto", "Un solo rebote limpio al llegar, como un botón que salta."),
        "en": ("Back", "One clean overshoot on arrival, like a button that pops."),
    },
    "elastica": {
        "f": elastica,
        "es": ("Elástica", "Varios rebotes que se apagan. Muy llamativa, úsala poco."),
        "en": ("Elastic", "Several bounces that die out. Loud, use it sparingly."),
    },
    "rebote": {
        "f": rebote,
        "es": ("Rebote", "Cae y rebota contra el suelo, como una pelota."),
        "en": ("Bounce", "Drops and bounces off the floor, like a ball."),
    },
    "lineal": {
        "f": lineal,
        "es": ("Lineal", "Velocidad constante. La de antes; solo si la buscas a propósito."),
        "en": ("Linear", "Constant speed. The old one; only if you want it on purpose."),
    },
}

POR_DEFECTO = "muelle"


def conocida(nombre):
    """True si esa curva existe. Lo que viene de fuera se comprueba."""
    return isinstance(nombre, str) and nombre in CURVAS


def curva(nombre, rebote_=None):
    """La funcion de una curva, o la de por defecto si el nombre no vale.

    `rebote_` solo cuenta para el muelle, y es lo que deja que una animacion
    concreta pida mas o menos pasada que la del catalogo sin inventar otra curva:
    "rebote" quiere un muelle de tres tiempos y "pop" uno que apenas se pase, y
    los dos son el mismo muelle con distinta amortiguacion.
    """
    nombre = nombre if conocida(nombre) else POR_DEFECTO
    if nombre == "muelle" and rebote_ is not None:
        return lambda t: muelle(t, rebote_)
    return CURVAS[nombre]["f"]


def claves(desde, hasta, nombre, dur, pasos, rebote_=None):
    """La curva como lista de claves `(momento, valor)`, con momento en [0, dur].

    Es la forma que ya entendian los dos caminos de salida, asi que ni el MP4 ni
    Fusion tienen que saber que detras hay una curva: reciben claves como antes,
    solo que ahora muchas y bien puestas en vez de tres a ojo. `pasos` decide
    cuantas: el MP4 quiere una por fotograma, Fusion unas pocas porque cada una
    es un punto de su spline y con demasiadas se vuelve inmanejable a mano.

    La primera clave es `desde` y la ultima `hasta`, EXACTAS: la animacion acaba
    siempre donde tiene que acabar aunque la curva se pase por el camino.
    """
    f = curva(nombre, rebote_)
    pasos = max(2, int(pasos))
    out = []
    for i in range(pasos + 1):
        t = i / float(pasos)
        out.append((dur * t, desde + (hasta - desde) * f(t)))
    out[0] = (0.0, desde)
    out[-1] = (float(dur), hasta)
    return out


def catalogo(lang="es"):
    """La lista para el selector, con la misma forma que el resto de catalogos."""
    lang = lang if lang in ("es", "en") else "es"
    return [{"id": cid, "label": c[lang][0], "note": c[lang][1]}
            for cid, c in CURVAS.items()]


# Un paso por fotograma a 60, que es el fotograma mas corto que va a ver nadie.
# A 30 fps cada fotograma cae entre dos pasos, y como son tramos rectos de 17 ms
# el error en ese punto es invisible (se midio: menos de un pixel de tamaño).
PASO_MS = 1000.0 / 60.0


def muestras(nombre, dur_ms, desde, hasta):
    """La curva evaluada a lo largo de la entrada: [(ms, valor), ...].

    `desde` y `hasta` son los valores de la propiedad (un tamaño, una opacidad).
    El primer punto es `desde` en 0 ms y el ultimo `hasta` en `dur_ms`, EXACTOS,
    para que la animacion acabe siempre donde tiene que acabar aunque la curva
    se pase por el camino.
    """
    f = curva(nombre)
    n = max(2, int(math.ceil(dur_ms / PASO_MS)))
    out = []
    for i in range(n + 1):
        t = i / float(n)
        v = desde + (hasta - desde) * f(t)
        out.append((dur_ms * t, v))
    out[0] = (0.0, desde)
    out[-1] = (float(dur_ms), hasta)
    return out
