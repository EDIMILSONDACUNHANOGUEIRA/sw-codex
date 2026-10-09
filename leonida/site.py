"""Site de notícias OFICIAIS de GTA VI (Leonida Wire), gerado a partir dos posts.

    python -m leonida site          # gera site/ (HTML estático) a partir de posts/*/post.yaml

Cada post publicado no TikTok vira uma matéria no site, com a imagem oficial limpa no topo, o texto,
a galeria (arte editada + imagem limpa + slides) e as fontes. Só entram notícias oficiais/confirmadas:
posts com tag vazamento ou rumor (ou `site: false`) ficam de fora.

O site é estático (HTML + CSS + um pouco de JS para o contador) e fica em site/, versionado no git.
A Vercel publica essa pasta (vercel.json).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import re
import shutil
from pathlib import Path
from urllib.parse import quote

from PIL import Image

from .config import FONTS_DIR, OUT_DIR, POSTS_DIR, ROOT, brand, days_to_release

SITE_DIR = ROOT / "site"
ASSETS_SRC = Path(__file__).resolve().parent / "site_assets"
EXCLUDE_TAGS = {"vazamento", "rumor"}
TAG_LABEL = {"oficial": "Oficial", "urgente": "Urgente", "viral": "Viralizou", "contagem": "Contagem",
             "analise": "Análise"}
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro",
          "outubro", "novembro", "dezembro"]


def cfg() -> dict:
    c = {"nome": "Leonida Wire", "url": "https://leonida-wire-sage.vercel.app",
         "descricao": "Notícias oficiais de GTA VI todos os dias, em português.",
         "tiktok": "https://www.tiktok.com/@leonidawirebrz"}
    c.update(brand().get("site") or {})
    c["url"] = c["url"].rstrip("/")
    return c


# ------------------------------------------------------------------ texto

def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def strip_marks(s: str) -> str:
    return (s or "").replace("*", "")


def marked_html(s: str) -> str:
    """'GTA VI revela *rádios*' -> GTA VI revela <em>rádios</em> (destaque da manchete)."""
    out, hot = [], False
    for part in re.split(r"(\*)", s or ""):
        if part == "*":
            out.append("</em>" if hot else "<em>")
            hot = not hot
        else:
            out.append(esc(part))
    if hot:
        out.append("</em>")
    return "".join(out)


def inline_md(s: str) -> str:
    """Markdown mínimo dentro de um parágrafo: **negrito**, *itálico*, [link](url)."""
    t = esc(s)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
               lambda m: f'<a href="{m.group(2)}" target="_blank" rel="noopener">{m.group(1)}</a>', t)
    t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", t)
    return t


def md_to_html(md: str) -> str:
    """Markdown simples (parágrafos, ## títulos, listas com - , citações >) para HTML seguro."""
    blocks, para, items = [], [], []

    def flush():
        nonlocal para, items
        if para:
            blocks.append(f"<p>{inline_md(' '.join(para))}</p>")
            para = []
        if items:
            blocks.append("<ul>" + "".join(f"<li>{inline_md(i)}</li>" for i in items) + "</ul>")
            items = []

    for raw in (md or "").splitlines():
        line = raw.strip()
        if not line:
            flush()
        elif line.startswith("## "):
            flush()
            blocks.append(f"<h2>{inline_md(line[3:])}</h2>")
        elif line.startswith(("- ", "• ")):
            if para:
                flush()
            items.append(line[2:])
        elif line.startswith("> "):
            flush()
            blocks.append(f"<blockquote>{inline_md(line[2:])}</blockquote>")
        else:
            if items:
                flush()
            para.append(line)
    flush()
    return "\n".join(blocks)


EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]+")


def caption_to_md(caption: str) -> str:
    """Legenda do TikTok -> texto de matéria: tira emojis e a pergunta final de engajamento."""
    lines = [EMOJI_RE.sub("", ln).strip() for ln in (caption or "").strip().splitlines()]
    while lines and (not lines[-1] or lines[-1].endswith("?")):
        lines.pop()
    return "\n\n".join(ln for ln in lines if ln)          # cada linha da legenda vira um parágrafo


def fmt_date(d: str) -> str:
    x = dt.date.fromisoformat(str(d)[:10])
    return f"{x.day} de {MONTHS[x.month - 1]} de {x.year}"


# ------------------------------------------------------------------ dados

def load_articles() -> list[dict]:
    """Matérias do site a partir de posts/*/post.yaml (só oficiais), da mais nova para a mais antiga."""
    import yaml
    arts = []
    for f in sorted(POSTS_DIR.glob("*/post.yaml")):
        p = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        p.setdefault("id", f.parent.name)
        tag = (p.get("tag") or "").lower()
        if tag in EXCLUDE_TAGS or p.get("site") is False or "pt" not in p:
            continue
        pt = p["pt"]
        site_cfg = p.get("site") if isinstance(p.get("site"), dict) else {}
        slug = re.sub(r"^\d{4}-\d{2}-\d{2}-", "", p["id"])
        date = str(p.get("date") or p["id"][:10])[:10]
        folder = next(iter(sorted(OUT_DIR.glob(f"*/{p['id']}"))), None)
        body_md = site_cfg.get("texto") or caption_to_md(pt.get("caption", ""))
        extras = []
        for sl in pt.get("slides") or []:
            title = strip_marks(sl.get("title", ""))
            if sl.get("type") == "list" and sl.get("items"):
                extras.append(f"## {title}\n" + "\n".join(f"- {i}" for i in sl["items"]))
            elif sl.get("type") == "grid" and sl.get("items"):
                extras.append(f"## {title}\n" + "\n".join(
                    f"- **{i.get('label', '')}**" + (f": {i['sub']}" if i.get("sub") else "") for i in sl["items"]))
        if not site_cfg.get("texto") and extras:
            body_md += "\n\n" + "\n\n".join(extras)
        arts.append({
            "id": p["id"], "slug": slug, "date": date, "tag": tag,
            "kicker": pt.get("kicker", ""),
            "headline": pt.get("headline", ""), "title": strip_marks(pt.get("headline", "")),
            "summary": pt.get("summary", ""), "body_html": md_to_html(body_md),
            "hashtags": pt.get("hashtags") or [],
            "source": p.get("source") or {}, "image": p.get("image"), "base_dir": f.parent,
            "fotos_limpas": p.get("fotos_limpas") or [], "folder": folder,
            "tiktok_url": site_cfg.get("tiktok"),
        })
    arts.sort(key=lambda a: (a["date"], _added_at(a["base_dir"] / "post.yaml"), a["id"]), reverse=True)
    return arts


def _added_at(f: Path) -> int:
    """Quando o post entrou no git (desempata notícias do mesmo dia: a mais recente primeiro)."""
    import subprocess
    try:
        out = subprocess.run(["git", "log", "--diff-filter=A", "--format=%ct", "--", str(f)], cwd=ROOT,
                             capture_output=True, text=True, timeout=10).stdout.split()
        if out:
            return int(out[-1])
    except Exception:  # noqa: BLE001
        pass
    return int(f.stat().st_mtime)


# ------------------------------------------------------------------ imagens

def _save_web(im: Image.Image, dst: Path, width: int, quality: int = 82, fmt: str = "WEBP") -> tuple[int, int]:
    im = im.convert("RGB")
    if im.width > width:
        im = im.resize((width, int(round(im.height * width / im.width))), Image.LANCZOS)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "WEBP":
        im.save(dst, "WEBP", quality=quality, method=6)
    else:
        im.save(dst, "JPEG", quality=quality, optimize=True, progressive=True)
    return im.size


def build_images(a: dict, out: Path) -> dict:
    """Imagem limpa (hero 16:9), miniatura, og:image e galeria (arte editada + limpa + slides)."""
    from .media import load_image
    imgdir = out / "img" / a["slug"]
    res = {"hero": None, "thumb": None, "og": None, "gallery": []}
    src = None
    if a.get("image"):
        try:
            src = load_image(a["image"], a["base_dir"]).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            print(f"  [site] sem imagem para {a['id']}: {exc}")
    if src is not None:
        # hero/miniatura em 16:9 a partir da imagem LIMPA (sem texto)
        w, h = src.size
        th = int(w * 9 / 16)
        crop = src if h <= th else src.crop((0, (h - th) // 2, w, (h - th) // 2 + th))
        res["hero"] = ("img/%s/hero.webp" % a["slug"], _save_web(crop, imgdir / "hero.webp", 1600, 80))
        res["thumb"] = ("img/%s/thumb.webp" % a["slug"], _save_web(crop, imgdir / "thumb.webp", 720, 78))
        og = crop.resize((1200, 675), Image.LANCZOS) if crop.width >= 1200 else crop
        res["og"] = ("img/%s/og.jpg" % a["slug"], _save_web(og, imgdir / "og.jpg", 1200, 85, "JPEG"))
    folder = a.get("folder")
    if folder and (folder / "br").exists():
        for png in sorted((folder / "br").glob("*.png")):
            name = png.stem
            if name.endswith(("siga", "follow")):      # o slide "siga" não faz sentido no site
                continue
            dst = imgdir / "galeria" / f"{name}.webp"
            size = _save_web(Image.open(png), dst, 1080, 82)
            label = ("Imagem oficial (limpa)" if "imagem-limpa" in name else
                     "Capa" if name.endswith("capa") else
                     "Slide")
            res["gallery"].append((f"img/{a['slug']}/galeria/{name}.webp", size, label))
    return res


# ------------------------------------------------------------------ HTML

def countdown_html() -> str:
    days = days_to_release()
    return (f'<a class="countdown" href="/sobre/#lancamento" data-release="{brand()["release_date"]}">'
            f'<b id="cd-days">{max(0, days)}</b><span><i>dias</i><i>para o GTA VI</i></span></a>')


def page(title: str, body: str, *, desc: str, path: str, og_image: str | None = None,
         og_type: str = "website", extra_head: str = "", main_class: str = "") -> str:
    c = cfg()
    full_title = f"{title} | {c['nome']}" if title != c["nome"] else f"{c['nome']} — Notícias de GTA VI"
    url = c["url"] + path
    og = f'{c["url"]}/{og_image}' if og_image else f'{c["url"]}/assets/og-default.jpg'
    nav = [("/", "Início"), ("/noticias/", "Notícias"), ("/imagens/", "Imagens oficiais"), ("/sobre/", "Sobre")]
    cur = ' aria-current="page"'
    nav_html = "".join(f'<a href="{h}"{cur if (h == path or (h != "/" and path.startswith(h))) else ""}>{t}</a>'
                       for h, t in nav)
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(full_title)}</title>
<meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{url}">
<meta name="theme-color" content="#0B0614">
<meta property="og:site_name" content="{esc(c['nome'])}">
<meta property="og:locale" content="pt_BR">
<meta property="og:type" content="{og_type}">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{url}">
<meta property="og:image" content="{og}">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="/assets/icon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{esc(c['nome'])}" href="/feed.xml">
<link rel="preload" href="/assets/fonts/Anton-Regular.ttf" as="font" type="font/ttf" crossorigin>
<link rel="stylesheet" href="/assets/style.css?v={asset_version()}">
{extra_head}
</head>
<body>
<header class="top">
  <div class="wrap top-in">
    <a class="logo" href="/" aria-label="{esc(c['nome'])} — início"><span class="mark">LW</span><span class="name">LEONIDA WIRE<small>notícias de GTA VI</small></span></a>
    {countdown_html()}
  </div>
  <nav class="wrap nav" aria-label="Seções">{nav_html}</nav>
</header>
<main class="{main_class}">
{body}
</main>
<footer class="foot">
  <div class="wrap foot-in">
    <div>
      <a class="logo small" href="/"><span class="mark">LW</span><span class="name">LEONIDA WIRE</span></a>
      <p>{esc(c['descricao'])}</p>
      <p><a class="btn tiktok" href="{c['tiktok']}" target="_blank" rel="noopener">Siga no TikTok @leonidawirebrz</a></p>
    </div>
    <p class="legal">Site de fã, sem vínculo com a Rockstar Games ou a Take-Two Interactive. Grand Theft Auto e GTA VI são marcas
    da Take-Two. Imagens oficiais © Rockstar Games, usadas com crédito para fins jornalísticos.</p>
  </div>
</footer>
<script src="/assets/app.js?v={asset_version()}" defer></script>
</body>
</html>
"""


_ASSET_V = None


def asset_version() -> str:
    global _ASSET_V
    if _ASSET_V is None:
        h = hashlib.sha1()
        for f in sorted(ASSETS_SRC.glob("*")):
            h.update(f.read_bytes())
        _ASSET_V = h.hexdigest()[:8]
    return _ASSET_V


def tag_pill(tag: str) -> str:
    return f'<span class="tag tag-{esc(tag or "noticia")}">{esc(TAG_LABEL.get(tag, "Notícia"))}</span>'


def card(a: dict, imgs: dict, big: bool = False) -> str:
    href = f"/noticias/{a['slug']}/"
    thumb = imgs.get("hero" if big else "thumb")
    img = (f'<img src="/{thumb[0]}" width="{thumb[1][0]}" height="{thumb[1][1]}" alt="" '
           f'loading="{"eager" if big else "lazy"}" decoding="async">' if thumb else '<div class="noimg"></div>')
    return f"""<article class="card{' big' if big else ''}">
  <a href="{href}" class="card-img">{img}</a>
  <div class="card-body">
    <div class="meta">{tag_pill(a['tag'])}<time datetime="{a['date']}">{fmt_date(a['date'])}</time></div>
    <h{2 if big else 3}><a href="{href}">{marked_html(a['headline'])}</a></h{2 if big else 3}>
    <p>{esc(a['summary'])}</p>
  </div>
</article>"""


def article_page(a: dict, imgs: dict, related: list[tuple[dict, dict]]) -> str:
    c = cfg()
    src = a["source"] or {}
    hero = imgs.get("hero")
    hero_html = (f'<figure class="hero"><img src="/{hero[0]}" width="{hero[1][0]}" height="{hero[1][1]}" '
                 f'alt="Imagem oficial de GTA VI" decoding="async" fetchpriority="high">'
                 f'<figcaption>Imagem oficial: Rockstar Games</figcaption></figure>') if hero else ""
    gal = "".join(
        f'<figure><a href="/{g[0]}" target="_blank" rel="noopener"><img src="/{g[0]}" width="{g[1][0]}" '
        f'height="{g[1][1]}" alt="{esc(g[2])}" loading="lazy" decoding="async"></a><figcaption>{esc(g[2])}</figcaption></figure>'
        for g in imgs.get("gallery", []))
    gallery_html = (f'<section class="gallery"><h2>Imagens do post</h2><p class="muted">Primeiro a arte do '
                    f'Leonida Wire, depois a imagem oficial limpa.</p><div class="gal">{gal}</div></section>') if gal else ""
    src_html = (f'<p class="source">Fonte: <a href="{esc(src["url"])}" target="_blank" rel="noopener">'
                f'{esc(src.get("name") or src["url"])}</a></p>') if src.get("url") else (
        f'<p class="source">Fonte: {esc(src.get("name", ""))}</p>' if src.get("name") else "")
    share_url = f"{c['url']}/noticias/{a['slug']}/"
    share_txt = f"{a['title']} {share_url}"
    tiktok = a.get("tiktok_url") or c["tiktok"]
    rel = "".join(card(r, ri) for r, ri in related)
    rel_html = f'<section class="related"><h2>Mais notícias</h2><div class="grid">{rel}</div></section>' if rel else ""
    ld = {"@context": "https://schema.org", "@type": "NewsArticle", "headline": a["title"][:110],
          "datePublished": a["date"], "dateModified": a["date"], "inLanguage": "pt-BR",
          "image": [f"{c['url']}/{imgs['og'][0]}"] if imgs.get("og") else [],
          "author": {"@type": "Organization", "name": c["nome"]},
          "publisher": {"@type": "Organization", "name": c["nome"]},
          "mainEntityOfPage": share_url, "description": a["summary"]}
    body = f"""<article class="post wrap narrow">
  <div class="meta">{tag_pill(a['tag'])}<time datetime="{a['date']}">{fmt_date(a['date'])}</time></div>
  <h1>{marked_html(a['headline'])}</h1>
  <p class="lead">{esc(a['summary'])}</p>
  {hero_html}
  <div class="content">{a['body_html']}</div>
  {src_html}
  <div class="share">
    <a class="btn" href="https://wa.me/?text={quote(share_txt)}" target="_blank" rel="noopener">Compartilhar no WhatsApp</a>
    <a class="btn ghost" href="{tiktok}" target="_blank" rel="noopener">Ver no TikTok</a>
  </div>
  {gallery_html}
</article>
<div class="wrap">{rel_html}</div>"""
    return page(a["title"], body, desc=a["summary"] or a["title"], path=f"/noticias/{a['slug']}/",
                og_image=imgs["og"][0] if imgs.get("og") else None, og_type="article",
                extra_head=f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')


def home_page(arts, imgs) -> str:
    c = cfg()
    if not arts:
        return page(c["nome"], '<div class="wrap"><p>Em breve.</p></div>', desc=c["descricao"], path="/")
    first, rest = arts[0], arts[1:13]
    grid = "".join(card(a, imgs[a["id"]]) for a in rest)
    days = days_to_release()
    body = f"""<section class="wrap lead-story">{card(first, imgs[first['id']], big=True)}</section>
<section class="wrap">
  <div class="section-head"><h2>Últimas notícias</h2><a href="/noticias/">Ver todas</a></div>
  <div class="grid">{grid}</div>
</section>
<section class="wrap release" id="lancamento">
  <div class="release-in">
    <p class="eyebrow">Lançamento oficial</p>
    <p class="big-date">19 de novembro de 2026</p>
    <p>PS5 e Xbox Series X|S · faltam <b class="js-days">{max(0, days)}</b> dias</p>
  </div>
  <a class="btn tiktok" href="{c['tiktok']}" target="_blank" rel="noopener">Notícias todo dia no TikTok</a>
</section>"""
    return page(c["nome"], body, desc=c["descricao"], path="/", og_image=imgs[first["id"]]["og"][0]
                if imgs[first["id"]].get("og") else None)


def list_page(arts, imgs) -> str:
    tags = sorted({a["tag"] for a in arts if a["tag"]})
    chips = '<button class="chip" aria-pressed="true" data-tag="">Todas</button>' + "".join(
        f'<button class="chip" aria-pressed="false" data-tag="{esc(t)}">{esc(TAG_LABEL.get(t, t.title()))}</button>'
        for t in tags)
    items = "".join(f'<div data-tag="{esc(a["tag"])}">{card(a, imgs[a["id"]])}</div>' for a in arts)
    body = f"""<section class="wrap">
  <h1 class="page-title">Notícias</h1>
  <p class="muted">Tudo o que é oficial sobre GTA VI, com fonte, da mais nova para a mais antiga.</p>
  <div class="chips" role="toolbar" aria-label="Filtrar por tipo">{chips}</div>
  <div class="grid filterable">{items}</div>
</section>"""
    return page("Notícias", body, desc="Todas as notícias oficiais de GTA VI no Leonida Wire.", path="/noticias/")


def images_page(arts, imgs) -> str:
    figs = []
    for a in arts:
        im = imgs[a["id"]]
        if im.get("hero"):
            figs.append(f'<figure><a href="/noticias/{a["slug"]}/"><img src="/{im["thumb"][0]}" width="{im["thumb"][1][0]}" '
                        f'height="{im["thumb"][1][1]}" alt="{esc(a["title"])}" loading="lazy" decoding="async"></a>'
                        f'<figcaption>{esc(a["title"])}</figcaption></figure>')
    body = f"""<section class="wrap">
  <h1 class="page-title">Imagens oficiais</h1>
  <p class="muted">As imagens da Rockstar que aparecem nas nossas notícias, limpas, sem texto por cima.</p>
  <div class="gal wide">{''.join(figs)}</div>
</section>"""
    return page("Imagens oficiais", body, desc="Imagens oficiais de GTA VI divulgadas pela Rockstar Games.",
                path="/imagens/")


def about_page() -> str:
    c = cfg()
    body = f"""<section class="wrap narrow post">
  <h1 class="page-title">Sobre o Leonida Wire</h1>
  <div class="content">
  <p>O Leonida Wire publica todos os dias as notícias <strong>oficiais</strong> de Grand Theft Auto VI em português:
  anúncios da Rockstar, imagens novas, trailers, entrevistas com a equipe e o que os principais sites de games
  confirmam.</p>
  <h2>Como checamos</h2>
  <ul>
    <li>Cada notícia é conferida na fonte oficial da Rockstar ou em pelo menos dois veículos confiáveis.</li>
    <li>Sempre mostramos a fonte no fim da matéria.</li>
    <li>Não publicamos vazamentos nem material não oficial.</li>
  </ul>
  <h2 id="lancamento">Lançamento</h2>
  <p>GTA VI chega em <strong>19 de novembro de 2026</strong> para PlayStation 5 e Xbox Series X|S.</p>
  <h2>Siga</h2>
  <p>Vídeos todos os dias no TikTok: <a href="{c['tiktok']}" target="_blank" rel="noopener">@leonidawirebrz</a>.</p>
  </div>
</section>"""
    return page("Sobre", body, desc="Quem somos e como checamos as notícias de GTA VI.", path="/sobre/")


def notfound_page() -> str:
    body = """<section class="wrap narrow post"><h1 class="page-title">Página não encontrada</h1>
<p>Essa página não existe (ou mudou de lugar). <a href="/">Voltar para as notícias</a>.</p></section>"""
    return page("Página não encontrada", body, desc="Página não encontrada.", path="/404.html")


def feed_xml(arts) -> str:
    c = cfg()
    items = []
    for a in arts[:30]:
        d = dt.datetime.fromisoformat(a["date"] + "T12:00:00+00:00")
        items.append(f"""<item><title>{esc(a['title'])}</title><link>{c['url']}/noticias/{a['slug']}/</link>
<guid>{c['url']}/noticias/{a['slug']}/</guid><pubDate>{d.strftime('%a, %d %b %Y %H:%M:%S +0000')}</pubDate>
<description>{esc(a['summary'])}</description></item>""")
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>{esc(c['nome'])}</title><link>{c['url']}/</link>
<description>{esc(c['descricao'])}</description><language>pt-br</language>
{''.join(items)}
</channel></rss>
"""


def sitemap_xml(arts) -> str:
    c = cfg()
    urls = ["/", "/noticias/", "/imagens/", "/sobre/"] + [f"/noticias/{a['slug']}/" for a in arts]
    last = arts[0]["date"] if arts else dt.date.today().isoformat()
    lastmod = {f"/noticias/{a['slug']}/": a["date"] for a in arts}
    body = "".join(f"<url><loc>{c['url']}{u}</loc><lastmod>{lastmod.get(u, last)}</lastmod></url>" for u in urls)
    return f'<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>\n'


def build(out: Path = SITE_DIR, log=print) -> Path:
    """Gera o site completo em `out` (apaga e recria)."""
    arts = load_articles()
    if out.exists():
        shutil.rmtree(out)
    (out / "assets" / "fonts").mkdir(parents=True)
    for f in ASSETS_SRC.glob("*"):
        shutil.copy(f, out / "assets" / f.name)
    for fn in ("Anton-Regular.ttf", "Inter-Medium.otf", "Inter-Bold.otf", "Inter-ExtraBold.otf"):
        shutil.copy(FONTS_DIR / fn, out / "assets" / "fonts" / fn)
    imgs = {}
    for a in arts:
        log(f"  [site] {a['id']}")
        imgs[a["id"]] = build_images(a, out)
    # imagem padrão para compartilhamento
    first_og = next((imgs[a["id"]]["og"] for a in arts if imgs[a["id"]].get("og")), None)
    if first_og:
        shutil.copy(out / first_og[0], out / "assets" / "og-default.jpg")

    def write(rel: str, text: str):
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding="utf-8")

    write("index.html", home_page(arts, imgs))
    write("noticias/index.html", list_page(arts, imgs))
    write("imagens/index.html", images_page(arts, imgs))
    write("sobre/index.html", about_page())
    write("404.html", notfound_page())
    for i, a in enumerate(arts):
        related = [(r, imgs[r["id"]]) for r in arts if r["id"] != a["id"]][:3]
        write(f"noticias/{a['slug']}/index.html", article_page(a, imgs[a["id"]], related))
    write("feed.xml", feed_xml(arts))
    write("sitemap.xml", sitemap_xml(arts))
    write("robots.txt", f"User-agent: *\nAllow: /\nSitemap: {cfg()['url']}/sitemap.xml\n")
    log(f"✅ site gerado em {out.relative_to(ROOT)} ({len(arts)} notícias)")
    return out
