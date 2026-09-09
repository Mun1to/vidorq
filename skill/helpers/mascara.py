"""Seguir una mascara por el video: lo que Blackmagic cobra 295 dolares por dar.

**Magic Mask es de Studio.** Comprobado el 2026-09-09: la version Free de Resolve
no lo trae, y enmascarar a mano es el camino que deja Blackmagic. O sea que esto
no es "una funcion mas": es de las pocas cosas por las que alguien paga Studio, y
Vidorq puede darla dentro de la version gratis. Eso lo convierte en la pieza mas
valiosa del producto despues del timeline nativo.

## Como esta partido, y por que asi

Segmentar y SEGUIR son dos problemas distintos, y confundirlos es el error que
hace que una mascara parpadee:

- **Segmentar** contesta "que pixeles son el objeto EN ESTE fotograma". Lo hace un
  modelo, y es intercambiable: `segmentador.py` decide cual hay.
- **Seguir** contesta "el objeto de este fotograma es el mismo de antes, y se ha
  movido asi". Eso lo hace ESTE modulo, y es lo que no se puede comprar hecho.

Segmentar cada fotograma por su cuenta y llamarlo tracking da una mascara que
tiembla: cada fotograma decide solo, y el borde salta uno o dos pixeles cada vez.
Sobre un plano de 10 segundos son 300 decisiones independientes y se ve como
ruido en el contorno. Aqui la mascara del fotograma anterior se ARRASTRA con el
movimiento medido de la imagen (flujo optico) y se mezcla con la que propone el
modelo, asi que el contorno tiene memoria.

## La licencia decide el modelo, y esto ya descarto a uno

`RobustVideoMatting` es mejor que lo que hay aqui y viene con memoria temporal de
fabrica, pero es **GPL-3.0** (comprobado el 2026-09-09 en su LICENSE), y una
dependencia copyleft dentro de un producto que se va a cobrar obliga a abrir el
producto entero (regla AG). Descartado por lo mismo que Remotion y Piper.
**U-2-Net es Apache 2.0** y ese si vale. YOLO-seg de Ultralytics es AGPL: tampoco.

## Salida

Dos, y las dos del mismo sitio:

- **Un matte con canal alfa**, que es el camino que YA funciona en Resolve Free:
  `resolve_captions.place_overlays` lleva meses metiendo PNG con alfa en su propia
  pista. No hay que inventar nada.
- **El contorno como poligono**, para el dia que se pueda escribir un `Polygon`
  animado dentro de un `.comp` y la mascara entre editable a mano. Eso NO esta
  medido todavia: las 417 plantillas de fabrica de Blackmagic no traen ni un nodo
  `Polygon`, asi que la sintaxis hay que sacarsela a Fusion con Resolve abierto,
  como se hizo con `StyledTextCLS`. Hasta entonces el poligono se calcula y se
  guarda, que es gratis, pero quien lo pinta es el matte.
"""
from __future__ import annotations

import numpy as np

try:
    import cv2
except Exception:                                     # pragma: no cover
    cv2 = None


# Cuanto pesa la mascara arrastrada del fotograma anterior frente a la que propone
# el modelo ahora. 0 = cada fotograma decide solo, 1 = la primera mascara se
# arrastra para siempre y el objeto se le escapa.
#
# MEDIDO EL 2026-09-09 SOBRE DOS ESCENAS, y la leccion vale mas que el numero:
#
#   escena sintetica (sujeto liso, fondo suave, respuesta conocida)
#     sin memoria   temblor 0.01277   IoU 0.881
#     con memoria   temblor 0.01285   IoU 0.878      <- la memoria NO hace nada
#
#   metraje real (gameplay, camara moviendose, detalle en todo el cuadro)
#     sin memoria          temblor 0.03604
#     con memoria          temblor 0.02571           <- 28,7% menos
#     memoria + 1 de cada 3 temblor 0.01105          <- 69% menos, y 3,6x mas rapido
#
# Con la escena facil se habria escrito "la memoria es decoracion, quitala", y
# habria sido falso: en metraje de verdad es lo que sujeta el borde. Por eso el
# proyecto tiene escrito que esto se prueba con video real y no con fondos de
# colores. El sintetico sirve para medir el ACIERTO (ahi hay respuesta conocida);
# el real, para medir el TEMBLOR, que es lo unico que se ve al reproducir.
MEMORIA = 0.45

# Cada cuantos fotogramas se le pregunta al modelo. Los de en medio se rellenan
# arrastrando la mascara con el movimiento medido.
#
# 3 sale de la misma tabla: sobre metraje real baja el tiempo al 27% Y el temblor
# a un tercio. No es una concesion por ir rapido, sale MEJOR: entre dos
# fotogramas seguidos el objeto se mueve unos pocos pixeles, y el flujo optico lo
# sigue con mas continuidad de la que tiene el modelo volviendo a decidir de cero.
CADA = 3

# Por debajo de esto un pixel no es del objeto. La mascara del modelo llega como
# probabilidad de 0 a 1, y binarizar tarde (al final, no por fotograma) es lo que
# deja que la memoria trabaje con medias tintas en el borde.
CORTE = 0.5

# Lado al que se encoge la imagen para medir el movimiento. El flujo optico no
# necesita resolucion completa (el movimiento de un plano es de decenas de
# pixeles, no de decimas) y a 1920 tarda catorce veces mas para el mismo empujon.
LADO_FLUJO = 480


def disponible():
    """True si esta maquina puede seguir una mascara.

    Se pregunta antes de ofrecer el boton: una funcion que aparece y luego falla
    es peor que una que no aparece.
    """
    return cv2 is not None


def _encoger(img, lado=LADO_FLUJO):
    """La imagen reducida para medir movimiento, y por cuanto se redujo."""
    h, w = img.shape[:2]
    k = lado / float(max(w, h))
    if k >= 1.0:
        return img, 1.0
    return cv2.resize(img, (max(2, int(w * k)), max(2, int(h * k))),
                      interpolation=cv2.INTER_AREA), k


def flujo(gris_antes, gris_ahora):
    """Cuanto se ha movido cada pixel entre dos fotogramas.

    Farneback y no un metodo disperso: hace falta el movimiento de TODA la
    imagen para poder arrastrar una mascara entera, no el de un puñado de
    esquinas. Se mide en pequeño y se devuelve a tamaño completo, porque el
    campo de movimiento es suave y aguanta el reescalado sin perder nada util.
    """
    ch, k = _encoger(gris_ahora)
    ca, _ = _encoger(gris_antes)
    f = cv2.calcOpticalFlowFarneback(ca, ch, None,
                                     pyr_scale=0.5, levels=3, winsize=15,
                                     iterations=3, poly_n=5, poly_sigma=1.2,
                                     flags=0)
    if k < 1.0:
        h, w = gris_ahora.shape[:2]
        f = cv2.resize(f, (w, h), interpolation=cv2.INTER_LINEAR) / k
    return f


def arrastrar(mascara, f):
    """La mascara de antes, movida a donde el flujo dice que esta ahora.

    Se remuestrea la mascara con el campo de movimiento INVERTIDO: para saber que
    valor va en el pixel (x, y) de ahora, hay que mirar de donde VENIA, que es
    (x, y) menos su desplazamiento. Hacerlo al reves deja agujeros donde el
    objeto se separa del fondo, que es exactamente el borde que se quiere limpio.
    """
    h, w = mascara.shape[:2]
    xx, yy = np.meshgrid(np.arange(w, dtype=np.float32),
                         np.arange(h, dtype=np.float32))
    mapa_x = (xx - f[..., 0]).astype(np.float32)
    mapa_y = (yy - f[..., 1]).astype(np.float32)
    return cv2.remap(mascara, mapa_x, mapa_y, interpolation=cv2.INTER_LINEAR,
                     borderMode=cv2.BORDER_REPLICATE)


def pulir(m):
    """Quita las islas sueltas y tapa los agujeros de dentro.

    Un modelo de segmentacion deja motas: pixeles sueltos que pasan el corte
    lejos del objeto, y agujeros dentro de el. En una imagen fija no se ven; en
    movimiento aparecen y desaparecen, y eso SI se ve. Se limpia con una apertura
    (mata motas) seguida de un cierre (tapa agujeros), en ese orden: al reves, el
    cierre agranda las motas antes de que nadie las mate.
    """
    b = (m > CORTE).astype(np.uint8)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    b = cv2.morphologyEx(b, cv2.MORPH_OPEN, k)
    b = cv2.morphologyEx(b, cv2.MORPH_CLOSE, k)
    # El borde se devuelve suave, no binario: un contorno con escalones de un
    # pixel se ve como una sierra cuando el objeto se mueve despacio.
    return cv2.GaussianBlur(b.astype(np.float32), (0, 0), 1.2)


def seguir(fotogramas, segmenta, memoria=MEMORIA, cada=CADA, aviso=None):
    """La mascara de cada fotograma, con memoria del anterior.

    `fotogramas` es cualquier cosa que devuelva imagenes BGR una a una, para que
    un video de dos horas no tenga que caber en memoria. `segmenta` es la funcion
    que propone la mascara de UN fotograma y devuelve flotantes de 0 a 1: se pasa
    de fuera a proposito, para que cambiar de modelo no toque este archivo.

    `cada` deja preguntarle al modelo uno de cada N fotogramas y rellenar los de
    en medio arrastrando con el flujo. Con `cada=3` el trabajo del modelo baja a
    un tercio y la mascara sigue pegada al objeto, porque entre dos fotogramas
    seguidos casi nada se mueve mas que unos pixeles. Es el mando que convierte
    esto en algo usable sin GPU.
    """
    previa = None
    gris_previo = None
    for i, cuadro in enumerate(fotogramas):
        gris = cv2.cvtColor(cuadro, cv2.COLOR_BGR2GRAY)
        if previa is None:
            actual = segmenta(cuadro)
        else:
            movida = arrastrar(previa, flujo(gris_previo, gris))
            if i % max(1, cada) == 0:
                propuesta = segmenta(cuadro)
                # La mezcla es sobre la PROBABILIDAD, antes de binarizar. Mezclar
                # dos mascaras ya binarias solo puede dar 0, 0.5 o 1, y el 0.5 se
                # va a un lado u otro por un pixel de nada.
                actual = memoria * movida + (1.0 - memoria) * propuesta
            else:
                # Fotograma barato: nadie pregunta al modelo, se arrastra y ya.
                actual = movida
        previa = np.clip(actual, 0.0, 1.0)
        gris_previo = gris
        if aviso and i % 25 == 0:
            aviso(i)
        yield pulir(previa)


def contorno(m, suave=0.004):
    """El borde de la mascara como lista de puntos, en coordenadas de 0 a 1.

    Se guarda aunque hoy no lo pinte nadie, porque es lo que hara falta el dia
    que se pueda escribir un `Polygon` de Fusion: un poligono de treinta puntos
    es una mascara que se puede EDITAR a mano dentro de Resolve, y un matte de
    imagenes no.

    `suave` es la tolerancia de Douglas-Peucker en fraccion del perimetro. Sin
    simplificar, el contorno de una persona a 1080p trae unos 3000 puntos y eso
    no es editable por nadie; con 0.004 baja a unas decenas y el ojo no nota la
    diferencia.
    """
    b = (m > CORTE).astype(np.uint8)
    cs, _ = cv2.findContours(b, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cs:
        return []
    c = max(cs, key=cv2.contourArea)
    aprox = cv2.approxPolyDP(c, suave * cv2.arcLength(c, True), True)
    h, w = m.shape[:2]
    return [(float(p[0][0]) / w, float(p[0][1]) / h) for p in aprox]


def a_png_alfa(cuadro, m):
    """El fotograma con la mascara puesta como transparencia (BGRA).

    Este es el formato que Resolve Free ya sabe tragar: `place_overlays` lleva
    meses metiendo PNG con alfa en su propia pista, asi que la mascara llega al
    timeline por un camino que YA esta probado, sin depender de que algun dia se
    pueda escribir un `Polygon` animado.
    """
    alfa = np.clip(m * 255.0, 0, 255).astype(np.uint8)
    return np.dstack([cuadro, alfa])
