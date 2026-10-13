"""Sugestões locais de cortes de gameplay, sem modelo obrigatório.

Movimento e energia sonora ajudam a localizar momentos para revisão. Esses sinais
não entendem a história, não identificam o jogo e não garantem potencial viral.
O plano preserva os tempos originais para o editor revisar ou trocar os trechos.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import numpy as np
from PIL import Image, ImageDraw

from . import clips, gfx

FPS = 30


def _seconds(value: str | float) -> float:
    try:
        result = 0.0
        for part in str(value).split(":"):
            result = result * 60 + float(part)
    except (ValueError, TypeError) as exc:
        raise ValueError(f"Tempo inválido: {value!r}.") from exc
    if not math.isfinite(result) or result < 0:
        raise ValueError("Os tempos precisam ser finitos e positivos ou zero.")
    return result


def probe(path: Path) -> dict:
    """Metadados essenciais; rejeita lives e fontes sem duração conhecida."""
    command = ["ffprobe", "-v", "error", "-show_format", "-show_streams",
               "-of", "json", str(path)]
    try:
        result = subprocess.run(command, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", check=True)
        data = json.loads(result.stdout)
    except (OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        raise ValueError("Não foi possível ler o vídeo. Confira o arquivo ou o download.") from exc
    videos = [s for s in data.get("streams", [])
              if s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic")]
    if not videos:
        raise ValueError("A fonte precisa conter uma faixa de vídeo.")
    values = [data.get("format", {}).get("duration"), videos[0].get("duration")]
    duration = 0.0
    for value in values:
        try:
            duration = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(duration) and duration > 0:
            break
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Use um vídeo concluído com duração conhecida; lives não são aceitas.")
    return {"duration": duration, "has_audio": any(s.get("codec_type") == "audio"
            for s in data.get("streams", [])), "width": videos[0].get("width", 0),
            "height": videos[0].get("height", 0)}


def _resolve(source: str, credit: str, log) -> tuple[Path, str, str, str]:
    parsed = urlparse(source)
    url = ""
    if parsed.scheme in ("http", "https") and parsed.hostname:
        url = source
        log("Baixando a fonte com yt-dlp; o tempo depende do tamanho do vídeo.")
        path = clips.download(source).resolve()
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_file():
            raise ValueError("Informe um link http/https ou um arquivo de vídeo existente.")
    title = path.stem
    meta_path = path.with_suffix(".info.json")
    if url and meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            title = meta.get("title") or title
            credit = credit or meta.get("channel") or meta.get("uploader") or ""
        except (OSError, json.JSONDecodeError):
            pass
    if not credit:
        credit = "Fonte enviada pelo usuário"
    return path, url, title, credit


def _motion(path: Path, duration: float, interval: float, log) -> np.ndarray:
    """Compara quadros pequenos; guarda apenas um valor por amostra."""
    width, height = 96, 54
    # noref pula só quadros que nenhum outro usa (B não referenciados): decodifica bem
    # menos em gameplays longas sem criar buracos na amostragem de 1 quadro a cada 2 s+.
    command = ["ffmpeg", "-v", "error", "-nostdin", "-threads", "2", "-skip_frame", "noref", "-i", str(path),
               "-an", "-vf", f"fps=1/{interval:.8f},scale={width}:{height}:flags=fast_bilinear",
               "-pix_fmt", "gray", "-f", "rawvideo", "pipe:1"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    previous = None
    values = []
    frame_bytes = width * height
    next_report = 60.0
    try:
        while True:
            raw = process.stdout.read(frame_bytes)
            if not raw:
                break
            if len(raw) != frame_bytes:
                raise RuntimeError("A análise encontrou um quadro incompleto.")
            frame = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
            values.append(0.0 if previous is None else float(np.abs(frame - previous).mean() / 255))
            previous = frame
            processed = len(values) * interval
            if processed >= next_report:
                log(f"Quadros analisados: {min(processed, duration):.0f}/{duration:.0f} s.")
                next_report += max(60, duration / 12)
        if process.wait() != 0:
            raise RuntimeError("O FFmpeg não conseguiu analisar os quadros da fonte.")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()
    if not values:
        raise RuntimeError("A fonte não produziu quadros para análise.")
    return np.asarray(values, dtype=np.float64)


def _energy(path: Path, interval: float, bins: int, log) -> np.ndarray:
    """RMS por janela, lendo o áudio em blocos (sem carregar a faixa inteira)."""
    log("Analisando energia do áudio e possíveis pausas.")
    rate = 8000
    chunk_bytes = max(1, round(interval * rate)) * 4
    command = ["ffmpeg", "-v", "error", "-nostdin", "-threads", "2", "-i", str(path),
               "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(rate),
               "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    values = []
    try:
        while True:
            raw = process.stdout.read(chunk_bytes)
            if not raw:
                break
            raw = raw[:len(raw) - len(raw) % 4]
            samples = np.frombuffer(raw, dtype="<f4")
            values.append(float(np.sqrt(np.mean(samples.astype(np.float64) ** 2))) if samples.size else 0)
            if len(values) % max(1, round(120 / interval)) == 0:
                log(f"Áudio analisado: {len(values) * interval:.0f} s.")
        if process.wait() != 0:
            raise RuntimeError("O FFmpeg não conseguiu analisar a faixa de áudio.")
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.kill()
        process.wait()
    result = np.zeros(bins, dtype=np.float64)
    count = min(len(values), bins)
    result[:count] = values[:count]
    return np.nan_to_num(result, nan=0, posinf=0, neginf=0)


def _normalise(values: np.ndarray, floor: float) -> np.ndarray:
    values = np.maximum(np.nan_to_num(values, nan=0, posinf=0, neginf=0), 0)
    high = max(float(np.percentile(values, 95)), floor)
    return np.clip(values / high, 0, 1)


def _overlap(a: dict, b: dict) -> bool:
    return min(a["end"], b["end"]) - max(a["start"], b["start"]) > .001


def _window(peak: float, length: float, duration: float) -> tuple[float, float]:
    length = min(length, duration)
    start = max(0, min(peak - length * .4, duration - length))
    return round(start, 3), round(start + length, 3)


def _diverse(items: list[dict], duration: float, count: int, budget: float | None = None) -> list[dict]:
    """Seleciona momentos e reserva o custo real de cada trecho em quadros."""
    selected: list[dict] = []
    pending = [dict(item) for item in items]
    # The renderer rounds each excerpt up to a complete frame. Account for that
    # cost before selection, instead of rounding only the summed raw seconds.
    remaining_frames = math.floor(budget * FPS) if budget is not None else None
    spacing = duration / max(1, count)
    while pending and len(selected) < count and (remaining_frames is None or remaining_frames > 0):
        def rank(item):
            distance = min((abs(item["peak"] - old["peak"]) for old in selected), default=spacing)
            diversity = min(1.0, distance / max(1, spacing))
            # All-zero signals still prefer distributed examples for review.
            score = .1 + item["score"]
            return (item.get("manual", False), score * (.65 + .35 * diversity),
                    -abs(item["peak"] - duration / 2))
        item = max(pending, key=rank)
        pending.remove(item)
        if any(_overlap(item, old) for old in selected):
            continue
        length = item["end"] - item["start"]
        frames = math.ceil(length * FPS - 1e-7)
        if remaining_frames is not None and frames > remaining_frames:
            remaining = remaining_frames / FPS
            # Preserve context for the last excerpt; avoid pointless 1-second tails.
            if remaining < min(8.0, length):
                continue
            # Keep sub-millisecond precision: rounding a 2/30-second boundary to
            # 0.067 would introduce one extra encoded frame and exceed the budget.
            item["end"] = item["start"] + remaining
            frames = math.ceil((item["end"] - item["start"]) * FPS - 1e-7)
            if frames > remaining_frames:
                # Subtraction at very large source timestamps can round upwards.
                item["end"] = math.nextafter(item["end"], item["start"])
                frames = math.ceil((item["end"] - item["start"]) * FPS - 1e-7)
            item["peak"] = min(item["peak"], item["end"])
            item["reason"] += "; encurtado para respeitar o orçamento do vídeo longo"
        selected.append(item)
        if remaining_frames is not None:
            remaining_frames -= frames
    return sorted(selected, key=lambda item: item["start"])


def select_moments(times: np.ndarray, scores: np.ndarray, duration: float, *,
                   max_long: float = 660, short_count: int = 3, short_seconds: float = 45,
                   markers: list[dict] | None = None, lang: str = "pt") -> tuple[list, list, list]:
    """Seleção determinística; função separada para testar limites e marcadores."""
    times = np.asarray(times, dtype=np.float64)
    scores = np.clip(np.nan_to_num(np.asarray(scores, dtype=np.float64)), 0, 1)
    if times.size != scores.size or not times.size:
        raise ValueError("Amostras de tempo e atividade precisam ter o mesmo tamanho e não estar vazias.")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("Duração da fonte inválida.")
    candidates: list[dict] = []
    for index, marker in enumerate(markers or []):
        if not isinstance(marker, dict) or "start" not in marker or "end" not in marker:
            raise ValueError("Cada marcador precisa conter start e end.")
        start, end = _seconds(marker["start"]), _seconds(marker["end"])
        if end <= start or end > duration + .001:
            raise ValueError(f"Marcador {index + 1}: o intervalo deve estar dentro da fonte.")
        peak = (start + end) / 2
        candidate = {"id": f"manual-{index + 1:02}", "start": start,
                     "end": min(end, duration), "peak": round(peak, 3),
                     "title": str(marker.get("title") or (f"Momento {index + 1:02}" if lang == "pt" else f"Moment {index + 1:02}")),
                     "reason": "marcador informado pelo editor" if lang == "pt" else "editor-supplied marker",
                     "score": 1.0, "manual": True}
        if any(_overlap(candidate, previous) for previous in candidates):
            raise ValueError("Os marcadores não podem se sobrepor. Una ou ajuste os intervalos.")
        candidates.append(candidate)
    context = min(short_seconds, duration)
    target = max(12, math.ceil(max_long / max(1, context)) * 3, short_count * 4)
    # A candidate per region provides coverage even in a quiet, multi-hour stream.
    regions = min(len(times), target)
    region_peaks = []
    for region in np.array_split(np.arange(len(times)), regions):
        peak_index = int(region[int(np.argmax(scores[region]))])
        region_peaks.append(peak_index)
    ordered = sorted(region_peaks, key=lambda i: (-scores[i], abs(times[i] - duration / 2)))
    ordered.extend(sorted(range(len(times)), key=lambda i: (-scores[i], abs(times[i] - duration / 2))))
    for index in ordered:
        start, end = _window(float(times[index]), context, duration)
        candidate = {"id": "", "start": start, "end": end,
                     "peak": round(min(float(times[index]), duration), 3),
                     "title": "",
                     "reason": ("sinais de movimento e/ou energia sonora; revisar contexto" if scores[index] > .15 else
                                "sinais baixos; amostra de contexto para revisão"),
                     "score": round(float(scores[index]), 5), "manual": False}
        if any(_overlap(candidate, previous) for previous in candidates):
            continue
        candidate["id"] = f"auto-{len(candidates) + 1:02}"
        # Título único por corte (número + tempo da fonte); o editor troca na revisão.
        candidate["title"] = (f"Momento {len(candidates) + 1:02} · {_stamp(candidate['peak'])}" if lang == "pt"
                              else f"Moment {len(candidates) + 1:02} · {_stamp(candidate['peak'])}")
        candidates.append(candidate)
        if len(candidates) >= target + len(markers or []):
            break
    long = _diverse(candidates, duration, max(1, math.ceil(max_long / max(1, context)) + len(markers or [])), max_long)
    short_items = []
    if duration >= 30:
        # Use one complete context window per suggestion, including short human markers.
        length = min(short_seconds, duration)
        for candidate in candidates:
            item = dict(candidate)
            start, end = _window(item["peak"], length, duration)
            # For a longer manual marker, stay within the selected human interval.
            if item.get("manual") and candidate["end"] - candidate["start"] >= length:
                start = max(candidate["start"], min(start, candidate["end"] - length))
                end = start + length
            item.update(start=round(start, 3), end=round(end, 3))
            short_items.append(item)
    shorts = _diverse(short_items, duration, short_count)
    return sorted(candidates, key=lambda item: item["start"]), long, shorts


def _stamp(seconds: float) -> str:
    value = max(0, round(seconds))
    return f"{value // 3600:02}:{value // 60 % 60:02}:{value % 60:02}"


def _storyboard(path: Path, selected: list[dict], output: Path, log) -> list[str]:
    items = selected[:40]
    columns, tile_w, tile_h = 4, 320, 224
    image = Image.new("RGB", (columns * tile_w, math.ceil(len(items) / columns) * tile_h + 48), "#0B0614")
    draw = ImageDraw.Draw(image)
    heading = gfx.font("body", 20)
    small = gfx.font("body", 15)
    draw.text((16, 12), "QUADROS REAIS — REVISAR CONTEXTO, TÍTULO E CONTEÚDO", font=heading, fill="#FFC857")
    for index, item in enumerate(items):
        if index % 8 == 0:
            log(f"Montando storyboard: {index}/{len(items)} quadros.")
        command = ["ffmpeg", "-v", "error", "-nostdin", "-ss", f"{item['peak']:.3f}",
                   "-i", str(path), "-frames:v", "1", "-vf", "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"]
        result = subprocess.run(command, capture_output=True, check=False)
        x, y = index % columns * tile_w, index // columns * tile_h + 48
        if result.returncode == 0 and len(result.stdout) == 320 * 180 * 3:
            frame = Image.frombytes("RGB", (320, 180), result.stdout)
            image.paste(frame, (x, y))
        else:
            raise RuntimeError(f"Não foi possível extrair o quadro {item['id']} para revisão.")
        draw.text((x + 8, y + 183), f"{item['id']} · {_stamp(item['start'])}–{_stamp(item['end'])}", font=small, fill="white")
        draw.text((x + 8, y + 204), f"pico {_stamp(item['peak'])} · sinal {item['score']:.2f}", font=small, fill="#FFC857")
    image.save(output, quality=92)
    return [item["id"] for item in items]


def analyze(source: str, output: Path, *, max_long: float = 660, short_count: int = 3,
            short_seconds: float = 45, title: str = "Melhores momentos de GTA", credit: str = "",
            lang: str = "pt", markers: list[dict] | None = None, log=print) -> dict:
    """Baixa/lê uma fonte e grava plan.json + storyboard.jpg em uma pasta nova."""
    max_long, short_seconds = float(max_long), float(short_seconds)
    if not math.isfinite(max_long) or not 0 < max_long <= 660:
        raise ValueError("O vídeo longo deve ter um limite entre 1 e 660 segundos (11 minutos).")
    if not math.isfinite(short_seconds) or not 30 <= short_seconds <= 60:
        raise ValueError("Os cortes verticais devem ter de 30 a 60 segundos.")
    if isinstance(short_count, bool) or not isinstance(short_count, int) or short_count < 0:
        raise ValueError("A quantidade de shorts precisa ser um inteiro maior ou igual a zero.")
    if lang not in ("pt", "en"):
        raise ValueError("Idioma inválido: use pt ou en.")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "plan.json").exists() or (output / "storyboard.jpg").exists():
        raise FileExistsError("A pasta já contém uma análise. Crie uma versão nova para preservá-la.")
    path, url, source_title, credit = _resolve(str(source), credit, log)
    info = probe(path)
    duration = info["duration"]
    # Only the sample density is bounded; 30-minute and longer sources remain valid.
    interval = max(2.0, duration / 15000)
    log(f"Fonte: {duration / 60:.1f} minutos. Análise local, uma amostra a cada {interval:.1f} s.")
    motion = _motion(path, duration, interval, log)
    energy = _energy(path, interval, len(motion), log) if info["has_audio"] else np.zeros(len(motion))
    motion_score = _normalise(motion, .025)
    audio_score = _normalise(energy, .008)
    scores = .65 * motion_score + .35 * audio_score if energy.max() > .001 else motion_score
    # A short smoothing window avoids selecting an isolated compression glitch.
    if len(scores) >= 3:
        scores = np.convolve(scores, np.array([.2, .6, .2]), mode="same")
    times = np.minimum((np.arange(len(scores)) + .5) * interval, max(0, duration - .1))
    candidates, long, shorts = select_moments(times, scores, duration, max_long=max_long,
                                            short_count=short_count, short_seconds=short_seconds,
                                            markers=markers, lang=lang)
    if not long:
        raise ValueError("Nenhum trecho aproveitável foi encontrado dentro do orçamento informado.")
    review_items = []
    for item in long + shorts + candidates:
        if item["id"] not in [old["id"] for old in review_items]:
            review_items.append(item)
    storyboard_ids = _storyboard(path, review_items, output / "storyboard.jpg", log)
    plan = {"version": 1, "source": {"path": str(path), "url": url, "title": source_title,
            "credit": credit, "duration": duration, "has_audio": info["has_audio"]},
            "language": lang, "title": str(title), "max_long_seconds": max_long,
            "short_seconds": short_seconds, "candidates": candidates, "long": long, "shorts": shorts,
            "analysis": {"method": "local-motion-audio-energy", "requires_review": True,
            "sample_interval_seconds": interval, "sample_count": len(scores),
            "storyboard_candidate_ids": storyboard_ids, "source_width": info["width"],
            "source_height": info["height"], "requested_shorts": short_count,
            "selected_shorts": len(shorts), "limitations": [
                "Sinais técnicos sugerem trechos; não compreendem falas, objetivos ou contexto narrativo.",
                "Revisar os intervalos, os títulos e o conteúdo antes de entregar ou publicar.",
                "Não há garantia de viralização; nenhuma classificação automática de GTA VI é realizada."],
            "warnings": (["Fonte menor que 30 segundos: nenhum short foi esticado."] if duration < 30 else [])}}
    with (output / "plan.json").open("x", encoding="utf-8") as handle:
        json.dump(plan, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    log(f"Plano criado: {len(long)} trechos para o longo e {len(shorts)} shorts. Revise o storyboard e plan.json.")
    return plan
