"""Vídeo 9:16 animado a partir das camadas da capa.

Motor principal: HyperFrames (HeyGen, Apache-2.0) — HTML + GSAP -> MP4 determinístico.
  https://github.com/heygen-com/hyperframes
Fallback: FFmpeg (Ken Burns + entrada dos textos), caso Node/Chrome não estejam disponíveis.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

from PIL import Image

from .config import CACHE_DIR, HF_DIR
from .render import Render

HF_VERSION = os.environ.get("HYPERFRAMES_VERSION", "0.8.141")
FPS = 30


def _bbox_center(im: Image.Image) -> tuple[int, int]:
    bb = im.split()[-1].getbbox()
    if not bb:
        return im.width // 2, im.height // 2
    return (bb[0] + bb[2]) // 2, (bb[1] + bb[3]) // 2


def _timeline(r: Render, duration: float) -> list[str]:
    """Gera os comandos GSAP para cada camada conforme a dica de animação."""
    cmds: list[str] = []
    line_i = 0
    n_lines = sum(1 for L in r.layers if L.anim == "line")
    t_after_lines = 1.3 + n_lines * 0.14 + 0.35
    for idx, L in enumerate(sorted(r.layers, key=lambda x: x.order)):
        sel = f"#L{idx}"
        cx, cy = _bbox_center(L.image)
        origin = f'"{cx}px {cy}px"'
        a = L.anim
        if a == "kenburns":
            cmds.append(f'tl.fromTo("{sel}", {{scale: 1.14}}, {{scale: 1.0, duration: {duration}, ease: "power1.out"}}, 0);')
        elif a == "kicker":
            cmds.append(f'tl.set("{sel}", {{transformOrigin: {origin}}}, 0);')
            cmds.append(f'tl.fromTo("{sel}", {{opacity: 0, scale: 1.35}}, {{opacity: 1, scale: 1, duration: 0.75, ease: "power3.out"}}, 0.15);')
            cmds.append(f'tl.to("{sel}", {{y: -18, duration: {duration - 0.9:.2f}, ease: "none"}}, 0.9);')
        elif a == "subject":
            cmds.append(f'tl.set("{sel}", {{transformOrigin: {origin}}}, 0);')
            cmds.append(f'tl.fromTo("{sel}", {{opacity: 0, y: 90}}, {{opacity: 1, y: 0, duration: 0.85, ease: "power3.out"}}, 0.45);')
            cmds.append(f'tl.to("{sel}", {{scale: 1.035, duration: {duration - 1.3:.2f}, ease: "none"}}, 1.3);')
        elif a == "down":
            cmds.append(f'tl.fromTo("{sel}", {{opacity: 0, y: -40}}, {{opacity: 1, y: 0, duration: 0.5, ease: "power3.out"}}, 0.8);')
        elif a == "pop":
            start = 1.05 if L.name == "tag" else 0.95
            cmds.append(f'tl.set("{sel}", {{transformOrigin: {origin}}}, 0);')
            cmds.append(f'tl.fromTo("{sel}", {{opacity: 0, scale: 0.55}}, {{opacity: 1, scale: 1, duration: 0.55, ease: "back.out(2.2)"}}, {start});')
        elif a == "line":
            t = 1.3 + line_i * 0.14
            line_i += 1
            cmds.append(f'tl.fromTo("{sel}", {{opacity: 0, x: -90}}, {{opacity: 1, x: 0, duration: 0.55, ease: "power4.out"}}, {t:.2f});')
        elif a == "up":
            t = t_after_lines + (0.15 if L.name == "footer" else 0)
            cmds.append(f'tl.fromTo("{sel}", {{opacity: 0, y: 34}}, {{opacity: 1, y: 0, duration: 0.5, ease: "power3.out"}}, {t:.2f});')
        else:  # fade
            t = 0.0 if L.name == "shade" else 0.25
            cmds.append(f'tl.fromTo("{sel}", {{opacity: 0}}, {{opacity: 1, duration: 0.45, ease: "power1.out"}}, {t});')
    # flash de câmera no início
    cmds.append('tl.fromTo("#flash", {opacity: 0.55}, {opacity: 0, duration: 0.4, ease: "power2.out"}, 0);')
    return cmds


def build_composition(r: Render, workdir: Path, duration: float = 8.0) -> Path:
    workdir.mkdir(parents=True, exist_ok=True)
    (workdir / "layers").mkdir(exist_ok=True)
    W, H = r.image.size
    tags = []
    for idx, L in enumerate(sorted(r.layers, key=lambda x: x.order)):
        if L.name == "bg":
            fn = f"layers/{idx:02d}_{L.name}.jpg"
            L.image.convert("RGB").save(workdir / fn, quality=92)
        else:
            fn = f"layers/{idx:02d}_{L.name}.png"
            L.image.save(workdir / fn, optimize=True)
        tags.append(
            f'      <img id="L{idx}" class="clip layer" src="{fn}" alt="" '
            f'data-start="0" data-duration="{duration}" data-track-index="{idx}" style="z-index:{idx}" />')
    shutil.copy(HF_DIR / "gsap.min.js", workdir / "gsap.min.js")
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
      .clip {{ position: absolute; left: 0; top: 0; width: {W}px; height: {H}px; }}
      .layer {{ display: block; will-change: transform, opacity; }}
      #flash {{ background: #ffffff; opacity: 0; z-index: 999; }}
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="{duration}" data-width="{W}" data-height="{H}">
{chr(10).join(tags)}
      <div id="flash" class="clip" data-start="0" data-duration="{duration}" data-track-index="{len(tags)}"></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {{}};
      const tl = gsap.timeline({{ paused: true }});
      {chr(10).join('      ' + c for c in _timeline(r, duration)).lstrip()}
      window.__timelines["main"] = tl;
      tl.seek(0);
    </script>
  </body>
</html>
"""
    (workdir / "index.html").write_text(html, encoding="utf-8")
    (workdir / "hyperframes.json").write_text(json.dumps({"paths": {"assets": "layers"}}, indent=2))
    return workdir / "index.html"


def _hyperframes_render(workdir: Path, out: Path, quality: str = "high") -> None:
    npx = shutil.which("npx")
    if not npx:
        raise RuntimeError("npx (Node.js >= 22) não encontrado")
    env = dict(os.environ, HYPERFRAMES_NO_TELEMETRY="1", HYPERFRAMES_SKIP_SKILLS="1")
    cmd = [npx, "--yes", f"hyperframes@{HF_VERSION}", "render", "-c", "index.html",
           "-o", str(out.resolve()), "-q", quality, "-f", str(FPS),
           "--video-bitrate", os.environ.get("LEONIDA_VIDEO_BITRATE", "12M")]
    proc = subprocess.run(cmd, cwd=workdir, env=env, capture_output=True, text=True, timeout=900)
    if proc.returncode != 0 or not out.exists():
        tail = (proc.stdout + proc.stderr)[-1500:]
        raise RuntimeError(f"HyperFrames falhou:\n{tail}")


def _ffmpeg_render(r: Render, out: Path, duration: float) -> None:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    tmp = CACHE_DIR / "ff" / hashlib.sha1(str(out).encode()).hexdigest()[:10]
    tmp.mkdir(parents=True, exist_ok=True)
    W, H = r.image.size
    base = Image.new("RGBA", (W, H))
    over = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for L in sorted(r.layers, key=lambda x: x.order):
        (base if L.order <= 4 else over).alpha_composite(L.image)
    base.convert("RGB").save(tmp / "base.png")
    over.save(tmp / "over.png")
    frames = int(duration * FPS)
    vf = (f"[0:v]scale={W * 2}:{H * 2},zoompan=z='1.12-0.12*on/{frames}':x='iw/2-(iw/zoom/2)':"
          f"y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}[b];"
          f"[1:v]format=rgba,fade=in:st=0.5:d=0.6:alpha=1[o];[b][o]overlay=0:0,format=yuv420p[v]")
    cmd = [ff, "-y", "-loop", "1", "-t", str(duration), "-i", str(tmp / "base.png"),
           "-loop", "1", "-t", str(duration), "-i", str(tmp / "over.png"),
           "-filter_complex", vf, "-map", "[v]", "-r", str(FPS), "-c:v", "libx264", "-crf", "16",
           "-preset", "slow", "-movflags", "+faststart", "-t", str(duration), str(out)]
    subprocess.run(cmd, check=True, capture_output=True)


def render_video(r: Render, out: Path, duration: float = 8.0, engine: str | None = None) -> str:
    """Gera o MP4. Retorna o motor usado ('hyperframes' ou 'ffmpeg')."""
    engine = engine or os.environ.get("LEONIDA_VIDEO_ENGINE", "auto")
    out.parent.mkdir(parents=True, exist_ok=True)
    if engine in ("auto", "hyperframes"):
        key = hashlib.sha1(r.image.tobytes()).hexdigest()[:12]
        work = CACHE_DIR / "hf" / key
        try:
            build_composition(r, work, duration)
            _hyperframes_render(work, out)
            return "hyperframes"
        except Exception as exc:  # noqa: BLE001
            if engine == "hyperframes":
                raise
            print(f"  [video] HyperFrames indisponível ({str(exc).splitlines()[0]}); usando FFmpeg")
    _ffmpeg_render(r, out, duration)
    return "ffmpeg"
