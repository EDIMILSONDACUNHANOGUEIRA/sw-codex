"""Projetos locais de cortes: análise revisável -> exportação versionada.

Não publica em redes e não faz afirmações sobre o conteúdo dos momentos.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import os
import re
import unicodedata
import uuid
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from urllib.parse import quote, urlsplit

from .config import OUT_DIR

PROJECTS = Path(os.environ.get("LEONIDA_GAMEPLAY_HOME", OUT_DIR / "gameplay"))
_PROJECT_HOME: ContextVar[Path | None] = ContextVar("leonida_gameplay_home", default=None)


@contextmanager
def project_home(path: str | Path):
    """Isola os projetos de uma requisição/job sem alterar saídas das notícias."""
    token = _PROJECT_HOME.set(Path(path).resolve())
    try:
        yield
    finally:
        _PROJECT_HOME.reset(token)


def project_root() -> Path:
    return _PROJECT_HOME.get() or PROJECTS


def _number(value, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label}: informe um número finito")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label}: informe um número finito") from None
    if not math.isfinite(result):
        raise ValueError(f"{label}: informe um número finito")
    return result


def _text(value, label: str, limit: int = 160, *, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"{label}: texto simples com até {limit} caracteres")
    result = value.strip()
    if required and not result:
        raise ValueError(f"{label}: preencha o texto")
    return result


def source_url(source: str) -> str:
    """O formulário web aceita links; arquivos locais só pelo CLI."""
    if not isinstance(source, str) or len(source) > 4096:
        raise ValueError("Informe um link HTTP ou HTTPS do vídeo")
    url = urlsplit(source.strip())
    if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
        raise ValueError("Informe um link HTTP ou HTTPS, sem credenciais na URL")
    return source.strip()


def options(*, max_long=660, short_count=3, short_seconds=45, lang="pt", title="Melhores momentos de GTA", credit="") -> dict:
    maximum = _number(max_long, "Duração do vídeo longo")
    seconds = _number(short_seconds, "Duração dos shorts")
    count = _number(short_count, "Quantidade de shorts")
    if not 0 < maximum <= 660:
        raise ValueError("O vídeo longo deve durar até 11 minutos")
    if not 30 <= seconds <= 60:
        raise ValueError("Os shorts devem ter entre 30 e 60 segundos")
    if not count.is_integer() or not 0 <= count <= 10:
        raise ValueError("Escolha de 0 a 10 shorts por projeto")
    if lang not in ("pt", "en"):
        raise ValueError("Idioma: pt ou en")
    return {"max_long": maximum, "short_count": int(count), "short_seconds": seconds,
            "lang": lang, "title": _text(title, "Título", 100), "credit": _text(credit, "Crédito", required=False)}


def _write_new(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
        file.write("\n")


def project_path(project_id: str) -> Path:
    if not isinstance(project_id, str) or not re.fullmatch(r"[a-z0-9-]{1,120}", project_id):
        raise ValueError("Projeto inválido")
    root = project_root().resolve()
    path = (root / project_id).resolve()
    if path.parent != root or not (path / "plan.json").is_file():
        raise FileNotFoundError("Projeto de gameplay não encontrado")
    return path


def url_for(path: str | Path) -> str:
    if _PROJECT_HOME.get() is not None or os.environ.get("LEONIDA_GAMEPLAY_HOME"):
        relative = Path(path).resolve().relative_to(project_root().resolve())
        return "/gameplay-files/" + quote(relative.as_posix(), safe="/")
    relative = Path(path).resolve().relative_to(OUT_DIR.resolve())
    return "/prontos/" + quote(relative.as_posix(), safe="/")


def analyze(source: str, *, max_long=660, short_count=3, short_seconds=45,
            title="Melhores momentos de GTA", credit="", lang="pt", markers=None, log=print) -> dict:
    from .gameplay_analysis import analyze as inspect

    settings = options(max_long=max_long, short_count=short_count, short_seconds=short_seconds,
                       title=title, credit=credit, lang=lang)
    normalized = unicodedata.normalize("NFKD", settings["title"]).encode("ascii", "ignore").decode().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized).strip("-")[:60] or "gameplay"
    project_id = f"{dt.date.today().isoformat()}-{slug}-{uuid.uuid4().hex[:8]}"
    output = project_root() / project_id
    output.mkdir(parents=True, exist_ok=False)
    plan = inspect(source, output, markers=markers, log=log, **settings)
    validate_plan(plan)
    _write_new(output / "project.json", {"project_id": project_id, "title": plan["title"],
               "created": dt.datetime.now().isoformat(timespec="seconds")})
    return {"project_id": project_id, "plan": plan, "plan_url": url_for(output / "plan.json"),
            "storyboard_url": url_for(output / "storyboard.jpg")}


def validate_plan(plan: dict, *, original: dict | None = None) -> dict:
    """Vincula a edição à fonte analisada e recusa timestamps fora do vídeo."""
    if not isinstance(plan, dict) or plan.get("version") != 1:
        raise ValueError("Plano de gameplay inválido (versão 1 necessária)")
    result = copy.deepcopy(plan)
    source = result.get("source")
    if not isinstance(source, dict):
        raise ValueError("Plano sem vídeo fonte")
    if original is not None:
        if source != original.get("source"):
            raise ValueError("A fonte não pode ser trocada no plano; analise o novo vídeo")
        # Candidatos e diagnósticos permanecem como evidência da análise original.
        result["candidates"] = copy.deepcopy(original.get("candidates", []))
        result["analysis"] = copy.deepcopy(original.get("analysis", {}))
    duration = _number(source.get("duration"), "Duração da fonte")
    if duration <= 0 or not isinstance(source.get("path"), str) or not Path(source["path"]).is_file():
        raise ValueError("Vídeo fonte ausente ou sem duração válida")
    settings = options(max_long=result.get("max_long_seconds"), short_seconds=result.get("short_seconds"),
                       short_count=len(result.get("shorts", [])) if isinstance(result.get("shorts"), list) else 0,
                       title=result.get("title"), credit=source.get("credit", ""), lang=result.get("language"))
    result["title"] = settings["title"]
    for kind in ("long", "shorts"):
        intervals = result.get(kind)
        if not isinstance(intervals, list) or len(intervals) > (80 if kind == "long" else 10):
            raise ValueError(f"Lista de cortes {kind} inválida")
        total = 0.0
        seen = set()
        for item in intervals:
            if not isinstance(item, dict):
                raise ValueError("Cada corte precisa de início, fim e título")
            item["start"] = _number(item.get("start"), "Início do corte")
            item["end"] = _number(item.get("end"), "Fim do corte")
            if not 0 <= item["start"] < item["end"] <= duration + 0.001:
                raise ValueError("Corte fora da duração da fonte")
            item["title"] = _text(item.get("title"), "Título do corte", 100)
            identifier = _text(item.get("id"), "Identificador do corte", 100)
            if identifier in seen:
                raise ValueError(f"Corte repetido em {kind}")
            seen.add(identifier)
            length = item["end"] - item["start"]
            if kind == "shorts" and not 30 - 0.001 <= length <= 60 + 0.001:
                raise ValueError("Cada short deve ter entre 30 e 60 segundos")
            total += math.ceil(length * 30 - 1e-7) / 30 if kind == "long" else length
            peak = _number(item.get("peak", (item["start"] + item["end"]) / 2), "Momento de destaque")
            # Ao ajustar limites, o quadro da capa acompanha o novo trecho.
            item["peak"] = min(max(peak, item["start"]), max(item["start"], item["end"] - 0.05))
        if kind == "long":
            if total > settings["max_long"] + 0.001:
                raise ValueError("Os cortes selecionados ultrapassam o limite do vídeo longo")
            ordered = sorted(intervals, key=lambda x: x["start"])
            if any(a["end"] > b["start"] + 0.001 for a, b in zip(ordered, ordered[1:])):
                raise ValueError("Os cortes do vídeo longo se sobrepõem")
    return result


def render_project(project_id: str, plan: dict | None = None, *, music=True, subtitles=False,
                   speech_language="pt", creator_srt=None, music_mode=None, music_path=None,
                   music_volume=.10, log=print) -> dict:
    from .gameplay_render import render

    project = project_path(project_id)
    original = json.loads((project / "plan.json").read_text(encoding="utf-8"))
    selected = validate_plan(plan if plan is not None else original, original=original)
    if not selected["long"] and not selected["shorts"]:
        raise ValueError("Selecione pelo menos um corte")
    output = project / "exports" / f"export-{uuid.uuid4().hex[:10]}"
    output.parent.mkdir(parents=True, exist_ok=True)
    files = render(selected, output, music=music, subtitles=subtitles,
                   speech_language=speech_language, creator_srt=creator_srt, music_mode=music_mode,
                   music_path=music_path, music_volume=music_volume, log=log)
    _write_new(output / "selection.json", selected)
    result = {"project_id": project_id, "long": None, "shorts": [],
              "plan_url": url_for(output / "selection.json"), "output": str(output),
              "music_mode":files.get("music_mode"), "music_volume":files.get("music_volume")}
    for kind in ("long", "shorts"):
        items = files.get(kind)
        if kind == "long":
            items = [items] if items else []
        converted = []
        for item in items or []:
            record = {k: v for k, v in item.items() if k in ("duration", "title", "width", "height")}
            checks = item.get("qa")
            if isinstance(checks, dict):
                record.update({k: v for k, v in checks.items() if k in ("duration", "width", "height")})
            for name in ("video", "cover", "caption", "subtitles", "qa", "preview"):
                if isinstance(item.get(name), (str, Path)):
                    record[name + "_url"] = url_for(item[name])
            if isinstance(checks, dict) and item.get("video"):
                record["qa_url"] = url_for(Path(item["video"]).parent / "qa" / "validacao.json")
            converted.append(record)
        result[kind] = converted[0] if kind == "long" and converted else (None if kind == "long" else converted)
    result["qa_url"] = url_for(files.get("manifest") or output / "manifest.json")
    _write_new(output / "delivery.json", result)
    return result


def projects() -> list[dict]:
    saved = []
    for file in sorted(project_root().glob("*/project.json"), reverse=True):
        try:
            record = json.loads(file.read_text(encoding="utf-8"))
            project = project_path(record["project_id"])
            record["plan"] = json.loads((project / "plan.json").read_text(encoding="utf-8"))
            record["storyboard_url"] = url_for(project / "storyboard.jpg")
            deliveries = sorted(project.glob("exports/*/delivery.json"), key=lambda p: p.stat().st_mtime, reverse=True)
            if deliveries:
                record["result"] = json.loads(deliveries[0].read_text(encoding="utf-8"))
            saved.append(record)
        except (ValueError, KeyError, OSError):
            continue
    return saved
