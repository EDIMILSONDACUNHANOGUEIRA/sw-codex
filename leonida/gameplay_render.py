"""Exportação local de melhores momentos com gameplay inteira e capas de quadros reais.

O plano é revisável antes da exportação. Não há publicação automática nem geração de
rostos: os arquivos finais só aparecem quando todos os vídeos passam pela decodificação.
"""
from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from . import gfx
from .config import brand

FPS = 30
LONG_SIZE = (1920, 1080)
SHORT_SIZE = (1080, 1920)
SHORT_WINDOW = (0, 620, 1080, 608)
MAX_LONG_SECONDS = 660


def _run(args: list[str], *, cwd: Path | None = None) -> bytes:
    proc = subprocess.run(args, capture_output=True, cwd=cwd)
    if proc.returncode:
        # Limit diagnostics; never include cookies, environment variables or headers.
        message = proc.stderr.decode("utf-8", "replace")[-2200:].strip()
        raise RuntimeError(f"FFmpeg não concluiu a exportação: {message}")
    return proc.stdout


def _probe(path: Path) -> dict:
    probe = shutil.which("ffprobe")
    if not probe:
        raise RuntimeError("ffprobe não encontrado; instale o FFmpeg antes de exportar.")
    return json.loads(_run([probe, "-v", "error", "-show_streams", "-show_format",
                            "-of", "json", str(path)]))


def _duration(meta: dict) -> float:
    duration = float(meta.get("format", {}).get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("O arquivo de origem não tem duração válida.")
    return duration


def _remove_scratch(path: Path, parent: Path, expected_name: str):
    """Remove only the named scratch folder created by this export invocation."""
    resolved = path.resolve()
    if path.name != expected_name or resolved.parent != parent.resolve() or path.is_symlink():
        raise RuntimeError("Pasta temporária mudou de localização; limpeza cancelada.")
    shutil.rmtree(resolved)


def _validate(plan: dict) -> tuple[Path, dict]:
    if not isinstance(plan, dict) or plan.get("version", 1) != 1:
        raise ValueError("Plano de gameplay precisa usar a versão 1.")
    lang = plan.get("language", "pt")
    if lang not in ("pt", "en"):
        raise ValueError("Idioma precisa ser pt ou en.")
    source = plan.get("source") or {}
    path = Path(source.get("path") or "")
    if not path.is_file():
        raise ValueError("Arquivo de origem não encontrado no plano.")
    meta = _probe(path)
    if not any(s.get("codec_type") == "video" for s in meta.get("streams", [])):
        raise ValueError("A origem precisa conter vídeo.")
    duration = _duration(meta)
    maximum = float(plan.get("max_long_seconds", MAX_LONG_SECONDS))
    if not math.isfinite(maximum) or not 0 < maximum <= MAX_LONG_SECONDS:
        raise ValueError("O vídeo longo pode ter no máximo 11 minutos (660 segundos).")
    target = float(plan.get("short_seconds", 45))
    if not math.isfinite(target) or not 30 <= target <= 60:
        raise ValueError("Shorts precisam ter de 30 a 60 segundos.")
    long = plan.get("long") or []
    shorts = plan.get("shorts") or []
    if not isinstance(long, list) or not isinstance(shorts, list) or not (long or shorts):
        raise ValueError("O plano precisa conter ao menos um momento para exportar.")
    total = 0.0
    for kind, moments in (("long", long), ("shorts", shorts)):
        for moment in moments:
            if not isinstance(moment, dict):
                raise ValueError("Cada momento precisa ser um objeto com início e fim.")
            try:
                start, end = float(moment["start"]), float(moment["end"])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Momento sem início/fim numérico.") from exc
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start or end > duration + .05:
                raise ValueError("Momento fora da duração da origem ou com intervalo inválido.")
            length = end - start
            if kind == "shorts" and not 30 - 1e-6 <= length <= 60 + 1e-6:
                raise ValueError("Cada short precisa ter de 30 a 60 segundos.")
            # Encodes use complete frames; account for their actual duration in the budget.
            if kind == "long":
                total += math.ceil(length * FPS - 1e-7) / FPS
    if total > maximum + 1e-6:
        raise ValueError("A soma dos cortes supera o limite do vídeo longo.")
    return path.resolve(), meta


def _fit_text(draw: ImageDraw.ImageDraw, text: str, width: int, *, size=90, minimum=36,
              lines=3, kind="display") -> tuple[object, list[str]]:
    text = " ".join(str(text).replace("*", "").split()) or "GAMEPLAY"
    for px in range(size, minimum - 1, -2):
        font = gfx.font(kind, px)
        wrapped = gfx.wrap_text(text, font, width)
        if len(wrapped) <= lines and all(draw.textlength(line, font=font) <= width for line in wrapped):
            return font, wrapped
    font = gfx.font(kind, minimum)
    wrapped = gfx.wrap_text(text, font, width)
    # Full text is retained in caption/manifest. A single unbroken word can also
    # exceed the canvas even when the number of wrapped lines is within budget.
    omitted_lines = len(wrapped) > lines
    visible = []
    for index, line in enumerate(wrapped[:lines]):
        needs_ellipsis = (draw.textlength(line, font=font) > width or
                          (omitted_lines and index == lines - 1))
        if needs_ellipsis:
            while line and draw.textlength(line.rstrip() + "…", font=font) > width:
                line = line[:-1]
            line = line.rstrip() + "…"
            if draw.textlength(line, font=font) > width:
                line = ""
        visible.append(line)
    return font, visible


def _line(draw, xy, text, width, *, size=30, color="white", kind="bold"):
    font, lines = _fit_text(draw, text, width, size=size, minimum=max(18, size - 14), lines=1, kind=kind)
    draw.text(xy, lines[0], font=font, fill=color)


def _overlay(size: tuple[int, int], title: str, credit: str, lang: str) -> Image.Image:
    w, h = size
    image = Image.new("RGBA", size)
    draw = ImageDraw.Draw(image)
    handle = brand()["handle"][lang]
    if size == LONG_SIZE:
        draw.rectangle((0, 0, w, 69), fill="#0B0614")
        draw.rectangle((0, 68, w, 71), fill="#FF2E88")
        _line(draw, (26, 18), "LEONIDA WIRE", 360, size=31)
        _line(draw, (408, 22), title, 845, size=27, kind="body")
        _line(draw, (1290, 23), handle, 390, size=24, color="#FFC857")
        # Credit is in the header, never on the game's map or subtitles.
        _line(draw, (1660, 24), credit, 234, size=21, kind="body")
    else:
        x, y, vw, vh = SHORT_WINDOW
        draw.rectangle((0, 0, w, 575), fill=(11, 6, 20, 190))
        draw.rectangle((0, 1260, w, h), fill=(11, 6, 20, 205))
        _line(draw, (64, 170), "LEONIDA WIRE", 866, size=48)
        draw.rectangle((64, 246, 206, 252), fill="#FF2E88")
        label = "MOMENTO DA GAMEPLAY" if lang == "pt" else "GAMEPLAY MOMENT"
        _line(draw, (64, 286), label, 866, size=28, color="#FFC857")
        font, lines = _fit_text(draw, title, 866, size=72, minimum=44, lines=3)
        for index, text in enumerate(lines):
            draw.text((64, 342 + index * (font.size + 10)), text, font=font, fill="white")
        draw.rectangle((x, y - 4, x + vw - 1, y + vh + 4), outline="#FFC857", width=3)
        credit_label = ("Crédito: " if lang == "pt" else "Credit: ") + credit
        _line(draw, (64, 1287), credit_label, 866, size=29, kind="body")
        _line(draw, (64, 1378), handle, 866, size=42, color="#FFC857")
        question = "QUAL FOI O MELHOR MOMENTO?" if lang == "pt" else "WHICH MOMENT WAS THE BEST?"
        _line(draw, (64, 1480), question, 866, size=29)
    return image


def _extract_frame(ff: str, source: Path, at: float, out: Path):
    _run([ff, "-v", "error", "-nostdin", "-ss", str(max(0, at)), "-i", str(source),
          "-frames:v", "1", "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease",
          "-update", "1", "-y", str(out)])
    if not out.is_file() or out.stat().st_size == 0:
        raise RuntimeError("Não foi possível extrair o quadro real para a capa.")


def _cover(frame: Path, overlay: Image.Image, title: str, size: tuple[int, int], out: Path):
    with Image.open(frame) as opened:
        actual = opened.convert("RGB")
    if size == SHORT_SIZE:
        bg = ImageOps.fit(actual, size, method=Image.Resampling.LANCZOS).filter(ImageFilter.GaussianBlur(30))
        bg = Image.blend(bg, Image.new("RGB", size, "#0B0614"), .35).convert("RGBA")
        x, y, vw, vh = SHORT_WINDOW
        # Foreground is contained, so every pixel of the source frame remains visible.
        viewport = Image.new("RGB", (vw, vh), "#0B0614")
        contained = ImageOps.contain(actual, (vw, vh), Image.Resampling.LANCZOS)
        viewport.paste(contained, ((vw - contained.width) // 2, (vh - contained.height) // 2))
        bg.paste(viewport, (x, y))
        bg.alpha_composite(overlay)
    else:
        bg = ImageOps.pad(actual, size, method=Image.Resampling.LANCZOS, color="#0B0614").convert("RGBA")
        shade = Image.new("RGBA", size)
        draw = ImageDraw.Draw(shade)
        for row in range(420, size[1]):
            alpha = min(220, int((row - 420) / (size[1] - 420) * 235))
            draw.line((0, row, size[0], row), fill=(11, 6, 20, alpha))
        bg.alpha_composite(shade)
        draw = ImageDraw.Draw(bg)
        font, lines = _fit_text(draw, title, size[0] - 144, size=118, minimum=54, lines=3)
        top = size[1] - 115 - len(lines) * (font.size + 12)
        for i, line in enumerate(lines):
            draw.text((72, top + i * (font.size + 12)), line, font=font, fill="white", stroke_width=2,
                      stroke_fill="#0B0614")
        bg.alpha_composite(overlay)
    bg.convert("RGB").save(out, quality=95, subsampling=0)


def _encode_clip(ff: str, source: Path, moment: dict, out: Path, overlay_path: Path,
                 *, vertical: bool, has_audio: bool):
    duration = float(moment["end"]) - float(moment["start"])
    inputs = ["-ss", str(moment["start"]), "-t", str(duration), "-i", str(source),
              "-loop", "1", "-i", str(overlay_path)]
    if not has_audio:
        inputs += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
    if vertical:
        x, y, w, h = SHORT_WINDOW
        vf = ("[0:v]split=2[whole][back];"
              "[back]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,"
              "boxblur=10:2,scale=1080:1920,eq=brightness=-0.12[bg];"
              f"[whole]scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0x0B0614[game];"
              f"[bg][game]overlay={x}:{y}[base];[base][1:v]overlay=0:0,fps={FPS},setsar=1[v]")
    else:
        vf = ("[0:v]scale=1920:1010:force_original_aspect_ratio=decrease:flags=lanczos,"
              "pad=1920:1010:(ow-iw)/2:(oh-ih)/2:color=0x0B0614,"
              f"pad=1920:1080:0:70:color=0x0B0614[base];[base][1:v]overlay=0:0,fps={FPS},setsar=1[v]")
    fade = min(.06, duration / 4)
    audio_index = 0 if has_audio else 2
    vf += (f";[{audio_index}:a:0]aresample=48000,aformat=channel_layouts=stereo,"
           f"afade=t=in:st=0:d={fade},afade=t=out:st={max(0, duration - fade)}:d={fade}[a]")
    _run([ff, "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "2", *inputs,
          "-filter_complex", vf, "-map", "[v]", "-map", "[a]", "-t", str(duration),
          "-r", str(FPS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-threads", "4",
          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
          "-movflags", "+faststart", str(out)])


def _finalize(ff: str, base: Path, out: Path, theme: Path | None, *, seconds: float, ass: Path | None = None):
    args = [ff, "-v", "error", "-nostdin", "-y", "-filter_complex_threads", "2", "-i", str(base)]
    if theme:
        args += ["-stream_loop", "-1", "-i", str(theme)]
        audio = ("[0:a]asplit=2[dry][control];[1:a]aresample=48000,volume=0.10[bed];"
                 "[bed][control]sidechaincompress=threshold=0.025:ratio=8:attack=20:release=400[duck];"
                 "[dry][duck]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]")
        args += ["-filter_complex", audio, "-map", "0:v:0", "-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    else:
        args += ["-map", "0:v:0", "-map", "0:a:0", "-c:a", "copy"]
    if ass:
        # Relative filename avoids drive-letter/filter escaping on Windows.
        args += ["-vf", f"subtitles=filename={ass.name}", "-c:v", "libx264", "-preset", "veryfast",
                 "-crf", "19", "-threads", "4"]
    else:
        args += ["-c:v", "copy"]
    args += ["-movflags", "+faststart", "-t", str(seconds), "-shortest", str(out)]
    _run(args, cwd=ass.parent if ass else None)


def _subtitles(base: Path, language: str, out: Path, *, vertical: bool) -> Path:
    from .clips import transcribe_ass
    ass = transcribe_ass(base, language, out, 1450)
    if not ass:
        raise RuntimeError("Legendas solicitadas, mas a transcrição não encontrou fala. Exporte sem --legendas ou revise a origem.")
    if not vertical:
        content = ass.read_text(encoding="utf-8")
        content = content.replace("PlayResX: 1080", "PlayResX: 1920").replace("PlayResY: 1920", "PlayResY: 1080")
        content = content.replace("Style: Cap,Anton,86,", "Style: Cap,Anton,52,")
        content = content.replace(",60,60,470,1", ",80,80,90,1")
        ass.write_text(content, encoding="utf-8")
    return ass


def _qa(ff: str, video: Path, folder: Path, size: tuple[int, int], expected: float) -> dict:
    meta = _probe(video)
    streams = meta.get("streams", [])
    v = next((s for s in streams if s.get("codec_type") == "video"), {})
    a = next((s for s in streams if s.get("codec_type") == "audio"), {})
    duration = _duration(meta)
    if (v.get("width"), v.get("height")) != size:
        raise RuntimeError("QA: resolução exportada diferente da solicitada.")
    try:
        numerator, denominator = map(float, v.get("avg_frame_rate", "0/1").split("/"))
        actual_fps = numerator / denominator
    except (ValueError, ZeroDivisionError):
        actual_fps = 0
    if abs(actual_fps - FPS) > .05:
        raise RuntimeError("QA: taxa de quadros diferente de 30 fps.")
    if abs(duration - expected) > .20:
        raise RuntimeError(f"QA: duração exportada {duration:.3f}s diferente do plano {expected:.3f}s.")
    if not a:
        raise RuntimeError("QA: vídeo exportado sem faixa de áudio.")
    _run([ff, "-v", "error", "-nostdin", "-i", str(video), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"])
    raw = _run([ff, "-v", "error", "-nostdin", "-i", str(video), "-map", "0:a:0", "-vn",
                "-ac", "1", "-ar", "16000", "-f", "s16le", "-"])
    audio = np.frombuffer(raw, dtype="<i2")
    rms = float(np.sqrt(np.mean((audio.astype(np.float32) / 32768) ** 2))) if audio.size else 0.0
    qa_dir = folder / "qa"
    qa_dir.mkdir()
    cell = (480, 270) if size == LONG_SIZE else (180, 320)
    sheet = Image.new("RGB", (cell[0] * 3, (cell[1] + 32) * 2), "#0B0614")
    draw = ImageDraw.Draw(sheet)
    for index in range(6):
        at = min(duration - .05, duration * index / 6)
        frame = qa_dir / f"quadro-{index + 1:02d}.jpg"
        _run([ff, "-v", "error", "-nostdin", "-y", "-ss", str(max(0, at)), "-i", str(video),
              "-frames:v", "1", "-vf", f"scale={cell[0]}:{cell[1]}", "-update", "1", str(frame)])
        with Image.open(frame) as opened:
            xy = ((index % 3) * cell[0], (index // 3) * (cell[1] + 32))
            sheet.paste(opened, xy)
        draw.text((xy[0] + 10, xy[1] + cell[1] + 5), f"{at:.1f}s", font=gfx.font("body", 20), fill="white")
    sheet.save(qa_dir / "previa.jpg", quality=90)
    result = {"duration": round(duration, 3), "width": size[0], "height": size[1],
              "fps": v.get("avg_frame_rate"), "video_codec": v.get("codec_name"),
              "audio_codec": a.get("codec_name"), "decoded_all_streams": True,
              "audio_rms": round(rms, 7), "audio_non_silent": rms > 1e-5,
              "visual_review": False, "warning": "Áudio silencioso na origem e sem música." if rms <= 1e-5 else None}
    (qa_dir / "validacao.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def _caption(plan: dict, title: str, moment: dict | None = None) -> str:
    lang = plan.get("language", "pt")
    source = plan["source"]
    credit = source.get("credit") or source.get("title") or "Arquivo enviado"
    prefix = "Crédito: " if lang == "pt" else "Credit: "
    question = "Qual foi o melhor momento para você?" if lang == "pt" else "Which moment was your favorite?"
    tags = " ".join(brand().get("hashtags", {}).get(lang, []))
    url = source.get("url") or ""
    return f"{title.replace('*', '')}\n\n{question}\n\n{prefix}{credit}\n{url}\n\n{tags}\n"


def render(plan: dict, output: Path, *, music: bool = True, subtitles: bool = False, log=print) -> dict:
    """Exporta em uma pasta nova, com validação e promoção atômica ao terminar.

    Música é tema local, reduzida e comprimida pelo áudio da gameplay. A seleção
    semântica dos momentos/capas continua registrada como revisão visual pendente.
    """
    output = Path(output).resolve()
    if output.exists():
        raise FileExistsError(f"A pasta de exportação já existe; escolha uma versão nova: {output}")
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg não encontrado; instale o FFmpeg antes de exportar.")
    source, meta = _validate(plan)
    theme = None
    if music:
        from .music import theme_path
        theme = theme_path(seed=str(plan.get("title", "gameplay")))
        if not theme or not theme.is_file():
            raise RuntimeError("Música tema GTA VI não encontrada. Importe a faixa antes de exportar ou solicite explicitamente --sem-musica.")
        theme_meta = _probe(theme)
        if not any(s.get("codec_type") == "audio" for s in theme_meta.get("streams", [])):
            raise RuntimeError("A música tema não contém áudio válido.")
        _duration(theme_meta)
    if subtitles and importlib.util.find_spec("faster_whisper") is None:
        raise RuntimeError("Legendas solicitadas: instale faster-whisper ou exporte sem --legendas.")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.parent / f".{output.name}.staging-{uuid.uuid4().hex[:10]}"
    staging.mkdir()
    work = staging / ".work"
    work.mkdir()
    language = plan.get("language", "pt")
    credit = plan["source"].get("credit") or plan["source"].get("title") or "Arquivo enviado"
    title = str(plan.get("title") or plan["source"].get("title") or "Melhores momentos da gameplay")
    has_audio = any(s.get("codec_type") == "audio" for s in meta.get("streams", []))
    results: dict = {"output": str(output), "long": None, "shorts": [], "plan": str(output / "plano.json"),
                     "manifest": str(output / "manifest.json"), "music": bool(theme), "subtitles": subtitles,
                     "published": False, "visual_review": False}
    try:
        long_moments = plan.get("long") or []
        if long_moments:
            folder = staging / "longo"
            folder.mkdir()
            overlay = _overlay(LONG_SIZE, title, credit, language)
            ov_path = work / "overlay-longo.png"
            overlay.save(ov_path)
            pieces = []
            for index, moment in enumerate(long_moments):
                log(f"  [gameplay] longo: momento {index + 1}/{len(long_moments)}")
                piece = work / f"longo-{index + 1:03d}.mp4"
                _encode_clip(ff, source, moment, piece, ov_path, vertical=False, has_audio=has_audio)
                pieces.append(piece)
            listing = work / "concat.txt"
            # File names are our own ASCII names; no user text reaches the concat syntax.
            lengths = [math.ceil((float(m["end"]) - float(m["start"])) * FPS - 1e-7) / FPS for m in long_moments]
            listing.write_text("\n".join(f"file '{p.name}'\nduration {length:.9f}" for p, length in zip(pieces, lengths)) + "\n", encoding="utf-8")
            base = work / "longo-base.mp4"
            _run([ff, "-v", "error", "-nostdin", "-y", "-f", "concat", "-safe", "1", "-i", str(listing),
                  "-c", "copy", "-movflags", "+faststart", str(base)])
            ass = _subtitles(base, language, work / "subs-longo.ass", vertical=False) if subtitles else None
            expected = sum(lengths)
            _finalize(ff, base, folder / "video.mp4", theme, seconds=expected, ass=ass)
            qa = _qa(ff, folder / "video.mp4", folder, LONG_SIZE, expected)
            if qa["duration"] > float(plan.get("max_long_seconds", 660)) + .05:
                raise RuntimeError("QA: o vídeo longo ultrapassou o limite do plano.")
            cover_moment = max(long_moments, key=lambda m: float(m.get("score", 0)))
            peak = min(float(cover_moment["end"]) - .1, max(float(cover_moment["start"]), float(cover_moment.get("peak", cover_moment["start"]))))
            real = work / "quadro-capa-longo.png"
            _extract_frame(ff, source, peak, real)
            _cover(real, overlay, title, LONG_SIZE, folder / "capa.jpg")
            (folder / "legenda.txt").write_text(_caption(plan, title), encoding="utf-8")
            results["long"] = {"video": str(output / "longo/video.mp4"), "cover": str(output / "longo/capa.jpg"),
                               "caption": str(output / "longo/legenda.txt"), "preview": str(output / "longo/qa/previa.jpg"),
                               "qa": qa, "cover_source_time": round(peak, 3), "moments": len(long_moments)}
        for index, moment in enumerate(plan.get("shorts") or []):
            log(f"  [gameplay] short {index + 1}/{len(plan['shorts'])}")
            name = f"short-{index + 1:02d}"
            folder = staging / name
            folder.mkdir()
            short_title = str(moment.get("title") or title)
            overlay = _overlay(SHORT_SIZE, short_title, credit, language)
            ov_path = work / f"overlay-{name}.png"
            overlay.save(ov_path)
            base = work / f"{name}-base.mp4"
            _encode_clip(ff, source, moment, base, ov_path, vertical=True, has_audio=has_audio)
            ass = _subtitles(base, language, work / f"subs-{name}.ass", vertical=True) if subtitles else None
            _finalize(ff, base, folder / "video.mp4", theme, seconds=float(moment["end"]) - float(moment["start"]), ass=ass)
            qa = _qa(ff, folder / "video.mp4", folder, SHORT_SIZE, float(moment["end"]) - float(moment["start"]))
            peak = min(float(moment["end"]) - .1, max(float(moment["start"]), float(moment.get("peak", moment["start"]))))
            real = work / f"quadro-{name}.png"
            _extract_frame(ff, source, peak, real)
            _cover(real, overlay, short_title, SHORT_SIZE, folder / "capa.jpg")
            (folder / "legenda.txt").write_text(_caption(plan, short_title, moment), encoding="utf-8")
            results["shorts"].append({"id": moment.get("id", name), "title": short_title,
                                      "video": str(output / name / "video.mp4"), "cover": str(output / name / "capa.jpg"),
                                      "caption": str(output / name / "legenda.txt"), "preview": str(output / name / "qa/previa.jpg"),
                                      "qa": qa, "cover_source_time": round(peak, 3)})
        (staging / "plano.json").write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (staging / "manifest.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        # Only scratch data created in this invocation is removed, before the atomic promotion.
        _remove_scratch(work, staging, ".work")
        staging.rename(output)
        log(f"  [gameplay] exportação e decodificação concluídas: {output}")
        return results
    except Exception:
        # Keep existing exports untouched; never leave a failed export under its final name.
        if staging.exists():
            _remove_scratch(staging, output.parent, staging.name)
        raise
