"""Trilha sonora dos vídeos: SEMPRE a música tema de GTA VI (nunca música aleatória do TikTok).

Os arquivos ficam só no seu PC (assets/music/, fora do git — direitos autorais). Pode ter mais de uma
faixa tema (ex.: a do trailer 1 e a do trailer 2): o app alterna entre elas, uma por post. Para baixar
a música de um vídeo (ex.: o trailer oficial no YouTube):

    python -m leonida musica "https://www.youtube.com/watch?v=..." --inicio 0:12 --nome trailer-2

Depois disso, todo vídeo de post sai com a música tema e todo corte ganha a música por baixo do áudio
original. Configuração em config/brand.yaml -> music.
"""
from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
from pathlib import Path

from .config import CACHE_DIR, ROOT, brand


def _cfg() -> dict:
    return brand().get("music") or {}


AUDIO_EXT = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".opus", ".flac")
MIN_THEME_SECONDS = 10.0       # faixa menor que isso é corte quebrado, não música tema
SILENT_DB = -45.0              # volume médio abaixo disso: faixa muda ou quase


def _partial(path: Path) -> bool:
    """Arquivos de trabalho (tema.tmp.mp3, .part) nunca entram como música."""
    return ".tmp." in path.name or path.name.endswith((".part", ".tmp")) or path.name.startswith(".")


def _probe_seconds(path: Path) -> float | None:
    probe = shutil.which("ffprobe")
    if not probe:
        return None
    r = subprocess.run([probe, "-v", "error", "-select_streams", "a:0", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


@functools.lru_cache(maxsize=64)
def _usable(path: str, mtime: float, size: int) -> bool:
    seconds = _probe_seconds(Path(path))
    return seconds is None or seconds >= MIN_THEME_SECONDS


def mean_volume(path: Path) -> float | None:
    """Volume médio em dB (volumedetect); None sem ffmpeg."""
    ff = shutil.which("ffmpeg")
    if not ff:
        return None
    r = subprocess.run([ff, "-v", "info", "-nostdin", "-i", str(path), "-map", "0:a:0", "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    match = re.search(r"mean_volume:\s*(-?[\d.]+|-inf) dB", r.stderr)
    if not match:
        return float("-inf")
    return float(match.group(1))


def check_track(path: Path) -> None:
    """Recusa faixa curta ou muda antes de ela virar a música de todos os vídeos."""
    seconds = _probe_seconds(path)
    if seconds is not None and seconds < .5:
        # silenceremove apaga uma faixa toda silenciosa: sobra quase nada.
        raise ValueError("a música está muda ou vazia; confira o link/arquivo e o ponto de início")
    if seconds is not None and seconds < MIN_THEME_SECONDS:
        raise ValueError(f"a música tem só {seconds:.1f}s; use um trecho de pelo menos {MIN_THEME_SECONDS:g}s")
    volume = mean_volume(path)
    if volume is not None and volume < SILENT_DB:
        raise ValueError("a música está muda ou baixa demais; confira o link/arquivo e o ponto de início")


def themes() -> list[Path]:
    """Todas as faixas tema disponíveis em assets/music/ (ordem alfabética).

    Ignora arquivos de trabalho e faixas curtas demais (corte quebrado).
    """
    cfg = _cfg()
    if cfg.get("enabled", True) is False:
        return []
    folder = ROOT / Path(cfg.get("file", "assets/music/tema.mp3")).parent
    if not folder.exists():
        return []
    found = []
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() not in AUDIO_EXT or not p.is_file() or _partial(p):
            continue
        stat = p.stat()
        if stat.st_size > 0 and _usable(str(p), stat.st_mtime, stat.st_size):
            found.append(p)
    return found


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
    try:
        return import_file(raw, start=start, length=length, name=name, log=log)
    finally:
        raw.unlink(missing_ok=True)


def import_file(src: Path, start=None, length: float = 120.0, name: str | None = None, log=print) -> Path:
    """Instala um arquivo de áudio como música tema: corta a partir de `start` (e o silêncio do começo),
    padroniza o volume para o nível do TikTok (-14 LUFS), remove a capa embutida e salva em MP3."""
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado")
    out = ROOT / _cfg().get("file", "assets/music/tema.mp3")
    if name:
        out = out.with_name(re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") + ".mp3")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.mp3")
    try:
        subprocess.run([ff, "-y", "-ss", str(_ts(start)), "-t", str(length), "-i", str(src), "-map", "0:a:0", "-vn",
                        "-af", "silenceremove=start_periods=1:start_threshold=-50dB,loudnorm=I=-14:TP=-1.5:LRA=11",
                        "-ar", "44100", "-b:a", "256k", str(tmp)], check=True, capture_output=True)
        check_track(tmp)          # a faixa anterior só é substituída por uma música válida
        tmp.replace(out)
    finally:
        tmp.unlink(missing_ok=True)
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


def apply(video: Path, under_original: bool | None = None, seed: str | None = None,
          fade_out: float = 1.2) -> bool:
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
    fade_len = max(0.1, float(fade_out))
    fade_out = max(0.0, dur - fade_len)
    has_audio = _has_audio(video) if under_original is None else under_original
    vol = float(cfg.get("under_clip", 0.3) if has_audio else cfg.get("volume", 1.0))
    start = _ts(cfg.get("start", 0))
    music = (f"[1:a]atrim=0:{dur:.3f},asetpts=PTS-STARTPTS,volume={vol},"
             f"afade=t=in:st=0:d=0.35,afade=t=out:st={fade_out:.3f}:d={fade_len:.2f}[m]")
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
