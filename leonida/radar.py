"""Radar de notícias de GTA VI: busca os feeds, filtra, agrupa a mesma história e ranqueia."""
from __future__ import annotations

import calendar
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import re
import time
import unicodedata

import feedparser
import requests

from .config import OUT_DIR, STATE_DIR, USER_AGENT, sources

RADAR_FILE = STATE_DIR / "radar.json"
SEEN_FILE = STATE_DIR / "seen.json"

STOP = set("""a o os as de da do das dos e em no na nos nas um uma para por com que se ao à
the a an of to in on for and with is are be at by from as it its this that new gta 6 vi grand theft
auto rockstar game games jogo""".split())


def _now() -> float:
    return time.time()


def _clean_title(title: str) -> str:
    title = html.unescape(re.sub(r"<[^>]+>", "", title or "")).strip()
    # Google News: "Título - Veículo"
    return re.sub(r"\s+[-–|]\s+[^-–|]{2,40}$", "", title).strip()


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]+", " ", text)


# sinônimos PT/EN -> forma canônica (ajuda a agrupar a mesma história nos dois idiomas)
CANON = {
    "leak": "leak", "leaks": "leak", "leaked": "leak", "leaker": "leak", "cyberleek": "leak",
    "vazamento": "leak", "vazamentos": "leak", "vazado": "leak", "vazada": "leak", "vaza": "leak",
    "radio": "radio", "radios": "radio", "station": "radio", "stations": "radio", "estacoes": "radio",
    "estacao": "radio", "podcast": "podcast", "podcasts": "podcast", "music": "radio", "musica": "radio",
    "screenshot": "screenshot", "screenshots": "screenshot", "imagens": "screenshot", "images": "screenshot",
    "trailer": "trailer", "gameplay": "gameplay", "minutes": "minutes", "minutos": "minutes",
    "release": "release", "lancamento": "release", "delay": "delay", "delayed": "delay", "adiado": "delay",
    "adiamento": "delay", "price": "price", "preco": "price", "preorder": "preorder", "prevenda": "preorder",
    "first": "first", "primeira": "first", "person": "person", "pessoa": "person", "headphones": "headphones",
    "fones": "headphones", "foot": "foot", "australia": "australia", "australian": "australia",
    "australiano": "australia", "governo": "government", "government": "government",
}


def _tokens(text: str) -> set[str]:
    out = set()
    for w in _norm(text).split():
        if len(w) <= 2 or w in STOP:
            continue
        out.add(CANON.get(w, w))
    return out


def _match(text: str, must: list[str]) -> bool:
    t = " " + _norm(text) + " "
    return any((" " + _norm(k) + " ") in t or _norm(k).replace(" ", "") in t.replace(" ", "") for k in must)


def _score_item(text: str, kw: dict) -> int:
    t = _norm(text)
    s = 0
    for k, v in (kw.get("boost") or {}).items():
        if _norm(str(k)) in t:
            s += int(v)
    for k, v in (kw.get("penalty") or {}).items():
        if _norm(str(k)) in t:
            s += int(v)
    return s


def _fetch_feed(src: dict) -> list[dict]:
    try:
        r = requests.get(src["url"], headers={"User-Agent": USER_AGENT}, timeout=25)
        r.raise_for_status()
        d = feedparser.parse(r.content)
    except Exception as exc:  # noqa: BLE001
        return [{"_error": f"{src['name']}: {exc}"}]
    items = []
    for e in d.entries[:60]:
        ts = e.get("published_parsed") or e.get("updated_parsed")
        published = calendar.timegm(ts) if ts else _now()
        summary = html.unescape(re.sub(r"<[^>]+>", " ", e.get("summary", "") or ""))
        summary = re.sub(r"\s+", " ", summary).strip()[:500]
        thumb = None
        for key in ("media_thumbnail", "media_content"):
            if e.get(key):
                thumb = e[key][0].get("url")
                break
        items.append({
            "title": _clean_title(e.get("title", "")),
            "url": e.get("link", ""),
            "summary": summary,
            "published": published,
            "source": src["name"],
            "lang": src.get("lang", "en"),
            "weight": float(src.get("weight", 1.0)),
            "official": bool(src.get("official")),
            "community": bool(src.get("community")),
            "aggregator": bool(src.get("aggregator")),
            "video": bool(src.get("video")) or "youtube.com" in e.get("link", ""),
            "thumb": thumb,
        })
    return items


def fetch_all(max_age_hours: float = 72) -> tuple[list[dict], list[str]]:
    cfg = sources()
    kw = cfg.get("keywords", {})
    must = kw.get("must_match", [])
    items, errors = [], []
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for batch in ex.map(_fetch_feed, cfg["sources"]):
            for it in batch:
                if "_error" in it:
                    errors.append(it["_error"])
                    continue
                if _now() - it["published"] > max_age_hours * 3600:
                    continue
                text = f"{it['title']} {it['summary']}"
                if not _match(text, must):
                    continue
                it["kw_score"] = _score_item(text, kw)
                items.append(it)
    return items, errors


def cluster(items: list[dict], threshold: float = 0.3) -> list[dict]:
    """Agrupa matérias sobre a mesma história (similaridade de palavras do título)."""
    items = sorted(items, key=lambda x: (-x["weight"], -x["published"]))
    clusters: list[dict] = []
    for it in items:
        toks = _tokens(it["title"])
        best, best_sim = None, 0.0
        for c in clusters:
            inter = len(toks & c["tokens"])
            union = len(toks | c["tokens"]) or 1
            sim = max(inter / union, inter / (min(len(toks), len(c["tokens"])) or 1) * 0.75)
            if sim > best_sim:
                best, best_sim = c, sim
        if best and best_sim >= threshold:
            best["items"].append(it)
            best["tokens"] |= toks
        else:
            clusters.append({"tokens": set(toks), "items": [it]})
    return clusters


TOPICS = ["leak", "radio", "podcast", "screenshot", "trailer", "delay", "price", "preorder", "australia"]


def merge_by_topic(clusters: list[dict]) -> list[dict]:
    """Segunda passada: junta grupos cujo tema dominante é o mesmo (ex.: todos os 'leak')."""
    merged: dict[str, dict] = {}
    out = []
    for c in clusters:
        counts = {t: sum(1 for i in c["items"] if t in _tokens(i["title"])) for t in TOPICS}
        top = max(counts, key=counts.get)
        if counts[top] == 0 or counts[top] < len(c["items"]) / 2:
            out.append(c)
            continue
        if top in merged:
            merged[top]["items"].extend(c["items"])
            merged[top]["tokens"] |= c["tokens"]
        else:
            merged[top] = c
            out.append(c)
    return out


def _story(c: dict) -> dict:
    its = c["items"]
    lead = max(its, key=lambda x: (not x["aggregator"], x["weight"], -x["published"]))
    pt = [i for i in its if i["lang"] == "pt"]
    en = [i for i in its if i["lang"] == "en"]
    outlets = {i["source"] for i in its}
    # Google News agrega vários veículos: conta cada manchete como uma fonte distinta
    coverage = len(outlets) + sum(1 for i in its if i["aggregator"]) * 0.5
    newest = max(i["published"] for i in its)
    oldest = min(i["published"] for i in its)
    hours = (_now() - oldest) / 3600
    score = (max(i["kw_score"] for i in its) + 12 * min(coverage, 12)
             + 25 * max(i["weight"] for i in its) + (30 if any(i["official"] for i in its) else 0)
             - 1.6 * hours)
    sid = hashlib.sha1(_norm(lead["title"]).encode()).hexdigest()[:10]
    return {
        "id": sid,
        "title": lead["title"],
        "title_pt": (max(pt, key=lambda x: x["weight"])["title"] if pt else None),
        "title_en": (max(en, key=lambda x: x["weight"])["title"] if en else None),
        "summary": lead["summary"][:300],
        "score": round(score, 1),
        "coverage": len(its),
        "official": any(i["official"] for i in its),
        "video": any(i["video"] for i in its),
        "community": all(i["community"] for i in its),
        "published": dt.datetime.fromtimestamp(newest, dt.timezone.utc).isoformat(),
        "first_seen": dt.datetime.fromtimestamp(oldest, dt.timezone.utc).isoformat(),
        "thumb": next((i["thumb"] for i in its if i.get("thumb")), None),
        "sources": [{"name": i["source"], "title": i["title"], "url": i["url"], "lang": i["lang"]}
                    for i in sorted(its, key=lambda x: -x["weight"])][:12],
    }


def scan(max_age_hours: float = 72, limit: int = 40) -> dict:
    items, errors = fetch_all(max_age_hours)
    stories = sorted((_story(c) for c in merge_by_topic(cluster(items))), key=lambda s: -s["score"])[:limit]
    seen = load_seen()
    for s in stories:
        s["is_new"] = not is_seen(s, seen)
    data = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "count": len(stories),
            "errors": errors, "stories": stories}
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    RADAR_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    write_markdown(data)
    return data


def load_radar() -> dict:
    if RADAR_FILE.exists():
        return json.loads(RADAR_FILE.read_text(encoding="utf-8"))
    return {"stories": []}


def load_seen() -> dict:
    if SEEN_FILE.exists():
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    return {}


def _story_tokens(story: dict) -> set[str]:
    toks: set[str] = set()
    for src in story.get("sources", []):
        toks |= _tokens(src.get("title", ""))
    return toks or _tokens(story.get("title", ""))


def mark_seen(story_ids, status: str = "seen") -> None:
    """Marca histórias como vistas. Guarda as palavras-chave para reconhecer a mesma história
    mesmo que o título principal mude na próxima busca."""
    seen = load_seen()
    by_id = {s["id"]: s for s in load_radar().get("stories", [])}
    for sid in story_ids:
        entry = {"status": status, "at": dt.datetime.now(dt.timezone.utc).isoformat()}
        if sid in by_id:
            entry["title"] = by_id[sid]["title"]
            entry["tokens"] = sorted(_story_tokens(by_id[sid]))
        seen[sid] = entry
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(seen, ensure_ascii=False, indent=1), encoding="utf-8")


def is_seen(story: dict, seen: dict | None = None, max_age_hours: float = 72) -> bool:
    seen = load_seen() if seen is None else seen
    if story["id"] in seen:
        return True
    toks = _story_tokens(story)
    now = dt.datetime.now(dt.timezone.utc)
    for entry in seen.values():
        if not entry.get("tokens"):
            continue
        try:
            age = (now - dt.datetime.fromisoformat(entry["at"])).total_seconds() / 3600
        except Exception:
            age = 0
        if age > max_age_hours:
            continue
        other = set(entry["tokens"])
        shared = len(toks & other)
        if shared >= 4 and shared / (min(len(toks), len(other)) or 1) >= 0.5:
            return True
    return False


def write_markdown(data: dict) -> None:
    """prontos/RADAR.md — painel das notícias do momento, legível direto no GitHub."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    lines = ["# 📡 Radar GTA VI", "", f"Atualizado: {data['generated_at'][:16].replace('T', ' ')} UTC", "",
             "| # | Score | Notícia | Fontes | Novo |", "|---|---|---|---|---|"]
    for i, s in enumerate(data["stories"][:30], 1):
        t = s["title"].replace("|", "/")
        if s.get("title_pt") and s["title_pt"] != s["title"]:
            t += f"<br>🇧🇷 {s['title_pt'].replace('|', '/')}"
        link = s["sources"][0]["url"]
        flags = ("⭐ " if s["official"] else "") + ("🎬 " if s["video"] else "")
        lines.append(f"| {i} | {s['score']:.0f} | {flags}[{t}]({link}) | {s['coverage']} | "
                     f"{'🆕' if s.get('is_new') else ''} |")
    (OUT_DIR / "RADAR.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
