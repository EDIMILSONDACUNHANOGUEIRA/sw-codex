"""Renderização das artes 9:16 no estilo LEONIDA WIRE.

Capa (cover):
  fundo com color grading "Vice" -> palavra gigante (kicker) -> personagem recortado na frente
  -> escurecimento inferior -> selo + manchete com destaque em gradiente -> resumo -> fonte.
  Topo: marca + contador de dias para o lançamento. Cantos em estilo "mira" neon.

Cada elemento é guardado também como camada RGBA separada, usada pelo vídeo animado (HyperFrames).
"""
from __future__ import annotations

import datetime as dt
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

def brand_bar(size, lang: str, y: int) -> Image.Image:
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
    right = W - 64
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


def headline_lines(size, words_lines, fnt, x: int, y: int, line_h: int) -> list[Image.Image]:
    """Uma camada por linha; palavras marcadas com *...* recebem o gradiente pôr-do-sol."""
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
        out.append(layer)
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
        focus = (focus[0], 0.5)
    focus = tuple(focus)

    # ---------- bloco inferior (calculado de baixo p/ cima)
    text_w = W - s_left - s_right
    bottom = H - s_bottom
    ui = UI[lang]
    src_name = (post.get("source") or {}).get("name", "")
    footer_txt = f"{ui['source']}: {src_name.upper()}  •  {fmt_date(post.get('date'), lang)}" if src_name \
        else fmt_date(post.get("date"), lang)
    ff = gfx.font("bold", 24)
    footer_y = bottom - 30
    fsum = gfx.font("body", 36)
    summary_lines = gfx.wrap_text(loc.get("summary", ""), fsum, text_w) if loc.get("summary") else []
    if len(summary_lines) > 2:
        fsum = gfx.font("body", 32)
        summary_lines = gfx.wrap_text(loc.get("summary", ""), fsum, text_w)[:3]
    sum_lh = int(fsum.size * 1.32)
    sum_y = footer_y - 30 - len(summary_lines) * sum_lh
    words = gfx.parse_marked(loc["headline"])
    # prefere 3 linhas grandes; se não couber, 4 linhas
    fh, hl_lines = gfx.fit_font("display", lambda f: gfx.wrap_words(words, f, text_w), 3, 124, 100, 4)
    if len(hl_lines) > 3:
        fh, hl_lines = gfx.fit_font("display", lambda f: gfx.wrap_words(words, f, text_w), 4, 108, 72, 4)
    line_h = int(fh.size * 1.06)
    head_y = sum_y - 26 - len(hl_lines) * line_h
    tag_text, tag_color = _tag_info(post.get("tag", ""), lang)
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
        subj_src = bg
        if zoom < 0.999 and mask is not None:
            # personagem vem da foto nítida, sem a mistura com o fundo desfocado
            hz = int(H * zoom)
            sharp = raw.copy()
            sharp.paste(gfx.cover_fit(src, (W, hz), focus), (0, H - hz))
            subj_src = gfx.vice_grade(upscale.sharpen(sharp), float(post.get("grade", 1.0))).convert("RGBA")
    bg.alpha_composite(gfx.vertical_fade(size, pal["night"], 0.0, 0.22, 200, 0))
    bg.alpha_composite(gfx.scanlines(size, 4, 4))
    layers.append(Layer("bg", bg, "kenburns", 0))

    # ---------- kicker + personagem
    kl = None
    if kicker and layout != "card" and (mask is not None or post.get("kicker_without_cutout")):
        kl, _, _ = kicker_layer(size, kicker, mask, k_ymin, k_ymax)
        layers.append(Layer("kicker", kl, "kicker", 1))
    if mask is not None:
        fin = gfx.look()
        subj = _blank(size)
        subj.paste(subj_src, (0, 0), mask)
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
            subj = gfx.light_wrap(subj, behind, mask, 8, 0.35)
            subj.putalpha(mask)
        layers.append(Layer("subject", subj, "subject", 3))

    if layout == "card":
        card_w = W - 2 * s_left
        ratio = src.height / src.width
        card_h = int(min(card_w * ratio, pill_y - 60 - (s_top + 130)))
        card_w2 = int(card_h / ratio) if card_w * ratio > card_h else card_w
        img = upscale.sharpen(gfx.cover_fit(src, (card_w2, card_h), focus), 70)
        img = gfx.vice_grade(img, 0.6).convert("RGBA")
        cx = (W - card_w2) // 2
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
    layers.append(Layer("brand", brand_bar(size, lang, s_top), "down", 5))
    layers.append(Layer("countdown", countdown_chip(size, lang, s_top + 4, today), "pop", 6))

    # ---------- textos
    pill, _ = tag_pill(size, tag_text, tag_color, s_left, pill_y)
    layers.append(Layer("tag", pill, "pop", 7))
    for i, ln in enumerate(headline_lines(size, hl_lines, fh, s_left, head_y, line_h)):
        layers.append(Layer(f"headline_{i}", ln, "line", 8 + i))
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

    img = _blank(size)
    for ly in sorted(layers, key=lambda L: L.order):
        img.alpha_composite(ly.image)
    return Render(gfx.finish(img.convert("RGB")), layers, {"focus": focus, "has_cutout": mask is not None, "zoom": zoom,
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
    return bg


def _slide_title(img: Image.Image, title: str, y: int) -> int:
    W, H = img.size
    s_top, s_bottom, s_left, s_right = _safe()
    words = gfx.parse_marked(title)
    f, lines = gfx.fit_font("display", lambda f: gfx.wrap_words(words, f, W - s_left - s_right), 2, 104, 64, 4)
    lh = int(f.size * 1.06)
    for ln in headline_lines(img.size, lines, f, s_left, y, lh):
        img.alpha_composite(ln)
    return y + len(lines) * lh


def slide_grid(post: dict, lang: str, slide: dict, base_dir: Path | None = None, today=None) -> Image.Image:
    W, H = _canvas()
    s_top, s_bottom, s_left, s_right = _safe()
    img = _slide_bg(post, base_dir, slide.get("background"))
    img.alpha_composite(brand_bar((W, H), lang, s_top - 20))
    img.alpha_composite(countdown_chip((W, H), lang, s_top - 16, today))
    y = _slide_title(img, slide["title"], s_top + 130) + 40
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
                ll = gfx.wrap_text(it.get("label", "").upper(), fl, t)
                sl = gfx.wrap_text(it.get("sub", ""), fs, t) if it.get("sub") else []
                hmax = max(hmax, 14 + len(ll) * int(fl.size * 1.08) + (8 + len(sl) * int(fs.size * 1.3) if sl else 0))
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
    for r, row in enumerate(rows):
        for c, it in enumerate(row):
            x = x0 + c * (tile + gap)
            pic = upscale.sharpen(gfx.cover_fit(load_image(it["image"], base_dir), (tile, th)), 50).convert("RGBA")
            if inside:
                pic.alpha_composite(gfx.vertical_fade((tile, th), "#0B0614", 0.35, 1.0, 0, 230))
            rm = gfx.rounded_mask((tile, th), 22)
            gm = Image.new("L", (W, H), 0)
            gm.paste(rm, (x, y))
            img.alpha_composite(gfx.glow(gm, "#FF2E88", 18, 0.6, spread=2))
            img.paste(pic, (x, y), rm)
            ring = Image.new("L", (W, H), 0)
            ImageDraw.Draw(ring).rounded_rectangle([x, y, x + tile - 1, y + th - 1], radius=22, outline=255, width=3)
            img.alpha_composite(gfx.fill_with(ring, gfx.neon((W, H), 45)))
            if inside:
                sub_h = int(fs.size * 1.4) if it.get("sub") else 0
                ty = y + th - 26 - sub_h - int(fl.size * 1.25)
                img.alpha_composite(text_block((W, H), [it.get("label", "").upper()], fl, x + 26, ty, 0, "#FFFFFF"))
                if it.get("sub"):
                    img.alpha_composite(text_block((W, H), [it["sub"]], fs, x + 26, ty + int(fl.size * 1.28), 0,
                                                   gfx.rgba("#FFC857", 245)))
                continue
            ty = y + th + 14
            for ln in gfx.wrap_text(it.get("label", "").upper(), fl, tile):
                img.alpha_composite(text_block((W, H), [ln], fl, x, ty, 0, "#FFFFFF"))
                ty += int(fl.size * 1.08)
            if it.get("sub"):
                sl = gfx.wrap_text(it["sub"], fs, tile)
                img.alpha_composite(text_block((W, H), sl, fs, x, ty + 8, int(fs.size * 1.3),
                                               gfx.rgba("#FFC857", 240)))
        y += th + lab_h + (26 if inside else 30)
    if slide.get("note"):
        fn = gfx.font("body", 30)
        nl = gfx.wrap_text(slide["note"], fn, area_w)
        ny = min(y + 6, H - s_bottom - len(nl) * 40)
        img.alpha_composite(text_block((W, H), nl, fn, s_left, ny, 40, gfx.rgba("#E9E3F5", 235)))
    img.alpha_composite(corner_brackets((W, H)))
    return img.convert("RGB")


def slide_list(post: dict, lang: str, slide: dict, base_dir: Path | None = None, today=None) -> Image.Image:
    W, H = _canvas()
    s_top, s_bottom, s_left, s_right = _safe()
    img = _slide_bg(post, base_dir, slide.get("background"))
    img.alpha_composite(brand_bar((W, H), lang, s_top - 20))
    img.alpha_composite(countdown_chip((W, H), lang, s_top - 16, today))
    y = _slide_title(img, slide["title"], s_top + 140) + 50
    area_w = W - s_left - s_right - 96
    items = slide["items"]
    fsz = 52 if len(items) <= 4 else 42
    while True:
        f = gfx.font("bold", fsz)
        blocks = [gfx.wrap_text(t, f, area_w) for t in items]
        total = sum(len(b) * int(fsz * 1.3) + 48 for b in blocks)
        if y + total <= H - s_bottom or fsz <= 28:
            break
        fsz -= 2
    y += max(0, int((H - s_bottom - y - total) * 0.3))
    fn = gfx.font("display", 48)
    lh = int(fsz * 1.3)
    for i, block in enumerate(blocks, 1):
        badge = _blank((72, 72))
        badge.paste(gfx.sunset((72, 72), 135), (0, 0), gfx.rounded_mask((72, 72), 18))
        num = str(i)
        ImageDraw.Draw(badge).text(((72 - fn.getlength(num)) / 2, 2), num, font=fn, fill=gfx.rgba("#0B0614"))
        img.alpha_composite(badge, (s_left, y - 4))
        img.alpha_composite(text_block((W, H), block, f, s_left + 96, y, lh, "#FFFFFF"))
        y += len(block) * lh + 48
    img.alpha_composite(corner_brackets((W, H)))
    return img.convert("RGB")


def slide_cta(post: dict, lang: str, base_dir: Path | None = None, today=None) -> Image.Image:
    W, H = _canvas()
    s_top, s_bottom, s_left, s_right = _safe()
    ui = UI[lang]
    b = brand()
    img = _slide_bg(post, base_dir)
    img.alpha_composite(countdown_chip((W, H), lang, s_top - 16, today))
    fs = gfx.font("script", 150)
    name = b["name"].title()
    m = gfx.text_mask((W, H), ((W - fs.getlength(name)) / 2, 520), name, fs)
    img.alpha_composite(gfx.glow(m, "#FF2E88", 30, 1.0))
    img.alpha_composite(gfx.fill_with(m, gfx.sunset((W, H), 90)))
    fh = gfx.font("display", 84)
    hl = gfx.wrap_text(ui["follow"], fh, W - 2 * s_left - 40)
    y = 800
    for ln in hl:
        x = (W - fh.getlength(ln)) / 2
        img.alpha_composite(text_block((W, H), [ln], fh, int(x), y, 0, "#FFFFFF"))
        y += int(fh.size * 1.08)
    f2 = gfx.font("display", 70)
    handle = b["handle"][lang]
    hm = gfx.text_mask((W, H), ((W - f2.getlength(handle)) / 2, y + 40), handle, f2)
    img.alpha_composite(gfx.glow(hm, "#22D3EE", 20, 0.8))
    img.alpha_composite(gfx.fill_with(hm, "#22D3EE"))
    fb = gfx.font("body", 36)
    sub = ui["follow_sub"]
    img.alpha_composite(text_block((W, H), [sub], fb, int((W - fb.getlength(sub)) / 2), y + 150, 0,
                                   gfx.rgba("#E9E3F5", 240)))
    fsv = gfx.font("heavy", 30)
    sv = ui["save"]
    img.alpha_composite(text_block((W, H), [sv], fsv, int((W - gfx.text_width(sv, fsv)) / 2), y + 240, 0,
                                   gfx.rgba("#FFC857", 240)))
    img.alpha_composite(corner_brackets((W, H)))
    return img.convert("RGB")
