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
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from . import gfx, music
from .config import ROOT

FPS = 30
W, H = 1080, 1920
T = 0.40                    # duração das transições
ENTER = 0.24                # quando os textos começam a entrar (o slide novo já está assentando)
HUD = {"brand", "live", "countdown", "frame", "handle"}   # topo fixo e @ discreto (o @ grande do "siga" é cta_handle)
CONTENT_ANIMS = {"line", "pop", "pop_first", "up", "slide", "wipe", "photo"}

# tempo mínimo de leitura (segundos depois de tudo ter entrado), por tipo de cena
HOLD = {"cover": 3.2, "list": 2.6, "grid": 2.6, "foto": 2.4, "cta": 1.3}


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
            bg = gfx.finish(L.image.convert("RGB"))      # grão/halação como nas artes
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
    """Batidas da música tema (tempo constante estimado pela energia/onsets). Lista vazia se não der."""
    path = music.theme_path(seed)
    ff = shutil.which("ffmpeg")
    if not path or not ff:
        return []
    start = music._ts((music._cfg() or {}).get("start", 0))
    sr, hop, n = 22050, 512, 1024
    try:
        raw = subprocess.run([ff, "-v", "error", "-ss", str(start), "-t", f"{seconds + 2:.2f}", "-stream_loop", "-1",
                              "-i", str(path), "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                             capture_output=True, check=True, timeout=60).stdout
    except (subprocess.SubprocessError, OSError):
        return []
    x = np.frombuffer(raw, dtype=np.float32)
    if len(x) < sr * 4:
        return []
    frames = np.lib.stride_tricks.sliding_window_view(x, n)[::hop] * np.hanning(n).astype(np.float32)
    mag = np.log1p(np.abs(np.fft.rfft(frames, axis=1)) * 10)
    flux = np.maximum(0, np.diff(mag, axis=0)).sum(axis=1)
    flux = flux - np.convolve(flux, np.ones(16) / 16, mode="same")
    flux = np.maximum(flux, 0)
    if flux.max() <= 0:
        return []
    flux /= flux.max()
    fps = sr / hop
    best, best_lag = -1.0, 0
    for bpm in np.arange(70, 181, 0.5):
        lag = fps * 60 / bpm
        idx = np.arange(0, len(flux) - lag, lag)
        score = flux[(idx + lag).astype(int)].dot(flux[idx.astype(int)]) / max(1, len(idx))
        score *= math.exp(-0.5 * (math.log2(bpm / 120)) ** 2)      # prefere ~120 BPM
        if score > best:
            best, best_lag = score, lag
    if best_lag <= 0:
        return []
    phases = np.arange(0, best_lag, 1.0)
    sums = [flux[np.arange(p, len(flux), best_lag).astype(int)].sum() for p in phases]
    p0 = phases[int(np.argmax(sums))]
    beats = np.arange(p0, len(flux), best_lag) / fps
    return [float(b) for b in beats if b <= seconds + 0.5]


def _snap(t: float, beats: list[float], tol: float = 0.22) -> float:
    if not beats:
        return t
    b = min(beats, key=lambda v: abs(v - t))
    return b if abs(b - t) <= tol else t


# ------------------------------------------------------------------ roteiro (tempos de cada cena)

def _plan_entries(sc: Scene, beats_local: list[float] | None = None) -> None:
    """Define quando cada camada entra (tempo local) e quando a cena assenta."""
    if not sc.enters:
        sc.settle = 0.0
        return
    lines = [s for s in sc.sprites if s.anim == "line"]
    for i, s in enumerate(lines):
        s.start, s.dur = ENTER + 0.09 * i, 0.55
    t_after = ENTER + 0.09 * max(0, len(lines) - 1) + (0.36 if lines else 0.0)
    if sc.kind == "cta":
        em = [s for s in sc.sprites if s.name == "emblem"]
        if em:                               # o sol entra primeiro; nome e textos vêm logo atrás
            em[0].anim = "pop_first"
            em[0].start, em[0].dur = ENTER - 0.08, 0.5
            for i, s in enumerate(lines):
                s.start = ENTER + 0.22 + 0.09 * i
            t_after = ENTER + 0.22 + 0.09 * max(0, len(lines) - 1) + 0.36
        for s in sc.sprites:
            if s.anim == "wipe":
                s.start, s.dur = ENTER, 0.75
        t_after = max(t_after, ENTER + 0.5)
    if sc.kind == "foto":
        for s in sc.sprites:
            if s.anim == "photo":
                s.start, s.dur = ENTER - 0.1, 0.6
        t_after = ENTER + 0.35
    steps = sorted({s.step for s in sc.sprites if s.step is not None})
    times: list[float] = []
    t = t_after + 0.05
    gap = 0.62 if sc.kind == "list" else 0.16
    for k in steps:
        tt = _snap(t, beats_local or []) if sc.kind == "list" else t
        if times and tt - times[-1] < (0.42 if sc.kind == "list" else 0.12):
            tt = times[-1] + (0.42 if sc.kind == "list" else 0.12)
        times.append(tt)
        t = tt + gap
    sc.times = times
    for s in sc.sprites:
        if s.step is not None and s.step in steps:
            st = times[steps.index(s.step)]
            if s.anim == "pop":
                s.start, s.dur = st - (0.04 if sc.kind == "list" else 0), 0.42
            else:
                s.start, s.dur = st, 0.5
    end_steps = (times[-1] + 0.5) if times else t_after
    ups = [s for s in sc.sprites if s.anim == "up"]
    pops = [s for s in sc.sprites if s.anim == "pop" and s.step is None and s.name not in HUD]
    for i, s in enumerate(pops):
        s.start, s.dur = (ENTER + 0.05 if sc.kind == "foto" else t_after + 0.05 * i), 0.42
    base_up = max(t_after, (pops[-1].start + 0.15) if pops else 0)
    for i, s in enumerate(ups):
        s.start, s.dur = base_up + 0.07 * i, 0.45
    ends = [s.start + s.dur for s in sc.sprites if s.anim in CONTENT_ANIMS]
    sc.settle = max([end_steps, t_after] + ends)


def plan(scenes: list[Scene], target: float | None, seed: str | None) -> list[float]:
    """Durações das cenas (com as batidas da música). Devolve os inícios globais de cada cena."""
    beats = beat_grid(seed, (target or 22) + 6)
    for sc in scenes:
        _plan_entries(sc)
        sc.dur = sc.settle + HOLD.get(sc.kind, 2.5) + T
    total = sum(s.dur for s in scenes) - T * (len(scenes) - 1)
    if target:
        extra = float(target) - total
        weights = {"cover": 1.2, "list": 1.6, "grid": 1.2, "foto": 0.6, "cta": 0.25}
        wsum = sum(weights.get(s.kind, 1.0) for s in scenes)
        for s in scenes:
            hold = HOLD.get(s.kind, 2.5)
            add = extra * weights.get(s.kind, 1.0) / wsum
            add = max(-hold * 0.35, min(hold * 1.8, add))
            s.dur += add
    # encaixa as viradas de cena nas batidas e reprograma os itens das listas nas batidas locais
    starts, g = [], 0.0
    for i, s in enumerate(scenes):
        starts.append(g)
        if beats and i < len(scenes) - 1:
            cut = g + s.dur - T / 2
            snapped = _snap(cut, beats, 0.25)
            s.dur = max(s.settle + 1.2 + T, s.dur + (snapped - cut))
        if s.kind == "list" and beats:
            _plan_entries(s, [b - g for b in beats if g <= b <= g + s.dur])
            s.dur = max(s.dur, s.settle + 1.6 + T)
        g += s.dur - T
    for s, st in zip(scenes, starts):
        s.t0 = st
        s.pulses = beats[::2]           # um pulso a cada 2 batidas: ritmo sem tremedeira
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


def _bg_frame(sc: Scene, t: float) -> Image.Image:
    """Fundo com push-in lento (sub-pixel, sem tremer)."""
    z = 1.0 + 0.05 * in_out_sine(t / max(sc.dur, 0.1)) + _pulse(sc, t)
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


def _content(sc: Scene, t: float) -> Image.Image:
    """Fundo + camadas de conteúdo (sem o topo fixo) no tempo local t."""
    canvas = _bg_frame(sc, t).convert("RGBA")
    life = t / max(sc.dur, 0.1)
    for sp in sc.sprites:
        if sp.name in HUD:
            continue
        a = sp.anim
        if a in ("shade", "fade", "static"):
            _blit(canvas, sp.img, sp.x, sp.y)
        elif a == "kicker":
            s = 1.0 + 0.04 * in_out_sine(life)
            cx, cy = sp.x + sp.img.width / 2, sp.y + sp.img.height / 2
            im, x, y = _scaled(sp, s, (cx, cy))
            _blit(canvas, im, x, y - 14 * in_out_sine(life))
        elif a == "subject":
            s = 1.0 + 0.06 * in_out_sine(life)
            im, x, y = _scaled(sp, s, (sp.x + sp.img.width / 2, sp.y + sp.img.height))
            _blit(canvas, im, x, y - 18 * in_out_sine(life))
        elif not sc.enters or t >= sp.start + sp.dur:
            _blit(canvas, sp.img, sp.x, sp.y)
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
        im, x, y = _scaled(sp, 1.04 - 0.04 * e, (sp.x + w / 2, sp.y + h / 2))
        _blit(canvas, im, x, y + 40 * (1 - e), e)
    else:
        _blit(canvas, sp.img, sp.x, sp.y, out_cubic(p))


def _hud(sc: Scene, t_global: float, t_local: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for sp in sc.sprites:
        if sp.name not in HUD:
            continue
        if sp.name == "live":
            _blit(layer, sp.img, sp.x, sp.y, 0.35 + 0.65 * (0.5 + 0.5 * math.cos(2 * math.pi * t_global / 1.1)))
        elif sp.name == "countdown" and sc.kind == "cover" and 0.45 < t_local < 0.95:
            k = math.sin(math.pi * (t_local - 0.45) / 0.5)
            im, x, y = _scaled(sp, 1 + 0.07 * k, (sp.x + sp.img.width / 2, sp.y + sp.img.height / 2))
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
    d = np.sqrt(((xx - cx) / (sw * 0.75)) ** 2 + ((yy - cy) / (sh * 0.55)) ** 2)
    m = np.clip(1 - d, 0, 1) ** 1.6 * min(1.0, amount)
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
            z = 1 + 0.30 * q ** 2
            cw, ch = W / z, H / z
            im = a.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
            return _flash(im, 0.85 * q, warm=False)
        q = (p - 0.5) / 0.5
        z = 1.12 - 0.12 * out_cubic(q)
        cw, ch = W / z, H / z
        im = b.resize((W, H), Image.BILINEAR, box=((W - cw) / 2, (H - ch) / 2, (W + cw) / 2, (H + ch) / 2))
        return _flash(im, 0.85 * (1 - q), warm=False)
    # flash: luz quente cruzando
    mix = Image.blend(a, b, in_out_sine(p))
    return _flash(mix, 0.9 * math.sin(math.pi * p), True, p)


def _kind_between(a: Scene, b: Scene) -> str:
    if a.kind == "cover":
        return "punch"
    if b.kind in ("cta", "cover"):
        return "flash"
    return "whip"


# ------------------------------------------------------------------ montagem

def render_frames(scenes: list[Scene], starts: list[float]):
    """Gera os quadros (RGB) do vídeo inteiro, terminando no 1º quadro da capa (loop)."""
    first = scenes[0]
    loop_content = _content(first, 0.0).convert("RGB")
    total = starts[-1] + scenes[-1].dur
    n = int(round(total * FPS))
    for f in range(n):
        g = f / FPS
        i = max(k for k, s in enumerate(starts) if s <= g + 1e-9)
        sc = scenes[i]
        t = g - starts[i]
        out_end = sc.dur - T
        if t < out_end:
            frame = _content(sc, t).convert("RGB")
            hud = _hud(sc, g, t)
        else:
            p = min(1.0, (t - out_end) / T)
            if i + 1 < len(scenes):
                nxt, tn = scenes[i + 1], t - out_end
                b = _content(nxt, tn).convert("RGB")
                hud_b = _hud(nxt, g, tn)
                kind = _kind_between(sc, nxt)
            else:                                   # loop: volta para o 1º quadro da capa
                nxt, b, kind = first, loop_content, "flash"
                hud_b = _hud(first, 0.0, 0.0)
                if f == n - 1:
                    p = 1.0
            a = _content(sc, t).convert("RGB")
            frame = _transition(kind, a, b, p)
            hud = Image.blend(_hud(sc, g, t), hud_b, p) if p > 0 else _hud(sc, g, t)
        fr = frame.convert("RGBA")
        fr.alpha_composite(hud)
        yield fr.convert("RGB")


def build(scenes: list[Scene], out: Path, seed: str | None = None, target: float | None = None,
          log=print) -> Path:
    """Renderiza o vídeo v2 com a música tema em `out`. Lança postvideo.MusicMissing sem música."""
    from .postvideo import MusicMissing
    if not music.theme_path(seed):
        raise MusicMissing("nenhuma música tema em assets/music/ — rode: "
                           "python -m leonida musica \"URL do trailer\" --inicio 0:12")
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    starts = plan(scenes, target, seed)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)
    tmp = out.with_name(".v2_" + out.name)
    cmd = [ff, "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "18",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for fr in render_frames(scenes, starts):
            proc.stdin.write(fr.tobytes())
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError(f"ffmpeg falhou: {err[-800:]}")
    except BaseException:
        proc.kill()
        tmp.unlink(missing_ok=True)
        raise
    ok = music.apply(tmp, under_original=False, seed=seed, fade_out=0.5)
    if not ok or not music._has_audio(tmp):
        tmp.unlink(missing_ok=True)
        raise MusicMissing("não consegui colocar a música tema no vídeo — confira assets/music/")
    tmp.replace(out)
    total = starts[-1] + scenes[-1].dur
    log(f"  🎬 vídeo v2 (textos animados) com música tema: {out.relative_to(ROOT)} ({total:.1f}s, "
        f"{music.theme_path(seed).name})")
    return out
