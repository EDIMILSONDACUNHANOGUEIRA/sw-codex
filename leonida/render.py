"""Renderização das artes 9:16 no estilo LEONIDA WIRE.

Capa (cover):
  fundo com color grading "Vice" -> palavra gigante (kicker) -> personagem recortado na frente
  -> escurecimento inferior -> selo + manchete com destaque em gradiente -> resumo -> fonte.
  Topo: marca + contador de dias para o lançamento. Cantos em estilo "mira" neon.

Cada elemento é guardado também como camada RGBA separada, usada pelo vídeo animado (HyperFrames).
"""
from __future__ import annotations

import datetime as dt
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import cutout as cut
from . import gfx, upscale
from .config import brand, days_to_release
from .media import load_image

MONTHS = {
    "pt": ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"],
    "en": ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"],
}
UI = {
    "pt": {"source": "FONTE", "days": "DIAS", "day": "DIA", "until": "PARA O GTA VI",
           "out": "JÁ DISPONÍVEL", "follow": "SIGA PARA NÃO PERDER NADA",
           "follow_sub": "Notícias de GTA VI todos os dias, em português.",
           "save": "SALVE • COMPARTILHE • COMENTE", "swipe": "ARRASTE"},
    "en": {"source": "SOURCE", "days": "DAYS", "day": "DAY", "until": "UNTIL GTA VI",
           "out": "OUT NOW", "follow": "FOLLOW SO YOU DON'T MISS A THING",
           "follow_sub": "Daily GTA VI news, fast.",
           "save": "SAVE • SHARE • COMMENT", "swipe": "SWIPE"},
}


@dataclass
class Layer:
    name: str
    image: Image.Image          # RGBA, tamanho do canvas
    anim: str = "fade"          # dica de animação para o vídeo
    order: int = 0
    step: int | None = None     # ordem de entrada dentro do slide (itens de lista, quadros da grade)
    extra: dict = field(default_factory=dict)   # ex.: {"hot": máscara das palavras em destaque}


@dataclass
class Render:
    image: Image.Image
    layers: list[Layer] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def _canvas():
    c = brand()["canvas"]
    return int(c["width"]), int(c["height"])


def _safe():
    s = brand()["safe_area"]
    return int(s["top"]), int(s["bottom"]), int(s["left"]), int(s["right"])


def fmt_date(d: str | dt.date | None, lang: str) -> str:
    if not d:
        d = dt.date.today()
    if isinstance(d, str):
        d = dt.date.fromisoformat(d[:10])
    m = MONTHS[lang][d.month - 1]
    return f"{d.day:02d} {m} {d.year}" if lang == "pt" else f"{m} {d.day:02d}, {d.year}"


def _blank(size):
    return Image.new("RGBA", size, (0, 0, 0, 0))


def _protected(text: str) -> str:
    """Mantém nomes compostos juntos em qualquer bloco, inclusive texto sem destaque."""
    for pattern in (r"\bGTA\s+(?:VI|6)\b", r"\b18\s+anos\b", r"\bXbox\s+Series\s+X\s*\|\s*S\b"):
        text = re.sub(pattern, lambda m: re.sub(r"\s+", "\u00a0", m.group()), text, flags=re.I)
    return text


def _wrap_words(words, fnt, max_w: int):
    lines = gfx.wrap_words(words, fnt, max_w)
    # Evita a última palavra isolada sem mudar o conteúdo ou quebrar nomes protegidos.
    if len(lines) > 1 and len(lines[-1]) == 1 and len(lines[-2]) >= 3:
        candidate = [lines[-2][-1], *lines[-1]]
        if fnt.getlength(" ".join(w for w, _ in candidate)) <= max_w:
            lines[-2] = lines[-2][:-1]
            lines[-1] = candidate
    return lines


def _wrap_text(text: str, fnt, max_w: int) -> list[str]:
    words = [(token, False) for token in _protected(text).split(" ") if token]
    return [" ".join(w for w, _ in line) for line in _wrap_words(words, fnt, max_w)]


def _line_height(fnt, factor: float = 1.3) -> int:
    box = fnt.getbbox("ÁÉÇgjpq")
    return max(math.ceil(fnt.size * factor), box[3] - box[1] + 10)


def _finished_bg(bg: Image.Image) -> Image.Image:
    """Acabamento uma única vez no fundo, compartilhado pela arte e pelo vídeo."""
    return gfx.finish(bg.convert("RGB")).convert("RGBA")


def _tag_info(tag: str, lang: str) -> tuple[str, str]:
    tags = brand()["tags"]
    t = tags.get((tag or "").lower())
    if not t:
        return (tag or "").upper(), brand()["palette"]["pink"]
    return t[lang], t["color"]


def _is_light(hex_color: str) -> bool:
    r, g, b = gfx.hex_rgb(hex_color)
    return (0.299 * r + 0.587 * g + 0.114 * b) > 150


# ============================================================ blocos reutilizáveis

def _logo_cfg() -> dict:
    return {"versao": "v2", "arquivo": "assets/brand/logo.png", **(brand().get("logo") or {})}


def _vice_sun(d: int) -> Image.Image:
    """Emblema "sol de Vice": círculo pôr-do-sol com as faixas synthwave na metade de baixo.
    Desenhado em 4x e reduzido, para a borda sair lisa."""
    s = d * 4
    circle = Image.new("L", (s, s), 0)
    ImageDraw.Draw(circle).ellipse([0, 0, s - 1, s - 1], fill=255)
    cut = ImageDraw.Draw(circle)
    for top, thick in ((0.555, 0.030), (0.655, 0.045), (0.760, 0.060), (0.870, 0.075)):
        cut.rectangle([0, int(s * top), s, int(s * (top + thick))], fill=0)
    grad = gfx.linear_gradient((s, s), [(0.0, "#FFD27A"), (0.38, "#FF8A3D"), (0.70, "#FF2E88"),
                                        (1.0, "#7B2FF7")], 90)
    sun = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    sun.paste(grad, (0, 0), circle)
    ring = Image.new("L", (s, s), 0)
    ImageDraw.Draw(ring).ellipse([2, 2, s - 3, s - 3], outline=255, width=7)
    ring = Image.fromarray(np.minimum(np.asarray(ring), np.asarray(circle)))
    sun.alpha_composite(gfx.fill_with(ring, gfx.rgba("#FFFFFF", 70)))
    return sun.resize((d, d), Image.LANCZOS)


def _custom_logo(d: int) -> Image.Image | None:
    """assets/brand/logo.png (ex.: a foto de perfil escolhida), recortada em círculo."""
    from .config import ROOT
    p = ROOT / _logo_cfg()["arquivo"]
    if not p.exists():
        return None
    im = gfx.cover_fit(Image.open(p).convert("RGB"), (d * 4, d * 4)).convert("RGBA")
    m = Image.new("L", (d * 4, d * 4), 0)
    ImageDraw.Draw(m).ellipse([0, 0, d * 4 - 1, d * 4 - 1], fill=255)
    im.putalpha(m)
    return im.resize((d, d), Image.LANCZOS)


def brand_layers(size, lang: str, y: int) -> tuple[Image.Image, Image.Image | None]:
    """Logo do topo em duas camadas: (marca, ponto "ao vivo"). O vídeo faz o ponto piscar."""
    if _logo_cfg()["versao"] != "v2":
        return _brand_bar_v1(size, lang, y), None
    _, _, left, _ = _safe()
    b = brand()
    layer, live = _blank(size), _blank(size)
    d = 88
    emblem = _custom_logo(d) or _vice_sun(d)
    em = Image.new("L", size, 0)
    em.paste(emblem.split()[-1], (left, y))
    layer.alpha_composite(gfx.drop_shadow(em, (0, 6), 12, 150))
    layer.alpha_composite(emblem, (left, y))
    # wordmark: 1ª palavra branca, o resto no gradiente do pôr do sol
    words = b["name"].split()
    first, rest = words[0], " ".join(words[1:])
    fn = gfx.font("display", 52)
    tx, ty = left + d + 20, y - 8
    m1 = gfx.text_mask(size, (tx, ty), first, fn, tracking=2)
    w1 = gfx.text_width(first, fn, 2) + fn.getlength(" ") * 0.9
    m2 = gfx.text_mask(size, (tx + w1, ty), rest, fn, tracking=2) if rest else Image.new("L", size, 0)
    both = Image.fromarray(np.maximum(np.asarray(m1), np.asarray(m2)))
    layer.alpha_composite(gfx.drop_shadow(both, (0, 3), 7, 160))
    layer.alpha_composite(gfx.fill_with(m1, "#FFFFFF"))
    if rest:
        band = gfx.linear_gradient((size[0], 64), [(0.0, "#FFD27A"), (0.5, "#FF8A3D"), (1.0, "#FF2E88")], 90)
        grad = _blank(size)
        grad.paste(band, (0, ty + 6))
        layer.alpha_composite(gfx.fill_with(m2, grad))
    # linha de baixo: ● NOTÍCIAS DE GTA VI
    ft = gfx.font("heavy", 19)
    dot_r, dot_y = 6, y + 77
    dm = Image.new("L", size, 0)
    ImageDraw.Draw(dm).ellipse([tx + 2, dot_y - dot_r, tx + 2 + 2 * dot_r, dot_y + dot_r], fill=255)
    live.alpha_composite(gfx.glow(dm, "#FF3B3B", 8, 0.8))
    live.alpha_composite(gfx.fill_with(dm, "#FF3B3B"))
    tm = gfx.text_mask(size, (tx + 2 * dot_r + 14, dot_y - 13), b["tagline"][lang], ft, tracking=4)
    layer.alpha_composite(gfx.drop_shadow(tm, (0, 2), 4, 150))
    layer.alpha_composite(gfx.fill_with(tm, gfx.rgba("#E9E3F5", 235)))
    return layer, live


def top_layers(size, lang: str, y_brand: int, y_count: int, today: dt.date | None = None) -> list["Layer"]:
    """Topo de todas as artes: logo (+ ponto "ao vivo") e contador de dias."""
    logo, live = brand_layers(size, lang, y_brand)
    chip = countdown_chip(size, lang, y_count, today)
    # A largura do contador varia com a quantidade de dias. Mantém um vão de 20 px
    # entre o conteúdo da marca e o selo, inclusive com três algarismos.
    core = chip.split()[-1].point(lambda a: 255 if a >= 220 else 0).getbbox()
    logo_core = logo.split()[-1].point(lambda a: 255 if a >= 220 else 0).getbbox()
    if core and logo_core and logo_core[2] > core[0] - 20:
        _, _, left, _ = _safe()
        box = logo.split()[-1].getbbox()
        if live is not None:
            lb = live.split()[-1].getbbox()
            box = (min(box[0], lb[0]), min(box[1], lb[1]), max(box[2], lb[2]), max(box[3], lb[3]))
        scale = (core[0] - 20 - left) / (logo_core[2] - left)
        def compact(layer):
            result = _blank(size)
            crop = layer.crop(box)
            result.alpha_composite(crop.resize((max(1, round(crop.width * scale)),
                                                max(1, round(crop.height * scale))), Image.LANCZOS),
                                   (round(left + (box[0] - left) * scale),
                                    round(y_brand + (box[1] - y_brand) * scale)))
            return result
        logo = compact(logo)
        live = compact(live) if live is not None else None
    out = [Layer("brand", logo, "brand", 5)]
    if live is not None:
        out.append(Layer("live", live, "live", 5))
    out.append(Layer("countdown", chip, "pop", 6))
    return out


def compose(layers: list["Layer"], size=None) -> Image.Image:
    size = size or layers[0].image.size
    img = _blank(size)
    for ly in sorted(layers, key=lambda L: L.order):
        img.alpha_composite(ly.image)
    return img


def brand_bar(size, lang: str, y: int) -> Image.Image:
    layer, live = brand_layers(size, lang, y)
    if live is not None:
        layer = layer.copy()
        layer.alpha_composite(live)
    return layer


def _brand_bar_v1(size, lang: str, y: int) -> Image.Image:
    W, H = size
    _, _, left, _ = _safe()
    b = brand()
    layer = _blank(size)
    # selo com iniciais
    mark = 74
    initials = "".join(w[0] for w in b["name"].split()[:2]).upper()
    grad = gfx.sunset((mark, mark), angle=135)
    sq = gfx.rounded_mask((mark, mark), 18)
    tile = _blank((mark, mark))
    tile.paste(grad, (0, 0), sq)
    f = gfx.font("display", 44)
    tw = f.getlength(initials)
    ImageDraw.Draw(tile).text(((mark - tw) / 2, 6), initials, font=f, fill=gfx.rgba("#0B0614"))
    glow_mask = Image.new("L", size, 0)
    glow_mask.paste(sq, (left, y))
    layer.alpha_composite(gfx.glow(glow_mask, "#FF2E88", 16, 0.7))
    layer.alpha_composite(tile, (left, y))
    # nome + tagline
    fn = gfx.font("display", 46)
    name_mask = gfx.text_mask(size, (left + mark + 20, y - 4), b["name"], fn, tracking=3)
    layer.alpha_composite(gfx.drop_shadow(name_mask, (0, 3), 6, 140))
    layer.alpha_composite(gfx.fill_with(name_mask, "#FFFFFF"))
    ft = gfx.font("heavy", 20)
    tag_mask = gfx.text_mask(size, (left + mark + 22, y + 52), b["tagline"][lang], ft, tracking=4)
    layer.alpha_composite(gfx.fill_with(tag_mask, gfx.rgba("#FFC857", 235)))
    return layer


def countdown_chip(size, lang: str, y: int, today: dt.date | None = None) -> Image.Image:
    W, H = size
    ui = UI[lang]
    days = days_to_release(today)
    layer = _blank(size)
    right = W - _safe()[3] - 8
    if days > 0:
        num = str(days)
        fnum = gfx.font("display", 66)
        fl1 = gfx.font("heavy", 19)
        fl2 = gfx.font("heavy", 17)
        l1 = ui["day"] if days == 1 else ui["days"]
        l2 = ui["until"]
        nw = fnum.getlength(num)
        lw = max(gfx.text_width(l1, fl1, 3), gfx.text_width(l2, fl2, 2))
        w = int(nw + lw + 22 * 2 + 14)
        h = 82
        x = right - w
        box = gfx.rounded_mask((w, h), 20)
        bg = Image.new("RGBA", (w, h), gfx.rgba("#0B0614", 190))
        border = gfx.neon((w, h), 0)
        bm = gfx.rounded_mask((w, h), 20)
        inner = gfx.rounded_mask((w - 6, h - 6), 17)
        ring = bm.copy()
        ring.paste(0, (3, 3), inner)
        chip = _blank((w, h))
        chip.paste(bg, (0, 0), box)
        chip.alpha_composite(gfx.fill_with(ring, border))
        nm = gfx.text_mask((w, h), (22, -6), num, fnum)
        chip.alpha_composite(gfx.fill_with(nm, gfx.sunset((w, h), 90)))
        chip.alpha_composite(gfx.fill_with(gfx.text_mask((w, h), (22 + nw + 14, 19), l1, fl1, 3), "#FFFFFF"))
        chip.alpha_composite(gfx.fill_with(gfx.text_mask((w, h), (22 + nw + 14, 45), l2, fl2, 2),
                                           gfx.rgba("#E9E3F5", 220)))
        gm = Image.new("L", size, 0)
        gm.paste(box, (x, y))
        layer.alpha_composite(gfx.glow(gm, "#FF2E88", 18, 0.55))
        layer.alpha_composite(chip, (x, y))
    else:
        f = gfx.font("display", 44)
        t = ui["out"]
        w = int(f.getlength(t) + 44)
        x = right - w
        chip = _blank((w, 70))
        chip.paste(gfx.sunset((w, 70), 0), (0, 0), gfx.rounded_mask((w, 70), 18))
        ImageDraw.Draw(chip).text((22, 6), t, font=f, fill=gfx.rgba("#0B0614"))
        layer.alpha_composite(chip, (x, y))
    return layer


def corner_brackets(size, inset: int = 26, length: int = 78, thick: int = 6) -> Image.Image:
    W, H = size
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for (cx, cy, sx, sy) in ((inset, inset, 1, 1), (W - inset, inset, -1, 1),
                             (inset, H - inset, 1, -1), (W - inset, H - inset, -1, -1)):
        x0, x1 = sorted([cx, cx + sx * length])
        y0, y1 = sorted([cy, cy + sy * thick])
        d.rectangle([x0, y0, x1, y1], fill=255)
        x0, x1 = sorted([cx, cx + sx * thick])
        y0, y1 = sorted([cy, cy + sy * length])
        d.rectangle([x0, y0, x1, y1], fill=255)
    layer = gfx.glow(m, "#FF2E88", 10, 0.8)
    layer.alpha_composite(gfx.fill_with(m, gfx.neon(size, 60)))
    return layer


def tag_pill(size, text: str, color: str, x: int, y: int) -> tuple[Image.Image, int]:
    f = gfx.font("heavy", 30)
    while gfx.text_width(text, f, 3) + 78 > size[0] - _safe()[3] - x - 8 and f.size > 14:
        f = gfx.font("heavy", f.size - 2)
    tw = gfx.text_width(text, f, 3)
    h = 58
    w = int(tw + 30 + 26 + 22)
    pill = _blank((w, h))
    pill.paste(Image.new("RGBA", (w, h), gfx.rgba(color)), (0, 0), gfx.rounded_mask((w, h), h // 2))
    ink = "#0B0614" if _is_light(color) else "#FFFFFF"
    d = ImageDraw.Draw(pill)
    d.ellipse([22, h / 2 - 7, 36, h / 2 + 7], fill=gfx.rgba(ink))
    pill.alpha_composite(gfx.fill_with(gfx.text_mask((w, h), (48, 9), text, f, 3), ink))
    layer = _blank(size)
    gm = Image.new("L", size, 0)
    gm.paste(gfx.rounded_mask((w, h), h // 2), (x, y))
    layer.alpha_composite(gfx.glow(gm, color, 20, 0.85))
    layer.alpha_composite(pill, (x, y))
    return layer, h


def headline_lines(size, words_lines, fnt, x: int, y: int, line_h: int, masks: bool = False) -> list:
    """Uma camada por linha; palavras marcadas com *...* recebem o gradiente pôr-do-sol.
    masks=True devolve (camada, máscara das palavras em destaque) — o vídeo passa um brilho nelas."""
    W, H = size
    out = []
    space = fnt.getlength(" ")
    for i, line in enumerate(words_lines):
        ly = y + i * line_h
        white = Image.new("L", size, 0)
        hot = Image.new("L", size, 0)
        dw, dh = ImageDraw.Draw(white), ImageDraw.Draw(hot)
        cx = x
        for w, hl in line:
            (dh if hl else dw).text((cx, ly), w.upper(), font=fnt, fill=255)
            cx += fnt.getlength(w.upper()) + space
        both = Image.fromarray(np.maximum(np.asarray(white), np.asarray(hot)))
        layer = _blank(size)
        layer.alpha_composite(gfx.drop_shadow(both, (0, 8), 14, 190))
        if np.asarray(hot).any():
            layer.alpha_composite(gfx.glow(hot, "#FF2E88", 22, 0.55))
        layer.alpha_composite(gfx.fill_with(white, "#FFFFFF"))
        if np.asarray(hot).any():
            asc = int(fnt.size * 0.12)
            band = gfx.linear_gradient((W, line_h), [(0.0, "#FFE08A"), (0.45, "#FF8A3D"), (1.0, "#FF2E88")], 90)
            grad = _blank(size)
            grad.paste(band, (0, ly + asc))
            layer.alpha_composite(gfx.fill_with(hot, grad))
        out.append((layer, hot if np.asarray(hot).any() else None) if masks else layer)
    return out


def text_block(size, lines, fnt, x: int, y: int, line_h: int, color, shadow=True) -> Image.Image:
    m = Image.new("L", size, 0)
    d = ImageDraw.Draw(m)
    for i, ln in enumerate(lines):
        d.text((x, y + i * line_h), ln, font=fnt, fill=255)
    layer = _blank(size)
    if shadow:
        layer.alpha_composite(gfx.drop_shadow(m, (0, 3), 8, 200))
    layer.alpha_composite(gfx.fill_with(m, color))
    return layer


def _fit_kicker(text: str, max_w: int, max_h: int):
    size = 520
    while size > 80:
        f = gfx.font("display", size)
        l, t, r, b = f.getbbox(text.upper())
        if (r - l) <= max_w and (b - t) <= max_h:
            return f, (l, t, r, b)
        size -= 6
    f = gfx.font("display", 80)
    return f, f.getbbox(text.upper())


def _kicker_place(size, text: str, mask: Image.Image | None, y_min: int, y_max: int):
    """Escolhe fonte e altura da palavra gigante. Retorna (font, bbox, top, cobertura 0..1)."""
    W, H = size
    f, (l, t, r, b) = _fit_kicker(text, W - 80, 430)
    kw, kh = r - l, b - t
    if mask is None:
        return f, (l, t, r, b), y_min, 0.0
    marr = np.asarray(mask, dtype=np.float32) / 255.0
    best_y, best_score, best_cov = y_min, None, 1.0
    for top in range(y_min, max(y_min + 1, y_max - kh), 16):
        region = marr[top:top + kh, (W - kw) // 2:(W + kw) // 2]
        cov = float(region.mean()) if region.size else 0.0
        # ideal: personagem cobre ~10-25% da palavra (profundidade sem matar a leitura)
        score = abs(cov - 0.17) + (top - y_min) / 4000
        if best_score is None or score < best_score:
            best_y, best_score, best_cov = top, score, cov
    return f, (l, t, r, b), best_y, best_cov


def kicker_layer(size, text: str, mask: Image.Image | None, y_min: int, y_max: int):
    """Palavra gigante atrás do personagem (estilo capa de revista)."""
    W, H = size
    f, (l, t, r, b), top, cov = _kicker_place(size, text, mask, y_min, y_max)
    kw, kh = r - l, b - t
    x = (W - kw) // 2 - l
    m = gfx.text_mask(size, (x, top - t), text.upper(), f)
    layer = _blank(size)
    layer.alpha_composite(gfx.glow(m, "#FF2E88", 40, 0.9))
    grad = _blank(size)
    grad.paste(gfx.sunset((W, kh + 4), 90), (0, top))
    filled = gfx.fill_with(m, grad)
    filled.putalpha(filled.split()[-1].point(lambda v: v * 240 // 255))
    layer.alpha_composite(filled)
    return layer, (top, top + kh), cov


def compose_bg(src: Image.Image, full_mask: Image.Image | None, size, focus, zoom: float):
    """Fundo 9:16. zoom < 1 recua o enquadramento: a foto fica ancorada embaixo e o topo
    é estendido com a própria foto desfocada (abre espaço para a palavra gigante)."""
    W, H = size
    if zoom >= 0.999:
        bg = gfx.cover_fit(src, size, focus)
        m = gfx.cover_fit(full_mask.convert("RGB"), size, focus).convert("L") if full_mask is not None else None
        return bg, m
    h = int(H * zoom)
    fg = gfx.cover_fit(src, (W, h), focus)
    back = gfx.cover_fit(src, size, (focus[0], 0.0)).filter(ImageFilter.GaussianBlur(42))
    back = Image.blend(back, Image.new("RGB", size, gfx.hex_rgb(brand()["palette"]["night"])), 0.35)
    ramp_h = min(280, h // 3)
    ramp = np.ones((h, W), dtype=np.float32)
    ramp[:ramp_h] = np.linspace(0, 1, ramp_h, dtype=np.float32)[:, None] ** 1.3
    ramp_img = Image.fromarray((ramp * 255).astype(np.uint8), "L")
    back.paste(fg, (0, H - h), ramp_img)
    m = None
    if full_mask is not None:
        fm = gfx.cover_fit(full_mask.convert("RGB"), (W, h), focus).convert("L")
        # a máscara NÃO acompanha a rampa longa da foto (senão a cabeça fica transparente e a palavra
        # gigante "vaza" por dentro dela); só suaviza os primeiros px, onde a foto termina
        edge = np.ones((h, 1), dtype=np.float32)
        e = min(48, h // 10)
        edge[:e, 0] = np.linspace(0, 1, e, dtype=np.float32)
        fm = Image.fromarray((np.asarray(fm, dtype=np.float32) * edge).astype(np.uint8), "L")
        m = Image.new("L", size, 0)
        m.paste(fm, (0, H - h))
    return back, m


# ============================================================ capa

def cover(post: dict, lang: str, base_dir: Path | None = None, today: dt.date | None = None) -> Render:
    W, H = _canvas()
    size = (W, H)
    s_top, s_bottom, s_left, s_right = _safe()
    loc = post[lang]
    pal = brand()["palette"]
    layout = post.get("layout", "cover")
    want_cut = bool(post.get("cutout", True)) and layout == "cover"
    src = load_image(post["image"], base_dir)
    # foto pequena (ex.: 1280x720) -> upscale (Real-ESRGAN se instalado, senão Lanczos + nitidez)
    src = upscale.ensure_min(src, 1400, 0) if layout == "card" else upscale.ensure_min(src, 0, H)
    layers: list[Layer] = []

    # ---------- fundo
    mask = None
    focus = post.get("focus")
    full_mask = None
    if want_cut and cut.available():
        work = src.copy()
        work.thumbnail((1920, 1920), Image.LANCZOS)
        full_mask = cut.subject_mask(work)
        if full_mask is not None:
            full_mask = gfx.refine_mask(work, full_mask)   # borda segue cabelo/roupa da foto
        if full_mask is not None and not focus:
            c = cut.mask_centroid(full_mask)
            if c:
                focus = (c[0], 0.5)
    if not focus:
        focus = cut.face_focus(src) or (0.5, 0.5)
    focus = tuple(focus)

    # ---------- bloco inferior (calculado de baixo p/ cima)
    text_w = W - s_left - s_right
    bottom = H - s_bottom
    ui = UI[lang]
    src_name = (post.get("source") or {}).get("name", "")
    footer_txt = f"{ui['source']}: {src_name.upper()}  •  {fmt_date(post.get('date'), lang)}" if src_name \
        else fmt_date(post.get("date"), lang)
    ff = gfx.font("bold", 24)
    while gfx.text_width(footer_txt, ff, 2) > text_w - 8 and ff.size > 14:
        ff = gfx.font("bold", ff.size - 1)
    footer_y = bottom - 30
    fsum = gfx.font("body", 36)
    summary_lines = _wrap_text(loc.get("summary", ""), fsum, text_w) if loc.get("summary") else []
    while len(summary_lines) > 3 and fsum.size > 24:
        fsum = gfx.font("body", fsum.size - 2)
        summary_lines = _wrap_text(loc.get("summary", ""), fsum, text_w)
    sum_lh = _line_height(fsum, 1.32)
    sum_y = footer_y - 30 - len(summary_lines) * sum_lh
    words = gfx.parse_marked(_protected(loc["headline"].upper()))
    # prefere 3 linhas grandes; se não couber, 4 linhas
    fh, hl_lines = gfx.fit_font("display", lambda f: _wrap_words(words, f, text_w - 8), 3, 124, 100, 4)
    if len(hl_lines) > 3:
        fh, hl_lines = gfx.fit_font("display", lambda f: _wrap_words(words, f, text_w - 8), 4, 108, 72, 4)
    line_h = _line_height(fh, 1.16)
    head_y = sum_y - 26 - len(hl_lines) * line_h
    # Never let a long headline consume the photograph or silently lose lines.
    min_pill_y = s_top + 130 + 360 + 60 if layout == "card" else s_top + 350
    while (len(hl_lines) > 4 or head_y - 82 < min_pill_y or
           any(fh.getlength(" ".join(word for word, _ in line)) > text_w - 8 for line in hl_lines)) and fh.size > 52:
        fh = gfx.font("display", fh.size - 2)
        hl_lines = _wrap_words(words, fh, text_w - 8)
        line_h = _line_height(fh, 1.16)
        head_y = sum_y - 26 - len(hl_lines) * line_h
    if len(hl_lines) > 4 or head_y - 82 < min_pill_y or any(fh.getlength(" ".join(word for word, _ in line)) > text_w - 8 for line in hl_lines):
        raise ValueError("Manchete longa demais para manter a capa legível; use um título curto e leve os detalhes aos slides.")
    tag_text, tag_color = _tag_info(post.get("tag", ""), lang)
    if loc.get("selo"):                     # gancho no selo, ex.: "A ROCKSTAR POSTOU" (só se for verdade)
        tag_text = str(loc["selo"]).upper()
    pill_h = 58
    pill_y = head_y - 24 - pill_h

    # ---------- fundo (com recuo automático se o personagem esconder a palavra gigante)
    kicker = loc.get("kicker")
    k_ymin, k_ymax = s_top + 110, pill_y - 40
    subj_src = None
    if layout == "card":
        bg = gfx.cover_fit(src, size, focus).filter(ImageFilter.GaussianBlur(38))
        bg = gfx.vice_grade(bg, 1.0).convert("RGBA")
        bg.alpha_composite(Image.new("RGBA", size, gfx.rgba(pal["night"], 120)))
        zoom = 1.0
    else:
        zooms = [float(post["zoom"])] if post.get("zoom") else [1.0, 0.88, 0.8, 0.72]
        best = None
        for z in zooms:
            raw_z, mask_z = compose_bg(src, full_mask, size, focus, z)
            if not kicker or mask_z is None:
                best = (0, z, raw_z, mask_z)
                break
            *_, cov = _kicker_place(size, kicker, mask_z, k_ymin, k_ymax)
            # o rosto (topo do recorte) precisa ficar acima do bloco de texto
            rows = np.where(np.asarray(mask_z).mean(axis=1) > 6)[0]
            head = (rows[0] + 150 * z) if len(rows) else 0
            score = max(0.0, cov - 0.22) * 3 + max(0.0, head - (pill_y - 120)) / 300 + (1 - z) * 0.4
            if best is None or score < best[0]:
                best = (score, z, raw_z, mask_z)
        _, zoom, raw, mask = best
        bg = gfx.vice_grade(upscale.sharpen(raw), float(post.get("grade", 1.0))).convert("RGBA")
        if mask is None and zoom >= 0.999:
            # sem recorte: só clareia se um ROSTO foi detectado de verdade (cenário/noite fica como está),
            # e só na área do rosto, com borda suave
            face_pt = cut.face_focus(src)
            if face_pt:
                sw, sh = src.size
                sc = max(W / sw, H / sh)
                nw, nh = sw * sc, sh * sc
                left = min(max(focus[0] * nw - W / 2, 0), nw - W)
                top = min(max(focus[1] * nh - H / 2, 0), nh - H)
                cx, cy = face_pt[0] * nw - left, face_pt[1] * nh - top
                r = W * 0.16
                face = Image.new("L", size, 0)
                ImageDraw.Draw(face).ellipse([cx - r, cy - r * 1.3, cx + r, cy + r * 1.3], fill=255)
                lifted = lift_dark_subject(bg, face, whole=True)
                bg = Image.composite(lifted, bg, face.filter(ImageFilter.GaussianBlur(60)))
        subj_src = bg.copy()
        if zoom < 0.999 and mask is not None:
            # personagem vem da foto nítida, sem a mistura com o fundo desfocado
            hz = int(H * zoom)
            sharp = raw.copy()
            sharp.paste(gfx.cover_fit(src, (W, hz), focus), (0, H - hz))
            subj_src = gfx.vice_grade(upscale.sharpen(sharp), float(post.get("grade", 1.0))).convert("RGBA")
    bg.alpha_composite(gfx.vertical_fade(size, pal["night"], 0.0, 0.22, 200, 0))
    bg.alpha_composite(gfx.scanlines(size, 4, 4))
    layers.append(Layer("bg", _finished_bg(bg), "kenburns", 0))

    # ---------- kicker + personagem
    kl = None
    if kicker and layout != "card" and (mask is not None or post.get("kicker_without_cutout")):
        kl, _, _ = kicker_layer(size, kicker, mask, k_ymin, k_ymax)
        layers.append(Layer("kicker", kl, "kicker", 1))
    if mask is not None:
        fin = gfx.look()
        # Alpha não premultiplicado: preserve o RGB e aplique a máscara uma única vez.
        subj = subj_src.convert("RGBA").copy()
        subj.putalpha(mask)
        subj = lift_dark_subject(subj, mask)      # rosto escuro some no feed: clareia só o personagem
        if fin["neon"]:   # visual antigo: contorno rosa em volta do personagem
            glow_l = gfx.glow(mask, "#FF2E88", 26, 1.15, spread=4)
            gmask = np.asarray(glow_l.split()[-1]).astype(np.int16) - np.asarray(mask).astype(np.int16)
            glow_l.putalpha(Image.fromarray(np.clip(gmask, 0, 255).astype(np.uint8)))
            layers.append(Layer("subject_glow", glow_l, "subject", 2))
        elif kl is not None and fin["sombra_personagem"]:
            # sombra do personagem caindo sobre a palavra gigante (só onde há letra)
            sh = gfx.contact_shadow(mask, (16, 20), 20, 0.55)
            k_alpha = np.asarray(kl.split()[-1], dtype=np.float32) / 255.0
            sh.putalpha(Image.fromarray((np.asarray(sh.split()[-1]) * k_alpha).astype(np.uint8)))
            layers.append(Layer("subject_shadow", sh, "subject", 2))
        if fin["light_wrap"] and not fin["neon"]:
            behind = bg.copy()
            if kl is not None:
                behind.alpha_composite(kl)
            subj = gfx.light_wrap(subj, behind, mask, 4, 0.15)
            subj.putalpha(mask)
        layers.append(Layer("subject", subj, "subject", 3))

    if layout == "card":
        card_w = W - s_left - s_right
        ratio = src.height / src.width
        card_h = int(min(card_w * ratio, pill_y - 60 - (s_top + 130)))
        card_w2 = int(card_h / ratio) if card_w * ratio > card_h else card_w
        # Matching the source ratio keeps the full face, hands and scene in view.
        img = upscale.sharpen(src.resize((max(1, card_w2), max(1, card_h)), Image.Resampling.LANCZOS), 40)
        img = gfx.vice_grade(img, 0.6).convert("RGBA")
        cx = s_left + (card_w - card_w2) // 2
        cy = max(s_top + 130, (s_top + 120 + pill_y - 40 - card_h) // 2 + 20)
        rm = gfx.rounded_mask((card_w2, card_h), 30)
        card = _blank(size)
        gm = Image.new("L", size, 0)
        gm.paste(rm, (cx, cy))
        card.alpha_composite(gfx.glow(gm, "#FF2E88", 30, 0.9, spread=3))
        card.paste(img, (cx, cy), rm)
        ring = Image.new("L", size, 0)
        rd = ImageDraw.Draw(ring)
        rd.rounded_rectangle([cx, cy, cx + card_w2 - 1, cy + card_h - 1], radius=30, outline=255, width=5)
        card.alpha_composite(gfx.fill_with(ring, gfx.neon(size, 30)))
        layers.append(Layer("card", card, "subject", 3))

    # escurecimento inferior por cima do personagem (garante leitura da manchete)
    shade_start = max(0.30, (pill_y - 150) / H)
    shade = gfx.vertical_fade(size, pal["night"], shade_start, min(0.98, (head_y + 40) / H), 0, 238)
    shade.alpha_composite(gfx.vertical_fade(size, pal["night"], (bottom - 10) / H, 1.0, 0, 120))
    layers.append(Layer("shade", shade, "fade", 4))

    # ---------- topo
    layers += top_layers(size, lang, s_top, s_top + 4, today)

    # ---------- textos
    pill, _ = tag_pill(size, tag_text, tag_color, s_left, pill_y)
    layers.append(Layer("tag", pill, "pop", 7))
    for i, (ln, hot) in enumerate(headline_lines(size, hl_lines, fh, s_left, head_y, line_h, masks=True)):
        layers.append(Layer(f"headline_{i}", ln, "line", 8 + i, extra={"hot": hot} if hot else {}))
    if summary_lines:
        layers.append(Layer("summary", text_block(size, summary_lines, fsum, s_left, sum_y, sum_lh,
                                                  gfx.rgba(pal["mist"], 245)), "up", 20))
    foot = _blank(size)
    dm = Image.new("L", size, 0)
    ImageDraw.Draw(dm).rectangle([s_left, footer_y - 14, s_left + 70, footer_y - 10], fill=255)
    foot.alpha_composite(gfx.fill_with(dm, gfx.neon(size, 0)))
    foot.alpha_composite(gfx.fill_with(gfx.text_mask(size, (s_left, footer_y), footer_txt, ff, 2),
                                       gfx.rgba("#FFC857", 230)))
    layers.append(Layer("footer", foot, "up", 21))
    fw = gfx.font("heavy", 26)
    handle = brand()["handle"][lang]
    wm = gfx.text_mask(size, ((W - gfx.text_width(handle, fw, 3)) / 2, H - 92), handle, fw, 3)
    frame = corner_brackets(size)
    frame.alpha_composite(gfx.fill_with(wm, gfx.rgba("#FFFFFF", 150)))
    layers.append(Layer("frame", frame, "fade", 30))

    img = compose(layers, size).convert("RGB")
    return Render(img, layers, {"kind": "cover", "focus": focus, "has_cutout": mask is not None, "zoom": zoom,
                                              "headline_size": fh.size, "lines": len(hl_lines)})


# ============================================================ slides extras do carrossel

def _slide_bg(post: dict, base_dir: Path | None, img_ref: str | None = None) -> Image.Image:
    W, H = _canvas()
    pal = brand()["palette"]
    src = load_image(img_ref or post["image"], base_dir)
    bg = gfx.cover_fit(src, (W, H), tuple(post.get("focus") or (0.5, 0.5))).filter(ImageFilter.GaussianBlur(30))
    bg = gfx.vice_grade(bg, 1.0).convert("RGBA")
    bg.alpha_composite(Image.new("RGBA", (W, H), gfx.rgba(pal["night"], 175)))
    bg.alpha_composite(gfx.scanlines((W, H), 6, 4))
    return _finished_bg(bg)


def _slide_title(img: Image.Image, title: str, y: int) -> int:
    lys, y_end = _title_layers(img.size, title, y)
    for L in lys:
        img.alpha_composite(L.image)
    return y_end


def _title_layers(size, title: str, y: int, order: int = 10) -> tuple[list[Layer], int]:
    """Título do slide (Anton, destaque em gradiente), uma camada por linha."""
    W, H = size
    s_top, s_bottom, s_left, s_right = _safe()
    words = gfx.parse_marked(_protected(title.upper()))
    f, lines = gfx.fit_font("display", lambda f: _wrap_words(words, f, W - s_left - s_right - 8), 2, 104, 64, 4)
    lh = _line_height(f, 1.16)
    out = []
    for i, (ln, hot) in enumerate(headline_lines(size, lines, f, s_left, y, lh, masks=True)):
        out.append(Layer(f"title_{i}", ln, "line", order + i, extra={"hot": hot} if hot else {}))
    return out, y + len(lines) * lh


def lift_dark_subject(subj: Image.Image, mask: Image.Image, floor: float = 0.30,
                      target: float = 0.45, whole: bool = False) -> Image.Image:
    """Se a cabeça do recorte (terço de cima) estiver escura demais, clareia só o personagem (curva gama),
    para o rosto não sumir no feed. Personagem bem iluminado passa sem mudança."""
    m = np.asarray(mask, dtype=np.float32) / 255.0
    rows = np.where(m.max(axis=1) > 0.5)[0]
    if not len(rows):
        return subj
    top, bot = int(rows[0]), int(rows[-1])
    band = slice(top, bot + 1) if whole else slice(top, top + max(1, int((bot - top) * 0.35)))
    w = m[band]
    if w.sum() < 2000:
        return subj
    rgb = np.asarray(subj.convert("RGB"), dtype=np.float32)[band] / 255.0
    lum = rgb @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    mean = float((lum * w).sum() / w.sum())
    if mean >= floor:
        return subj
    # ganho de exposição (mantém o preto preto, ao contrário de uma curva gama) com ombro suave nas luzes
    # sem salto no limite: logo abaixo de `floor` o ganho é quase 1; bem escuro vai até `target`
    t_eff = mean + (target - mean) * min(1.0, (floor - mean) / 0.08)
    gain = min(2.2, max(1.0, t_eff / max(mean, 0.05)))
    arr = np.asarray(subj, dtype=np.float32).copy()
    y = arr[..., :3] / 255.0 * gain
    knee = 0.8
    y = np.where(y > knee, knee + (1 - np.exp(-(y - knee) / (1 - knee))) * (1 - knee), y)
    arr[..., :3] = 255.0 * y
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), subj.mode)


def is_official_image(ref: str | None) -> bool:
    """Screenshot/arte oficial da Rockstar (site oficial ou mídia da Rockstar)."""
    ref = (ref or "").lower()
    return "rockstargames.com" in ref or "media-rockstargames-com" in ref


def slide_foto(post: dict, lang: str, img_ref: str | None = None, base_dir: Path | None = None,
               credit: str = "Rockstar Games", with_layers: bool = False, label: str | None = None,
               context: str | None = None):
    """Imagem LIMPA: a foto oficial inteira, sem texto por cima, sem recorte e sem filtro.
    Fundo = a própria foto desfocada; só um selo discreto "IMAGEM OFICIAL" e o crédito."""
    W, H = _canvas()
    size = (W, H)
    s_top, s_bottom, s_left, s_right = _safe()
    src = load_image(img_ref or post["image"], base_dir).convert("RGB")
    src = upscale.ensure_min(src, W, 0)
    bg = gfx.cover_fit(src, (W, H)).filter(ImageFilter.GaussianBlur(48))
    bg = Image.blend(bg, Image.new("RGB", (W, H), gfx.hex_rgb(brand()["palette"]["night"])), 0.55).convert("RGBA")
    fc = gfx.font("bold", 26)
    cred = f"{'Imagem' if lang == 'pt' else 'Image'}: {credit}"
    credit_lines = _wrap_text(cred, fc, W - s_left - s_right - 8)
    credit_lh = _line_height(fc, 1.3)
    context_lines = []
    context_font = gfx.font("heavy", 44)
    if context:
        context_lines = _wrap_text(context, context_font, W - s_left - s_right - 8)
        while len(context_lines) > 3 and context_font.size > 30:
            context_font = gfx.font("heavy", context_font.size - 2)
            context_lines = _wrap_text(context, context_font, W - s_left - s_right - 8)
        if len(context_lines) > 3 or any(gfx.text_width(line, context_font) > W - s_left - s_right - 8 for line in context_lines):
            raise ValueError("Texto da imagem de apoio longo demais; use uma frase curta por cena.")
    context_lh = _line_height(context_font, 1.25)
    context_h = len(context_lines) * context_lh + (36 if context_lines else 0)
    top, bottom = s_top + 140, H - s_bottom
    credit_h = len(credit_lines) * credit_lh
    max_h = max(1, bottom - top - credit_h - 36 - context_h)
    scale = min(W / src.width, max_h / src.height)
    fw, fh = max(1, int(src.width * scale)), max(1, int(src.height * scale))
    fg = upscale.sharpen(src.resize((fw, fh), Image.LANCZOS), 40).convert("RGBA")
    x, y = (W - fw) // 2, top + max(0, (max_h - fh) // 2)
    layers = [Layer("bg", _finished_bg(bg), "kenburns", 0)]
    sm = Image.new("L", (W, H), 0)
    sm.paste(255, (x, y, x + fw, y + fh))
    photo = gfx.drop_shadow(sm, (0, 14), 30, 160)
    photo.alpha_composite(fg, (x, y))
    layers.append(Layer("photo", photo, "photo", 1))
    # selo e crédito discretos, FORA da foto
    label = label or ("IMAGEM OFICIAL" if lang == "pt" else "OFFICIAL IMAGE")
    pill, _ = tag_pill(size, label.upper(), "#22D3EE", s_left, y - 58 - 24)
    layers.append(Layer("tag", pill, "pop", 2))
    layers.append(Layer("credit", text_block(size, credit_lines, fc, s_left, y + fh + 24, credit_lh, gfx.rgba("#E9E3F5", 220)),
                        "up", 3))
    if context_lines:
        layers.append(Layer("visual_context", text_block(size, context_lines, context_font, s_left,
                            y + fh + 24 + credit_h + 36, context_lh, "#FFFFFF"), "up", 4))
    layers.append(Layer("handle", _handle_layer(size, lang), "static", 30))
    img = compose(layers, size).convert("RGB")
    return Render(img, layers, {"kind": "foto"}) if with_layers else img


def _handle_layer(size, lang: str) -> Image.Image:
    W, H = size
    fw2 = gfx.font("heavy", 26)
    handle = brand()["handle"][lang]
    wm = gfx.text_mask(size, ((W - gfx.text_width(handle, fw2, 3)) / 2, H - 92), handle, fw2, 3)
    return gfx.fill_with(wm, gfx.rgba("#FFFFFF", 150))


def slide_grid(post: dict, lang: str, slide: dict, base_dir: Path | None = None, today=None,
               with_layers: bool = False):
    W, H = _canvas()
    size = (W, H)
    s_top, s_bottom, s_left, s_right = _safe()
    layers = [Layer("bg", _slide_bg(post, base_dir, slide.get("background")), "kenburns", 0)]
    layers += top_layers(size, lang, s_top, s_top + 4, today)
    tl, y = _title_layers(size, slide["title"], s_top + 130)
    layers += tl
    y += 40
    items = slide["items"]
    cols = int(slide.get("cols", 3 if len(items) > 4 else 2))
    ratio = float(slide.get("tile_ratio", 1.0))
    gap = 26
    area_w = W - s_left - s_right
    note_h = 90 if slide.get("note") else 0
    avail_h = H - s_bottom - y - note_h
    rows = [items[i:i + cols] for i in range(0, len(items), cols)]
    fl = gfx.font("display", 38 if cols == 3 else 48)
    fs = gfx.font("bold", 25 if cols == 3 else 28)
    tile = (area_w - gap * (cols - 1)) // cols

    def label_height(t):
        hmax = 0
        for row in rows:
            for it in row:
                ll = _wrap_text(it.get("label", "").upper(), fl, t - 8)
                sl = _wrap_text(it.get("sub", ""), fs, t - 8) if it.get("sub") else []
                hmax = max(hmax, 14 + len(ll) * _line_height(fl, 1.16) + (8 + len(sl) * _line_height(fs) if sl else 0))
        return hmax

    inside = cols == 1 or bool(slide.get("label_inside"))
    if inside:
        # imagens largas com legenda sobreposta (bom para screenshots 16:9)
        th = min(int(tile * ratio), (avail_h - (len(rows) - 1) * 26) // len(rows))
        lab_h = 0
        fl = gfx.font("display", 52)
        fs = gfx.font("bold", 28)
    else:
        # reduz o tile até a grade caber na altura disponível
        while tile > 160:
            total = len(rows) * (int(tile * ratio) + label_height(tile)) + (len(rows) - 1) * 30
            if total <= avail_h:
                break
            tile -= 8
        lab_h = label_height(tile)
        th = int(tile * ratio)
    grid_w = cols * tile + (cols - 1) * gap
    x0 = s_left + (area_w - grid_w) // 2
    k = 0
    for r, row in enumerate(rows):
        for c, it in enumerate(row):
            x = x0 + c * (tile + gap)
            cell = _blank(size)
            pic = upscale.sharpen(gfx.cover_fit(load_image(it["image"], base_dir), (tile, th)), 50).convert("RGBA")
            if inside:
                pic.alpha_composite(gfx.vertical_fade((tile, th), "#0B0614", 0.35, 1.0, 0, 230))
            rm = gfx.rounded_mask((tile, th), 22)
            gm = Image.new("L", (W, H), 0)
            gm.paste(rm, (x, y))
            cell.alpha_composite(gfx.glow(gm, "#FF2E88", 18, 0.6, spread=2))
            cell.paste(pic, (x, y), rm)
            ring = Image.new("L", (W, H), 0)
            ImageDraw.Draw(ring).rounded_rectangle([x, y, x + tile - 1, y + th - 1], radius=22, outline=255, width=3)
            cell.alpha_composite(gfx.fill_with(ring, gfx.neon((W, H), 45)))
            if inside:
                label_lines = _wrap_text(it.get("label", "").upper(), fl, tile - 60)
                sub_lines = _wrap_text(it.get("sub", ""), fs, tile - 60) if it.get("sub") else []
                label_h = len(label_lines) * _line_height(fl, 1.16)
                sub_h = len(sub_lines) * _line_height(fs) + (8 if sub_lines else 0)
                ty = y + th - 26 - sub_h - label_h
                cell.alpha_composite(text_block(size, label_lines, fl, x + 26, ty, _line_height(fl, 1.16), "#FFFFFF"))
                if it.get("sub"):
                    cell.alpha_composite(text_block(size, sub_lines, fs, x + 26, ty + label_h + 8, _line_height(fs),
                                                    gfx.rgba("#FFC857", 245)))
            else:
                ty = y + th + 14
                for ln in _wrap_text(it.get("label", "").upper(), fl, tile - 8):
                    cell.alpha_composite(text_block(size, [ln], fl, x, ty, 0, "#FFFFFF"))
                    ty += _line_height(fl, 1.16)
                if it.get("sub"):
                    sl = _wrap_text(it["sub"], fs, tile - 8)
                    cell.alpha_composite(text_block(size, sl, fs, x, ty + 8, _line_height(fs),
                                                    gfx.rgba("#FFC857", 240)))
            k += 1
            layers.append(Layer(f"tile_{k}", cell, "pop", 30 + k, step=k))
        y += th + lab_h + (26 if inside else 30)
    if slide.get("note"):
        fn = gfx.font("body", 30)
        nl = _wrap_text(slide["note"], fn, area_w - 8)
        ny = min(y + 6, H - s_bottom - len(nl) * 40)
        layers.append(Layer("note", text_block(size, nl, fn, s_left, ny, 40, gfx.rgba("#E9E3F5", 235)), "up", 80))
    layers.append(Layer("frame", corner_brackets(size), "static", 90))
    img = compose(layers, size).convert("RGB")
    return Render(img, layers, {"kind": "grid", "steps": k}) if with_layers else img


def slide_list(post: dict, lang: str, slide: dict, base_dir: Path | None = None, today=None,
               upto: int | None = None, with_layers: bool = False):
    """Slide de lista. `upto` desenha só os primeiros itens (o layout é o da lista inteira, então os itens
    não mudam de lugar): é o que o vídeo clássico usa para os itens aparecerem um a um."""
    W, H = _canvas()
    size = (W, H)
    s_top, s_bottom, s_left, s_right = _safe()
    layers = [Layer("bg", _slide_bg(post, base_dir, slide.get("background")), "kenburns", 0)]
    layers += top_layers(size, lang, s_top, s_top + 4, today)
    tl, y = _title_layers(size, slide["title"], s_top + 140)
    layers += tl
    y += 50
    area_w = W - s_left - s_right - 96
    items = slide["items"]
    fsz = 52 if len(items) <= 4 else 42
    while True:
        f = gfx.font("bold", fsz)
        blocks = [_wrap_text(t, f, area_w - 8) for t in items]
        total = sum(len(b) * _line_height(f) + 48 for b in blocks)
        if y + total <= H - s_bottom or fsz <= 28:
            break
        fsz -= 2
    y += max(0, int((H - s_bottom - y - total) * 0.3))
    fn = gfx.font("display", 48)
    lh = _line_height(f)
    for i, block in enumerate(blocks, 1):
        if upto is not None and i > upto:
            break
        badge = _blank((72, 72))
        badge.paste(gfx.sunset((72, 72), 135), (0, 0), gfx.rounded_mask((72, 72), 18))
        num = str(i)
        ImageDraw.Draw(badge).text(((72 - fn.getlength(num)) / 2, 2), num, font=fn, fill=gfx.rgba("#0B0614"))
        bl = _blank(size)
        bl.alpha_composite(badge, (s_left, y - 4))
        layers.append(Layer(f"badge_{i}", bl, "pop", 30 + 2 * i, step=i))
        layers.append(Layer(f"item_{i}", text_block(size, block, f, s_left + 96, y, lh, "#FFFFFF"),
                            "slide", 31 + 2 * i, step=i))
        y += len(block) * lh + 48
    layers.append(Layer("frame", corner_brackets(size), "static", 90))
    img = compose(layers, size).convert("RGB")
    return Render(img, layers, {"kind": "list", "steps": len(blocks)}) if with_layers else img


def slide_cta(post: dict, lang: str, base_dir: Path | None = None, today=None, with_layers: bool = False):
    W, H = _canvas()
    size = (W, H)
    s_top, s_bottom, s_left, s_right = _safe()
    text_w = W - s_left - s_right - 8
    center_x = s_left + text_w / 2
    ui = UI[lang]
    b = brand()
    layers = [Layer("bg", _slide_bg(post, base_dir), "kenburns", 0),
              Layer("countdown", countdown_chip(size, lang, s_top + 4, today), "pop", 6)]
    if _logo_cfg()["versao"] == "v2":
        # logo grande: sol de Vice + LEONIDA WIRE (a mesma marca do topo)
        d = 250
        emblem = _custom_logo(d) or _vice_sun(d)
        el = _blank(size)
        em = Image.new("L", size, 0)
        ex, ey = (W - d) // 2, 330
        em.paste(emblem.split()[-1], (ex, ey))
        el.alpha_composite(gfx.glow(em, "#FF2E88", 40, 0.55))
        el.alpha_composite(gfx.drop_shadow(em, (0, 14), 26, 170))
        el.alpha_composite(emblem, (ex, ey))
        layers.append(Layer("emblem", el, "pop", 9))
        words = b["name"].split()
        first, rest = words[0], " ".join(words[1:])
        fw = gfx.font("display", 112)
        while gfx.text_width(first, fw, 3) + fw.getlength(" ") * 0.9 + gfx.text_width(rest, fw, 3) > text_w and fw.size > 60:
            fw = gfx.font("display", fw.size - 2)
        sp = fw.getlength(" ") * 0.9
        w1, w2 = gfx.text_width(first, fw, 3), gfx.text_width(rest, fw, 3) if rest else 0
        x0, wy = center_x - (w1 + (sp + w2 if rest else 0)) / 2, ey + d + 34
        m1 = gfx.text_mask(size, (x0, wy), first, fw, 3)
        m2 = gfx.text_mask(size, (x0 + w1 + sp, wy), rest, fw, 3) if rest else Image.new("L", size, 0)
        wl = _blank(size)
        wl.alpha_composite(gfx.drop_shadow(Image.fromarray(np.maximum(np.asarray(m1), np.asarray(m2))), (0, 6), 12, 180))
        wl.alpha_composite(gfx.fill_with(m1, "#FFFFFF"))
        if rest:
            band = gfx.linear_gradient((W, 140), [(0.0, "#FFD27A"), (0.5, "#FF8A3D"), (1.0, "#FF2E88")], 90)
            grad = _blank(size)
            grad.paste(band, (0, wy + 10))
            wl.alpha_composite(gfx.fill_with(m2, grad))
        layers.append(Layer("wordmark", wl, "line", 10))
    else:
        fs = gfx.font("script", 150)
        name = b["name"].title()
        while fs.getlength(name) > text_w and fs.size > 60:
            fs = gfx.font("script", fs.size - 2)
        m = gfx.text_mask(size, (center_x - fs.getlength(name) / 2, 520), name, fs)
        sig = gfx.glow(m, "#FF2E88", 30, 1.0)
        sig.alpha_composite(gfx.fill_with(m, gfx.sunset(size, 90)))
        layers.append(Layer("signature", sig, "wipe", 10))
    fh = gfx.font("display", 84)
    hl = _wrap_text(ui["follow"], fh, text_w)
    y = 800
    for i, ln in enumerate(hl):
        x = center_x - fh.getlength(ln) / 2
        layers.append(Layer(f"follow_{i}", text_block(size, [ln], fh, int(x), y, 0, "#FFFFFF"), "line", 11 + i))
        y += _line_height(fh, 1.16)
    f2 = gfx.font("display", 70)
    handle = b["handle"][lang]
    while f2.getlength(handle) > text_w and f2.size > 28:
        f2 = gfx.font("display", f2.size - 2)
    hm = gfx.text_mask(size, (center_x - f2.getlength(handle) / 2, y + 40), handle, f2)
    hlayer = gfx.glow(hm, "#22D3EE", 20, 0.8)
    hlayer.alpha_composite(gfx.fill_with(hm, "#22D3EE"))
    layers.append(Layer("cta_handle", hlayer, "pop", 20))
    fb = gfx.font("body", 36)
    sub = ui["follow_sub"]
    sub_layer = _blank(size)
    for i, ln in enumerate(_wrap_text(sub, fb, text_w)):
        sub_layer.alpha_composite(text_block(size, [ln], fb, int(center_x - fb.getlength(ln) / 2),
                                             y + 150 + i * _line_height(fb), 0, gfx.rgba("#E9E3F5", 240)))
    layers.append(Layer("sub", sub_layer, "up", 21))
    fsv = gfx.font("heavy", 30)
    sv = ui["save"]
    layers.append(Layer("save", text_block(size, [sv], fsv, int(center_x - gfx.text_width(sv, fsv) / 2), y + 240, 0,
                                           gfx.rgba("#FFC857", 240)), "up", 22))
    layers.append(Layer("frame", corner_brackets(size), "static", 90))
    img = compose(layers, size).convert("RGB")
    return Render(img, layers, {"kind": "cta"}) if with_layers else img
