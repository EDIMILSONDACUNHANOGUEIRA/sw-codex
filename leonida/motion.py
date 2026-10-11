"""Estilo v2: o vídeo de publicação com textos animados, câmera e transições.

Cada arte do post (capa, imagem limpa, listas, grade, "siga") chega aqui em camadas (render.Layer).
O motor anima as camadas quadro a quadro (Pillow/NumPy) e manda os quadros para o FFmpeg.
Não precisa de Node nem de Chrome: roda em qualquer PC que gera as artes.

Linguagem visual:
  - capa: legível desde o 1º quadro (é a miniatura e o ponto do loop); câmera viva (push-in no fundo,
    parallax no personagem, palavra gigante derivando), brilho passando nas palavras em destaque;
  - textos dos outros slides: linhas sobem de dentro de uma máscara, selos dão "pop", itens de lista
    entram um por batida da música (número pula, texto desliza com máscara);
  - transições: capa -> próximo = zoom punch com flash; entre slides = whip pan com borrão de movimento;
    para o "siga" e no fim = flash de luz quente; o vídeo termina no 1º quadro da capa (loop perfeito);
  - topo fixo (logo + contador) e o ponto "ao vivo" piscando.
"""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from . import gfx, music
from .config import ROOT

FPS = 30
W, H = 1080, 1920
T = 0.40                    # duração das transições
OUTRO = 0.25                # saída do texto acontece ANTES da transição
SETTLED_HOLD = 0.15         # alguns quadros com a composição exata da arte
CAMERA_SETTLE = 0.60        # recuo suave para a composição estática
ENTER = T                  # textos entram quando o whip já assentou, dentro da área segura
HUD = {"brand", "live", "countdown", "frame", "handle"}   # topo fixo e @ discreto (o @ grande do "siga" é cta_handle)
CONTENT_ANIMS = {"line", "pop", "pop_first", "up", "slide", "wipe", "photo"}

# tempo mínimo de leitura (segundos depois de tudo ter entrado), por tipo de cena
HOLD = {"cover": 3.2, "list": 2.6, "grid": 2.6, "foto": 2.2, "cta": 1.2}


# ------------------------------------------------------------------ easing

def _clamp(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def out_expo(x: float) -> float:
    x = _clamp(x)
    return 1.0 if x >= 1 else 1 - 2 ** (-10 * x)


def out_cubic(x: float) -> float:
    x = _clamp(x)
    return 1 - (1 - x) ** 3


def in_out_cubic(x: float) -> float:
    x = _clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def in_out_sine(x: float) -> float:
    return -(math.cos(math.pi * _clamp(x)) - 1) / 2


def out_back(x: float, s: float = 1.7) -> float:
    x = _clamp(x)
    return 1 + (s + 1) * (x - 1) ** 3 + s * (x - 1) ** 2


# ------------------------------------------------------------------ cenas

@dataclass
class Sprite:
    name: str
    anim: str
    order: int
    img: Image.Image            # RGBA recortado na área útil
    x: int
    y: int
    step: int | None = None
    hot: Image.Image | None = None   # máscara (L) das palavras em destaque, do tamanho de img
    start: float = 0.0          # quando a entrada começa (tempo local da cena)
    dur: float = 0.0


@dataclass
class Scene:
    kind: str                   # cover | foto | list | grid | cta
    bg: Image.Image             # RGB, tela inteira
    sprites: list[Sprite]
    dur: float = 3.0
    settle: float = 0.0         # quando tudo já entrou
    enters: bool = True         # a capa não tem entrada (legível no 1º quadro)
    times: list[float] = field(default_factory=list)   # entrada de cada passo (itens/quadros)
    t0: float = 0.0             # início da cena no vídeo
    pulses: list[float] = field(default_factory=list)  # batidas (tempo global) em que o fundo pulsa


def scene_from(render, kind: str) -> Scene:
    """Render (com camadas) -> Scene com as camadas recortadas (economiza memória e tempo)."""
    sprites: list[Sprite] = []
    bg = None
    for L in sorted(render.layers, key=lambda L: L.order):
        if L.name == "bg":
            bg = L.image.convert("RGB")  # render já finalizou este fundo; não aplicar grão duas vezes
            continue
        bb = L.image.getbbox()
        if not bb:
            continue
        pad = 2
        bb = (max(0, bb[0] - pad), max(0, bb[1] - pad), min(W, bb[2] + pad), min(H, bb[3] + pad))
        hot = L.extra.get("hot") if L.extra else None
        sprites.append(Sprite(L.name, L.anim, L.order, L.image.crop(bb), bb[0], bb[1], L.step,
                              hot.crop(bb) if hot is not None else None))
    if bg is None:
        bg = Image.new("RGB", (W, H), gfx.hex_rgb("#0B0614"))
    return Scene(kind, bg, sprites, enters=kind != "cover")


# ------------------------------------------------------------------ batidas da música

def beat_grid(seed: str | None, seconds: float) -> list[float]:
    """Batidas da música tema. Usa music.bpm / music.fase do brand.yaml quando existirem; senão estima o
    tempo (90–160 BPM) pelo fluxo espectral suavizado, testando todas as fases. Lista vazia se não der."""
    cfg = music._cfg() or {}
    if cfg.get("bpm"):
        per = 60.0 / float(cfg["bpm"])
        ph = float(cfg.get("fase", 0.0)) % per
        return [ph + k * per for k in range(int((seconds + 0.5 - ph) / per) + 1)]
    path = music.theme_path(seed)
    ff = shutil.which("ffmpeg")
    if not path or not ff:
        return []
    start = music._ts(cfg.get("start", 0))
    sr, hop, n = 22050, 512, 1024
    try:
        raw = subprocess.run([ff, "-v", "error", "-ss", str(start), "-stream_loop", "-1", "-i", str(path),
                              "-t", f"{seconds + 2:.2f}", "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                             capture_output=True, check=True, timeout=60).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    x = np.frombuffer(raw, dtype=np.float32)
    if len(x) < sr * 4:
        return []
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n).astype(np.float32)
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10)
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    flux = np.maximum(flux - np.convolve(flux, np.ones(16) / 16, mode="same"), 0)
    flux = np.convolve(flux, [0.1, 0.2, 0.4, 0.2, 0.1], mode="same")        # suaviza ~2 quadros
    if flux.max() <= 0:
        return []
    flux /= flux.max()
    fps = sr / hop
    idx = np.arange(len(flux), dtype=np.float32)
    best = (-1.0, 0.0, 0.0)
    for bpm in np.arange(90, 160.5, 0.5):
        lag = fps * 60 / bpm
        for ph in np.arange(0, lag, 1.0):
            pos = np.arange(ph, len(flux) - 1, lag)
            sc = float(np.interp(pos, idx, flux).mean())
            if sc > best[0]:
                best = (sc, lag, ph)
    _, lag, ph = best
    if lag <= 0:
        return []
    return [float(b) for b in np.arange(ph, len(flux), lag) / fps if b <= seconds + 0.5]


def _snap(t: float, beats: list[float], tol: float = 0.22) -> float:
    if not beats:
        return t
    b = min(beats, key=lambda v: abs(v - t))
    return b if abs(b - t) <= tol else t


# ------------------------------------------------------------------ roteiro (tempos de cada cena)

def _plan_entries(sc: Scene, beats_local: list[float] | None = None,
                  latest_settle: float | None = None) -> None:
    """Define quando cada camada entra (tempo local) e quando a cena assenta."""
    if not sc.enters:
        sc.settle = 0.0
        sc.times = []
        return
    lines = [s for s in sc.sprites if s.anim == "line"]
    for i, s in enumerate(lines):
        s.start, s.dur = ENTER + 0.08 * i, 0.5
    t_after = ENTER + 0.08 * max(0, len(lines) - 1) + (0.36 if lines else 0.0)
    if sc.kind == "cta":
        em = [s for s in sc.sprites if s.name == "emblem"]
        if em:                               # o sol entra primeiro; nome e textos vêm logo atrás
            em[0].anim = "pop_first"
            em[0].start, em[0].dur = ENTER - 0.08, 0.5
            for i, s in enumerate(lines):
                s.start = ENTER + 0.22 + 0.08 * i
            t_after = ENTER + 0.22 + 0.08 * max(0, len(lines) - 1) + 0.36
        for s in sc.sprites:
            if s.anim == "wipe":
                s.start, s.dur = ENTER, 0.75
        t_after = max(t_after, ENTER + 0.5)
    if sc.kind == "foto":
        for s in sc.sprites:
            if s.anim == "photo":
                s.start, s.dur = ENTER - 0.1, 0.5
        t_after = ENTER + 0.35
    steps = sorted({s.step for s in sc.sprites if s.step is not None})
    times: list[float] = []
    ups = [s for s in sc.sprites if s.anim == "up" and s.step is None]
    if sc.kind == "list":
        # Reserva também a entrada de notas/rodapé que vêm depois do último item.
        tail = max(0.5, 0.75 + 0.07 * (len(ups) - 1)) if ups else 0.5
        last_limit = latest_settle - tail if latest_settle is not None else math.inf
        for i in range(len(steps)):
            desired = times[-1] + 0.55 if times else t_after + 0.05
            low = times[-1] + 0.45 if times else max(ENTER, desired - 0.25)
            high = min(times[-1] + 0.7 if times else desired + 0.25,
                       last_limit - (len(steps) - i - 1) * 0.45)
            choices = [b for b in (beats_local or []) if low - 1e-8 <= b <= high + 1e-8
                       and abs(b - desired) <= 0.25 + 1e-8]
            times.append(min(choices, key=lambda b: abs(b - desired)) if choices
                         else min(max(desired, low), high))
    else:
        gap = 0.62 if sc.kind == "list" else 0.16
        times = [t_after + 0.05 + gap * i for i in range(len(steps))]
    sc.times = times
    for s in sc.sprites:
        if s.step is not None and s.step in steps:
            st = times[steps.index(s.step)]
            if s.anim == "pop":
                s.start, s.dur = st, 0.42
            else:
                s.start, s.dur = st, 0.5
    end_steps = (times[-1] + 0.5) if times else t_after
    pops = [s for s in sc.sprites if s.anim == "pop" and s.step is None and s.name not in HUD]
    for i, s in enumerate(pops):
        s.start, s.dur = (ENTER + 0.05 if sc.kind == "foto" else t_after + 0.05 * i), 0.42
    base_up = max(t_after, (pops[-1].start + 0.15) if pops else 0)
    if times:
        base_up = max(base_up, end_steps - 0.2)          # rodapé/nota entra depois dos itens
    for i, s in enumerate(ups):
        s.start, s.dur = base_up + 0.07 * i, 0.45
    ends = [s.start + s.dur for s in sc.sprites if s.anim in CONTENT_ANIMS]
    sc.settle = max([end_steps, t_after] + ends)


HOLD_MIN = {"cover": 2.4, "list": 2.5, "grid": 2.5, "foto": 1.8, "cta": 1.0}


def plan(scenes: list[Scene], target: float | None, seed: str | None, log=print) -> list[float]:
    """Agenda exata a 30 fps, com leitura preservada; alvo impossível gera ValueError.

    Mantém a API do motor v2: devolve os inícios e atualiza dur/settle/times das cenas.
    As batidas só deslocam uma entrada em até 250 ms, respeitando a reserva de leitura.
    """
    if not scenes:
        raise ValueError("vídeo v2 precisa de pelo menos uma cena")
    target = 20.0 if target is None else float(target)
    if not math.isfinite(target) or target <= 0:
        raise ValueError("video_segundos precisa ser positivo e finito")
    frames = round(target * FPS)
    if abs(frames / FPS - target) > 1e-7:
        raise ValueError("video_segundos precisa corresponder a quadros inteiros a 30 fps")
    target = frames / FPS
    for sc in scenes:
        _plan_entries(sc)
    minimum = [s.settle + HOLD_MIN.get(s.kind, 2.5) + OUTRO + T for s in scenes]
    required = sum(minimum) - T * (len(scenes) - 1)
    if target < required - 1e-7:
        raise ValueError(f"video_segundos={target:g} é curto para estas cenas: mínimo {required:.2f}s "
                         "para revelar todo o conteúdo, manter a lista legível por 2,5s e sair em 0,25s")
    beats = beat_grid(seed, target + 1)
    weights = [{"cover": 1.2, "list": 1.6, "grid": 1.2, "foto": 0.6, "cta": 0.25}.get(s.kind, 1.0)
               for s in scenes]
    extra = [(target - required) * w / sum(weights) for w in weights]
    starts = [0.0]
    for i in range(1, len(scenes)):
        desired = sum(minimum[:i]) + sum(extra[:i]) - T * i
        low = starts[-1] + minimum[i - 1] - T
        high = target - sum(minimum[i:]) + T * (len(scenes) - i - 1)
        choices = [b for b in beats if low - 1e-8 <= b <= high + 1e-8 and abs(b - desired) <= 0.25 + 1e-8]
        starts.append(min(choices, key=lambda b: abs(b - desired)) if choices
                      else min(max(desired, low), high))
    for i, (s, st) in enumerate(zip(scenes, starts)):
        s.dur = (starts[i + 1] + T if i + 1 < len(scenes) else target) - st
        if s.kind == "list":
            _plan_entries(s, [b - st for b in beats], s.dur - T - OUTRO - HOLD_MIN["list"])
        if s.settle + HOLD_MIN.get(s.kind, 2.5) + OUTRO + T > s.dur + 1e-7:
            raise ValueError("a agenda de entradas excedeu o tempo reservado para leitura")
        s.t0 = st
        s.pulses = [b for b in beats[::2] if b >= 0.3]   # pulso a cada 2 batidas; o 1º quadro fica igual à arte
    return starts


# ------------------------------------------------------------------ desenho

def _blit(canvas: Image.Image, im: Image.Image, x: float, y: float, opacity: float = 1.0) -> None:
    """alpha_composite com recorte nas bordas e opacidade."""
    if opacity <= 0.003:
        return
    x, y = int(round(x)), int(round(y))
    w, h = im.size
    l, t = max(0, x), max(0, y)
    r, b = min(canvas.width, x + w), min(canvas.height, y + h)
    if r <= l or b <= t:
        return
    src = im.crop((l - x, t - y, r - x, b - y)) if (l, t, r, b) != (x, y, x + w, y + h) else im
    if opacity < 0.997:
        src = src.copy()
        src.putalpha(src.getchannel("A").point(lambda v, o=opacity: int(v * o)))
    canvas.alpha_composite(src, (l, t))


def _scaled(sp: Sprite, s: float, anchor: tuple[float, float]) -> tuple[Image.Image, float, float]:
    """Escala a sprite em torno de um ponto (coordenadas da tela)."""
    if abs(s - 1) < 0.002:
        return sp.img, sp.x, sp.y
    w, h = sp.img.size
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    im = sp.img.resize((nw, nh), Image.BILINEAR)
    ax, ay = anchor
    return im, ax + (sp.x - ax) * s, ay + (sp.y - ay) * s


def _shine(sp: Sprite, p: float) -> Image.Image | None:
    """Brilho diagonal atravessando as palavras em destaque (p de 0 a 1)."""
    if sp.hot is None or p <= 0 or p >= 1:
        return None
    w, h = sp.hot.size
    xs = np.arange(w, dtype=np.float32)[None, :] + np.arange(h, dtype=np.float32)[:, None] * 0.35
    center = -0.3 * w + p * 1.6 * w
    band = np.clip(1 - np.abs(xs - center) / (w * 0.09 + 30), 0, 1) ** 1.5
    a = (np.asarray(sp.hot, dtype=np.float32) / 255.0) * band * 0.75
    out = Image.new("RGBA", (w, h), (255, 246, 214, 0))
    out.putalpha(Image.fromarray((a * 255).astype(np.uint8)))
    return out


CAM_ANCHOR = (W / 2, 0.45 * H)


def _settled(sc: Scene, t: float) -> bool:
    end = sc.dur - T - OUTRO
    return end - SETTLED_HOLD <= t <= end


def _camera_weight(sc: Scene, t: float) -> float:
    end = sc.dur - T - OUTRO - SETTLED_HOLD
    return 1 - in_out_sine((t - (end - CAMERA_SETTLE)) / CAMERA_SETTLE)


def static_frame(sc: Scene) -> Image.Image:
    """Composição canônica das camadas, igual à arte; usada no hold e no QA."""
    frame = sc.bg.convert("RGBA")
    for sp in sorted(sc.sprites, key=lambda s: s.order):
        _blit(frame, sp.img, sp.x, sp.y)
    return frame.convert("RGB")


def _cam(sc: Scene, t: float) -> float:
    return 1.0 + (0.05 * in_out_sine(t / max(sc.dur, 0.1)) + _pulse(sc, t)) * _camera_weight(sc, t)


def _bg_frame(sc: Scene, t: float, punch: float = 1.0) -> Image.Image:
    """Fundo com push-in lento (sub-pixel, sem tremer). Âncora = CAM_ANCHOR."""
    z = _cam(sc, t) * punch
    if z <= 1.0005:
        return sc.bg.copy()
    cw, ch = W / z, H / z
    x0, y0 = (W - cw) / 2, (H - ch) * 0.45
    return sc.bg.resize((W, H), Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch))


def _pulse(sc: Scene, t: float) -> float:
    """Pulso curto do fundo na batida da música (decai em ~0,25 s)."""
    g = sc.t0 + t
    k = 0.0
    for b in sc.pulses:
        if 0 <= g - b < 0.6:
            k = max(k, math.exp(-(g - b) / 0.12))
    return 0.012 * k


def _content(sc: Scene, t: float, punch: float = 1.0) -> Image.Image:
    """Fundo + camadas de conteúdo (sem o topo fixo) no tempo local t."""
    canvas = _bg_frame(sc, t, punch).convert("RGBA")
    life = t / max(sc.dur, 0.1)
    opacity = _clamp((sc.dur - T - t) / OUTRO)
    for sp in sc.sprites:
        if sp.name in HUD:
            continue
        a = sp.anim
        media = a in ("kicker", "subject", "photo", "shade", "fade", "static")
        if not media and opacity < 1:
            # Entrada já terminou: só texto/números saem; a mídia continua e o
            # punch nunca escala conteúdo que ocupa a área segura do TikTok.
            _blit(canvas, sp.img, sp.x, sp.y - 30 * (1 - opacity), opacity)
            continue
        if a in ("shade", "fade", "static"):
            _blit(canvas, sp.img, sp.x, sp.y)
        elif a == "kicker" or sp.name == "subject_shadow":
            # a palavra gigante (e a sombra do personagem sobre ela) anda um pouco diferente da câmera:
            # cresce menos e sobe só 6 px — o parallax vem daí, sem o personagem invadir a palavra
            e = in_out_sine(life) * _camera_weight(sc, t)
            kick = next((k for k in sc.sprites if k.anim == "kicker"), sp)
            anchor = (kick.x + kick.img.width / 2, kick.y + kick.img.height / 2)
            im, x, y = _scaled(sp, (1.0 + 0.03 * e) * punch, anchor)
            _blit(canvas, im, x, y - 6 * e)
        elif a == "subject":
            # o personagem também está no fundo: precisa da MESMA câmera, senão aparece um "fantasma"
            im, x, y = _scaled(sp, _cam(sc, t) * punch, CAM_ANCHOR)
            _blit(canvas, im, x, y)
        elif a == "photo" and (not sc.enters or t >= sp.start + sp.dur):
            # imagem limpa: continua assentando devagar e termina exatamente na composição da arte
            k = 0.035 * (1 - in_out_sine(_clamp((t - sp.start - sp.dur) / max(0.1, sc.dur - T - sp.start - sp.dur))))
            k *= _camera_weight(sc, t)
            im, x, y = _scaled(sp, (1.0 + k) * punch, (sp.x + sp.img.width / 2, sp.y + sp.img.height / 2))
            _blit(canvas, im, x, y)
        elif not sc.enters or t >= sp.start + sp.dur:
            _blit(canvas, sp.img, sp.x, sp.y)
            if not _settled(sc, t):
                _maybe_shine(canvas, sc, sp, t)
        elif t <= sp.start:
            continue
        else:
            _enter(canvas, sp, (t - sp.start) / sp.dur)
    return canvas


def _maybe_shine(canvas: Image.Image, sc: Scene, sp: Sprite, t: float) -> None:
    if sp.hot is None:
        return
    t0 = (0.35 + 0.12 * int(sp.name.rsplit("_", 1)[-1] or 0)) if not sc.enters else sp.start + sp.dur + 0.05
    sh = _shine(sp, (t - t0) / 0.7)
    if sh is not None:
        _blit(canvas, sh, sp.x, sp.y)


def _enter(canvas: Image.Image, sp: Sprite, p: float) -> None:
    a = sp.anim
    w, h = sp.img.size
    if a == "line":                       # sobe de dentro da máscara (a área da própria linha)
        e = out_expo(p)
        dy = (1 - e) * h * 0.95
        visible = int(round(h - dy))
        if visible <= 0:
            return
        part = sp.img.crop((0, 0, w, visible))
        _blit(canvas, part, sp.x, sp.y + dy, min(1.0, p * 3))
    elif a == "slide":                    # desliza da esquerda revelando da esquerda p/ direita
        e = out_expo(p)
        vis = int(round(w * (0.15 + 0.85 * e)))
        part = sp.img.crop((0, 0, max(1, vis), h))
        feather = min(60, vis)
        if e < 0.999 and feather > 1:                # borda suave na revelação (sem corte reto nas letras)
            ramp = np.ones(vis, dtype=np.float32)
            ramp[-feather:] = np.linspace(1, 0, feather, dtype=np.float32)
            al = (np.asarray(part.getchannel("A"), dtype=np.float32) * ramp[None, :]).astype(np.uint8)
            part = part.copy()
            part.putalpha(Image.fromarray(al))
        _blit(canvas, part, sp.x - 60 * (1 - e), sp.y, min(1.0, p * 2.5))
    elif a in ("pop", "pop_first"):
        s = 0.55 + 0.45 * out_back(p)
        im, x, y = _scaled(sp, s, (sp.x + w / 2, sp.y + h / 2))
        _blit(canvas, im, x, y, min(1.0, p * 3))
    elif a == "up":
        e = out_cubic(p)
        _blit(canvas, sp.img, sp.x, sp.y + 24 * (1 - e), e)
    elif a == "wipe":
        e = out_cubic(p)
        vis = int(round(w * e))
        if vis > 0:
            _blit(canvas, sp.img.crop((0, 0, vis, h)), sp.x, sp.y)
    elif a == "photo":
        e = out_cubic(p)
        im, x, y = _scaled(sp, 1.035, (sp.x + w / 2, sp.y + h / 2))
        _blit(canvas, im, x, y + 40 * (1 - e), e)
    else:
        _blit(canvas, sp.img, sp.x, sp.y, out_cubic(p))


def _hud(sc: Scene, t_global: float, t_local: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for sp in sc.sprites:
        if sp.name not in HUD:
            continue
        if sp.name == "live":
            pulse = 0.35 + 0.65 * (0.5 + 0.5 * math.cos(2 * math.pi * t_global / 1.1))
            _blit(layer, sp.img, sp.x, sp.y, 1 - (1 - pulse) * _camera_weight(sc, t_local))
        elif sp.name == "countdown" and sc.kind == "cover" and 0.45 < t_local < 0.95:
            k = math.sin(math.pi * (t_local - 0.45) / 0.5)
            # Ancora na borda direita: o pop não avança na coluna de botões.
            im, x, y = _scaled(sp, 1 + 0.07 * k, (sp.x + sp.img.width, sp.y + sp.img.height / 2))
            _blit(layer, im, x, y)
        else:
            _blit(layer, sp.img, sp.x, sp.y)
    return layer


# ------------------------------------------------------------------ transições

def _hblur(im: Image.Image, amount: float) -> Image.Image:
    """Borrão de movimento horizontal (reduz e amplia só na largura)."""
    k = int(1 + amount * 26)
    if k <= 1:
        return im
    return im.resize((max(8, W // k), H), Image.BILINEAR).resize((W, H), Image.BILINEAR)


_WARM = None


def _warm() -> Image.Image:
    global _WARM
    if _WARM is None:
        _WARM = gfx.linear_gradient((W, H), [(0.0, "#FFD27A"), (0.5, "#FF8A3D"), (1.0, "#FF2E88")], 120).convert("RGB")
    return _WARM


def _flash(im: Image.Image, amount: float, warm: bool = True, p: float = 0.5) -> Image.Image:
    """warm=False: flash branco uniforme (zoom punch). warm=True: vazamento de luz quente que atravessa a
    tela na diagonal (mancha suave, não pinta a tela inteira)."""
    if amount <= 0.003:
        return im
    if not warm:
        return Image.blend(im, ImageChops.screen(im, Image.new("RGB", (W, H), (255, 255, 255))), min(1.0, amount))
    sw, sh = 108, 192
    yy, xx = np.mgrid[0:sh, 0:sw].astype(np.float32)
    cx, cy = (-0.3 + 1.6 * p) * sw, (0.15 + 0.5 * p) * sh
    r = 0.75 + 0.35 * math.sin(math.pi * p)              # a mancha cresce no meio da transição
    d = np.sqrt(((xx - cx) / (sw * r)) ** 2 + ((yy - cy) / (sh * r * 0.75)) ** 2)
    m = np.clip(1 - d, 0, 1) ** 1.6 * min(1.0, amount)
    m = np.maximum(m, 0.92 * max(0.0, 1 - abs(p - 0.5) / 0.14))     # no pico a luz cobre tudo
    mask = Image.fromarray((m * 255).astype(np.uint8)).resize((W, H), Image.BILINEAR)
    return Image.composite(ImageChops.screen(im, _warm()), im, mask)


def _transition(kind: str, a: Image.Image, b: Image.Image, p: float) -> Image.Image:
    """a = conteúdo que sai, b = conteúdo que entra (RGB), p de 0 a 1."""
    if kind == "whip":
        e = in_out_cubic(p)
        dx = int(round(e * W))
        canvas = Image.new("RGB", (W, H))
        canvas.paste(a, (-dx, 0))
        canvas.paste(b, (W - dx, 0))
        speed = math.sin(math.pi * p)              # mais borrão no meio do movimento
        return _hblur(canvas, speed)
    if kind == "punch":
        if p < 0.5:
            q = p / 0.5
            return _flash(a, 0.95 * q ** 4, warm=False)
        q = (p - 0.5) / 0.5
        return _flash(b, 0.95 * (1 - q) ** 3, warm=False)
    # flash: luz quente cruzando
    src = a if p < 0.5 else b              # troca seca escondida no pico da luz (sem texto sobre texto)
    return _flash(src, min(1.0, 1.15 * math.sin(math.pi * p)), True, p)


def _kind_between(a: Scene, b: Scene) -> str:
    if a.kind == "cover":
        return "punch"
    if b.kind in ("cta", "cover"):
        return "flash"
    return "whip"


# ------------------------------------------------------------------ montagem

def _opening(first: Scene) -> Image.Image:
    frame = _content(first, 0.0)
    frame.alpha_composite(_hud(first, 0.0, 0.0))
    return frame.convert("RGB")


def frame_at(scenes: list[Scene], starts: list[float], frame_no: int,
             loop_frame: Image.Image | None = None) -> Image.Image:
    """Mesmo caminho do encode, acesso direto por índice a 30 fps para QA leve."""
    first = scenes[0]
    total = starts[-1] + scenes[-1].dur
    n = int(round(total * FPS))
    if not 0 <= frame_no < n:
        raise IndexError("quadro fora da duração do vídeo")
    g = frame_no / FPS
    if frame_no == 0 or frame_no == n - 1:
        return (loop_frame if loop_frame is not None else _opening(first)).copy()
    i = next((k for k, s in enumerate(scenes) if g < starts[k] + s.dur - 1e-9), len(scenes) - 1)
    sc = scenes[i]
    t = g - starts[i]
    out_end = sc.dur - T
    if _settled(sc, t):
        return static_frame(sc)
    if t < out_end:
        frame = _content(sc, t)
        frame.alpha_composite(_hud(sc, g, t))
        return frame.convert("RGB")
    p = min(1.0, (t - out_end) / T)
    if i + 1 < len(scenes):
        nxt, tn = scenes[i + 1], t - out_end
        b = _content(nxt, tn).convert("RGB")
        hud_b = _hud(nxt, g, tn)
        kind = _kind_between(sc, nxt)
    else:                                   # loop: volta para o 1º quadro da capa
        nxt, b, kind = first, _content(first, 0.0).convert("RGB"), "flash"
        hud_b = _hud(first, 0.0, 0.0)
    if kind == "punch":
        # Escala exclusivamente fundo/personagem/palavra gigante. O
        # texto que entra continua nas coordenadas originais da arte.
        za = 1 + 0.35 * (min(1, p * 2)) ** 3
        zb = 1.12 - 0.12 * out_expo(max(0, (p - 0.5) * 2))
        a = _content(sc, t, za).convert("RGB")
        b = _content(nxt, tn, zb).convert("RGB")
    else:
        a = _content(sc, t).convert("RGB")
    frame = _transition(kind, a, b, p).convert("RGBA")
    fa = frame.copy()
    fa.alpha_composite(_hud(sc, g, t))
    if p <= 0:
        return fa.convert("RGB")
    frame.alpha_composite(hud_b)
    return Image.blend(fa, frame, p).convert("RGB")


def render_frames(scenes: list[Scene], starts: list[float]):
    """Gera os quadros RGB; frame_at é compartilhado pelo encode e pela inspeção."""
    n = int(round((starts[-1] + scenes[-1].dur) * FPS))
    opening = _opening(scenes[0])
    for frame_no in range(n):
        yield frame_at(scenes, starts, frame_no, opening)


def build(scenes: list[Scene], out: Path, seed: str | None = None, target: float | None = None,
          log=print) -> Path:
    """Renderiza o vídeo v2 com a música tema em `out`. Lança postvideo.MusicMissing sem música."""
    from .postvideo import MusicMissing
    theme = music.theme_path(seed)
    if not theme:
        raise MusicMissing("nenhuma música tema em assets/music/ — rode: "
                           "python -m leonida musica \"URL do trailer\" --inicio 0:12")
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    starts = plan(scenes, target, seed, log)
    if any(sc.bg.size != (W, H) for sc in scenes):
        raise ValueError(f"as cenas v2 precisam medir {W}×{H}")
    total = starts[-1] + scenes[-1].dur
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cfg = music._cfg() or {}
    start = music._ts(cfg.get("start", 0))
    af = (f"atrim=duration={total:.9f},asetpts=PTS-STARTPTS,volume={float(cfg.get('volume', 1.0))},"
          f"afade=t=in:st=0:d=0.5,afade=t=out:st={max(0, total - 0.5):.9f}:d=0.5")
    # Temporário exclusivo: dois builds nunca removem a pasta de trabalho alheia.
    # O arquivo anterior continua disponível até vídeo e áudio novos estarem prontos.
    with tempfile.TemporaryDirectory(prefix=".motion-", dir=out.parent) as work:
        tmp = Path(work) / out.name
        errf = Path(work) / "ffmpeg.log"
        cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
               "-i", "-", "-ss", str(start), "-stream_loop", "-1", "-i", str(theme),
               "-map", "0:v:0", "-map", "1:a:0", "-af", af,
               "-vf", "scale=out_color_matrix=bt709:out_range=tv", "-c:v", "libx264", "-profile:v", "high",
               "-preset", "veryfast", "-threads", "4", "-crf", "18", "-pix_fmt", "yuv420p", "-colorspace", "bt709",
               "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
               "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-t", f"{total:.9f}",
               "-movflags", "+faststart", str(tmp)]
        with open(errf, "wb") as ef:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=ef)
            try:
                for fr in render_frames(scenes, starts):
                    proc.stdin.write(fr.tobytes())
                proc.stdin.close()
            except BrokenPipeError:
                # Espera o código real; lê o log ANTES da limpeza do temporário.
                try:
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
            except BaseException:
                proc.kill()
                proc.wait()
                try:
                    proc.stdin.close()
                except BrokenPipeError:
                    pass
                raise
            if proc.wait() != 0:
                ef.flush()
                raise RuntimeError("ffmpeg falhou: " + errf.read_text(errors="replace")[-800:])
        if not music._has_audio(tmp):
            raise MusicMissing("não consegui colocar a música tema no vídeo — confira assets/music/")
        os.replace(tmp, out)
    try:
        display = out.relative_to(ROOT)
    except ValueError:
        display = out
    log(f"  🎬 vídeo v2 (textos animados) com música tema: {display} ({total:.1f}s, {theme.name})")
    return out
