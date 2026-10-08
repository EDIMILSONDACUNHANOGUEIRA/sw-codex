"""Recorte do personagem (rembg / U²-Net) para o efeito "manchete atrás do personagem".

Opcional: se o rembg não estiver instalado, o post é renderizado sem o efeito de profundidade.
Repositório: https://github.com/danielgatis/rembg (MIT)
"""
from __future__ import annotations

import hashlib
from functools import lru_cache

import numpy as np
from PIL import Image, ImageFilter

from .config import CACHE_DIR

MODEL = "u2net_human_seg"


def available() -> bool:
    try:
        import rembg  # noqa: F401
        return True
    except Exception:
        return False


@lru_cache(maxsize=1)
def _session():
    from rembg import new_session
    return new_session(MODEL)


def subject_mask(im: Image.Image, work_px: int = 1280) -> Image.Image | None:
    """Máscara L (0-255) do personagem, no mesmo tamanho de `im`. None se indisponível/vazia."""
    if not available():
        return None
    key = hashlib.sha1(im.tobytes() + str(im.size).encode()).hexdigest()[:20]
    cache = CACHE_DIR / "masks" / f"{key}.png"
    if cache.exists():
        return Image.open(cache).convert("L")
    from rembg import remove
    small = im.copy()
    small.thumbnail((work_px, work_px), Image.LANCZOS)
    cut = remove(small, session=_session(), post_process_mask=True)
    mask = cut.split()[-1].resize(im.size, Image.LANCZOS)
    # suaviza a borda e remove ruído
    mask = mask.filter(ImageFilter.MedianFilter(5)).filter(ImageFilter.GaussianBlur(1.2))
    arr = np.asarray(mask)
    if (arr > 128).mean() < 0.01:
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    mask.save(cache)
    return mask


def mask_centroid(mask: Image.Image) -> tuple[float, float] | None:
    arr = np.asarray(mask, dtype=np.float32) / 255.0
    tot = arr.sum()
    if tot < 1:
        return None
    h, w = arr.shape
    ys, xs = np.mgrid[0:h, 0:w]
    return float((xs * arr).sum() / tot / w), float((ys * arr).sum() / tot / h)


def face_focus(im: Image.Image) -> tuple[float, float] | None:
    """Ponto de foco pelo maior rosto detectado (OpenCV Haar). Sem dependência pesada."""
    try:
        import cv2
    except Exception:
        return None
    if not hasattr(cv2, "CascadeClassifier"):   # OpenCV 5 removeu as cascatas Haar
        return None
    arr = np.asarray(im.convert("L"))
    scale = 900 / max(arr.shape)
    small = cv2.resize(arr, None, fx=scale, fy=scale) if scale < 1 else arr
    casc = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    faces = casc.detectMultiScale(small, scaleFactor=1.1, minNeighbors=6, minSize=(30, 30))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    H, W = small.shape
    return (x + w / 2) / W, (y + h / 2) / H
