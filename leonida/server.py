"""App web local: radar, editor com pré-visualização, prontos e cortes.

  python -m leonida serve   ->  http://localhost:8000
"""
from __future__ import annotations

import datetime as dt
import io
import shutil
import threading
import traceback
import uuid
from pathlib import Path

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from PIL import Image

from . import config, gallery, media, post, radar, render
from .config import OUT_DIR, POSTS_DIR

WEB = Path(__file__).resolve().parent / "web"
app = FastAPI(title="Leonida Studio")
config.ensure_dirs()
JOBS: dict[str, dict] = {}


def _job(fn, *args, **kw) -> str:
    jid = uuid.uuid4().hex[:10]
    JOBS[jid] = {"id": jid, "status": "running", "log": [], "result": None}

    def log(msg):
        JOBS[jid]["log"].append(str(msg))

    def run():
        try:
            JOBS[jid]["result"] = str(fn(*args, log=log, **kw))
            JOBS[jid]["status"] = "done"
            gallery.build()
        except Exception as exc:  # noqa: BLE001
            JOBS[jid]["status"] = "error"
            JOBS[jid]["log"].append(f"ERRO: {exc}")
            JOBS[jid]["log"].append(traceback.format_exc()[-1200:])

    threading.Thread(target=run, daemon=True).start()
    return jid


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


# ------------------------------------------------------------------ radar
@app.get("/api/radar")
def get_radar():
    data = radar.load_radar()
    seen = radar.load_seen()
    for s in data.get("stories", []):
        s["status"] = (seen.get(s["id"]) or {}).get("status")
    return data


@app.post("/api/radar/scan")
def scan_radar(hours: float = 72):
    radar.scan(max_age_hours=hours)
    return get_radar()


@app.post("/api/radar/{sid}/ignore")
def ignore_story(sid: str):
    radar.mark_seen([sid], "ignored")
    return {"ok": True}


# ------------------------------------------------------------------ posts
@app.get("/api/posts")
def list_posts():
    out = []
    for f in sorted(POSTS_DIR.glob("*/post.yaml"), reverse=True):
        try:
            p, _ = post.load(f)
        except Exception:
            continue
        date = str(p.get("date", ""))[:10]
        built = (OUT_DIR / date / p["id"] / "post.json").exists()
        out.append({"id": p["id"], "date": date, "tag": p.get("tag"), "built": built,
                    "headline": (p.get("pt") or {}).get("headline", ""), "needs_review": p.get("needs_review")})
    return out


@app.get("/api/posts/{pid}")
def get_post(pid: str):
    try:
        p, _ = post.load(pid)
    except FileNotFoundError:
        raise HTTPException(404, "post não encontrado")
    return p


@app.put("/api/posts/{pid}")
def put_post(pid: str, data: dict = Body(...)):
    data["id"] = pid
    if data.pop("_reviewed", False):
        data.pop("needs_review", None)
    post.save(data)
    return {"ok": True, "errors": post.validate(data)}


@app.post("/api/posts/new")
def new_post(data: dict = Body(...)):
    f = post.new(data.get("title") or "novo post", data.get("date"))
    return {"id": f.parent.name}


@app.post("/api/posts/from-story/{sid}")
def from_story(sid: str, use_ai: bool = True):
    from . import writer
    story = next((s for s in radar.load_radar()["stories"] if s["id"] == sid), None)
    if not story:
        raise HTTPException(404, "história não está no radar")
    try:
        p = writer.story_to_post(story, use_llm=None if use_ai else False)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(500, f"falha ao redigir: {exc}")
    radar.mark_seen([sid], "drafted")
    return {"id": p["id"], "needs_review": p.get("needs_review", False)}


@app.post("/api/posts/{pid}/preview")
def preview(pid: str, lang: str = "pt"):
    p, base = post.load(pid)
    if not p.get("image") or not (p.get(lang) or {}).get("headline"):
        raise HTTPException(400, "preencha imagem e manchete")
    date = str(p.get("date") or dt.date.today().isoformat())[:10]
    r = render.cover(p, lang, base, today=dt.date.fromisoformat(date))
    buf = io.BytesIO()
    r.image.save(buf, "JPEG", quality=88)
    return Response(buf.getvalue(), media_type="image/jpeg")


@app.post("/api/posts/{pid}/build")
def build_post(pid: str, video: bool = True):
    return {"job": _job(post.build, pid, video=video)}


@app.post("/api/posts/{pid}/upload")
async def upload_image(pid: str, file: UploadFile = File(...)):
    d = POSTS_DIR / pid
    d.mkdir(parents=True, exist_ok=True)
    name = "imagem" + (Path(file.filename or "x.jpg").suffix.lower() or ".jpg")
    with open(d / name, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    return {"image": name}


@app.post("/api/contagem")
def contagem(video: bool = True):
    from types import SimpleNamespace
    from .__main__ import cmd_contagem

    def run(log=print):
        cmd_contagem(SimpleNamespace(data=None, sem_video=not video, enviar=False))
        return "ok"
    return {"job": _job(run)}


@app.post("/api/posts/{pid}/send")
def send_post(pid: str):
    from . import notify
    p, _ = post.load(pid)
    folder = OUT_DIR / str(p.get("date"))[:10] / pid
    if not folder.exists():
        raise HTTPException(400, "gere o post antes de enviar")
    return {"sent": notify.send(folder)}


# ------------------------------------------------------------------ biblioteca / thumbs
@app.get("/api/library")
def library():
    return media.sync_rockstar_library()


@app.get("/api/thumb")
def thumb(url: str, w: int = 360):
    try:
        im = Image.open(media.fetch(url) if url.startswith("http") else media.resolve_image(url))
        im = im.convert("RGB")
        im.thumbnail((w, w * 2))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=80)
    return Response(buf.getvalue(), media_type="image/jpeg", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/meta")
def meta(url: str):
    try:
        return media.page_meta(url)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, str(exc))


# ------------------------------------------------------------------ cortes
@app.post("/api/clips")
def make_clip(data: dict = Body(...)):
    from . import clips
    return {"job": _job(clips.make_clip, data["src"], data["start"], data["end"],
                        headline={"pt": data["pt"], "en": data["en"]}, tag=data.get("tag", "viral"),
                        source=data.get("credit", ""), subtitles=bool(data.get("subtitles")),
                        music_on=data.get("music", True) not in (False, "false", "off"))}


@app.post("/api/music")
def set_music(data: dict = Body(...)):
    from . import music
    return {"job": _job(music.download, data["url"], data.get("start") or 0)}


# ------------------------------------------------------------------ jobs
@app.get("/api/jobs/{jid}")
def job(jid: str):
    if jid not in JOBS:
        raise HTTPException(404)
    return JOBS[jid]


@app.get("/api/status")
def status():
    import os
    from . import cutout, music
    return JSONResponse({
        "days": config.days_to_release(),
        "brand": config.brand()["name"],
        "claude": bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")),
        "cutout": cutout.available(),
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "node": bool(shutil.which("npx")),
        "telegram": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
        "music": bool(music.theme_path()),
    })


gallery.build()
app.mount("/prontos", StaticFiles(directory=str(OUT_DIR), html=True), name="prontos")
app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
