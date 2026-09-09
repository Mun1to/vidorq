"""Que pixeles son el objeto EN UN fotograma. El de al lado no le importa.

Va aparte de `mascara.py` a proposito: seguir un objeto por el video es un
problema que no cambia, y proponer que pixeles son suyos es un problema donde
sale un modelo mejor cada seis meses. Separados, cambiar de modelo es cambiar de
funcion, y no se toca nada de lo que ya funciona.

## Los dos escalones, y por que hay dos

**El de hoy, sin descargar nada** (`recorte`): GrabCut, que ya viene en OpenCV.
Se le da la caja de donde esta el objeto y separa figura de fondo mirando el
color. Con una persona hablando a camara sobre un fondo distinto va bien; con un
fondo del mismo color que la ropa, no. Es de 2004 y se nota, pero **funciona hoy,
en esta maquina, sin instalar ni descargar nada**, y eso vale mas que un plan.

**Lo que NO da, y esta medido**: velocidad. El 2026-09-09, sobre metraje real a
640x400, GrabCut tardo **5,3 segundos por fotograma** preguntando en todos, y
**1,2 preguntando 1 de cada 3**. A ese paso, un minuto de video son 36 minutos de
espera. O sea que sirve para ver que el seguimiento funciona y para una prueba
corta, y **no sirve para exportar**. Lo que abre esa puerta es el modelo de
abajo, que decide un fotograma en milisegundos en vez de en segundos; no es un
lujo, es la diferencia entre una funcion usable y una demo.

**El de verdad, y ya esta puesto** (`red`): **U-2-Net, licencia Apache 2.0**,
4,36 MB, en `skill/models/u2netp.onnx` con su licencia al lado. Mismo trato que
`faces.py` con YuNet: un fichero pequeño que viaja con el repo, corre en la CPU
con el `onnxruntime` que el motor ya lleva, y sigue funcionando con la red
desenchufada.

**La diferencia entre los dos, medida el 2026-09-09 y no estimada:**

    escena con respuesta conocida     GrabCut  IoU 0.881    U-2-Net  IoU 0.989
    metraje real, temblor             GrabCut  0.03604      U-2-Net  0.01754
    segundos por fotograma a 640x360  GrabCut  5.3          U-2-Net  0.43

Doce veces mas rapido y con la mitad de temblor. En minutos de espera: un minuto
de video pasaba de 36 minutos a 6 con el mismo mando de saltear puesto. Eso es lo
que convierte esto de demo en funcion.

**Lo que NO se puede usar, y esta comprobado**: `RobustVideoMatting` es GPL-3.0 y
`YOLO-seg` de Ultralytics es AGPL-3.0. Los dos son mejores que GrabCut y los dos
obligarian a abrir el producto de pago entero (regla AG). No se cuelan "de
momento": una vez dentro, sacarlos cuesta mas que no haberlos metido.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

try:
    import cv2
except Exception:                                     # pragma: no cover
    cv2 = None

# Donde se dejaria el modelo, con la misma forma que `faces.MODEL`. Que no este
# no es un error: es el escalon de hoy.
MODELO = Path(__file__).resolve().parent.parent / "models" / "u2netp.onnx"

# Iteraciones de GrabCut. Cuatro es donde deja de mejorar a ojo y sigue tardando
# poco; con ocho el borde de una persona no cambia y tarda el doble.
VUELTAS = 4

_sesion = None


def hay_red():
    """True si el modelo bueno esta instalado en esta maquina."""
    return MODELO.exists()


def motor():
    """Cual de los dos escalones va a trabajar. Para poder DECIRLO en pantalla.

    Una mascara regular con GrabCut y una buena con la red no se distinguen por
    el resultado hasta que ya la has exportado, asi que el usuario tiene derecho
    a saber cual le ha tocado antes de esperar cinco minutos.
    """
    if cv2 is None:
        return "ninguno"
    return "red" if hay_red() else "recorte"


def _caja_por_defecto(alto, ancho):
    """Donde suele estar el sujeto cuando nadie ha dicho donde esta.

    El centro y algo mas de la mitad del cuadro. No es adivinar: en un video de
    hablar a camara, que es el caso de la casa, el sujeto esta ahi. Si esta en
    otro sitio, se pasa la caja a mano y esto no se usa.
    """
    mx, my = int(ancho * 0.15), int(alto * 0.08)
    return (mx, my, ancho - 2 * mx, alto - 2 * my)


def recorte(cuadro, caja=None):
    """GrabCut: separa figura de fondo por color, partiendo de una caja.

    Devuelve flotantes de 0 a 1 como el resto de segmentadores, aunque GrabCut
    conteste en cuatro categorias: los "seguro dentro" y "probable dentro" valen
    1, y los otros 0. Se normaliza AQUI para que quien lo llame no tenga que
    saber que por dentro esto no es una red.
    """
    h, w = cuadro.shape[:2]
    caja = caja or _caja_por_defecto(h, w)
    m = np.zeros((h, w), np.uint8)
    fondo, figura = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(cuadro, m, tuple(int(v) for v in caja), fondo, figura,
                    VUELTAS, cv2.GC_INIT_WITH_RECT)
    except Exception:
        # Una caja degenerada (ancho o alto cero) tumba grabCut. Mejor una
        # mascara vacia que una exportacion perdida a la mitad.
        return np.zeros((h, w), np.float32)
    dentro = (m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD)
    return dentro.astype(np.float32)


def red(cuadro, caja=None):
    """El modelo ONNX. Misma firma que `recorte`, para que sean intercambiables.

    U-2-Net contesta un mapa de "cuanto destaca" por pixel, ya entre 0 y 1, que
    es justo lo que `mascara.seguir` espera: no se binariza aqui, porque la
    memoria entre fotogramas trabaja mejor con medias tintas en el borde.
    """
    global _sesion
    import onnxruntime as ort
    if _sesion is None:
        _sesion = ort.InferenceSession(str(MODELO),
                                       providers=["CPUExecutionProvider"])
    ent = _sesion.get_inputs()[0]
    lado = ent.shape[2] if isinstance(ent.shape[2], int) else 320
    h, w = cuadro.shape[:2]
    x = cv2.resize(cuadro, (lado, lado), interpolation=cv2.INTER_AREA)
    x = cv2.cvtColor(x, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    # La normalizacion de ImageNet, que es con la que se entreno. Saltarsela no
    # da error: da una mascara peor, que es la clase de fallo que no se ve.
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / \
        np.array([0.229, 0.224, 0.225], np.float32)
    x = np.transpose(x, (2, 0, 1))[None]
    salida = _sesion.run(None, {ent.name: x})[0]
    m = np.squeeze(salida)
    # U-2-Net saca varias salidas a distinta profundidad; la primera es la buena.
    if m.ndim == 3:
        m = m[0]
    lo, hi = float(m.min()), float(m.max())
    if hi > lo:
        m = (m - lo) / (hi - lo)
    return cv2.resize(m.astype(np.float32), (w, h), interpolation=cv2.INTER_LINEAR)


def elegir():
    """La funcion de segmentar que toca en esta maquina, sin preguntar nada.

    Que el que llama no tenga que saber cual hay es el motivo entero de que este
    archivo exista: `mascara.seguir(fotogramas, segmentador.elegir())` funciona
    igual con red o sin ella, y solo cambia lo buena que sale la mascara.
    """
    return red if hay_red() else recorte
