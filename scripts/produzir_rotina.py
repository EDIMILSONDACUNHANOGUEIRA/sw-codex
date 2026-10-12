"""Produção portátil com QA: português por padrão, 30–60 s, entrega local sem publicação."""
from pathlib import Path
import os
import sys
import time
import json
import subprocess
import shutil
import argparse

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parent.parent
default_cache = REPO / ".cache"
previous_cache = REPO.parent / "sw-codex" / ".cache"
if not (default_cache / "media").exists() and (previous_cache / "media").exists():
    default_cache = previous_cache  # reutiliza o cache do checkout anterior no mesmo PC
CACHE = Path(os.environ.get("LEONIDA_CACHE", default_cache))
sys.path.insert(0, str(REPO))
os.environ["LEONIDA_CACHE"] = str(CACHE)
os.environ["U2NET_HOME"] = str(CACHE / "models")
os.environ["NUMBA_CACHE_DIR"] = str(CACHE / "numba")
os.environ["OMP_NUM_THREADS"] = "4"

from leonida import post, motion

ORIGINAL_BUILD = motion.build
ORIGINAL_PLAN = motion.plan
RESULTS = []
CURRENT_OUTPUT = None
DETAIL = None


def run(cmd):
    return subprocess.run(cmd, check=True, capture_output=True)


def check_layers(scenes, starts, target, output, art_by_scene=None):
    frames = round(target * motion.FPS)
    start = motion.frame_at(scenes, starts, 0)
    end = motion.frame_at(scenes, starts, frames - 1)
    assert np.array_equal(np.asarray(start), np.asarray(end)), "loop fonte diferente"
    files = sorted(output.parent.parent.glob("*.png"))
    if art_by_scene is None:
        assert len(files) == len(scenes)
        art_by_scene = {id(scene.bg): art for scene, art in zip(scenes, files)}
    details = []
    for scene, st in zip(scenes, starts):
        art = art_by_scene[id(scene.bg)]
        t = (np.floor((st + scene.dur - motion.T - motion.OUTRO) * motion.FPS) - 1) / motion.FPS
        actual = motion.frame_at(scenes, starts, round(t * motion.FPS))
        with Image.open(art) as image:
            expected = np.asarray(image.convert("RGB"))
        assert np.array_equal(np.asarray(actual), expected), (scene.kind, "arte não aparece no vídeo")
        hold = None
        if scene.kind == "list":
            hold = scene.dur - motion.T - motion.OUTRO - scene.settle
            assert hold >= 2.5 - 1e-7, (scene.kind, hold)
            assert all(0.45 - 1e-7 <= b - a <= 0.7 + 1e-7 for a, b in zip(scene.times, scene.times[1:]))
        for sprite in scene.sprites:
            if sprite.anim in ("line", "up", "slide", "pop", "pop_first") or sprite.name in ("brand", "live", "countdown"):
                if sprite.name in ("photo", "emblem"):
                    continue
                core = sprite.img.getchannel("A").point(lambda a: 255 if a >= 220 else 0).getbbox()
                if core:
                    assert sprite.x + core[2] <= 930, (scene.kind, sprite.name, "direita", sprite.x + core[2])
                    assert sprite.y + core[3] <= 1540, (scene.kind, sprite.name, "inferior", sprite.y + core[3])
        details.append({"kind": scene.kind, "start": st, "end": st + scene.dur,
                        "items": list(scene.times), "read_hold_seconds": hold,
                        "carousel_match_at": float(t),
                        "has_subject": any(s.name == "subject" for s in scene.sprites)})
    return {"scenes": details, "source_loop_identical": True,
            "carousel_source_match": True, "static_core_text_safe": True}


def planned(scenes, target, seed, log=print, **options):
    global DETAIL
    originals = list(scenes)
    files = sorted(CURRENT_OUTPUT.parent.parent.glob("*.png"))
    assert len(files) == len(originals), "artes originais não correspondem às cenas"
    art_by_scene = {id(scene.bg): art for scene, art in zip(originals, files)}
    starts = ORIGINAL_PLAN(scenes, target, seed, log, **options)
    total = starts[-1] + scenes[-1].dur
    assert abs(total - float(target)) <= 1e-7, "duração fonte diferente do pedido"
    DETAIL = check_layers(scenes, starts, float(target), CURRENT_OUTPUT, art_by_scene)
    DETAIL["unique_art_count"] = len(art_by_scene)
    DETAIL["maximum_scene_seconds"] = max(scene.dur for scene in scenes)
    return starts


def wrapped(scenes, out, seed=None, target=None, log=print, **options):
    global CURRENT_OUTPUT
    CURRENT_OUTPUT = out
    clock = time.monotonic()
    result = ORIGINAL_BUILD(scenes, out, seed=seed, target=target, log=log, **options)
    DETAIL["encode_seconds_including_source_qa"] = time.monotonic() - clock
    RESULTS.append(DETAIL)
    return result


def check_video(video, destination, target):
    ff = shutil.which("ffmpeg")
    metadata = json.loads(run([shutil.which("ffprobe"), "-v", "error", "-show_streams", "-show_format",
                              "-of", "json", str(video)]).stdout)
    v = next(s for s in metadata["streams"] if s["codec_type"] == "video")
    a = next(s for s in metadata["streams"] if s["codec_type"] == "audio")
    assert (v["width"], v["height"], v["codec_name"], v["profile"], v["r_frame_rate"]) == (1080, 1920, "h264", "High", "30/1")
    assert a["codec_name"] == "aac"
    assert abs(float(metadata["format"]["duration"]) - target) <= 0.034
    assert int(v["nb_frames"]) == round(target * 30)
    small = run([ff, "-v", "error", "-i", str(video), "-vf", "scale=108:192", "-f", "rawvideo",
                 "-pix_fmt", "rgb24", "pipe:1"]).stdout
    frames = np.frombuffer(small, np.uint8).reshape(-1, 192, 108, 3)
    means = np.array([frame.mean() for frame in frames])
    stds = np.array([frame.std() for frame in frames])
    assert len(frames) == round(target * 30)
    assert np.all(means > 3) and np.all(stds > 1), "quadro vazio detectado"
    difference = np.abs(frames[0].astype(float) - frames[-1].astype(float))
    destination.mkdir(parents=True, exist_ok=True)
    run([ff, "-v", "error", "-y", "-i", str(video), "-vf", "fps=1", str(destination / "frame-%02d.jpg")])
    samples = sorted(destination.glob("frame-*.jpg"))
    columns, tw, th = 5, 216, 384
    sheet = Image.new("RGB", (columns * tw, ((len(samples) + columns - 1) // columns) * (th + 25)), "#0B0614")
    draw = ImageDraw.Draw(sheet)
    for n, sample in enumerate(samples):
        with Image.open(sample) as image:
            sheet.paste(image.resize((tw, th)), (n % columns * tw, n // columns * (th + 25)))
        draw.text((n % columns * tw + 7, n // columns * (th + 25) + th + 5), f"{n}s", fill="white")
    sheet.save(destination / "quadros-por-segundo.jpg", quality=92)
    artfiles = sorted(video.parent.glob("*.jpg"))
    arts = Image.new("RGB", (tw * len(artfiles), th), "#0B0614")
    for n, path in enumerate(artfiles):
        with Image.open(path) as image:
            arts.paste(image.resize((tw, th)), (n * tw, 0))
    arts.save(destination / "artes.jpg", quality=95)
    return {"video": {k: v[k] for k in ("width", "height", "codec_name", "profile", "r_frame_rate", "nb_frames", "color_space")},
            "audio_codec": a["codec_name"], "duration": float(metadata["format"]["duration"]),
            "frames_checked": len(frames), "black_or_empty_frames": 0,
            "decoded_loop_mean_pixel_difference_108px": float(difference.mean()),
            "minimum_frame_mean": float(means.min())}


def main():
    parser = argparse.ArgumentParser(description="Gera e verifica vídeos locais de 30 a 60 segundos; não publica.")
    parser.add_argument("posts", nargs="+")
    parser.add_argument("--lang", choices=("pt", "en"), default="pt", help="Português por padrão; inglês somente quando solicitado")
    args = parser.parse_args()
    motion.build = wrapped
    motion.plan = planned
    for pid in args.posts:
        data, _ = post.load(pid)
        from leonida.config import brand, LANG_FOLDER
        target = float(data.get("video_segundos", brand()["video"]["segundos"]))
        if not 30 <= target <= 60:
            parser.error(f"{pid}: a rotina aceita de 30 a 60 segundos")
        print(f"PRODUÇÃO {pid} / {args.lang}", flush=True)
        clock = time.monotonic()
        out = post.build(pid, video=False, langs=(args.lang,), estilo="v2")
        detail = RESULTS[-1]
        detail["total_build_seconds_including_source_qa"] = time.monotonic() - clock
        detail["id"] = pid
        detail["language"] = args.lang
        folder = out / LANG_FOLDER[args.lang]
        video = folder / "tiktok" / "post.mp4"
        qa = folder / "qa"
        detail.update(check_video(video, qa, target))
        pcm = run([shutil.which("ffmpeg"), "-v", "error", "-i", str(video), "-map", "0:a:0",
                   "-ac", "1", "-ar", "16000", "-f", "f32le", "pipe:1"]).stdout
        audio = np.frombuffer(pcm, np.float32)
        assert np.isfinite(audio).all() and abs(len(audio) / 16000 - target) < .1
        rms = [float(np.sqrt(np.mean(c.astype(np.float64) ** 2))) for c in np.array_split(audio, max(1, round(target / 5)))]
        assert min(rms) > .001, "áudio ausente em um trecho longo"
        detail["audio"] = {"duration": len(audio) / 16000, "finite": True, "rms": rms, "listened": False}
        detail["visual_review"] = False
        detail["published"] = False
        (qa / "validacao.json").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"video": str(video.resolve()), "qa": str(qa.resolve()), "duration": target,
                          "frames_checked": detail["frames_checked"]}, ensure_ascii=False), flush=True)
    print("PRODUÇÃO E CHECAGENS CONCLUÍDAS; revisar as imagens do QA antes de entregar.", flush=True)


if __name__ == "__main__":
    main()
