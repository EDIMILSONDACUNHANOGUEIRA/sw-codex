"""Leonida Cortes: servidor local sem radar, posts ou estado das notícias."""
from __future__ import annotations

import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import Body, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from leonida import gameplay, localguard

ROOT = Path(__file__).resolve().parents[2]
WEB = Path(__file__).resolve().parent / "web"
HOME = Path(os.environ.get("LEONIDA_GAMEPLAY_HOME", WEB.parent / "prontos")).resolve()
UPLOADS = Path(os.environ.get("LEONIDA_GAMEPLAY_UPLOADS", WEB.parent / "uploads")).resolve()
MAX_UPLOAD_BYTES = 20 * 1024**3
HOME.mkdir(parents=True, exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="Leonida Cortes")
localguard.install(app)   # só o próprio PC: sem CSRF nem DNS rebinding
JOBS: dict[str, dict] = {}
CANCEL: dict[str, threading.Event] = {}
gameplay.cleanup_orphans(HOME)   # sobras de trabalhos interrompidos na última execução


def _job(fn, *args, **kwargs) -> str:
    identifier = uuid.uuid4().hex[:10]
    JOBS[identifier] = {"id": identifier, "status": "running", "log": [], "result": None}
    CANCEL[identifier] = threading.Event()

    def log(message):
        # Cada passo do trabalho registra progresso; é aí que o cancelamento é atendido.
        if CANCEL[identifier].is_set():
            raise gameplay.JobCancelled("Cancelado pelo usuário")
        JOBS[identifier]["log"].append(str(message))

    def run():
        try:
            with gameplay.project_home(HOME):
                JOBS[identifier]["result"] = fn(*args, log=log, **kwargs)
            JOBS[identifier]["status"] = "done"
        except gameplay.JobCancelled:
            JOBS[identifier]["status"] = "cancelled"
            JOBS[identifier]["log"].append("Cancelado. Nenhum arquivo parcial foi mantido.")
        except Exception as exc:
            JOBS[identifier]["status"] = "error"
            JOBS[identifier]["log"].append(f"ERRO: {exc}")

    threading.Thread(target=run, daemon=True).start()
    return identifier


def _source(value) -> str:
    if isinstance(value, str) and value.startswith("upload:"):
        identifier = value[len("upload:"):]
        if not re.fullmatch(r"[a-f0-9]{32}", identifier):
            raise ValueError("Arquivo enviado inválido")
        found = list(UPLOADS.glob(identifier + ".*"))
        if len(found) != 1 or found[0].resolve().parent != UPLOADS or not found[0].is_file():
            raise ValueError("Arquivo enviado não encontrado")
        return str(found[0])
    return gameplay.source_url(value)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.post("/api/gameplay/upload")
async def upload(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".mp4", ".mkv", ".mov", ".webm", ".m4v", ".avi"):
        raise HTTPException(400, "Envie um arquivo de vídeo MP4, MKV, MOV, WebM, M4V ou AVI")
    identifier = uuid.uuid4().hex
    target = UPLOADS / (identifier + suffix)
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await file.read(2 * 1024**2):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, "O arquivo ultrapassa 20 GB")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "O arquivo está vazio")
    except Exception:
        # Remove apenas o temporário incompleto criado por esta requisição.
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"source": "upload:" + identifier, "filename": Path(file.filename or "video" ).name, "bytes": size}


def _music_source(value) -> Path:
    if not isinstance(value, str) or not re.fullmatch(r"music-upload:[a-f0-9]{32}", value):
        raise ValueError("Escolha e importe o arquivo da outra música")
    folder = UPLOADS / "music"
    if folder.resolve() != UPLOADS.resolve() / "music":
        raise ValueError("Pasta da música inválida")
    found = list(folder.glob(value.split(":", 1)[1] + ".*"))
    if len(found) != 1 or not found[0].is_file() or found[0].resolve().parent != folder:
        raise ValueError("Arquivo da música não encontrado")
    return found[0]


@app.post("/api/gameplay/music-upload")
async def upload_music(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in (".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"):
        raise HTTPException(400, "Envie uma música MP3, WAV, M4A, AAC, FLAC, OGG, OPUS ou AIFF")
    folder = UPLOADS / "music"
    if folder.resolve() != UPLOADS.resolve() / "music":
        raise HTTPException(400, "Pasta da música inválida")
    folder.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    target = folder / (identifier + suffix)
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await file.read(2 * 1024**2):
                size += len(chunk)
                if size > 512 * 1024**2:
                    raise HTTPException(413, "A música ultrapassa 512 MB")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "O arquivo da música está vazio")
        from leonida.gameplay_render import _probe, _duration
        try:
            metadata = _probe(target)
            if not any(s.get("codec_type") == "audio" for s in metadata.get("streams", [])):
                raise ValueError("Sem áudio")
            _duration(metadata)
        except (ValueError, RuntimeError):
            raise HTTPException(400, "Este arquivo não contém uma música válida") from None
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    return {"source": "music-upload:" + identifier,
            "filename": Path(file.filename or "musica").name, "bytes":size}


@app.get("/api/gameplay/projects")
def projects():
    with gameplay.project_home(HOME):
        return gameplay.projects()


def _revision_asset(folder: Path, filename: str) -> str | None:
    asset = folder / filename
    if not asset.is_file() or asset.resolve().parent != folder:
        return None
    return "/gameplay-files/revisoes/" + quote(folder.name, safe="") + "/" + quote(filename, safe="")


@app.get("/api/gameplay/revisions")
def revisions():
    directory = HOME / "revisoes"
    if not directory.is_dir() or directory.resolve() != HOME.resolve() / "revisoes":
        return []
    directory = directory.resolve()
    ready = []
    for folder in sorted(directory.iterdir(), key=lambda path: path.name, reverse=True):
        if not folder.is_dir() or folder.resolve() != folder or folder.resolve().parent != directory:
            continue
        folder = folder.resolve()
        video = _revision_asset(folder, "video.mp4")
        validation = _revision_asset(folder, "validacao.json")
        if not video or not validation:
            continue
        try:
            metadata = json.loads((folder / "validacao.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(metadata, dict):
            continue
        item = {"id": folder.name, "title": str(metadata.get("title") or folder.name),
                "video_url": video, "qa_url": validation}
        for field in ("duration", "width", "height"):
            value = metadata.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and 0 < value < 1_000_000:
                item[field] = value
        for field, filenames in (("cover_url", ("capa.jpg", "capa.png")),
                                 ("subtitles_url", ("legendas.srt",)),
                                 ("caption_url", ("legenda-publicacao.txt",))):
            for filename in filenames:
                url = _revision_asset(folder, filename)
                if url:
                    item[field] = url
                    break
        ready.append(item)
    return ready


@app.post("/api/gameplay/analyze")
def analyze(data: dict = Body(...)):
    try:
        source = _source(data.get("source", ""))
        settings = gameplay.options(
            max_long=gameplay._number(data.get("max_long_minutes", 11), "Minutos do vídeo longo") * 60,
            short_count=data.get("short_count", 3), short_seconds=data.get("short_seconds", 45),
            title=data.get("title") or "Melhores momentos de GTA", credit=data.get("credit", ""),
            lang=data.get("lang", "pt"))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"job": _job(gameplay.analyze, source, **settings)}


@app.post("/api/gameplay/render")
def render(data: dict = Body(...)):
    try:
        with gameplay.project_home(HOME):
            project = gameplay.project_path(data.get("project_id", ""))
            original = json.loads((project / "plan.json").read_text(encoding="utf-8"))
            plan = gameplay.validate_plan(data.get("plan") or original, original=original)
        if not plan["long"] and not plan["shorts"]:
            raise ValueError("Selecione pelo menos um corte")
        for field in ("music", "subtitles"):
            if field in data and not isinstance(data[field], bool):
                raise ValueError(f"{field}: use verdadeiro ou falso")
        language = data.get("speech_language", "auto")
        if language not in ("pt", "en", "auto"):
            raise ValueError("Idioma da fala: pt, en ou auto")
        creator_srt = data.get("creator_srt")
        if creator_srt is not None and (not isinstance(creator_srt, str) or len(creator_srt) > 2_000_000):
            raise ValueError("Envie a legenda SRT como texto, com até 2 MB")
        creator_srt = creator_srt or None
        mode = data.get("music_mode")
        if mode is not None and mode not in ("theme", "none", "custom"):
            raise ValueError("Música: tema GTA VI, nenhuma ou outra faixa")
        volume = gameplay._number(data.get("music_volume", .10), "Volume da música")
        if not 0 <= volume <= 1:
            raise ValueError("Volume da música deve ficar entre 0 e 1")
        music_path = str(_music_source(data.get("music_source"))) if mode == "custom" else None
        subtitles = data.get("subtitles")
        if subtitles is None:
            # Sem pedido explícito, legenda só quando o reconhecimento de voz está instalado.
            subtitles = bool(creator_srt) or _captions_available()
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from None
    return {"job": _job(gameplay.render_project, data["project_id"], plan,
                        music=data.get("music", True), subtitles=subtitles,
                        speech_language=language, creator_srt=creator_srt, music_mode=mode,
                        music_path=music_path, music_volume=volume)}


@app.get("/api/jobs/{identifier}")
def job(identifier: str):
    if identifier not in JOBS:
        raise HTTPException(404, "Tarefa não encontrada")
    return JOBS[identifier]


@app.post("/api/jobs/{identifier}/cancel")
def cancel_job(identifier: str):
    if identifier not in JOBS:
        raise HTTPException(404, "Tarefa não encontrada")
    if JOBS[identifier]["status"] == "running":
        CANCEL[identifier].set()
        JOBS[identifier]["log"].append("Cancelando… o trabalho para no próximo passo.")
    return {"status": JOBS[identifier]["status"], "cancelling": CANCEL[identifier].is_set()}


def _captions_available() -> bool:
    try:
        from leonida import speech_captions
        return bool(speech_captions.available())
    except (ImportError, AttributeError):
        return False


@app.get("/api/status")
def status():
    from leonida import music
    captions = _captions_available()
    return {"product": "Leonida Cortes", "brand": "Leonida Wire", "ffmpeg": bool(shutil.which("ffmpeg")),
            "music": bool(music.theme_path()), "captions": captions, "delivery": "local"}


@app.post("/api/music")
def set_music(data: dict = Body(...)):
    from leonida import music
    try:
        source = gameplay.source_url(data.get("url", ""))
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {"job": _job(music.download, source, data.get("start") or 0)}


app.mount("/gameplay-files", StaticFiles(directory=str(HOME)), name="gameplay-files")
app.mount("/static", StaticFiles(directory=str(WEB), check_dir=False), name="static")
