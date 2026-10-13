"""Legendas da fala, reconhecidas no computador e editáveis antes da exportação.

O áudio vem do arquivo de origem, antes de adicionar a música do editor. Texto
que já aparece na imagem do jogo não participa da transcrição. O idioma da fala
é independente do idioma usado na capa. A saída automática exige revisão.
"""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent


def _external_runtime() -> tuple[Path, Path] | None:
    """Runtime explícito ou instalação local anterior; sem caminhos pessoais no git."""
    configured = os.environ.get("LEONIDA_STT_PYTHON")
    deps_configured = os.environ.get("LEONIDA_STT_DEPS")
    if configured:
        executable = Path(configured).expanduser()
        deps = Path(deps_configured).expanduser() if deps_configured else Path()
        if executable.is_file() and (not deps_configured or (deps / "faster_whisper").is_dir()):
            return executable, deps
        return None
    executable = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
    if executable.is_file():
        for deps in (ROOT / ".cache/gameplay-v2-captions/deps", ROOT / ".cache/speech/deps"):
            if (deps / "faster_whisper").is_dir():
                return executable, deps
    return None


def available() -> bool:
    """Confirma a presença das dependências; a exportação informa falhas de carga."""
    return _external_runtime() is not None or importlib.util.find_spec("faster_whisper") is not None


def normalize_cues(cues: list | dict, duration: float | None = None) -> list[dict]:
    """Valida a transcrição editável sem inventar, traduzir ou preencher palavras."""
    if isinstance(cues, dict):
        cues = cues.get("segments", cues.get("cues", []))
    if not isinstance(cues, list):
        raise ValueError("Legendas precisam ser uma lista de falas com início, fim e texto.")
    if duration is not None and (not math.isfinite(duration) or duration <= 0):
        raise ValueError("Duração precisa ser positiva e finita.")
    result = []
    for item in cues:
        if not isinstance(item, dict):
            raise ValueError("Cada fala precisa ser um objeto com início, fim e texto.")
        try:
            start, end = float(item["start"]), float(item["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Fala sem início/fim numérico.") from exc
        text = item.get("text")
        if (not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start or
                duration is not None and end > duration + .05):
            raise ValueError("Fala fora da duração ou com intervalo inválido.")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Texto de cada fala precisa ser uma string não vazia.")
        if len(text) > 10000:
            raise ValueError("Uma fala é longa demais; divida a transcrição em intervalos.")
        row = dict(item)
        row.update(start=start, end=end, text=" ".join(text.split()))
        if "words" in row:
            if not isinstance(row["words"], list):
                raise ValueError("Palavras precisam ser uma lista com início, fim e texto.")
            words = []
            for word in row["words"]:
                if not isinstance(word, dict):
                    raise ValueError("Cada palavra precisa conter início, fim e texto.")
                try:
                    left, right = float(word["start"]), float(word["end"])
                except (KeyError, ValueError, TypeError) as exc:
                    raise ValueError("Palavra sem início/fim numérico.") from exc
                literal = word.get("word")
                if (not math.isfinite(left) or not math.isfinite(right) or left < 0 or right <= left or
                        left < start - .05 or right > end + .05 or not isinstance(literal, str) or not literal.strip()):
                    raise ValueError("Palavra fora da fala ou com texto/intervalo inválido.")
                words.append({**word, "start": left, "end": right, "word": literal.strip()})
            row["words"] = words
        result.append(row)
    return sorted(result, key=lambda row: (row["start"], row["end"]))


def remap_cues(cues: list | dict, moments: list[dict], *, frame_rate: float | None = None) -> list[dict]:
    """Sincroniza falas da origem com cortes concatenados, inclusive cortes repetidos."""
    if frame_rate is not None and (not math.isfinite(frame_rate) or frame_rate <= 0):
        raise ValueError("Taxa de quadros precisa ser positiva e finita.")
    clean = normalize_cues(cues)
    offset = 0.0
    remapped = []
    for moment in moments:
        start, end = float(moment["start"]), float(moment["end"])
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ValueError("Intervalo inválido para sincronizar a fala.")
        for cue in clean:
            left, right = max(start, cue["start"]), min(end, cue["end"])
            if right <= left:
                continue
            row = dict(cue)
            row.update(start=offset + left - start, end=offset + right - start,
                       source_start=left, source_end=right)
            words = cue.get("words")
            if isinstance(words, list) and words:
                kept = []
                for word in words:
                    if word["end"] <= start or word["start"] >= end:
                        continue
                    changed = dict(word)
                    changed.update(start=offset + max(start, word["start"]) - start,
                                   end=offset + min(end, word["end"]) - start)
                    kept.append(changed)
                row["words"] = kept
                # With word timestamps, do not repeat words removed by the cut.
                if kept:
                    row["text"] = " ".join(w.get("word", "").strip() for w in kept).strip()
                else:
                    continue
            remapped.append(row)
        length = end - start
        offset += math.ceil(length * frame_rate - 1e-7) / frame_rate if frame_rate else length
    return normalize_cues(remapped)


def _time(seconds: float, *, ass=False) -> str:
    if ass:
        units = max(0, round(seconds * 100))
        hours, units = divmod(units, 360000)
        minutes, units = divmod(units, 6000)
        secs, hundredths = divmod(units, 100)
        return f"{hours}:{minutes:02}:{secs:02}.{hundredths:02}"
    units = max(0, round(seconds * 1000))
    hours, units = divmod(units, 3600000)
    minutes, units = divmod(units, 60000)
    secs, milliseconds = divmod(units, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def write_srt(cues: list | dict, out: Path) -> Path:
    clean = normalize_cues(cues)
    text = "\n\n".join(f'{i}\n{_time(c["start"])} --> {_time(c["end"])}\n{c["text"]}'
                       for i, c in enumerate(clean, 1))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    return out


def _subtitle_chunks(cue: dict, font, max_width: int) -> list[dict]:
    """No máximo duas linhas; distribui blocos sem mudar as palavras da fala."""
    words = cue["text"].split()
    if any(font.getlength(word) > max_width for word in words):
        raise ValueError("Uma palavra da legenda não cabe na área segura; revise o SRT ou reduza a fonte.")
    lines, line = [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if line and font.getlength(candidate) > max_width:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    groups = [lines[index:index + 2] for index in range(0, len(lines), 2)]
    total = sum(len(" ".join(group)) for group in groups)
    left = cue["start"]
    result = []
    for index, group in enumerate(groups):
        right = cue["end"] if index == len(groups) - 1 else left + (cue["end"] - cue["start"]) * len(" ".join(group)) / total
        result.append({**cue, "start": left, "end": right, "lines": group})
        left = right
    return result


def write_ass(cues: list | dict, out: Path, *, size=(1080, 1920), y=1360, x=None,
              font_size=60, max_width=866) -> Path:
    """ASS abaixo da gameplay; duas linhas brancas com contorno, sem cobrir o HUD."""
    from . import gfx
    width, height = map(int, size)
    x = width // 2 if x is None else int(x)
    if width <= 0 or height <= 0 or not 0 <= int(y) < height or font_size < 12:
        raise ValueError("Dimensões/posição inválidas para as legendas.")
    if max_width <= 0 or max_width > width:
        raise ValueError("Largura da legenda precisa caber no vídeo.")
    if x - max_width / 2 < 0 or x + max_width / 2 > width:
        raise ValueError("Legenda ultrapassa as laterais do vídeo.")
    font = gfx.font("bold", int(font_size))
    clean = normalize_cues(cues)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Speech,Inter,{font_size},&H00FFFFFF,&H0057C8FF,&H0014060B,&H78000000,-1,0,0,0,100,100,0,0,1,4,1,8,64,150,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    for cue in clean:
        for chunk in _subtitle_chunks(cue, font, max_width):
            # Never let editable speech text execute ASS override tags.
            text = r"\N".join(line.replace("\\", "＼").replace("{", "(").replace("}", ")") for line in chunk["lines"])
            position = r"{\an8\pos(" + f"{x},{int(y)}" + ")}"
            lines.append(f'Dialogue: 0,{_time(chunk["start"], ass=True)},{_time(chunk["end"], ass=True)},Speech,,0,0,0,,{position}{text}')
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(header + "\n".join(lines) + "\n", encoding="utf-8")
    return out


def transcribe(source: Path, output: Path, language="auto", model="small", *,
               audio_stream: int = 0, log=print) -> dict:
    """Reconhece áudio da origem; nunca envia mídia para serviços de transcrição."""
    if language not in ("pt", "en", "auto", None):
        raise ValueError("Idioma da fala precisa ser pt, en ou auto.")
    if isinstance(audio_stream, bool) or not isinstance(audio_stream, int) or audio_stream < 0:
        raise ValueError("Faixa de áudio precisa ser um índice inteiro não negativo.")
    source, output = Path(source).resolve(), Path(output).resolve()
    if not source.is_file():
        raise FileNotFoundError("Arquivo de áudio/vídeo da origem não encontrado.")
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("FFmpeg não encontrado para extrair a fala.")
    runtime = _external_runtime()
    if not runtime and not available():
        raise RuntimeError("Transcrição local indisponível. Instale requirements-speech.txt em Python 3.12 ou configure LEONIDA_STT_PYTHON/LEONIDA_STT_DEPS.")
    from .config import CACHE_DIR
    cache = Path(CACHE_DIR) / "speech"
    cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    models = Path(os.environ.get("LEONIDA_STT_MODELS", ROOT / ".cache/gameplay-v2-captions/models"))
    if not models.parent.exists():
        models = cache / "models"
    log(f"  [fala] transcrição local CPU: {model}; idioma {language or 'auto'}; sem OCR do jogo")
    with tempfile.TemporaryDirectory(prefix="stt-", dir=cache) as directory:
        scratch = Path(directory)
        wav = scratch / "source-speech.wav"
        # Only source audio is mapped. The editor's new soundtrack is added later.
        command = [ff, "-v", "error", "-nostdin", "-i", str(source), "-map", f"0:a:{audio_stream}",
                   "-vn", "-af", "highpass=f=80,lowpass=f=7600,loudnorm=I=-18:TP=-2:LRA=9",
                   "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
        extracted = subprocess.run(command, capture_output=True)
        if extracted.returncode:
            raise RuntimeError("Não foi possível extrair a faixa de áudio da origem para as legendas.")
        request = scratch / "request.json"
        temporary_result = scratch / "result.json"
        request.write_text(json.dumps({"audio": str(wav), "output": str(temporary_result),
                                      "language": language, "model": str(model), "models": str(models)}), encoding="utf-8")
        executable, deps = runtime if runtime else (Path(sys.executable), None)
        env = os.environ.copy()
        env.update(PYTHONIOENCODING="utf-8", PYTHONUTF8="1", HF_HUB_DISABLE_TELEMETRY="1",
                   DO_NOT_TRACK="1", HF_HUB_DISABLE_XET="1", OMP_NUM_THREADS="4")
        if deps and str(deps) != ".":
            env["PYTHONPATH"] = str(deps)
        command = [str(executable), "-B", "-u", "-X", "utf8", str(Path(__file__).resolve()),
                   "--stt-worker", str(request)]
        completed = subprocess.run(command, capture_output=True, env=env)
        if completed.returncode or not temporary_result.is_file():
            # The detailed worker exception can contain local paths or transport settings.
            raise RuntimeError("A transcrição local falhou ao carregar o modelo ou reconhecer a fala. Confira o runtime/dependências e a disponibilidade do modelo; nenhuma mídia foi enviada.")
        data = json.loads(temporary_result.read_text(encoding="utf-8"))
    data.update(source=str(source), audio_stream=audio_stream, source_audio=True, added_music=False,
                subtitle_source="spoken_audio", reviewed=False, review_status="automatic_requires_review",
                speaker_separation=False,
                mixed_language_warning="Falas do criador e do jogo na mesma faixa exigem revisão; o ASR não identifica os locutores nem separa seus áudios.")
    data["segments"] = normalize_cues(data["segments"])
    # Trecho só com jogo/música é normal num corte: sai sem legenda, sem derrubar a exportação.
    data["no_speech"] = not data["segments"]
    if data["no_speech"]:
        log("  [fala] nenhuma fala reconhecida neste trecho; ele sai sem legenda")
    output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_srt(data, output.with_suffix(".srt"))
    return data


def _worker(request_path: Path):
    """Executado em runtime compatível; arquivos locais entram e saem deste processo."""
    import wave
    import numpy as np
    from faster_whisper import WhisperModel
    request = json.loads(request_path.read_text(encoding="utf-8"))
    model = WhisperModel(request["model"], device="cpu", compute_type="int8", cpu_threads=4,
                         download_root=request["models"],
                         local_files_only=os.environ.get("LEONIDA_STT_OFFLINE") == "1")
    language = request.get("language")
    language = None if language == "auto" else language
    # WAV extraction is deliberately fixed to mono 16-bit/16 kHz. Decoding with
    # stdlib avoids PyAV-version incompatibilities in isolated Windows runtimes.
    with wave.open(request["audio"], "rb") as wav:
        if wav.getsampwidth() != 2 or wav.getnchannels() != 1 or wav.getframerate() != 16000:
            raise ValueError("O worker requer áudio PCM mono de 16 kHz.")
        audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    segments, info = model.transcribe(audio, language=language, task="transcribe",
                                     word_timestamps=True, beam_size=5, vad_filter=True,
                                     condition_on_previous_text=False, temperature=0)
    rows = []
    for segment in segments:
        text = segment.text.strip()
        if not text or segment.end <= segment.start:
            continue
        words = [{"start": w.start, "end": w.end, "word": w.word.strip(), "probability": w.probability}
                 for w in (segment.words or []) if w.end > w.start]
        uncertain = segment.avg_logprob < -1 or segment.no_speech_prob > .7 or any(w["probability"] < .25 for w in words)
        rows.append({"start": segment.start, "end": segment.end, "text": text, "words": words,
                     "avg_logprob": segment.avg_logprob, "no_speech_prob": segment.no_speech_prob,
                     "needs_review": uncertain, "speaker": "unidentified"})
    result = {"version": 1, "method": f"faster-whisper {request['model']} CPU int8 local",
              "language": info.language, "language_probability": info.language_probability,
              "segments": rows}
    Path(request["output"]).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--stt-worker":
        raise SystemExit("Este módulo usa um worker local; use a API transcribe no editor.")
    _worker(Path(sys.argv[2]))
