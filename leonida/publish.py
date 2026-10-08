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

from . import music
from .config import LANG_FOLDER, LANGS, OUT_DIR, ROOT, STATE_DIR, brand

PUBLISHED = STATE_DIR / "publicados.json"
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
TIKTOK_DIR = "tiktok"


def export_jpegs(folder: Path) -> list[Path]:
    """Cópias JPEG (qualidade 95, cor sem subamostragem) das artes PNG, para o TikTok."""
    from PIL import Image
    out_dir = folder / TIKTOK_DIR
    if out_dir.exists():
        for old in out_dir.glob("*.jpg"):
            old.unlink()
    out = []
    for png in sorted(folder.glob("*.png")):
        if png.stem in ("previa", "preview"):
            continue
        out_dir.mkdir(exist_ok=True)
        dst = out_dir / f"{png.stem}.jpg"
        Image.open(png).convert("RGB").save(dst, "JPEG", quality=95, subsampling=0, optimize=True)
        out.append(dst)
    return out
VID_NAMES = ("video.mp4", "edicao.mp4", "edit.mp4", "corte.mp4", "clip.mp4")


def cfg() -> dict:
    c = {"repo_raw": "", "revisao_manual": ["vazamento", "rumor"], "formato": "auto",
         "metricool": {"br": "", "us": ""}, "limite_mensal": 20, "limite_diario": 1,
         "fuso": "America/Cuiaba"}
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
    out = {"id": post_id, "tag": tag, "manual_review": tag in c["revisao_manual"], "quota": quota(),
           "profiles": {}}
    for lang in LANGS:
        sub = LANG_FOLDER[lang]
        d = folder / sub
        if not d.exists():
            continue
        fmt = c["formato"]
        cap_file = d / ("legenda.txt" if lang == "pt" else "caption.txt")
        caption = cap_file.read_text(encoding="utf-8").strip() if cap_file.exists() else ""
        title = _headline(post_id, lang) or (caption.splitlines()[0] if caption else "")
        # vídeo de publicação (com a música tema embutida): tiktok/post.mp4, ou a edição/corte de vídeo
        # (a capa animada video.mp4 sozinha nunca é publicada: o vídeo do post é tiktok/post.mp4)
        own = ("edicao.mp4", "edit.mp4", "corte.mp4", "clip.mp4") if meta.get("type") in ("edit", "clip") else ()
        vids = [n for n in (f"{TIKTOK_DIR}/post.mp4", *own) if (d / n).exists()]
        if own and vids and not music.themes():
            vids = []                         # edição/corte sem música tema: não publica
        # o TikTok só aceita JPEG/WebP em post de fotos: usa a cópia em tiktok/*.jpg
        jpg_dir = d / TIKTOK_DIR
        imgs = sorted(f"{TIKTOK_DIR}/{p.name}" for p in jpg_dir.glob("*.jpg")) if jpg_dir.exists() else []
        if fmt == "video" or (fmt == "auto" and vids):
            kind, files = "video", vids[:1]
        else:
            kind, files = "carrossel", imgs
        ready, reason = bool(files), ""
        if not files:
            reason = ("vídeo com música tema não gerado: falta a música em assets/music/ "
                      "(python -m leonida musica \"URL do trailer\" --inicio 0:12) — rode o build de novo"
                      if kind == "video" else "sem artes em tiktok/*.jpg — rode o build de novo")
        media = [f"{base}/{sha}/{rel}/{sub}/{n}" for n in files]
        tiktok_data = {"disableComment": False, "disableDuet": False, "disableStitch": False,
                       "privacyOption": "PUBLIC_TO_EVERYONE", "commercialContentThirdParty": False,
                       "commercialContentOwnBrand": False,
                       # NUNCA música automática: o TikTok sorteia qualquer faixa. A música tema vai
                       # embutida no vídeo.
                       "autoAddMusic": False, "isAigc": False}
        if kind == "carrossel":
            tiktok_data.update({"title": title[:90], "photoCoverIndex": 0})
        out["profiles"][sub] = {
            "handle": brand()["handle"][lang],
            "blog_id": str((c.get("metricool") or {}).get(sub) or ""),
            "kind": kind,
            "ready": ready,
            "reason": reason,
            "media": media,
            "caption": caption,
            "title": title[:90],
            "already_published": done.get(sub),
            # pronto para o Metricool (createScheduledPost → info); falta só publicationDate
            "metricool_info": {
                "autoPublish": True, "draft": out["manual_review"], "descendants": [], "firstCommentText": "",
                "hasNotReadNotes": False, "media": media, "mediaAltText": [], "providers": [{"network": "tiktok"}],
                "publicationDate": {"dateTime": "AAAA-MM-DDTHH:MM:00", "timezone": c.get("fuso", "America/Cuiaba")},
                "shortener": False, "smartLinkData": {"ids": []}, "text": caption, "tiktokData": tiktok_data,
            },
        }
    return out


def quota(sub: str = "br", today: dt.date | None = None) -> dict:
    """Quantas publicações automáticas ainda cabem no plano do Metricool (mês e dia)."""
    c = cfg()
    today = today or dt.date.today()
    month = day = 0
    for entry in load_published().values():
        e = entry.get(sub)
        if not e or e.get("ref", "").startswith("manual"):
            continue
        d = dt.date.fromisoformat(str(e.get("for") or e["at"])[:10])
        if (d.year, d.month) == (today.year, today.month):
            month += 1
            if d == today:
                day += 1
    m_left = max(0, int(c["limite_mensal"]) - month)
    d_left = max(0, int(c["limite_diario"]) - day)
    return {"mes_usadas": month, "mes_restantes": m_left, "hoje_usadas": day, "hoje_restantes": d_left,
            "pode_agendar": min(m_left, d_left)}


def _headline(post_id: str, lang: str) -> str:
    try:
        from . import post
        data, _ = post.load(post_id)
        return (data.get(lang) or {}).get("headline", "").replace("*", "")
    except Exception:  # noqa: BLE001 — cortes/edições não têm post.yaml
        return ""


def mark(post_id: str, sub: str, ref: str, when: str | None = None) -> None:
    """ref = id do Metricool, ou 'manual' quando eu postei pelo app (não conta na cota)."""
    data = load_published()
    data.setdefault(post_id, {})[sub] = {"ref": ref, "at": dt.datetime.now(dt.timezone.utc).isoformat(),
                                         "for": when or dt.date.today().isoformat()}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PUBLISHED.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
