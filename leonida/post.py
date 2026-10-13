"""Post = especificação (posts/<id>/post.yaml) -> pasta pronta (prontos/<data>/<id>/{br,us}/...)."""
from __future__ import annotations

import datetime as dt
import json
import re
import shutil
import tempfile
import unicodedata
from pathlib import Path

import yaml

from . import gfx, motion, render
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


ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,159}")


def check_id(post_id) -> str:
    """Id vira nome de pasta: só letras, números, - e _ (nada de ../ ou caminho)."""
    if not isinstance(post_id, str) or not ID_RE.fullmatch(post_id):
        raise ValueError(f"id de post inválido: {post_id!r}")
    return post_id


def check_date(date) -> str:
    """Data vira nome de pasta em prontos/: precisa ser AAAA-MM-DD de verdade."""
    text = date.isoformat() if isinstance(date, dt.date) else date
    if not isinstance(text, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        raise ValueError(f"data inválida: {date!r} (use AAAA-MM-DD)")
    dt.date.fromisoformat(text)
    return text


def post_dir(post_id: str) -> Path:
    return POSTS_DIR / check_id(post_id)


def load(post_id_or_path: str | Path) -> tuple[dict, Path]:
    p = Path(post_id_or_path)
    if p.is_dir():
        p = p / "post.yaml"
    elif not p.exists():
        if isinstance(post_id_or_path, Path) or len(p.parts) > 1:
            raise FileNotFoundError(p)          # caminho inexistente; só um id simples vira posts/<id>
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
    if post.get("date") is not None:
        check_date(post["date"])
    d = post_dir(post["id"])
    d.mkdir(parents=True, exist_ok=True)
    with open(d / "post.yaml", "w", encoding="utf-8") as fh:
        yaml.dump(post, fh, Dumper=_Dumper, allow_unicode=True, sort_keys=False, width=110)
    return d / "post.yaml"


def new(title: str, date: str | None = None) -> Path:
    date = check_date(date or dt.date.today().isoformat())
    pid = f"{date}-{slugify(title, 48)}"
    d = post_dir(pid)
    d.mkdir(parents=True, exist_ok=True)
    f = d / "post.yaml"
    if not f.exists():
        f.write_text(TEMPLATE.format(id=pid, date=date), encoding="utf-8")
    return f


def validate(post: dict, langs=LANGS) -> list[str]:
    errs = []

    def text_field(value, path):
        if value is None or (isinstance(value, str) and not value.strip()):
            errs.append(f"{path} vazio")
            return False
        if not isinstance(value, str):
            errs.append(f"{path} deve ser texto (string)")
            return False
        return True

    if not post.get("image"):
        errs.append("image vazio")
    visuals = post.get("visuals", [])
    if not isinstance(visuals, list) or len(visuals) > 6:
        errs.append("visuals deve conter até 6 imagens de apoio")
    else:
        for i, visual in enumerate(visuals):
            path = f"visuals[{i}]"
            if not isinstance(visual, dict):
                errs.append(f"{path} deve conter image, credit e label")
                continue
            text_field(visual.get("image"), path + ".image")
            for field in ("credit", "label", "text"):
                if field in visual and (not isinstance(visual[field], str) or len(visual[field]) > 160):
                    errs.append(f"{path}.{field} deve ser texto curto")
    for lang in langs:
        loc = post.get(lang)
        if loc is None:
            loc = {}
        if not isinstance(loc, dict):
            errs.append(f"{lang} deve ser um objeto com headline e caption")
            continue
        headline_ok = text_field(loc.get("headline"), f"{lang}.headline")
        text_field(loc.get("caption"), f"{lang}.caption")
        if headline_ok and len(loc["headline"].replace("*", "")) > 95:
            errs.append(f"{lang}.headline longo demais (>95)")
        slides = loc.get("slides")
        if slides is None:
            continue
        if not isinstance(slides, list):
            errs.append(f"{lang}.slides deve ser uma lista de slides")
            continue
        for index, slide in enumerate(slides):
            path = f"{lang}.slides[{index}]"
            if not isinstance(slide, dict):
                errs.append(f"{path} deve ser um objeto com title e items")
                continue
            text_field(slide.get("title"), f"{path}.title")
            items = slide.get("items")
            if not isinstance(items, list):
                errs.append(f"{path}.items deve ser uma lista")
                continue
            if slide.get("type") != "grid":
                for item_index, item in enumerate(items):
                    item_path = f"{path}.items[{item_index}]"
                    if not text_field(item, item_path) and isinstance(item, dict):
                        errs.append(f"{item_path}: use aspas no YAML para texto que contenha ': '")
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
          today: dt.date | None = None, estilo: str | None = None, log=print) -> Path:
    """Renderiza tudo e devolve a pasta em prontos/."""
    post, base_dir = load(post_id_or_path)
    estilo = estilo or post.get("estilo") or (brand().get("video") or {}).get("estilo_padrao", "v2")
    if estilo not in {"v2", "dinamico", "classico"}:
        raise ValueError(f"estilo desconhecido: {estilo}")
    langs = tuple(langs)
    if not langs or any(lang not in LANG_FOLDER for lang in langs):
        raise ValueError(f"idiomas inválidos: {langs!r}")
    errs = validate(post, langs)
    if errs:
        raise ValueError(f"{post['id']}: " + "; ".join(errs))
    date = check_date(str(post.get("date") or dt.date.today().isoformat())[:10])
    today = today or dt.date.fromisoformat(date)
    out = OUT_DIR / date / check_id(post["id"])
    out.parent.mkdir(parents=True, exist_ok=True)
    # Só substitui a entrega depois do build completo. Erros deixam a pasta anterior intacta.
    with tempfile.TemporaryDirectory(prefix=".build-", dir=out.parent) as temporary:
        stage = Path(temporary) / post["id"]
        if out.exists():
            shutil.copytree(out, stage)
        else:
            stage.mkdir()
        _render_post(post, base_dir, stage, estilo, video, langs, today, log)
        previous = Path(temporary) / "previous"
        if out.exists():
            out.replace(previous)
        try:
            stage.replace(out)
        except BaseException:
            if previous.exists():
                previous.replace(out)
            raise
    return out


def _render_post(post, base_dir, out, estilo, video, langs, today, log):
    date = str(post.get("date") or today.isoformat())[:10]
    manifest = {"id": post["id"], "date": date, "tag": post.get("tag"),
                "source": post.get("source"), "files": {}}
    v2 = estilo == "v2"
    for lang in langs:
        scenes = []                          # estilo v2: cada arte em camadas, para o vídeo animado
        folder = out / LANG_FOLDER[lang]
        if folder.exists():
            shutil.rmtree(folder)
        folder.mkdir(parents=True)
        names = FILE_NAMES[lang]
        log(f"  [{lang}] capa…")
        r = render.cover(post, lang, base_dir, today=today)
        r.image.save(folder / names["cover"], optimize=True)
        if v2:
            scenes.append(motion.scene_from(r, "cover"))
            r = None  # as sprites recortadas já contêm a cena; libera os canvases RGBA integrais
        files = [names["cover"]]
        n = 2
        media_used = {post["image"]}
        chosen_visuals = []
        visual_facts = [item for slide in post[lang].get("slides") or [] if slide.get("type") == "list"
                        for item in slide.get("items") or [] if isinstance(item, str)]
        for visual in post.get("visuals") or []:
            ref = visual["image"]
            if ref in media_used:
                continue
            log(f"  [{lang}] imagem de apoio…")
            image = render.slide_foto(post, lang, ref, base_dir,
                                      credit=visual.get("credit") or post.get("credito_imagem") or "Rockstar Games",
                                      label=visual.get("label") or ("Imagem oficial ilustrativa" if lang == "pt" else "Official illustrative image"),
                                      context=visual.get("text") or (visual_facts[len(chosen_visuals)] if len(chosen_visuals) < len(visual_facts) else None),
                                      with_layers=v2)
            if v2:
                scenes.append(motion.scene_from(image, "foto"))
                image = image.image
            filename = f"{n:02d}_{'imagem-apoio' if lang == 'pt' else 'supporting-image'}.png"
            image.save(folder / filename, optimize=True)
            files.append(filename)
            n += 1
            media_used.add(ref)
            chosen_visuals.append(visual)
        if chosen_visuals:
            manifest["visuals"] = chosen_visuals
        # imagem nova da Rockstar: primeiro a arte editada (capa), depois a IMAGEM LIMPA (original)
        clean = list(post.get("fotos_limpas") or [])
        fl = post.get("foto_limpa", "auto")
        if fl is True or (fl == "auto" and render.is_official_image(post.get("image"))):
            clean.insert(0, post["image"])
        for ref in dict.fromkeys(clean):
            if ref in media_used and ref != post["image"]:
                continue
            log(f"  [{lang}] imagem limpa…")
            im = render.slide_foto(post, lang, ref, base_dir, credit=post.get("credito_imagem", "Rockstar Games"),
                                   with_layers=v2)
            if v2:
                scenes.append(motion.scene_from(im, "foto"))
                im = im.image
            fn = f"{n:02d}_{'imagem-limpa' if lang == 'pt' else 'clean-image'}.png"
            im.save(folder / fn, optimize=True)          # sem grão/filtro: é a imagem original
            files.append(fn)
            n += 1
            media_used.add(ref)
        for slide in (post[lang].get("slides") or []):
            log(f"  [{lang}] slide {slide.get('type')}…")
            kind = "grid" if slide.get("type") == "grid" else "list"
            if kind == "grid":
                im = render.slide_grid(post, lang, slide, base_dir, today, with_layers=v2)
            else:
                im = render.slide_list(post, lang, slide, base_dir, today, with_layers=v2)
            if v2:
                scenes.append(motion.scene_from(im, kind))
                im = im.image
            fn = f"{n:02d}_{slugify(slide.get('title', slide.get('type', 'slide')), 24)}.png"
            (im if v2 else gfx.finish(im.convert("RGB"))).save(folder / fn, optimize=True)
            if estilo == "dinamico" and slide.get("type") != "grid" and len(slide.get("items") or []) > 1:
                # vídeo dinâmico: os itens da lista aparecem um a um (quadros só para o vídeo, fora do git)
                rev = folder / ".reveal"
                rev.mkdir(exist_ok=True)
                for k in range(1, len(slide["items"])):
                    part = render.slide_list(post, lang, slide, base_dir, today, upto=k)
                    gfx.finish(part.convert("RGB")).save(rev / f"{Path(fn).stem}__{k}.png", optimize=True)
            files.append(fn)
            n += 1
        if (post[lang].get("slides") or clean or chosen_visuals) and post.get("cta", True):
            fn = f"{n:02d}_{'siga' if lang == 'pt' else 'follow'}.png"
            cta = render.slide_cta(post, lang, base_dir, today, with_layers=v2)
            if v2:
                scenes.append(motion.scene_from(cta, "cta"))
                cta = cta.image
            (cta if v2 else gfx.finish(cta.convert("RGB"))).save(folder / fn, optimize=True)
            files.append(fn)
        (folder / names["caption"]).write_text(caption_text(post, lang), encoding="utf-8")
        files.append(names["caption"])
        if video and not v2:                 # no v2 a capa já é animada dentro do post.mp4
            from . import video as vid
            log(f"  [{lang}] vídeo…")
            engine = vid.render_video(r, folder / names["video"])
            from . import music
            if music.apply(folder / names["video"], under_original=False, seed=post["id"]):
                manifest["music"] = True
            files.append(names["video"])
            manifest.setdefault("video_engine", engine)
        from . import publish
        publish.export_jpegs(folder)          # cópias JPEG para publicar no TikTok
        if publish.cfg()["formato"] == "video":
            # publicação em vídeo: é o único jeito de a música tema sempre tocar no TikTok
            from . import postvideo
            intro = folder / names["video"] if (folder / names["video"]).exists() else None
            if v2:
                target = post.get("video_segundos", (brand().get("video") or {}).get("segundos", 20))
                rhythm = {"max_scene_seconds": 7} if float(target) >= 30 else {}
                target = motion.fit_target(scenes, target, log, **rhythm)
                manifest["video_segundos"] = target
                published_video = motion.build(scenes, folder / "tiktok" / postvideo.OUT_NAME,
                                               seed=post["id"], target=target, log=log, **rhythm)
            else:
                published_video = postvideo.build(folder, seed=post["id"], intro=intro, log=log,
                                                 target=post.get("video_segundos"), estilo=estilo)
            files.append(str(published_video.relative_to(folder)).replace("\\", "/"))
            manifest["music"] = True
            manifest["publication_video_engine"] = estilo
        manifest["files"][LANG_FOLDER[lang]] = files
    (out / "post.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_readme(post, out, manifest)
    return out


def _write_readme(post: dict, out: Path, manifest: dict) -> None:
    """README.md da pasta — o GitHub mostra as imagens e legendas direto no navegador."""
    built_langs = [lang for lang, folder in LANG_FOLDER.items()
                   if manifest["files"].get(folder)]
    title_lang = built_langs[0]
    lines = [f"# {post[title_lang]['headline'].replace('*', '')}", ""]
    src = post.get("source") or {}
    if src.get("url"):
        lines += [f"Fonte: [{src.get('name', src['url'])}]({src['url']})", ""]
    for lang, label in (("pt", "🇧🇷 Perfil BR"), ("en", "🇺🇸 Perfil US")):
        if lang not in built_langs:
            continue
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
        if "tiktok/post.mp4" in files:
            lines += [f"🎬 Vídeo com música: [{folder}/tiktok/post.mp4]({folder}/tiktok/post.mp4)", ""]
        lines += ["```", caption_text(post, lang).strip(), "```", ""]
    (out / "README.md").write_text("\n".join(lines), encoding="utf-8")
