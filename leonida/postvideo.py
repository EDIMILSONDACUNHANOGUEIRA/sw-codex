"""Vídeo de publicação: o carrossel do post vira um vídeo 9:16 com a MÚSICA TEMA de GTA VI.

Por que vídeo e não post de fotos: pela API, o TikTok não deixa escolher a música de um post de fotos
(só "música automática", que sorteia qualquer faixa). Num vídeo, a música tema vai embutida no
arquivo, então ela sempre toca.

Montagem (só FFmpeg, roda em qualquer PC):
  - capa: usa o vídeo animado da capa (video.mp4, HyperFrames) se existir; senão, a capa estática
    com um zoom lento;
  - cada slide do carrossel com um zoom lento e transição suave entre eles;
  - música tema por baixo (music.apply), com fade no começo e no fim.

Saída: <post>/<br|us>/tiktok/post.mp4
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import music
from .config import ROOT

FPS = 30
W, H = 1080, 1920
COVER_SECONDS = 5.0      # capa estática
SLIDE_SECONDS = 4.5      # slides com texto: tempo para ler
LAST_SECONDS = 3.0       # último slide ("siga")
XFADE = 0.4              # transição entre slides
OUT_NAME = "post.mp4"


class MusicMissing(RuntimeError):
    """Não há música tema em assets/music/: o vídeo não pode sair (a regra é sempre ter música tema)."""


def _ff() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    return ff


def _duration(path: Path) -> float:
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def slides_of(folder: Path) -> list[Path]:
    """Artes do carrossel na ordem de publicação (01_capa, 02_..., último = siga/follow)."""
    return sorted(p for p in folder.glob("*.png") if p.stem not in ("previa", "preview"))


def _still_segment(img: Path, out: Path, seconds: float, zoom_to: float = 1.06) -> None:
    """Uma arte parada vira um trecho com zoom lento (sem tremer: amplia 2x antes do zoompan)."""
    frames = max(1, int(round(seconds * FPS)))
    vf = (f"scale={W * 2}:{H * 2}:flags=lanczos,"
          f"zoompan=z='1+{zoom_to - 1:.4f}*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d={frames}:s={W}x{H}:fps={FPS},format=yuv420p")
    subprocess.run([_ff(), "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{seconds:.3f}", "-i", str(img),
                    "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "medium", "-crf", "16",
                    "-an", str(out)], check=True, capture_output=True)


def _normalize_intro(src: Path, out: Path) -> None:
    subprocess.run([_ff(), "-y", "-i", str(src), "-vf", f"scale={W}:{H},fps={FPS},format=yuv420p",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-an", str(out)],
                   check=True, capture_output=True)


def build(folder: Path, seed: str, intro: Path | None = None, log=print, target: float | None = None) -> Path:
    """Gera <folder>/tiktok/post.mp4 com a música tema. Lança MusicMissing se não houver música tema.

    target: duração total desejada em segundos (ex.: 30). Os slides do meio esticam ou encolhem para caber;
    sem target, cada slide fica SLIDE_SECONDS."""
    if not music.theme_path(seed):
        raise MusicMissing("nenhuma música tema em assets/music/ — rode: "
                           "python -m leonida musica \"URL do trailer\" --inicio 0:12")
    slides = slides_of(folder)
    if not slides:
        raise RuntimeError(f"sem artes em {folder}")
    work = folder / "tiktok" / ".work"
    work.mkdir(parents=True, exist_ok=True)
    segs: list[Path] = []
    if intro is not None and intro.exists() and _duration(intro) > 1:
        seg = work / "s00.mp4"
        _normalize_intro(intro, seg)
        segs.append(seg)
        rest = slides[1:]                      # a capa já está no vídeo animado
    else:
        rest = slides
    slide_secs = SLIDE_SECONDS
    n_mid = len(slides) - 2                  # slides entre a capa e o último
    if target and n_mid > 0:
        head = _duration(segs[0]) if segs else COVER_SECONDS
        # total = capa + n_mid*s + último - XFADE*(transições)
        slide_secs = (float(target) - head - LAST_SECONDS + XFADE * (len(slides) - 1)) / n_mid
        slide_secs = max(3.0, min(9.0, slide_secs))
    for i, img in enumerate(rest):
        is_cover = not segs and i == 0
        is_last = i == len(rest) - 1 and len(slides) > 1
        secs = COVER_SECONDS if is_cover else (LAST_SECONDS if is_last else slide_secs)
        seg = work / f"s{len(segs):02d}.mp4"
        _still_segment(img, seg, secs, 1.045 if is_cover else 1.02)   # zoom leve: não corta margens
        segs.append(seg)
    final = folder / "tiktok" / OUT_NAME
    final.unlink(missing_ok=True)            # nunca deixar um post.mp4 antigo/mudo para trás
    out = work / OUT_NAME                    # monta e coloca a música em .work/; só move no fim
    if len(segs) == 1:
        shutil.copy(segs[0], out)
    else:
        # encadeia as transições: [0][1]xfade -> [v1]; [v1][2]xfade -> [v2] ...
        durs = [_duration(s) for s in segs]
        inputs, chain, offset, last = [], [], 0.0, "0:v"
        for s in segs:
            inputs += ["-i", str(s)]
        for k in range(1, len(segs)):
            offset += durs[k - 1] - XFADE
            label = f"v{k}"
            chain.append(f"[{last}][{k}:v]xfade=transition=fade:duration={XFADE}:offset={offset:.3f}[{label}]")
            last = label
        subprocess.run([_ff(), "-y", *inputs, "-filter_complex", ";".join(chain), "-map", f"[{last}]",
                        "-r", str(FPS), "-c:v", "libx264", "-preset", "slow", "-crf", "19", "-maxrate", "10M",
                        "-bufsize", "20M", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)],
                       check=True, capture_output=True)
    try:
        ok = music.apply(out, under_original=False, seed=seed)
    except (subprocess.CalledProcessError, OSError) as exc:
        ok = False
        log(f"  ⚠️  falha ao colocar a música tema ({exc})")
    if not ok or not music._has_audio(out):
        shutil.rmtree(work, ignore_errors=True)
        raise MusicMissing("não consegui colocar a música tema no vídeo (arquivo de música inválido?) — "
                           "o vídeo NÃO foi gerado; confira assets/music/ e rode o build de novo")
    os.replace(out, final)
    shutil.rmtree(work, ignore_errors=True)
    log(f"  🎵 vídeo com música tema: {final.relative_to(ROOT)} "
        f"({_duration(final):.1f}s, {music.theme_path(seed).name})")
    return final
