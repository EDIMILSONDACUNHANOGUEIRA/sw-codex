"""Radar de notícias de GTA VI: busca os feeds, filtra, agrupa a mesma história e ranqueia."""
from __future__ import annotations

import calendar
import concurrent.futures as cf
import datetime as dt
import hashlib
import html
import json
import os
import re
import tempfile
import threading
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


def _clean_title(title: str, outlet: str | None = None) -> str:
    """Tira tags HTML e, nos agregadores, o sufixo " - Veículo" que o Google News acrescenta.
    Só remove o sufixo quando ele é o nome do veículo: "GTA 6 - Trailer 3" fica inteiro."""
    title = html.unescape(re.sub(r"<[^>]+>", "", title or "")).strip()
    if outlet:
        suffix = re.compile(r"\s+[-–|]\s+" + re.escape(outlet.strip()) + r"\s*$", re.I)
        title = suffix.sub("", title)
    return title.strip()


# Classificação editorial. O dono só publica notícia OFICIAL ou confirmada: vazamento e rumor
# aparecem no radar com selo, mas nunca viram post (writer, auto e app bloqueiam).
LEAK_RE = re.compile(r"\b(?:leak\w*|leaker\w*|cyberle+k\w*|vaza\w*|vazou|datamin\w*|insiders?(?!\s*gaming)|"
                     r"hack(?:er|ers|ed)?|stolen|roubad\w*)\b", re.I)
RUMOR_RE = re.compile(r"\b(?:rumou?r\w*|boato\w*|unconfirmed|n[aã]o confirmad\w*|reportedly|allegedly|"
                      r"supostamente|teoria|theory|speculat\w*|especula\w*|alegadamente)\b", re.I)
BLOCKED_KINDS = ("vazamento", "rumor")
OFFICIAL_HOSTS = ("rockstargames.com", "take2games.com", "youtube.com/channel/UCULwHhkI31JHAKe57LZdzcA")
OTHER_GTA_RE = re.compile(r"\b(?:gta\s*(?:v|5|online|iv|4|san andreas|vice city stories)|grand theft auto\s*(?:v|online|iv))\b", re.I)
GTA6_RE = re.compile(r"\b(?:gta\s*(?:vi|6)|grand theft auto\s*(?:vi|6))\b", re.I)


def classify_text(text: str) -> str:
    if LEAK_RE.search(text or ""):
        return "vazamento"
    if RUMOR_RE.search(text or ""):
        return "rumor"
    return "noticia"


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


def _has_phrase(norm_text: str, phrase: str) -> bool:
    """Palavra/frase inteira ("oficial" não casa com "não oficial"... nem "deal" com "ideal")."""
    k = _norm(phrase).strip()
    return bool(k) and f" {k} " in f" {norm_text} "


NEGATED_OFFICIAL = re.compile(r"\b(?:unofficial|nao oficial|not official|sem confirmacao)\b")


def _score_item(text: str, kw: dict) -> int:
    t = re.sub(r"\s+", " ", _norm(text)).strip()
    s = 0
    for k, v in (kw.get("boost") or {}).items():
        if _has_phrase(t, str(k)):
            if _norm(str(k)).strip() in ("official", "oficial") and NEGATED_OFFICIAL.search(t):
                continue
            s += int(v)
    for k, v in (kw.get("penalty") or {}).items():
        if _has_phrase(t, str(k)):
            s += int(v)
    return s


def _fetch_feed(src: dict) -> list[dict]:
    d, last_exc = None, None
    for attempt in range(3):              # feeds do YouTube/Reddit falham de forma intermitente
        try:
            r = requests.get(src["url"], headers={"User-Agent": USER_AGENT}, timeout=25)
            r.raise_for_status()
            d = feedparser.parse(r.content)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    if d is None:
        return [{"_error": f"{src['name']}: {last_exc}"}]
    items = []
    now = _now()
    aggregator = bool(src.get("aggregator"))
    for e in d.entries[:60]:
        ts = e.get("published_parsed") or e.get("updated_parsed")
        if not ts:
            continue                      # sem data: subiria como "agora" a cada busca
        published = calendar.timegm(ts)
        if published > now + 3600:
            continue                      # data no futuro (feed quebrado) iria para o topo
        outlet = None
        if aggregator:
            srcinfo = e.get("source") or {}
            outlet = (srcinfo.get("title") if hasattr(srcinfo, "get") else None) or None
        title = _clean_title(e.get("title", ""), outlet)
        summary = html.unescape(re.sub(r"<[^>]+>", " ", e.get("summary", "") or ""))
        summary = re.sub(r"\s+", " ", summary).strip()[:500]
        if outlet:
            summary = re.sub(r"\s*" + re.escape(outlet) + r"\s*$", "", summary).strip()
            if _norm(summary).strip() == _norm(title).strip():
                summary = ""
        link = e.get("link", "")
        # "oficial" só para a própria Rockstar/Take-Two e falando de GTA VI (o Google indexa páginas
        # velhas do site da Rockstar — login, GTA V, loja — com data de rastreamento recente)
        official = bool(src.get("official")) and (not aggregator or bool(GTA6_RE.search(title)))
        thumb = None
        for key in ("media_thumbnail", "media_content"):
            if e.get(key):
                thumb = e[key][0].get("url")
                break
        items.append({
            "title": title,
            "url": link,
            "summary": summary,
            "published": published,
            "source": outlet or src["name"],
            "feed": src["name"],
            "kind": classify_text(f"{title} {summary}"),
            "lang": src.get("lang", "en"),
            "weight": float(src.get("weight", 1.0)),
            "official": official,
            "community": bool(src.get("community")),
            "aggregator": aggregator,
            "video": bool(src.get("video")) or "youtube.com" in link,
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
                if not GTA6_RE.search(it["title"]) and OTHER_GTA_RE.search(it["title"]):
                    it["kw_score"] -= 40      # GTA V / GTA Online / jogos antigos não são o foco
                items.append(it)
    return items, errors


def cluster(items: list[dict], threshold: float = 0.3) -> list[dict]:
    """Agrupa matérias sobre a mesma história (similaridade de palavras do título)."""
    items = sorted(items, key=lambda x: (-x["weight"], -x["published"]))
    clusters: list[dict] = []
    for it in items:
        toks = _tokens(it["title"])
        risky = it.get("kind") in BLOCKED_KINDS
        best, best_sim = None, 0.0
        for c in clusters:
            if c["risky"] != risky:
                continue                  # nunca mistura vazamento/rumor com notícia limpa
            inter = len(toks & c["tokens"])
            union = len(toks | c["tokens"]) or 1
            sim = max(inter / union, inter / (min(len(toks), len(c["tokens"])) or 1) * 0.75)
            if sim > best_sim:
                best, best_sim = c, sim
        if best and best_sim >= threshold:
            best["items"].append(it)
            best["tokens"] |= toks
        else:
            clusters.append({"tokens": set(toks), "items": [it], "risky": risky})
    return clusters


TOPICS = ["radio", "podcast", "screenshot", "trailer", "delay", "price", "preorder", "australia"]


def merge_by_topic(clusters: list[dict]) -> list[dict]:
    """Segunda passada: junta grupos do MESMO tema que também falam da mesma coisa (pelo menos 2
    palavras em comum além do tema e da mesma classe). Antes juntava todo "leak" numa história só —
    73 matérias diferentes viravam uma, e um rumor fundido com algo oficial ganhava selo OFICIAL."""
    out: list[dict] = []
    for c in clusters:
        counts = {t: sum(1 for i in c["items"] if t in _tokens(i["title"])) for t in TOPICS}
        top = max(counts, key=counts.get)
        if counts[top] == 0 or counts[top] < len(c["items"]) / 2:
            out.append(c)
            continue
        target = None
        for o in out:
            if o.get("topic") != top or o.get("risky") != c.get("risky"):
                continue
            if len((o["tokens"] & c["tokens"]) - {top}) >= 2:
                target = o
                break
        if target:
            target["items"].extend(c["items"])
            target["tokens"] |= c["tokens"]
        else:
            c["topic"] = top
            out.append(c)
    return out


def story_kind(items: list[dict]) -> str:
    """vazamento | rumor | oficial | confirmada (2+ veículos diferentes) | noticia."""
    kinds = {i.get("kind", "noticia") for i in items}
    if "vazamento" in kinds:
        return "vazamento"
    if "rumor" in kinds:
        return "rumor"
    if any(i["official"] for i in items):
        return "oficial"
    outlets = {i["source"] for i in items if not i.get("community")}
    return "confirmada" if len(outlets) >= 2 else "noticia"


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
    hours = max(0.0, (_now() - oldest) / 3600)
    kind = story_kind(its)
    official = kind == "oficial"
    score = (max(i["kw_score"] for i in its) + 12 * min(coverage, 12)
             + 25 * max(i["weight"] for i in its) + (30 if official else 0)
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
        "kind": kind,
        "blocked": kind in BLOCKED_KINDS,
        "official": official,
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
    _write_json(RADAR_FILE, data)
    write_markdown(data)
    return data


def _write_text_atomic(path, text: str) -> None:
    """Grava num temporário e troca de uma vez: quem lê nunca pega o arquivo pela metade."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_json(path, data) -> None:
    _write_text_atomic(path, json.dumps(data, ensure_ascii=False, indent=1))


def _read_json(path, default):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        return default                    # arquivo corrompido/vazio não derruba o radar
    return data if isinstance(data, type(default)) else default


def load_radar() -> dict:
    data = _read_json(RADAR_FILE, {"stories": []})
    data.setdefault("stories", [])
    return data


def load_seen() -> dict:
    return _read_json(SEEN_FILE, {})


def _story_tokens(story: dict) -> set[str]:
    toks: set[str] = set()
    for src in story.get("sources", []):
        toks |= _tokens(src.get("title", ""))
    return toks or _tokens(story.get("title", ""))


def mark_seen(story_ids, status: str = "seen") -> None:
    """Marca histórias como vistas. Guarda as palavras-chave para reconhecer a mesma história
    mesmo que o título principal mude na próxima busca."""
    with _SEEN_LOCK:
        _mark_seen_locked(story_ids, status)


_SEEN_LOCK = threading.Lock()


def _mark_seen_locked(story_ids, status: str) -> None:
    seen = load_seen()
    by_id = {s["id"]: s for s in load_radar().get("stories", [])}
    for sid in story_ids:
        entry = {"status": status, "at": dt.datetime.now(dt.timezone.utc).isoformat()}
        if sid in by_id:
            entry["title"] = by_id[sid]["title"]
            entry["tokens"] = sorted(_story_tokens(by_id[sid]))
            entry["kind"] = by_id[sid].get("kind")
        seen[sid] = entry
    _write_json(SEEN_FILE, seen)


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
        if entry.get("kind") and (entry["kind"] in BLOCKED_KINDS) != (story.get("kind") in BLOCKED_KINDS):
            continue                      # um vazamento visto não silencia a confirmação oficial
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
        flags = ("⭐ " if s["official"] else "") + ("🎬 " if s["video"] else "") + \
            ({"vazamento": "🚫 VAZAMENTO ", "rumor": "🚫 RUMOR "}.get(s.get("kind"), ""))
        lines.append(f"| {i} | {s['score']:.0f} | {flags}[{t}]({link}) | {s['coverage']} | "
                     f"{'🆕' if s.get('is_new') else ''} |")
    _write_text_atomic(OUT_DIR / "RADAR.md", "\n".join(lines) + "\n")
