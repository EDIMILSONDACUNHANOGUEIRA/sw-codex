"""Editor de vídeo: link (ou arquivo) -> edição 9:16 pronta para o TikTok.

O que ele faz, no estilo dos presets de câmera do Higgsfield, mas sobre o vídeo real:
  1. baixa o vídeo (yt-dlp) e acha os cortes de cena (FFmpeg, detecção de cena);
  2. escolhe os trechos no ritmo do estilo (hype, cinema, noticia) até a duração pedida;
  3. reenquadra cada trecho em 9:16 no personagem (recorte rembg, o mesmo das capas);
  4. aplica um movimento de câmera por trecho (dolly in/out, crash zoom, snap zoom, travelling,
     tilt, câmera na mão, dutch, impacto, câmera lenta) e uma transição em cada corte (whip pan,
     zoom-through, flash ou corte seco);
  5. renderiza no HyperFrames (HTML + GSAP -> MP4, determinístico);
  6. passa o acabamento no FFmpeg: grade de cor, grão de filme, moldura da marca com manchete
     (BR e US), legenda automática (opcional) e música tema por baixo do áudio original.

Motor principal: HyperFrames (https://github.com/heygen-com/hyperframes, Apache-2.0).
Sem Node/Chrome, cai para um motor FFmpeg mais simples (só zoom/travelling e cortes secos).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw

from . import clips, gfx, render
from .config import CACHE_DIR, FONTS_DIR, HF_DIR, OUT_DIR, brand

W, H = 1080, 1920
FPS = 30
HF_VERSION = os.environ.get("HYPERFRAMES_VERSION", "0.8.141")

# ------------------------------------------------------------------ estilos

STYLES = {
    # ritmo de TikTok: cortes curtos, câmera sempre viva, transições marcadas
    "hype": {"shot": (0.9, 1.7), "moves": ["snap_zoom", "handheld", "crash_zoom", "push_in", "truck_left",
                                            "impact", "dutch", "slowmo", "truck_right", "pull_out"],
             "transitions": ["whip", "flash", "zoom", "corte", "whip", "corte"]},
    # trailer: planos longos, movimentos lentos, cortes secos
    "cinema": {"shot": (2.4, 3.6), "moves": ["push_in", "pull_out", "truck_left", "tilt_up", "push_in",
                                              "truck_right"],
               "transitions": ["corte", "corte", "flash", "corte"]},
    # notícia: ritmo médio, movimentos discretos, a manchete é a estrela
    "noticia": {"shot": (1.8, 2.8), "moves": ["push_in", "truck_left", "pull_out", "handheld", "truck_right"],
                "transitions": ["corte", "whip", "corte", "flash"]},
}
SLOWMO_RATE = 0.5
TRANS_LEN = 0.16       # metade de uma transição (sai do plano A / entra no plano B)


@dataclass
class Shot:
    src_start: float          # segundo no vídeo original
    length: float             # duração na edição
    rate: float = 1.0         # 0.5 = câmera lenta
    move: str = "push_in"
    trans_in: str = "corte"
    focus: float = 0.5        # centro horizontal do enquadramento (0..1)
    file: str = ""            # trecho já cortado

    @property
    def src_len(self) -> float:
        return self.length * self.rate


@dataclass
class EditPlan:
    source: str
    style: str
    layout: str
    shots: list[Shot] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return sum(s.length for s in self.shots)


# ------------------------------------------------------------------ análise

def _ff() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    return ff


def probe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams",
                          str(path)], capture_output=True, text=True, check=True).stdout
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), {})
    return {"duration": float(info["format"].get("duration", 0)), "width": int(v.get("width", 1920)),
            "height": int(v.get("height", 1080)),
            "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])}


def scene_cuts(path: Path, t0: float, t1: float, threshold: float = 0.30) -> list[float]:
    """Instantes de corte de cena entre t0 e t1 (em segundos do vídeo original)."""
    proc = subprocess.run([_ff(), "-hide_banner", "-ss", f"{t0:.3f}", "-to", f"{t1:.3f}", "-i", str(path),
                           "-vf", f"scale=320:-2,select='gt(scene,{threshold})',showinfo", "-an", "-f", "null", "-"],
                          capture_output=True, text=True)
    times = [t0 + float(m) for m in re.findall(r"pts_time:([0-9.]+)", proc.stderr)]
    return sorted(t for t in times if t0 + 0.2 < t < t1 - 0.2)


def plan(path: Path, *, start: float = 0.0, end: float | None = None, duration: float = 20.0,
         style: str = "hype", layout: str = "cheio", seed_text: str = "") -> EditPlan:
    """Escolhe os trechos, o movimento de cada um e as transições."""
    st = STYLES[style]
    info = probe(path)
    end = min(end or info["duration"], info["duration"])
    if end - start < 1.0:
        raise ValueError("trecho muito curto")
    cuts = [start] + scene_cuts(path, start, end) + [end]
    lo, hi = st["shot"]
    # segmentos de cena -> pedaços no tamanho do estilo (pula 0,15 s depois de cada corte)
    pieces: list[tuple[float, float]] = []
    for a, b in zip(cuts, cuts[1:]):
        a += 0.15
        span = b - a - 0.05
        if span < lo * 0.6:
            continue
        n = max(1, int(span // hi))
        size = min(hi, span / n)
        for i in range(n):
            pieces.append((a + i * size, max(lo * 0.6, size)))
    if not pieces:                                   # vídeo sem cortes detectados
        n = max(1, int((end - start) // hi))
        size = (end - start) / n
        pieces = [(start + i * size, size) for i in range(n)]
    seed = int(hashlib.sha1((seed_text or str(path)).encode()).hexdigest()[:8], 16)
    rng_moves = st["moves"][seed % len(st["moves"]):] + st["moves"][:seed % len(st["moves"])]
    target = duration
    mean = (lo + hi) / 2
    n_want = max(2, round(target / mean))
    if len(pieces) > n_want:                          # distribui pelos trechos do vídeo inteiro
        step = (len(pieces) - 1) / (n_want - 1)
        pieces = [pieces[round(i * step)] for i in range(n_want)]
    shots: list[Shot] = []
    total = 0.0
    for i, (a, size) in enumerate(pieces):
        if total >= target - 0.3:
            break
        move = rng_moves[i % len(rng_moves)]
        rate = SLOWMO_RATE if move == "slowmo" else 1.0
        length = min(size / rate, hi * 1.2, target - total)
        if length < 0.5:
            break
        trans = "corte" if i == 0 else st["transitions"][(i + seed) % len(st["transitions"])]
        shots.append(Shot(src_start=a, length=round(length, 3), rate=rate, move=move, trans_in=trans))
        total += length
    return EditPlan(source=str(path), style=style, layout=layout, shots=shots)


def _subject_focus(frame: Path) -> float:
    """Centro horizontal do personagem num quadro (rembg); 0,5 se não achar ninguém."""
    try:
        from . import cutout
        im = Image.open(frame).convert("RGB")
        m = cutout.subject_mask(im, work_px=640)
        c = cutout.mask_centroid(m) if m is not None else None
        return round(c[0], 3) if c else 0.5
    except Exception:  # noqa: BLE001
        return 0.5


def prepare(plan_: EditPlan, work: Path, reframe: bool = True, log=print) -> None:
    """Corta cada trecho num MP4 próprio (30 fps, até 1080p) e acha o foco do enquadramento."""
    ff = _ff()
    src = Path(plan_.source)
    (work / "shots").mkdir(parents=True, exist_ok=True)
    for i, s in enumerate(plan_.shots):
        out = work / "shots" / f"s{i:02d}.mp4"
        if not out.exists():
            subprocess.run([ff, "-y", "-ss", f"{s.src_start:.3f}", "-i", str(src), "-t", f"{s.src_len + 0.1:.3f}",
                            "-vf", f"scale=-2:'min(1080,ih)',fps={FPS},format=yuv420p", "-c:v", "libx264",
                            "-preset", "veryfast", "-crf", "16", "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                            "-ac", "2", str(out)], check=True, capture_output=True)
        s.file = f"shots/{out.name}"
        if reframe and plan_.layout == "cheio":
            fr = work / "shots" / f"s{i:02d}.jpg"
            if not fr.exists():
                subprocess.run([ff, "-y", "-ss", f"{s.src_len / 2:.3f}", "-i", str(out), "-frames:v", "1",
                                str(fr)], check=True, capture_output=True)
            s.focus = _subject_focus(fr)
        log(f"  [editar] trecho {i + 1}/{len(plan_.shots)}: {s.src_start:6.2f}s  {s.length:.2f}s  "
            f"{s.move:<11} {s.trans_in}")


# ------------------------------------------------------------------ composição HyperFrames

def _handheld(sel: str, t0: float, d: float, amp: float, seed: int) -> list[str]:
    """Câmera na mão: pequenas oscilações determinísticas (sem aleatório no render)."""
    cmds = []
    steps = max(2, int(d / 0.28))
    for k in range(1, steps + 1):
        ph = seed * 1.7 + k
        x = amp * (math.sin(ph * 2.1) + 0.5 * math.sin(ph * 5.3))
        y = amp * 0.7 * (math.cos(ph * 1.7) + 0.4 * math.sin(ph * 4.1))
        r = 0.35 * math.sin(ph * 1.3)
        cmds.append(f'tl.to("{sel}", {{x: {x:.1f}, y: {y:.1f}, rotation: {r:.2f}, duration: {d / steps:.3f}, '
                    f'ease: "sine.inOut"}}, {t0 + (k - 1) * d / steps:.3f});')
    return cmds


def _move_cmds(sel: str, move: str, t0: float, d: float, idx: int) -> list[str]:
    e = f"{t0:.3f}"
    c = [f'tl.set("{sel}", {{scale: 1.0, x: 0, y: 0, rotation: 0, filter: "blur(0px)"}}, {e});']
    if move in ("push_in", "slowmo"):
        c.append(f'tl.fromTo("{sel}", {{scale: 1.0}}, {{scale: 1.14, duration: {d:.3f}, ease: "power1.inOut"}}, {e});')
    elif move == "pull_out":
        c.append(f'tl.fromTo("{sel}", {{scale: 1.18}}, {{scale: 1.0, duration: {d:.3f}, ease: "power2.out"}}, {e});')
    elif move == "snap_zoom":
        c.append(f'tl.fromTo("{sel}", {{scale: 1.55, filter: "blur(10px)"}}, {{scale: 1.06, filter: "blur(0px)", '
                 f'duration: 0.38, ease: "expo.out"}}, {e});')
        c.append(f'tl.to("{sel}", {{scale: 1.12, duration: {max(0.1, d - 0.38):.3f}, ease: "none"}}, {t0 + 0.38:.3f});')
    elif move == "crash_zoom":
        hold = max(0.2, d - 0.32)
        c.append(f'tl.fromTo("{sel}", {{scale: 1.0}}, {{scale: 1.05, duration: {hold:.3f}, ease: "none"}}, {e});')
        c.append(f'tl.to("{sel}", {{scale: 1.6, filter: "blur(6px)", duration: 0.32, ease: "expo.in"}}, '
                 f'{t0 + hold:.3f});')
    elif move in ("truck_left", "truck_right"):
        sgn = 1 if move == "truck_left" else -1
        c.append(f'tl.fromTo("{sel}", {{scale: 1.12, x: {90 * sgn}}}, {{scale: 1.12, x: {-90 * sgn}, '
                 f'duration: {d:.3f}, ease: "power1.inOut"}}, {e});')
    elif move == "tilt_up":
        c.append(f'tl.fromTo("{sel}", {{scale: 1.14, y: 80}}, {{scale: 1.14, y: -80, duration: {d:.3f}, '
                 f'ease: "power1.inOut"}}, {e});')
    elif move == "dutch":
        c.append(f'tl.fromTo("{sel}", {{scale: 1.18, rotation: -3.5}}, {{scale: 1.12, rotation: 2.5, '
                 f'duration: {d:.3f}, ease: "power1.inOut"}}, {e});')
    elif move == "handheld":
        c.append(f'tl.set("{sel}", {{scale: 1.08}}, {e});')
        c += _handheld(sel, t0, d, 7, idx)
    elif move == "impact":
        c.append(f'tl.set("{sel}", {{scale: 1.1}}, {e});')
        for k, amp in enumerate([22, -18, 14, -10, 6, -3, 0]):
            c.append(f'tl.to("{sel}", {{x: {amp}, y: {-amp * 0.6:.1f}, duration: 0.045, ease: "none"}}, '
                     f'{t0 + k * 0.045:.3f});')
        c.append(f'tl.to("{sel}", {{scale: 1.16, duration: {max(0.1, d - 0.32):.3f}, ease: "power1.out"}}, '
                 f'{t0 + 0.32:.3f});')
    return c


def _transition_cmds(prev: str | None, cur: str, kind: str, t: float) -> list[str]:
    """Transição no instante t (corte). O plano A sai nos últimos TRANS_LEN s, o B entra nos primeiros."""
    c: list[str] = []
    a, b = t - TRANS_LEN, f"{t:.3f}"
    if kind == "whip" and prev:
        c.append(f'tl.to("{prev}", {{x: "-=420", filter: "blur(18px)", duration: {TRANS_LEN}, ease: "power3.in"}}, '
                 f'{a:.3f});')
        c.append(f'tl.from("{cur}", {{x: "+=420", filter: "blur(18px)", duration: {TRANS_LEN}, '
                 f'ease: "power3.out", immediateRender: false}}, {b});')
    elif kind == "zoom" and prev:
        c.append(f'tl.to("{prev}", {{scale: "+=0.45", filter: "blur(12px)", duration: {TRANS_LEN}, ease: "power3.in"}}, '
                 f'{a:.3f});')
        c.append(f'tl.from("{cur}", {{scale: "+=0.35", filter: "blur(12px)", duration: {TRANS_LEN + 0.06}, '
                 f'ease: "power3.out", immediateRender: false}}, {b});')
    elif kind == "flash":
        c.append(f'tl.fromTo("#flash", {{opacity: 0.85}}, {{opacity: 0, duration: 0.28, ease: "power2.out"}}, {b});')
    return c


def composition(plan_: EditPlan, work: Path, audio: bool = True) -> Path:
    """Monta o index.html do HyperFrames com os trechos, movimentos e transições."""
    shutil.copy(HF_DIR / "gsap.min.js", work / "gsap.min.js")
    total = plan_.duration
    win_top = 0
    win_h = H
    if plan_.layout == "janela":
        win_top, win_h = 640, 608
    els, cmds = [], []
    t = 0.0
    prev = None
    for i, s in enumerate(plan_.shots):
        info = probe(work / s.file)
        ar = info["width"] / max(1, info["height"])
        # vídeo cobre a janela; foco horizontal no personagem
        vh = win_h
        vw = vh * ar
        if vw < W:
            vw, vh = W, W / ar
        left = min(0.0, max(W - vw, W / 2 - vw * s.focus))
        top = (win_h - vh) / 2
        rate = f' data-playback-rate="{s.rate}"' if s.rate != 1.0 else ""
        snd = (' data-has-audio="true"' if audio and s.rate == 1.0 and info["has_audio"] else " muted")
        vid = (f'<video id="v{i}" src="{s.file}" data-start="{t:.3f}" data-duration="{s.length:.3f}" '
               f'data-media-start="0"{rate} data-track-index="{i}"{snd} playsinline '
               f'style="left:{left:.1f}px;top:{top:.1f}px;width:{vw:.1f}px;height:{vh:.1f}px"></video>')
        bg = ""
        if plan_.layout == "janela":
            bg = (f'<video id="b{i}" class="blurbg" src="{s.file}" data-start="{t:.3f}" '
                  f'data-duration="{s.length:.3f}" data-media-start="0"{rate} data-track-index="{100 + i}" '
                  f'muted playsinline></video>')
        els.append(f'{bg}<div id="w{i}" class="win"><div id="m{i}" class="mv">{vid}</div></div>')
        sel = f"#m{i}"
        cmds.append(f'tl.set("#w{i}", {{autoAlpha: 0}}, 0);')
        cmds.append(f'tl.set("#w{i}", {{autoAlpha: 1}}, {t:.3f});')
        cmds.append(f'tl.set("#w{i}", {{autoAlpha: 0}}, {t + s.length:.3f});')
        cmds += _move_cmds(sel, s.move, t, s.length, i)
        cmds += _transition_cmds(prev, sel, s.trans_in, t) if i else []
        prev = sel
        t += s.length
    html = f"""<!doctype html>
<html lang="en" data-resolution="portrait">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width={W}, height={H}" />
    <script src="gsap.min.js"></script>
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      html, body {{ width: {W}px; height: {H}px; overflow: hidden; background: #0B0614; }}
      #root {{ position: relative; width: {W}px; height: {H}px; overflow: hidden; }}
      .win {{ position: absolute; left: 0; top: {win_top}px; width: {W}px; height: {win_h}px; overflow: hidden; }}
      .mv {{ position: absolute; left: 0; top: 0; width: {W}px; height: {win_h}px;
             transform-origin: 50% 50%; will-change: transform, filter; }}
      .mv video {{ position: absolute; object-fit: cover; }}
      .blurbg {{ position: absolute; left: -15%; top: -5%; width: 130%; height: 110%; object-fit: cover;
                 filter: blur(38px) brightness(0.5) saturate(1.2); }}
      #flash {{ position: absolute; inset: 0; background: #fff; opacity: 0; z-index: 900; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{total:.3f}" data-width="{W}" data-height="{H}">
      {chr(10).join('      ' + e for e in els).lstrip()}
      <div id="flash"></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      {chr(10).join('      ' + c for c in cmds).lstrip()}
      tl.set({{}}, {{}}, {total:.3f});
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
    (work / "index.html").write_text(html, encoding="utf-8")
    (work / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "shots"}}, indent=2))
    return work / "index.html"


def _render_hyperframes(work: Path, out: Path) -> None:
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx (Node.js >= 22) não encontrado")
    env = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_SKIP_SKILLS="1")
    cmd = [npx, "--yes", f"hyperframes@{HF_VERSION}", "render", "-c", "index.html", "-o", str(out.resolve()),
           "-q", "high", "-f", str(FPS), "--video-bitrate", os.environ.get("LEONIDA_VIDEO_BITRATE", "12M")]
    proc = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError("HyperFrames falhou:\n" + (proc.stdout + proc.stderr)[-1500:])


def _render_ffmpeg(plan_: EditPlan, work: Path, out: Path, audio: bool = True) -> None:
    """Motor reserva (sem Node/Chrome): zoom e travelling por trecho, cortes secos."""
    ff = _ff()
    parts = []
    for i, s in enumerate(plan_.shots):
        n = max(1, int(s.length * FPS))
        z = {"pull_out": f"1.18-0.18*on/{n}", "snap_zoom": f"1.06+0.06*on/{n}"}.get(s.move, f"1+0.14*on/{n}")
        x = {"truck_left": f"(iw-iw/zoom)*(0.5+0.08-0.16*on/{n})",
             "truck_right": f"(iw-iw/zoom)*(0.5-0.08+0.16*on/{n})"}.get(s.move, "(iw-iw/zoom)/2")
        fx = s.focus if plan_.layout == "cheio" else 0.5
        crop = (f"scale=-2:{H * 2},crop={W * 2}:{H * 2}:'min(max(0,iw*{fx}-{W}),iw-{W * 2})':0"
                if plan_.layout == "cheio" else f"scale={W * 2}:-2,pad={W * 2}:{H * 2}:0:(oh-ih)/2")
        vf = (f"setpts=PTS/{s.rate},{crop},zoompan=z='{z}':x='{x}':y='(ih-ih/zoom)/2':d=1:s={W}x{H}:fps={FPS},"
              f"trim=0:{s.length:.3f},setpts=PTS-STARTPTS,format=yuv420p")
        p = work / f"ff_{i:02d}.mp4"
        af = (f"atempo={s.rate}," if s.rate != 1.0 else "") + f"atrim=0:{s.length:.3f},asetpts=PTS-STARTPTS"
        cmd = [ff, "-y", "-i", str(work / s.file), "-f", "lavfi", "-t", f"{s.length:.3f}", "-i",
               "anullsrc=r=48000:cl=stereo", "-filter_complex",
               f"[0:v]{vf}[v];" + (f"[0:a]{af}[a]" if audio and probe(work / s.file)["has_audio"] and s.rate == 1.0
                                   else "[1:a]anull[a]"),
               "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-c:a", "aac",
               "-ar", "48000", "-ac", "2", str(p)]
        subprocess.run(cmd, check=True, capture_output=True)
        parts.append(p)
    lst = work / "concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    subprocess.run([ff, "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)],
                   check=True, capture_output=True)


# ------------------------------------------------------------------ acabamento

def grain_tiles(work: Path, n: int = 6) -> list[Path]:
    """Texturas de grão de filme (em "grumos", como em `gfx.finish`) para animar no vídeo."""
    import numpy as np
    from scipy import ndimage
    out = []
    for k in range(n):
        p = work / f"grain_{k}.png"
        if not p.exists():
            rng = np.random.default_rng(100 + k)
            g = ndimage.zoom(rng.normal(0, 1, (H // 2 + 1, W // 2 + 1)).astype(np.float32), 2, order=3)[:H, :W]
            v = np.clip(128 + g * 26, 0, 255).astype(np.uint8)
            Image.fromarray(v, "L").save(p)
        out.append(p)
    return out


def overlay_full(lang: str, headline: str, tag: str, source: str, date: str | None) -> Image.Image:
    """Moldura para o formato cheio: marca e contador no topo, selo + manchete abaixo, fonte e @ no rodapé.
    Sem caixa escura pesada: só um degradê suave atrás do texto (o vídeo continua respirando)."""
    s_top, s_bottom, s_left, s_right = render._safe()
    size = (W, H)
    pal = brand()["palette"]
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    img.alpha_composite(gfx.vertical_fade(size, pal["night"], 0.0, 0.34, 200, 0))
    img.alpha_composite(gfx.vertical_fade(size, pal["night"], 0.78, 1.0, 0, 150))
    img.alpha_composite(render.brand_bar(size, lang, s_top))
    img.alpha_composite(render.countdown_chip(size, lang, s_top + 4))
    y = s_top + 118
    if headline:
        tag_text, tag_color = render._tag_info(tag, lang)
        pill, ph = render.tag_pill(size, tag_text, tag_color, s_left, y)
        img.alpha_composite(pill)
        words = gfx.parse_marked(headline)
        fh, lines = gfx.fit_font("display", lambda f: gfx.wrap_words(words, f, W - s_left - s_right), 3, 92, 60, 4)
        lh = int(fh.size * 1.06)
        for ln in render.headline_lines(size, lines, fh, s_left, y + ph + 20, lh):
            img.alpha_composite(ln)
    ui = render.UI[lang]
    ff = gfx.font("bold", 24)
    foot = f"{ui['source']}: {source.upper()}" if source else ""
    if foot:
        img.alpha_composite(render.text_block(size, [foot], ff, s_left, H - s_bottom + 40, 0,
                                              gfx.rgba("#FFC857", 230)))
    fw = gfx.font("heavy", 26)
    handle = brand()["handle"][lang]
    wm = gfx.text_mask(size, ((W - gfx.text_width(handle, fw, 3)) / 2, H - 92), handle, fw, 3)
    img.alpha_composite(gfx.fill_with(wm, gfx.rgba("#FFFFFF", 150)))
    return img


def finish_video(base: Path, out: Path, overlay: Image.Image, work: Path, lang: str, *,
                 subtitles: bool = False, subs_y: int = 1250) -> None:
    """Grade de cor + grão animado + moldura da marca (+ legenda) sobre a edição renderizada."""
    ff = _ff()
    ov = work / f"overlay_{lang}.png"
    overlay.save(ov)
    grain_tiles(work)
    fin = gfx.look()
    grain_a = 0.10 * float(fin.get("grao", 1.0))
    # grão: as texturas em loop a 12 fps (ritmo de grão de filme), misturadas em "overlay"
    inputs = [ff, "-y", "-i", str(base), "-loop", "1", "-i", str(ov),
              "-stream_loop", "-1", "-framerate", "12", "-i", str(work / "grain_%d.png")]
    fc = (f"[0:v]eq=contrast=1.06:saturation=1.10:gamma=0.98,"
          f"curves=master='0/0.02 0.25/0.23 0.75/0.78 1/0.97',vignette=angle=PI/5,format=gbrp[g];"
          f"[2:v]fps={FPS},format=gray,format=gbrp[gr];"
          f"[g][gr]blend=all_mode=overlay:all_opacity={grain_a:.3f}:shortest=1,format=yuv420p[g2];"
          f"[1:v]format=rgba,fade=in:st=0.15:d=0.45:alpha=1[o];"
          f"[g2][o]overlay=0:0:shortest=1[v0]")
    last = "v0"
    if subtitles:
        ass = clips.transcribe_ass(base, "pt" if lang == "pt" else "en", work / f"subs_{lang}.ass", subs_y)
        if ass:
            fc += f";[v0]subtitles={ass.as_posix()}:fontsdir={FONTS_DIR.as_posix()}[v1]"
            last = "v1"
    dur = probe(base)["duration"]
    cmd = inputs + ["-filter_complex", fc, "-map", f"[{last}]", "-map", "0:a?", "-t", f"{dur:.3f}",
                    "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-maxrate", "14M", "-bufsize", "28M",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("FFmpeg (acabamento) falhou:\n" + proc.stderr[-1500:])


def contact_sheet(video: Path, out: Path, n: int = 8) -> Path:
    """Prévia: n quadros lado a lado, para revisar a edição sem abrir o vídeo."""
    ff = _ff()
    dur = probe(video)["duration"]
    frames = []
    tmp = out.parent / ".sheet"
    tmp.mkdir(exist_ok=True)
    for k in range(n):
        t = dur * (k + 0.5) / n
        p = tmp / f"{k}.jpg"
        subprocess.run([ff, "-y", "-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1", "-vf", "scale=270:480",
                        str(p)], check=True, capture_output=True)
        frames.append(Image.open(p).convert("RGB"))
    sheet = Image.new("RGB", (270 * n, 480))
    for k, f in enumerate(frames):
        sheet.paste(f, (270 * k, 0))
    sheet.save(out, quality=85)
    shutil.rmtree(tmp, ignore_errors=True)
    return out


# ------------------------------------------------------------------ entrada principal

def make_edit(src: str, *, start: str | float = 0, end: str | float | None = None, duration: float = 20.0,
              style: str = "hype", layout: str = "cheio", headline: dict | None = None, tag: str = "viral",
              source: str = "", date: str | None = None, langs=("pt", "en"), subtitles: bool = False,
              audio: bool = True, music_on: bool = True, engine: str | None = None, name: str | None = None,
              log=print) -> Path:
    """Gera prontos/<data>/<nome>/{br,us}/edicao.mp4 (+ legenda e prévia)."""
    if style not in STYLES:
        raise ValueError(f"estilo desconhecido: {style} (use {', '.join(STYLES)})")
    headline = headline or {}
    path = Path(src) if Path(src).exists() else clips.download(src)
    if not source and not Path(src).exists():
        source = clips.uploader(src) or ""
    date = date or dt.date.today().isoformat()
    slug = re.sub(r"[^a-z0-9]+", "-", (headline.get("en") or headline.get("pt") or path.stem).lower())[:40].strip("-")
    name = name or f"{date}-edicao-{slug or 'video'}"
    work = CACHE_DIR / "edits" / hashlib.sha1(f"{src}|{start}|{end}|{duration}|{style}|{layout}".encode()
                                              ).hexdigest()[:12]
    work.mkdir(parents=True, exist_ok=True)
    t0 = clips._ts(start)
    t1 = clips._ts(end) if end not in (None, "") else None
    log(f"🎬 editando {src} ({style}, {layout}, {duration:.0f}s)")
    p = plan(path, start=t0, end=t1, duration=duration, style=style, layout=layout, seed_text=src)
    prepare(p, work, log=log)
    (work / "plan.json").write_text(json.dumps(asdict(p), indent=2, ensure_ascii=False))
    base = work / "base.mp4"
    engine = engine or os.environ.get("LEONIDA_VIDEO_ENGINE", "auto")
    used = "ffmpeg"
    if engine in ("auto", "hyperframes"):
        try:
            composition(p, work, audio=audio)
            log("  [editar] renderizando no HyperFrames…")
            _render_hyperframes(work, base)
            used = "hyperframes"
        except Exception as exc:  # noqa: BLE001
            if engine == "hyperframes":
                raise
            log(f"  [editar] HyperFrames indisponível ({str(exc).splitlines()[0]}); usando FFmpeg")
    if used == "ffmpeg":
        _render_ffmpeg(p, work, base, audio=audio)
    out_root = OUT_DIR / date / name
    files = {}
    for lang in langs:
        folder = out_root / ("br" if lang == "pt" else "us")
        folder.mkdir(parents=True, exist_ok=True)
        if layout == "janela":
            ov, top = clips.overlay(lang, headline.get(lang, ""), tag, source, date)
            subs_y = top + 608 + 230
        else:
            ov = overlay_full(lang, headline.get(lang, ""), tag, source, date)
            subs_y = int(H * 0.68)
        out = folder / ("edicao.mp4" if lang == "pt" else "edit.mp4")
        log(f"  [editar] acabamento {lang} -> {out}")
        finish_video(base, out, ov, work, lang, subtitles=subtitles, subs_y=subs_y)
        if music_on:
            from . import music
            music.apply(out)
        contact_sheet(out, folder / ("previa.jpg" if lang == "pt" else "preview.jpg"))
        cap_name = "legenda.txt" if lang == "pt" else "caption.txt"
        base_tags = " ".join(brand()["hashtags"][lang])
        credit = ("Fonte: " if lang == "pt" else "Source: ") + source if source else ""
        text = (headline.get(lang) or "").replace("*", "")
        (folder / cap_name).write_text(f"{text}\n\n{credit}\n\n{base_tags}\n".lstrip(), encoding="utf-8")
        files[lang] = str(out)
    (out_root / "post.json").write_text(json.dumps({
        "id": name, "type": "edit", "date": date, "src": src, "engine": used, "style": style, "layout": layout,
        "duration": round(p.duration, 2), "shots": [asdict(s) for s in p.shots], "files": files}, indent=2,
        ensure_ascii=False))
    log(f"  [editar] motor: {used} · {len(p.shots)} trechos · {p.duration:.1f}s")
    return out_root
