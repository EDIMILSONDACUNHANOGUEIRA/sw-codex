"""Cortes 9:16 de vídeos (trailers, gameplay, vídeos virais) no estilo da marca.

- Download: yt-dlp (https://github.com/yt-dlp/yt-dlp) — YouTube, X/Twitter, Reddit, TikTok etc.
- Montagem: FFmpeg — fundo desfocado + vídeo centralizado + moldura com manchete/selo/fonte.
- Legenda automática (opcional): faster-whisper (https://github.com/SYSTRAN/faster-whisper).

Use só trechos curtos, sempre com crédito e com comentário/edição própria (uso transformativo).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from . import gfx, render
from .config import CACHE_DIR, FONTS_DIR, OUT_DIR, brand

W, H = 1080, 1920
VIDEO_TOP = 640          # topo da janela do vídeo (16:9 -> 1080x608)


def _ts(t: str | float) -> float:
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(p) for p in str(t).split(":")]
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return sec


def download(url: str) -> Path:
    """Baixa o vídeo (melhor MP4 até 1080p) para o cache."""
    key = hashlib.sha1(url.encode()).hexdigest()[:14]
    out_dir = CACHE_DIR / "videos"
    out_dir.mkdir(parents=True, exist_ok=True)
    found = list(out_dir.glob(f"{key}.*"))
    if found:
        return found[0]
    import os
    import yt_dlp
    opts = {
        "outtmpl": str(out_dir / f"{key}.%(ext)s"),
        "format": "bv*[height<=1440]+ba/b[height<=1440]/bv*+ba/b",
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
        # o YouTube exige um runtime de JavaScript: usa Deno ou o Node.js (já instalado p/ o HyperFrames)
        "js_runtimes": {"deno": {}, "node": {}},
    }
    # YouTube às vezes pede login: LEONIDA_YTDLP_BROWSER=chrome (ou firefox/edge) usa os cookies do navegador
    if os.environ.get("LEONIDA_YTDLP_BROWSER"):
        opts["cookiesfrombrowser"] = (os.environ["LEONIDA_YTDLP_BROWSER"],)
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    found = list(out_dir.glob(f"{key}.*"))
    if not found:
        raise RuntimeError("download falhou")
    return found[0]


def overlay(lang: str, headline: str, tag: str, source: str, date: str | None = None,
            video_h: int = 608) -> tuple[Image.Image, int]:
    """Moldura transparente: marca, contador, selo, manchete (acima do vídeo) e fonte (abaixo).

    Retorna (imagem, y do topo da janela de vídeo)."""
    size = (W, H)
    s_top, s_bottom, s_left, s_right = render._safe()
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    words = gfx.parse_marked(headline)
    text_w = W - s_left - s_right
    fh, lines = gfx.fit_font("display", lambda f: gfx.wrap_words(words, f, text_w), 3, 96, 60, 4)
    lh = int(fh.size * 1.06)
    pill_y = s_top + 118
    head_y = pill_y + 58 + 22
    video_top = max(VIDEO_TOP, head_y + len(lines) * lh + 36)
    # escurece o fundo desfocado atrás dos textos
    pal = brand()["palette"]
    dark = gfx.vertical_fade(size, pal["night"], 0.0, video_top / H, 215, 150)
    dark.alpha_composite(gfx.vertical_fade(size, pal["night"], (video_top + video_h) / H, 1.0, 0, 90))
    dark.paste((0, 0, 0, 0), (0, video_top, W, video_top + video_h))   # janela do vídeo fica limpa
    img.alpha_composite(dark)
    img.alpha_composite(render.brand_bar(size, lang, s_top))
    img.alpha_composite(render.countdown_chip(size, lang, s_top + 4))
    tag_text, tag_color = render._tag_info(tag, lang)
    pill, ph = render.tag_pill(size, tag_text, tag_color, s_left, pill_y)
    img.alpha_composite(pill)
    for ln in render.headline_lines(size, lines, fh, s_left, head_y, lh):
        img.alpha_composite(ln)
    # moldura neon da janela de vídeo
    ring = Image.new("L", size, 0)
    ImageDraw.Draw(ring).rectangle([0, video_top - 3, W - 1, video_top + video_h + 2], outline=255, width=4)
    img.alpha_composite(gfx.glow(ring, "#FF2E88", 16, 0.9))
    img.alpha_composite(gfx.fill_with(ring, gfx.neon(size, 0)))
    ff = gfx.font("bold", 26)
    ui = render.UI[lang]
    foot = f"{ui['source']}: {source.upper()}  •  {render.fmt_date(date, lang)}" if source else render.fmt_date(date, lang)
    img.alpha_composite(render.text_block(size, [foot], ff, s_left, video_top + video_h + 26, 0,
                                          gfx.rgba("#FFC857", 235)))
    img.alpha_composite(render.corner_brackets(size))
    fw = gfx.font("heavy", 26)
    handle = brand()["handle"][lang]
    wm = gfx.text_mask(size, ((W - gfx.text_width(handle, fw, 3)) / 2, H - 92), handle, fw, 3)
    img.alpha_composite(gfx.fill_with(wm, gfx.rgba("#FFFFFF", 150)))
    return img, video_top


def _ass_time(t: float) -> str:
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def transcribe_ass(media_path: Path, lang: str, out: Path, y: int) -> Path | None:
    """Legenda palavra-a-palavra em .ass (estilo TikTok). Requer faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except Exception:
        print("  [cortes] faster-whisper não instalado — sem legenda automática")
        return None
    model = WhisperModel("small", device="auto", compute_type="int8")
    segs, _ = model.transcribe(str(media_path), language=lang[:2] if lang else None, word_timestamps=True)
    words = [w for s in segs for w in (s.words or [])]
    if not words:
        return None
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Anton,86,&H00FFFFFF,&H0057C8FF,&H00140B0B,&H64000000,0,0,0,0,100,100,1,0,1,6,2,2,60,60,{H - y},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    chunk: list = []
    for w in words + [None]:
        if w is not None:
            chunk.append(w)
        if chunk and (w is None or len(chunk) == 3 or w.word.strip().endswith((".", "?", "!", ","))):
            end = chunk[-1].end
            for i, cw in enumerate(chunk):
                parts = []
                for j, x in enumerate(chunk):
                    t = x.word.strip().upper().replace("{", "").replace("}", "")
                    parts.append("{\\c&H3D8AFF&}" + t + "{\\c&HFFFFFF&}" if j == i else t)
                ws = cw.start
                we = chunk[i + 1].start if i + 1 < len(chunk) else end
                lines.append(f"Dialogue: 0,{_ass_time(ws)},{_ass_time(we)},Cap,,0,0,0,,{' '.join(parts)}")
            chunk = []
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out


def make_clip(src: str, start: str | float, end: str | float, *, headline: dict, tag: str = "viral",
              source: str = "", date: str | None = None, langs=("pt", "en"), subtitles: bool = False,
              name: str | None = None, music_on: bool = True, log=print) -> Path:
    """Gera prontos/<data>/<nome>/{br,us}/corte.mp4 + legenda."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    path = Path(src) if Path(src).exists() else download(src)
    t0, t1 = _ts(start), _ts(end)
    if t1 <= t0:
        raise ValueError("fim precisa ser depois do início")
    date = date or dt.date.today().isoformat()
    name = name or f"{date}-corte-{re.sub(r'[^a-z0-9]+', '-', headline.get('en', 'clip').lower())[:40].strip('-')}"
    out_root = OUT_DIR / date / name
    work = CACHE_DIR / "clips" / name
    work.mkdir(parents=True, exist_ok=True)
    # trecho bruto (para transcrição)
    raw = work / "raw.mp4"
    subprocess.run([ff, "-y", "-ss", str(t0), "-to", str(t1), "-i", str(path), "-c:v", "libx264", "-preset",
                    "veryfast", "-crf", "18", "-c:a", "aac", "-b:a", "192k", str(raw)], check=True,
                   capture_output=True)
    files = {}
    for lang in langs:
        folder = out_root / ("br" if lang == "pt" else "us")
        folder.mkdir(parents=True, exist_ok=True)
        ov, video_top = overlay(lang, headline[lang], tag, source, date)
        ov_path = work / f"overlay_{lang}.png"
        ov.save(ov_path)
        vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=28:2,"
              f"eq=brightness=-0.12:saturation=1.25[bg];"
              f"[0:v]scale={W}:608:force_original_aspect_ratio=decrease:flags=lanczos,unsharp=5:5:0.5,"
              f"pad={W}:608:(ow-iw)/2:(oh-ih)/2:color=black@0[fg];"
              f"[bg][fg]overlay=0:{video_top}[base];"
              f"[base][1:v]overlay=0:0[v0]")
        last = "v0"
        if subtitles:
            ass = transcribe_ass(raw, lang if lang == "en" else "pt", work / f"subs_{lang}.ass",
                                 video_top + 608 + 230)
            if ass:
                vf += f";[v0]subtitles={ass.as_posix()}:fontsdir={FONTS_DIR.as_posix()}[v1]"
                last = "v1"
        out = folder / ("corte.mp4" if lang == "pt" else "clip.mp4")
        log(f"  [cortes] {lang} -> {out}")
        subprocess.run([ff, "-y", "-i", str(raw), "-loop", "1", "-i", str(ov_path), "-filter_complex", vf,
                        "-map", f"[{last}]", "-map", "0:a?", "-shortest", "-c:v", "libx264", "-preset", "slow",
                        "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags",
                        "+faststart", str(out)], check=True, capture_output=True)
        if music_on:
            from . import music
            music.apply(out)
        cap_name = "legenda.txt" if lang == "pt" else "caption.txt"
        base_tags = " ".join(brand()["hashtags"][lang])
        credit = ("Fonte: " if lang == "pt" else "Source: ") + source if source else ""
        (folder / cap_name).write_text(f"{headline[lang].replace('*', '')}\n\n{credit}\n\n{base_tags}\n",
                                       encoding="utf-8")
        files[lang] = str(out)
    (out_root / "post.json").write_text(json.dumps({"id": name, "type": "clip", "date": date, "src": src,
                                                    "start": t0, "end": t1, "files": files}, indent=2))
    return out_root
