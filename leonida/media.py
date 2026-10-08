"""Download de imagens (com cache), og:image de matérias e biblioteca oficial da Rockstar."""
from __future__ import annotations

import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image

from .config import CACHE_DIR, ROOT, USER_AGENT

HEADERS = {"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8"}
ROCKSTAR = "https://www.rockstargames.com"
ROCKSTAR_SCREENS_PAGE = f"{ROCKSTAR}/VI/downloads/screenshots"
LIBRARY_FILE = CACHE_DIR / "rockstar_library.json"


def _cache_path(url: str, suffix: str = "") -> Path:
    h = hashlib.sha1(url.encode()).hexdigest()[:16]
    ext = suffix or Path(url.split("?")[0]).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm", ".mov"):
        ext = ".img"
    return CACHE_DIR / "media" / f"{h}{ext}"


def fetch(url: str, referer: str | None = None, timeout: int = 30) -> Path:
    """Baixa uma URL para o cache local e devolve o caminho (reaproveita se já existe)."""
    path = _cache_path(url)
    if path.exists() and path.stat().st_size > 0:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    with requests.get(url, headers=headers, timeout=timeout, stream=True) as r:
        r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "text/html" in ctype:
            raise ValueError(f"URL devolveu HTML, não mídia: {url}")
        tmp = path.with_suffix(path.suffix + ".part")
        with open(tmp, "wb") as fh:
            for chunk in r.iter_content(1 << 16):
                fh.write(chunk)
        tmp.replace(path)
    return path


def resolve_image(ref: str, base_dir: Path | None = None) -> Path:
    """Aceita URL http(s), caminho relativo ao post, ou caminho relativo à raiz do projeto."""
    if re.match(r"^https?://", ref):
        referer = ROCKSTAR + "/VI" if "rockstargames.com" in ref else None
        return fetch(ref, referer=referer)
    for cand in ((base_dir / ref) if base_dir else None, ROOT / ref, Path(ref)):
        if cand and cand.exists():
            return cand
    raise FileNotFoundError(ref)


def load_image(ref: str, base_dir: Path | None = None) -> Image.Image:
    im = Image.open(resolve_image(ref, base_dir))
    im.load()
    return im.convert("RGB")


_META_RE = r'<meta[^>]+(?:property|name)=["\']{key}["\'][^>]+content=["\']([^"\']+)'
_META_RE_REV = r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\']{key}["\']'


def page_meta(url: str, timeout: int = 20) -> dict:
    """Lê og:image / og:title / og:description de uma matéria."""
    r = requests.get(url, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    out = {"final_url": r.url}
    for key, name in (("og:image", "image"), ("og:title", "title"),
                      ("og:description", "description"), ("og:video", "video"),
                      ("twitter:image", "twitter_image")):
        m = re.search(_META_RE.format(key=re.escape(key)), r.text, re.I) or \
            re.search(_META_RE_REV.format(key=re.escape(key)), r.text, re.I)
        if m:
            out[name] = html.unescape(m.group(1))
    if "image" not in out and "twitter_image" in out:
        out["image"] = out["twitter_image"]
    if out.get("image"):
        out["image"] = urljoin(r.url, out["image"])
    return out


def sync_rockstar_library(force: bool = False) -> list[dict]:
    """Lista as screenshots oficiais de GTA VI publicadas no site da Rockstar.

    Útil como imagem de fundo quando a notícia não tem uma imagem boa.
    """
    if LIBRARY_FILE.exists() and not force:
        return json.loads(LIBRARY_FILE.read_text())
    r = requests.get(ROCKSTAR_SCREENS_PAGE, headers=HEADERS, timeout=30)
    r.raise_for_status()
    paths = sorted(set(re.findall(
        r'/VI/_next/static/media/([A-Za-z_]+_\d{2})\.[^"\'\s)\\]+\.(?:jpg|jpeg|png|webp)', r.text)))
    full = {}
    for m in re.finditer(r'(/VI/_next/static/media/([A-Za-z_]+_\d{2})\.[^"\'\s)\\]+\.(?:jpg|jpeg|png|webp))', r.text):
        full.setdefault(m.group(2), ROCKSTAR + m.group(1))
    items = []
    for name in paths:
        group = re.sub(r"_\d{2}$", "", name)
        items.append({"name": name, "group": group, "url": full[name]})
    LIBRARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_FILE.write_text(json.dumps(items, indent=1))
    return items


def library_pick(group_hint: str = "", index: int = 0) -> str | None:
    """Escolhe uma screenshot oficial pelo nome do grupo (ex.: 'Vice_City', 'Lucia_Caminos')."""
    try:
        items = sync_rockstar_library()
    except Exception:
        return None
    pool = [i for i in items if group_hint.lower() in i["group"].lower()] or items
    pool = [i for i in pool if not i["group"].startswith(("ULTIMATE", "VINTAGE"))] or pool
    return pool[index % len(pool)]["url"] if pool else None
