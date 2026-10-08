"""Publicação no TikTok via Metricool (parceiro oficial do TikTok).

O app não fala direto com o TikTok: a API oficial exige app auditado, senão os posts saem privados.
O Metricool já é aprovado e publica em modo público. Fluxo:

  1. `python -m leonida build <id>` gera as artes em prontos/;
  2. commit + push (o repositório é público, então cada arquivo ganha um link raw.githubusercontent.com);
  3. `python -m leonida publicacao <id>` monta o pacote (links fixos no commit + legenda) para BR e US;
  4. o agente agenda no Metricool (ferramenta createScheduledPost) com esse pacote;
  5. `python -m leonida publicacao <id> --marcar br:<id-metricool> us:<id-metricool>` registra em
     state/publicados.json, para nunca publicar duas vezes.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

from .config import LANG_FOLDER, LANGS, OUT_DIR, ROOT, STATE_DIR, brand

PUBLISHED = STATE_DIR / "publicados.json"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
VID_NAMES = ("video.mp4", "edicao.mp4", "edit.mp4", "corte.mp4", "clip.mp4")


def cfg() -> dict:
    c = {"repo_raw": "", "revisao_manual": ["vazamento", "rumor"], "formato": "auto",
         "metricool": {"br": "", "us": ""}}
    c.update(brand().get("publicar") or {})
    return c


def load_published() -> dict:
    if PUBLISHED.exists():
        return json.loads(PUBLISHED.read_text(encoding="utf-8"))
    return {}


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def _folder(post_id: str) -> Path:
    hits = sorted(OUT_DIR.glob(f"*/{post_id}"))
    if not hits:
        raise FileNotFoundError(f"post não renderizado: {post_id} (rode o build antes)")
    return hits[-1]


def package(post_id: str) -> dict:
    """Pacote de publicação por perfil: tipo (carrossel/vídeo), links públicos e legenda.

    Os links apontam para o commit atual (não para o branch), então não mudam se a arte for
    regenerada depois. Exige que a pasta já esteja commitada e enviada ao GitHub."""
    c = cfg()
    base = c["repo_raw"].rstrip("/")
    if not base:
        raise RuntimeError("defina publicar.repo_raw em config/brand.yaml")
    folder = _folder(post_id)
    rel = folder.relative_to(ROOT).as_posix()
    if _git("status", "--porcelain", "--", rel):
        raise RuntimeError(f"{rel} tem mudanças sem commit: faça commit + push antes de publicar")
    sha = _git("rev-parse", "HEAD")
    if not _git("branch", "-r", "--contains", sha):
        raise RuntimeError("o commit atual ainda não foi enviado ao GitHub (git push)")
    meta = json.loads((folder / "post.json").read_text(encoding="utf-8")) if (folder / "post.json").exists() else {}
    tag = (meta.get("tag") or "").lower()
    done = load_published().get(post_id, {})
    out = {"id": post_id, "tag": tag, "manual_review": tag in c["revisao_manual"], "profiles": {}}
    for lang in LANGS:
        sub = LANG_FOLDER[lang]
        d = folder / sub
        if not d.exists():
            continue
        imgs = sorted(p.name for p in d.iterdir() if p.suffix.lower() in IMG_EXT
                      and p.stem not in ("previa", "preview"))
        vids = [n for n in VID_NAMES if (d / n).exists()]
        fmt = c["formato"]
        kind = "video" if (fmt == "video" and vids) or (fmt == "auto" and vids and not imgs) else "carrossel"
        if kind == "carrossel" and not imgs:
            continue
        files = [vids[0]] if kind == "video" else imgs
        cap_file = d / ("legenda.txt" if lang == "pt" else "caption.txt")
        caption = cap_file.read_text(encoding="utf-8").strip() if cap_file.exists() else ""
        title = _headline(post_id, lang) or (caption.splitlines()[0] if caption else "")
        out["profiles"][sub] = {
            "handle": brand()["handle"][lang],
            "blog_id": str((c.get("metricool") or {}).get(sub) or ""),
            "kind": kind,
            "media": [f"{base}/{sha}/{rel}/{sub}/{n}" for n in files],
            "caption": caption,
            "title": title[:90],
            "already_published": done.get(sub),
        }
    return out


def _headline(post_id: str, lang: str) -> str:
    try:
        from . import post
        data, _ = post.load(post_id)
        return (data.get(lang) or {}).get("headline", "").replace("*", "")
    except Exception:  # noqa: BLE001 — cortes/edições não têm post.yaml
        return ""


def mark(post_id: str, sub: str, ref: str, when: str | None = None) -> None:
    data = load_published()
    data.setdefault(post_id, {})[sub] = {"ref": ref, "at": when or dt.datetime.now(dt.timezone.utc).isoformat()}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
