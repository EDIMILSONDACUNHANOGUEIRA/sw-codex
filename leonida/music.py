"""Trilha sonora dos vídeos: SEMPRE a música tema de GTA VI (nunca música aleatória do TikTok).

Os arquivos ficam só no seu PC (assets/music/, fora do git — direitos autorais). Pode ter mais de uma
faixa tema (ex.: a do trailer 1 e a do trailer 2): o app alterna entre elas, uma por post. Para baixar
a música de um vídeo (ex.: o trailer oficial no YouTube):

    python -m leonida musica "https://www.youtube.com/watch?v=..." --inicio 0:12 --nome trailer-2

Depois disso, todo vídeo de post sai com a música tema e todo corte ganha a música por baixo do áudio
original. Configuração em config/brand.yaml -> music.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .config import CACHE_DIR, ROOT, brand


def _cfg() -> dict:
    return brand().get("music") or {}


AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")


def themes() -> list[Path]:
    """Todas as faixas tema disponíveis em assets/music/ (ordem alfabética)."""
    cfg = _cfg()
    if cfg.get("enabled", True) is False:
        return []
    folder = ROOT / Path(cfg.get("file", "assets/music/tema.mp3")).parent
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir()
                  if p.suffix.lower() in AUDIO_EXT and p.is_file() and p.stat().st_size > 0)


def theme_path(seed: str | None = None) -> Path | None:
    """Faixa tema do post. Com várias faixas, `seed` (o id do post) escolhe uma de forma fixa:
    o mesmo post sempre recebe a mesma música, e posts diferentes alternam entre as faixas."""
    files = themes()
    if not files:
        return None
    if seed is None or len(files) == 1:
        preferred = ROOT / _cfg().get("file", "assets/music/tema.mp3")
        return preferred if preferred in files else files[0]
    import hashlib
    return files[int(hashlib.sha1(seed.encode()).hexdigest()[:8], 16) % len(files)]


def _ts(t) -> float:
    if t is None or t == "":
        return 0.0
    if isinstance(t, (int, float)):
        return float(t)
    sec = 0.0
    for part in str(t).split(":"):
        sec = sec * 60 + float(part)
    return sec


def download(url: str, start=None, length: float = 120.0, log=print, name: str | None = None) -> Path:
    """Baixa o áudio (yt-dlp), corta a partir de `start`, normaliza o volume e salva como música tema.
    `name` (ex.: "trailer-2") salva como faixa extra em assets/music/<name>.mp3."""
    import yt_dlp

    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    tmp_dir = CACHE_DIR / "music"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    opts = {
        "outtmpl": str(tmp_dir / "raw.%(ext)s"),
        "format": "bestaudio/best",
        "quiet": True,
        "noprogress": True,
        "overwrites": True,
        "js_runtimes": {"deno": {}, "node": {}},
    }
    if os.environ.get("LEONIDA_YTDLP_BROWSER"):
        opts["cookiesfrombrowser"] = (os.environ["LEONIDA_YTDLP_BROWSER"],)
    log("  [música] baixando áudio…")
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])
    raw = next(iter(sorted(tmp_dir.glob("raw.*"))), None)
    if not raw:
        raise RuntimeError("download do áudio falhou")
    out = ROOT / _cfg().get("file", "assets/music/tema.mp3")
    if name:
        import re
        out = out.with_name(re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") + ".mp3")
    out.parent.mkdir(parents=True, exist_ok=True)
    s = _ts(start)
    subprocess.run([ff, "-y", "-ss", str(s), "-t", str(length), "-i", str(raw),
                    "-af", "loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "44100", "-b:a", "256k", str(out)],
                   check=True, capture_output=True)
    raw.unlink(missing_ok=True)
    log(f"  [música] salva em {out}")
    return out


def _has_audio(video: Path) -> bool:
    probe = shutil.which("ffprobe")
    if not probe:
        return False
    r = subprocess.run([probe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    return bool(r.stdout.strip())


def _duration(video: Path) -> float:
    r = subprocess.run([shutil.which("ffprobe") or "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(video)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 8.0


def apply(video: Path, under_original: bool | None = None, seed: str | None = None) -> bool:
    """Coloca a música tema no MP4 (substitui o arquivo). Retorna False se não houver música tema.

    - Vídeo sem áudio (posts de notícia): a música entra no volume `volume`.
    - Vídeo com áudio (cortes): a música entra por baixo, no volume `under_clip`.
    - `seed` (id do post) escolhe a faixa quando há mais de uma.
    """
    theme = theme_path(seed)
    ff = shutil.which("ffmpeg")
    if not theme or not ff or not video.exists():
        return False
    cfg = _cfg()
    dur = _duration(video)
    fade_out = max(0.0, dur - 1.2)
    has_audio = _has_audio(video) if under_original is None else under_original
    vol = float(cfg.get("under_clip", 0.3) if has_audio else cfg.get("volume", 1.0))
    start = _ts(cfg.get("start", 0))
    music = (f"[1:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={vol},"
             f"afade=t=in:st=0:d=0.35,afade=t=out:st={fade_out:.3f}:d=1.2[m]")
    if has_audio:
        fc = music + ";[0:a][m]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a]"
    else:
        fc = music.replace("[m]", "[a]")
    tmp = video.with_suffix(".music.mp4")
    subprocess.run([ff, "-y", "-i", str(video), "-ss", str(start), "-stream_loop", "-1", "-i", str(theme),
                    "-filter_complex", fc, "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                    "-b:a", "192k", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(tmp)],
                   check=True, capture_output=True)
    tmp.replace(video)
    return True
