"""Primitivas gráficas do estilo "Vice": fontes, gradientes, color grading, texto com brilho."""
from __future__ import annotations

import re
from functools import lru_cache

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from .config import FONTS_DIR

FONT_FILES = {
    "display": "Anton-Regular.ttf",        # manchetes
    "script": "Yellowtail-Regular.ttf",    # assinatura retrô
    "body": "Inter-Medium.otf",            # resumo
    "bold": "Inter-Bold.otf",
    "heavy": "Inter-ExtraBold.otf",
}


@lru_cache(maxsize=256)
def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / FONT_FILES[kind]), size)


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgba(h: str, a: int = 255) -> tuple[int, int, int, int]:
    return (*hex_rgb(h), a)


# ---------------------------------------------------------------- gradientes

def linear_gradient(size, stops, angle: float = 90.0) -> Image.Image:
    """Gradiente linear RGBA. stops = [(pos 0..1, '#hex' ou (r,g,b,a)), ...].

    angle 0 = da esquerda p/ a direita, 90 = de cima p/ baixo.
    """
    w, h = size
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    rad = np.deg2rad(angle)
    proj = xx * np.cos(rad) + yy * np.sin(rad)
    proj = (proj - proj.min()) / max(1e-6, (proj.max() - proj.min()))
    cols = []
    for pos, c in stops:
        c = rgba(c) if isinstance(c, str) else (tuple(c) + (255,))[:4]
        cols.append((pos, np.array(c, dtype=np.float32)))
    out = np.zeros((h, w, 4), dtype=np.float32)
    for (p0, c0), (p1, c1) in zip(cols, cols[1:]):
        m = (proj >= p0) & (proj <= p1)
        t = ((proj - p0) / max(1e-6, p1 - p0))[..., None]
        out[m] = (c0 * (1 - t) + c1 * t)[m]
    out[proj < cols[0][0]] = cols[0][1]
    out[proj > cols[-1][0]] = cols[-1][1]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8), "RGBA")


def sunset(size, angle: float = 90.0) -> Image.Image:
    """Gradiente assinatura: dourado -> laranja -> rosa -> roxo."""
    return linear_gradient(size, [(0.0, "#FFD36E"), (0.35, "#FF8A3D"),
                                  (0.7, "#FF2E88"), (1.0, "#B03CFF")], angle)


def neon(size, angle: float = 0.0) -> Image.Image:
    return linear_gradient(size, [(0.0, "#FF2E88"), (0.5, "#FF8A3D"), (1.0, "#22D3EE")], angle)


# ---------------------------------------------------------------- imagem

def cover_fit(im: Image.Image, size, focus=(0.5, 0.5)) -> Image.Image:
    """Recorta/escala para preencher size mantendo o ponto de foco visível."""
    tw, th = size
    sw, sh = im.size
    scale = max(tw / sw, th / sh)
    nw, nh = int(round(sw * scale)), int(round(sh * scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    fx, fy = focus
    left = int(min(max(fx * nw - tw / 2, 0), nw - tw))
    top = int(min(max(fy * nh - th / 2, 0), nh - th))
    return im.crop((left, top, left + tw, top + th))


def look() -> dict:
    """Acabamento das artes (config/brand.yaml -> acabamento). Padrão: visual fotográfico, sem neon."""
    from .config import brand
    cfg = {"neon": False, "scanlines": False, "grao": 1.0, "halacao": 1.0, "sombra_personagem": True,
           "light_wrap": True}
    cfg.update(brand().get("acabamento") or {})
    return cfg


def _lum(a: np.ndarray) -> np.ndarray:
    return 0.2126 * a[..., 0] + 0.7152 * a[..., 1] + 0.0722 * a[..., 2]


def _skin_weight(a: np.ndarray) -> np.ndarray:
    """0..1 — quanto o pixel parece pele (matiz laranja/vermelho, saturação moderada)."""
    mx, mn = a.max(axis=-1), a.min(axis=-1)
    sat = (mx - mn) / (mx + 1e-6)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    warm = (r >= g) & (g >= b)                       # matiz entre vermelho e amarelo
    hue = np.where(warm, (g - b) / (r - b + 1e-6), 0)  # 0 = vermelho, 1 = amarelo
    w = warm * np.clip(1 - np.abs(hue - 0.42) / 0.38, 0, 1)
    w *= np.clip(1 - np.abs(sat - 0.38) / 0.32, 0, 1) * np.clip((mx - 0.12) / 0.2, 0, 1)
    return w.astype(np.float32)


def vice_grade(im: Image.Image, strength: float = 1.0, seed: int = 6) -> Image.Image:
    """Color grading do estilo, com cara de foto tratada (não de filtro):
    curva fílmica (sombras levemente lavadas, altas luzes que não estouram), vibrance em vez de
    saturação bruta, tons de pele protegidos, split toning roxo/quente discreto e vinheta suave.
    O grão fica no acabamento final (`finish`), por cima de tudo."""
    a = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    h, w, _ = a.shape
    skin = _skin_weight(a)[..., None]
    # curva em S suave + ombro nas altas luzes + preto levemente lavado (matte)
    a = a + strength * 0.12 * (a - 0.5) * (1 - np.abs(2 * a - 1))
    a = np.where(a > 0.78, 0.78 + 0.22 * np.tanh((a - 0.78) / 0.22), a)
    a = 0.012 * strength + a * (1 - 0.012 * strength)
    # vibrance: realça cores apagadas, quase não mexe nas já saturadas nem na pele
    lum = _lum(a)[..., None]
    sat = (a.max(axis=-1, keepdims=True) - a.min(axis=-1, keepdims=True))
    a = lum + (a - lum) * (1 + 0.22 * strength * (1 - sat) * (1 - 0.7 * skin))
    # split toning (sombras roxas, altas luzes quentes) — mais leve na pele
    shadow = np.array([0.22, 0.10, 0.34], dtype=np.float32)
    high = np.array([1.00, 0.80, 0.62], dtype=np.float32)
    ws = ((1 - lum) ** 2.4) * 0.20 * strength * (1 - 0.6 * skin)
    wh = (lum ** 2.5) * 0.08 * strength
    a = a * (1 - ws) + shadow * ws
    a = a * (1 - wh) + high * wh
    # vinheta suave, elíptica
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    d = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)
    a *= (1 - 0.22 * strength * np.clip(d - 0.6, 0, 1) ** 1.6)[..., None]
    return Image.fromarray((a.clip(0, 1) * 255 + 0.5).astype(np.uint8), "RGB")


def finish(im: Image.Image, grain: float | None = None, halation: float | None = None, seed: int = 7) -> Image.Image:
    """Acabamento fotográfico aplicado na arte inteira (foto + textos), como numa revista impressa:
    halação nas luzes fortes e grão de filme (em "grumos", mais forte nos meios-tons, quase sem cor).
    É o que tira o aspecto liso/plástico de imagem gerada."""
    from scipy import ndimage
    cfg = look()
    grain = cfg["grao"] if grain is None else grain
    halation = cfg["halacao"] if halation is None else halation
    mode = im.mode
    rgb = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    h, w, _ = rgb.shape
    if halation > 0:
        lum = _lum(rgb)
        hot = np.clip((lum - 0.80) / 0.2, 0, 1)
        small = ndimage.zoom(hot, 0.25, order=1)
        glow = ndimage.zoom(ndimage.gaussian_filter(small, 5), (h / small.shape[0], w / small.shape[1]), order=1)
        glow = glow[:h, :w]
        tint = np.array([1.0, 0.42, 0.22], dtype=np.float32)
        rgb = rgb + (glow[..., None] * tint * 0.07 * halation) * (1 - rgb)
    if grain > 0:
        rng = np.random.default_rng(seed)
        gh, gw = int(h / 1.7) + 1, int(w / 1.7) + 1
        mono = ndimage.zoom(rng.normal(0, 1, (gh, gw)).astype(np.float32), 1.7, order=3)[:h, :w]
        chroma = ndimage.zoom(rng.normal(0, 1, (gh // 2 + 1, gw // 2 + 1, 3)).astype(np.float32),
                              (3.4, 3.4, 1), order=1)[:h, :w]
        lum = _lum(rgb)
        weight = (0.35 + 2.6 * lum * (1 - lum))[..., None]          # mais grão nos meios-tons
        rgb = rgb + (mono[..., None] * 0.017 + chroma * 0.0035) * grain * weight
    out = Image.fromarray((rgb.clip(0, 1) * 255 + 0.5).astype(np.uint8), "RGB")
    if mode == "RGBA":
        out.putalpha(im.split()[-1])
    return out


def _box(x: np.ndarray, r: int) -> np.ndarray:
    from scipy import ndimage
    return ndimage.uniform_filter(x, size=2 * r + 1, mode="reflect")


def refine_mask(image: Image.Image, mask: Image.Image, radius: int = 6, eps: float = 1e-3) -> Image.Image:
    """Filtro guiado (He et al.): a borda da máscara passa a seguir a foto (cabelo, ombro, tecido)
    em vez da borda "recortada a tesoura" típica de remoção de fundo."""
    I = np.asarray(image.convert("L").resize(mask.size), dtype=np.float32) / 255.0
    p = np.asarray(mask, dtype=np.float32) / 255.0
    # o U²-Net deixa áreas meio transparentes (topo da cabeça, cabelo escuro): o fundo "vaza" por
    # dentro do personagem. Firma o miolo antes de refinar a borda.
    p = np.clip((p - 0.12) / 0.5, 0, 1)
    mI, mp = _box(I, radius), _box(p, radius)
    cov = _box(I * p, radius) - mI * mp
    var = _box(I * I, radius) - mI * mI
    a = cov / (var + eps)
    b = mp - a * mI
    q = _box(a, radius) * I + _box(b, radius)
    # mantém o miolo sólido e só refina a faixa de borda
    core = _box((p > 0.5).astype(np.float32), radius) 
    q = np.where(core > 0.98, 1.0, np.where(core < 0.02, 0.0, q))
    return Image.fromarray((np.clip(q, 0, 1) * 255 + 0.5).astype(np.uint8), "L")


def contact_shadow(mask: Image.Image, offset=(14, 18), radius: int = 18, opacity: float = 0.5) -> Image.Image:
    """Sombra que o personagem projeta no que está atrás dele (a palavra gigante)."""
    m = ImageChops.offset(mask, *offset).filter(ImageFilter.GaussianBlur(radius))
    m = m.point(lambda v: int(v * opacity))
    layer = Image.new("RGBA", mask.size, (8, 4, 16, 0))
    layer.putalpha(m)
    return layer


def light_wrap(subject: Image.Image, behind: Image.Image, mask: Image.Image, width: int = 10,
               amount: float = 0.55) -> Image.Image:
    """A luz do fundo "invade" a borda do personagem, como acontece numa foto real.
    Sem isso o recorte parece colado por cima."""
    m = np.asarray(mask, dtype=np.float32) / 255.0
    inner = np.asarray(mask.filter(ImageFilter.GaussianBlur(width)), dtype=np.float32) / 255.0
    band = np.clip(m - inner, 0, 1) * 2.2
    band = np.clip(band, 0, 1)[..., None] * amount
    back = np.asarray(behind.convert("RGB").filter(ImageFilter.GaussianBlur(width * 1.5)), dtype=np.float32)
    s = np.asarray(subject.convert("RGBA"), dtype=np.float32)
    rgb = s[..., :3]
    screen = 255 - (255 - rgb) * (255 - back) / 255
    s[..., :3] = rgb * (1 - band) + screen * band
    return Image.fromarray(s.clip(0, 255).astype(np.uint8), "RGBA")


def scanlines(size, alpha: int = 10, gap: int = 4) -> Image.Image:
    w, h = size
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    if not look()["scanlines"]:          # linhas de TV denunciam "template digital"
        return layer
    d = ImageDraw.Draw(layer)
    for y in range(0, h, gap):
        d.line([(0, y), (w, y)], fill=(0, 0, 0, alpha))
    return layer


def vertical_fade(size, color: str, start: float, end: float, a0: int, a1: int) -> Image.Image:
    """Camada de cor com alpha variando de a0 (em y=start) até a1 (em y=end); start/end em 0..1."""
    w, h = size
    y = np.linspace(0, 1, h, dtype=np.float32)
    t = np.clip((y - start) / max(1e-6, end - start), 0, 1)
    t = t * t * (3 - 2 * t)  # smoothstep
    alpha = (a0 + (a1 - a0) * t).astype(np.uint8)
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[..., :3] = hex_rgb(color)
    arr[..., 3] = alpha[:, None]
    return Image.fromarray(arr, "RGBA")


def rounded_mask(size, radius: int) -> Image.Image:
    m = Image.new("L", size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255)
    return m


def glow(mask: Image.Image, color: str, radius: int, strength: float = 1.0, spread: int = 0) -> Image.Image:
    """Brilho neon a partir de uma máscara L.

    Com `acabamento.neon: false` (padrão) vira uma sombra escura e curta: separa o elemento do
    fundo sem o halo colorido que dá cara de arte gerada por IA."""
    if not look()["neon"]:
        color, radius, strength, spread = "#07030D", max(4, int(radius * 0.45)), strength * 0.38, 0
    m = mask
    if spread:
        m = m.filter(ImageFilter.MaxFilter(spread * 2 + 1))
    m = m.filter(ImageFilter.GaussianBlur(radius))
    if strength != 1.0:
        m = m.point(lambda v: min(255, int(v * strength)))
    layer = Image.new("RGBA", mask.size, rgba(color, 0))
    solid = Image.new("RGBA", mask.size, rgba(color))
    layer.paste(solid, (0, 0), m)
    return layer


def drop_shadow(mask: Image.Image, offset=(0, 8), radius: int = 14, alpha: int = 170) -> Image.Image:
    m = ImageChops.offset(mask, *offset).filter(ImageFilter.GaussianBlur(radius))
    m = m.point(lambda v: v * alpha // 255)
    layer = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    layer.putalpha(m)
    return layer


def fill_with(mask: Image.Image, fill) -> Image.Image:
    """Preenche a máscara com uma cor ('#hex') ou imagem RGBA (gradiente)."""
    if isinstance(fill, Image.Image):
        src = fill if fill.size == mask.size else fill.resize(mask.size)
    else:
        src = Image.new("RGBA", mask.size, rgba(fill) if isinstance(fill, str) else fill)
    out = Image.new("RGBA", mask.size, (0, 0, 0, 0))
    out.paste(src, (0, 0), mask)
    return out


# ---------------------------------------------------------------- texto

def parse_marked(text: str) -> list[tuple[str, bool]]:
    """'GTA VI revela *rádios*' -> [('GTA',False),('VI',False),('revela',False),('rádios',True)]."""
    words, hl = [], False
    # "GTA VI" / "GTA 6" nunca quebram linha (espaço não separável)
    text = re.sub(r"\b(GTA)\s+(VI|6)\b", "\\1\u00a0\\2", text, flags=re.I)
    for token in text.replace("\n", " \n ").split(" "):
        if not token:
            continue
        if token == "\n":
            words.append(("\n", False))
            continue
        start = token.startswith("*")
        end = token.rstrip(".,!?:;…\"'”)").endswith("*")
        clean = token.replace("*", "")
        cur = hl or start
        words.append((clean, cur))
        if start and not end:
            hl = True
        if end:
            hl = False
    return words


def wrap_words(words, fnt, max_w: int) -> list[list[tuple[str, bool]]]:
    lines, cur = [], []
    space = fnt.getlength(" ")
    width = 0.0
    for w, hl in words:
        if w == "\n":
            lines.append(cur)
            cur, width = [], 0.0
            continue
        ww = fnt.getlength(w)
        if cur and width + space + ww > max_w:
            lines.append(cur)
            cur, width = [], 0.0
        width += (space if cur else 0) + ww
        cur.append((w, hl))
    if cur:
        lines.append(cur)
    return lines


def wrap_text(text: str, fnt, max_w: int) -> list[str]:
    return [" ".join(w for w, _ in line) for line in wrap_words([(t, False) for t in text.split()], fnt, max_w)]


def text_mask(size, xy, text, fnt, tracking: float = 0.0) -> Image.Image:
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    if not tracking:
        d.text(xy, text, font=fnt, fill=255)
        return m
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=fnt, fill=255)
        x += fnt.getlength(ch) + tracking
    return m


def text_width(text: str, fnt, tracking: float = 0.0) -> float:
    if not tracking:
        return fnt.getlength(text)
    return sum(fnt.getlength(c) + tracking for c in text) - tracking


def fit_font(kind: str, lines_fn, max_lines: int, start: int, minimum: int, step: int = 4):
    """Diminui a fonte até o texto caber em max_lines linhas. lines_fn(font) -> linhas."""
    size = start
    while size > minimum:
        f = font(kind, size)
        lines = lines_fn(f)
        if len(lines) <= max_lines:
            return f, lines
        size -= step
    f = font(kind, minimum)
    return f, lines_fn(f)
