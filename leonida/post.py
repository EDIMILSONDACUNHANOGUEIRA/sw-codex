"""Post = especificação (posts/<id>/post.yaml) -> pasta pronta (prontos/<data>/<id>/{br,us}/...)."""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import unicodedata
from pathlib import Path

import yaml

from . import gfx, render
from .config import LANG_FOLDER, LANGS, OUT_DIR, POSTS_DIR, brand

FILE_NAMES = {
    "pt": {"cover": "01_capa.png", "caption": "legenda.txt", "video": "video.mp4"},
    "en": {"cover": "01_cover.png", "caption": "caption.txt", "video": "video.mp4"},
}

TEMPLATE = """# Especificação de um post. Palavras entre *asteriscos* ganham o destaque em gradiente.
id: {id}
date: "{date}"
tag: oficial            # oficial | urgente | vazamento | rumor | viral | contagem | analise
image: ""               # URL ou caminho da imagem principal (screenshot oficial de preferência)
# layout: cover         # cover (recorte do personagem) | card (imagem emoldurada)
# zoom: 0.85            # força o recuo do enquadramento (1.0 = sem recuo)
# focus: [0.5, 0.5]     # ponto de foco do recorte (x, y de 0 a 1)
source:
  name: ""
  url: ""
pt:
  kicker: ""            # palavra gigante atrás do personagem (1 palavra curta)
  headline: ""          # manchete (até ~70 caracteres)
  summary: ""           # 1-2 frases (até ~120 caracteres)
  caption: |

  hashtags: []
  slides: []            # opcional: [{{type: list|grid, title: ..., items: [...]}}]
en:
  kicker: ""
  headline: ""
  summary: ""
  caption: |

  hashtags: []
  slides: []
"""


def slugify(text: str, maxlen: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text[:maxlen].strip("-") or "post"


def post_dir(post_id: str) -> Path:
    return POSTS_DIR / post_id


def load(post_id_or_path: str | Path) -> tuple[dict, Path]:
    p = Path(post_id_or_path)
    if p.is_dir():
        p = p / "post.yaml"
    elif not p.exists():
        p = post_dir(str(post_id_or_path)) / "post.yaml"
    with open(p, encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    data.setdefault("id", p.parent.name)
    return data, p.parent


class _Dumper(yaml.SafeDumper):
    pass


def _str_repr(dumper, value):
    # legendas com várias linhas ficam legíveis no arquivo (bloco "|")
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_repr)


def save(post: dict) -> Path:
    d = post_dir(post["id"])
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "post.yaml", "w", encoding="utf-8") as fh:
        yaml.dump(post, fh, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=110)
    return d / "post.yaml"


def new(title: str, date: str | None = None) -> Path:
    date = date or dt.date.today().isoformat()
    pid = f"{date}-{slugify(title, 48)}"
    d = post_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "post.yaml"
    if not f.exists():
        f.write_text(TEMPLATE.format(id=pid, date=date), encoding="utf-8")
    return f


def validate(post: dict) -> list[str]:
    errs = []
    if not post.get("image"):
        errs.append("image vazio")
    for lang in LANGS:
        loc = post.get(lang) or {}
        if not loc.get("headline"):
            errs.append(f"{lang}.headline vazio")
        if not (loc.get("caption") or "").strip():
            errs.append(f"{lang}.caption vazio")
        if len(loc.get("headline", "").replace("*", "")) > 95:
            errs.append(f"{lang}.headline longo demais (>95)")
    return errs


def caption_text(post: dict, lang: str) -> str:
    loc = post[lang]
    base = brand()["hashtags"][lang]
    tags, seen = [], set()
    for t in list(loc.get("hashtags") or []) + list(base):
        t = t if t.startswith("#") else "#" + t
        if t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    body = (loc.get("caption") or "").strip()
    src = post.get("source") or {}
    credit = ""
    if src.get("name") and src["name"].lower() not in body.lower():
        credit = ("\n\nFonte: " if lang == "pt" else "\n\nSource: ") + src["name"]
    return f"{body}{credit}\n\n{' '.join(tags[:9])}\n"


def build(post_id_or_path: str | Path, *, video: bool = True, langs=LANGS,
          today: dt.date | None = None, log=print) -> Path:
    """Renderiza tudo e devolve a pasta em prontos/."""
    post, base_dir = load(post_id_or_path)
    errs = validate(post)
    if errs:
        raise ValueError(f"{post['id']}: " + "; ".join(errs))
    date = str(post.get("date") or dt.date.today().isoformat())[:10]
    today = today or dt.date.fromisoformat(date)
    out = OUT_DIR / date / post["id"]
    manifest = {"id": post["id"], "date": date, "tag": post.get("tag"),
                "source": post.get("source"), "files": {}}
    for lang in langs:
        folder = out / LANG_FOLDER[lang]
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        names = FILE_NAMES[lang]
        log(f"  [{lang}] capa…")
        r = render.cover(post, lang, base_dir, today=today)
        r.image.save(folder / names["cover"], optimize=True)
        files = [names["cover"]]
        n = 2
        for slide in (post[lang].get("slides") or []):
            log(f"  [{lang}] slide {slide.get('type')}…")
            if slide.get("type") == "grid":
                im = render.slide_grid(post, lang, slide, base_dir, today)
            else:
                im = render.slide_list(post, lang, slide, base_dir, today)
            fn = f"{n:02d}_{slugify(slide.get('title', slide.get('type', 'slide')), 24)}.png"
            gfx.finish(im.convert("RGB")).save(folder / fn, optimize=True)
            files.append(fn)
            n += 1
        if post[lang].get("slides") and post.get("cta", True):
            fn = f"{n:02d}_{'siga' if lang == 'pt' else 'follow'}.png"
            gfx.finish(render.slide_cta(post, lang, base_dir, today).convert("RGB")).save(folder / fn, optimize=True)
            files.append(fn)
        (folder / names["caption"]).write_text(caption_text(post, lang), encoding="utf-8")
        files.append(names["caption"])
        if video:
            from . import video as vid
            log(f"  [{lang}] vídeo…")
            engine = vid.render_video(r, folder / names["video"])
            from . import music
            if music.apply(folder / names["video"], under_original=False):
                manifest["music"] = True
            files.append(names["video"])
            manifest.setdefault("video_engine", engine)
        manifest["files"][LANG_FOLDER[lang]] = files
    (out / "post.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readme(post, out, manifest)
    return out


def _write_readme(post: dict, out: Path, manifest: dict) -> None:
    """README.md da pasta — o GitHub mostra as imagens e legendas direto no navegador."""
    lines = [f"# {post['pt']['headline'].replace('*', '')}", ""]
    src = post.get("source") or {}
    if src.get("url"):
        lines += [f"Fonte: [{src.get('name', src['url'])}]({src['url']})", ""]
    for lang, label in (("pt", "🇧🇷 Perfil BR"), ("en", "🇺🇸 Perfil US")):
        folder = LANG_FOLDER[lang]
        files = manifest["files"].get(folder, [])
        if not files:
            continue
        lines += [f"## {label}", ""]
        imgs = [f for f in files if f.endswith(".png")]
        lines.append(" ".join(f'<img src="{folder}/{f}" width="240">' for f in imgs))
        lines.append("")
        if "video.mp4" in files:
            lines += [f"🎬 Vídeo: [{folder}/video.mp4]({folder}/video.mp4)", ""]
        lines += ["```", caption_text(post, lang).strip(), "```", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
