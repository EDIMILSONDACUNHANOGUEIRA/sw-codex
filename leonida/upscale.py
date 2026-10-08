"""Qualidade de imagem: upscale de fotos pequenas e nitidez final.

Se o Real-ESRGAN estiver instalado (https://github.com/xinntao/Real-ESRGAN — baixe o
`realesrgan-ncnn-vulkan` dos Releases, funciona em placas NVIDIA/AMD/Intel no Windows), fotos abaixo da
resolução necessária são ampliadas com IA. Sem ele, usamos Lanczos + nitidez.

  - coloque o executável no PATH, ou
  - defina REALESRGAN_BIN=C:\\caminho\\realesrgan-ncnn-vulkan.exe
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess

from PIL import Image, ImageFilter

from .config import CACHE_DIR


def _realesrgan_bin() -> str | None:
    return os.environ.get("REALESRGAN_BIN") or shutil.which("realesrgan-ncnn-vulkan")


def ai_upscale(im: Image.Image, scale: int = 4) -> Image.Image | None:
    exe = _realesrgan_bin()
    if not exe:
        return None
    key = hashlib.sha1(im.tobytes() + str(im.size).encode()).hexdigest()[:20]
    work = CACHE_DIR / "upscale"
    work.mkdir(parents=True, exist_ok=True)
    out = work / f"{key}_x{scale}.png"
    if not out.exists():
        src = work / f"{key}.png"
        im.save(src)
        try:
            subprocess.run([exe, "-i", str(src), "-o", str(out), "-n", "realesrgan-x4plus", "-s", str(scale)],
                           check=True, capture_output=True, timeout=600)
        except Exception as exc:  # noqa: BLE001
            print(f"  [upscale] Real-ESRGAN falhou ({exc}); usando Lanczos")
            return None
    return Image.open(out).convert("RGB")


def ensure_min(im: Image.Image, min_w: int, min_h: int) -> Image.Image:
    """Garante que a foto tem resolução suficiente para o recorte final (sem ficar com cara de 720p)."""
    if im.width >= min_w and im.height >= min_h:
        return im
    factor = max(min_w / im.width, min_h / im.height)
    big = ai_upscale(im, 4 if factor > 2 else 2)
    if big is not None:
        return big
    nw, nh = int(im.width * factor + 0.5), int(im.height * factor + 0.5)
    up = im.resize((nw, nh), Image.LANCZOS)
    return up.filter(ImageFilter.UnsharpMask(radius=2.0, percent=70, threshold=2))


def sharpen(im: Image.Image, amount: int = 60) -> Image.Image:
    """Nitidez leve depois do redimensionamento (deixa a foto 'crocante' no celular)."""
    return im.filter(ImageFilter.UnsharpMask(radius=1.4, percent=amount, threshold=2))
