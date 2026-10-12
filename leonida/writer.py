"""Redator: transforma uma história do radar em post.yaml (PT + EN).

Três caminhos:
  1. Claude API (se ANTHROPIC_API_KEY ou `ant auth login` estiver configurado) — automático.
  2. Codex / Claude Code no seu PC — eles leem o AGENTS.md e preenchem o post.yaml.
  3. Modelo simples (sem IA) — rascunho com o título original, marcado para revisão.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import html as htmlmod
from urllib.parse import urlparse

import requests

from . import media
from .config import USER_AGENT, brand, days_to_release
from .post import post_dir, save, slugify

MODEL = os.environ.get("LEONIDA_MODEL", "claude-opus-5-5")

STYLE_GUIDE = """Você é o redator do perfil de notícias de GTA VI "{brand}" no TikTok, com dois perfis:
- BR (português do Brasil, @{h_pt}): linguagem de gamer brasileiro, direta, empolgada, sem ser forçada. Pode usar gírias leves ("insano", "vazou", "bora").
- US (inglês americano, @{h_en}): punchy, hype-news style, short sentences.

Regras de conteúdo (obrigatórias):
- Só use fatos que estão na matéria/fontes fornecidas. Nunca invente datas, preços, nomes ou números.
- Se for vazamento/rumor, deixe claro que não é oficial ("segundo o leaker", "ainda não confirmado").
- Nada de conteúdo explícito/sexual mesmo que a fonte mencione; TikTok derruba. Fale "cenas polêmicas" no máximo.
- Sempre credite a fonte principal na legenda.
- Hoje é {today}. Faltam {days} dias para o lançamento (19/11/2026, PS5 e Xbox Series X|S).

Formato da arte (campos):
- kicker: UMA palavra curta e forte (até 9 letras) que aparece gigante atrás do personagem. Ex.: "VAZOU", "RÁDIOS", "TRAILER", "LEAKED", "RADIO".
- headline: manchete em até 70 caracteres. Marque 2 a 4 palavras de impacto com *asteriscos* (viram destaque em gradiente).
- summary: 1 frase de contexto, até 115 caracteres.
- caption: legenda do TikTok. Gancho na 1ª linha, 2-4 linhas curtas com os fatos, uma pergunta para gerar comentários, emojis com moderação (máx. 3). Sem hashtags dentro da caption.
- hashtags: 3 a 5 hashtags específicas da notícia (as genéricas #gta6 #gtavi já são adicionadas automaticamente).
- facts: 3 ou 4 tópicos curtos ("o que sabemos") para um slide extra do carrossel. Opcional (lista vazia se não fizer sentido).
- tag: oficial | urgente | vazamento | rumor | viral | analise.
- image_hint: se a imagem da matéria não servir, qual grupo de screenshots oficiais combina: Jason_Duval, Lucia_Caminos, Jason_and_Lucia, Vice_City, Leonida_Keys, Grassrivers, Port_Gellhorn, Ambrosia, Mount_Kalaga_National_Park.
"""

LOC_SCHEMA = {
    "type": "object",
    "properties": {
        "kicker": {"type": "string"},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "caption": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "facts": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["kicker", "headline", "summary", "caption", "hashtags", "facts"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "tag": {"type": "string", "enum": ["oficial", "urgente", "vazamento", "rumor", "viral", "analise"]},
        "image_hint": {"type": "string"},
        "pt": LOC_SCHEMA,
        "en": LOC_SCHEMA,
    },
    "required": ["tag", "image_hint", "pt", "en"],
    "additionalProperties": False,
}


def article_text(url: str, limit: int = 6000) -> str:
    """Texto corrido de uma matéria (parágrafos <p>), para dar fatos ao redator."""
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
    except Exception:
        return ""
    paras = re.findall(r"<p[^>]*>(.*?)</p>", r.text, re.S | re.I)
    text = " ".join(re.sub(r"<[^>]+>", "", p) for p in paras)
    text = re.sub(r"\s+", " ", htmlmod.unescape(text)).strip()
    return text[:limit]


def _story_brief(story: dict) -> str:
    lines = [f"Título principal: {story['title']}"]
    if story.get("title_pt"):
        lines.append(f"Título em português: {story['title_pt']}")
    lines.append(f"Resumo do feed: {story.get('summary', '')}")
    lines.append("Fontes:")
    for s in story["sources"][:8]:
        lines.append(f"- [{s['lang']}] {s['name']}: {s['title']} ({s['url']})")
    lead = next((s for s in story["sources"] if "news.google.com" not in s["url"]), None)
    if lead:
        body = article_text(lead["url"])
        if body:
            lines.append(f"\nTexto da matéria principal ({lead['name']}):\n{body}")
    return "\n".join(lines)


def draft_with_claude(story: dict) -> dict:
    import anthropic

    b = brand()
    system = STYLE_GUIDE.format(brand=b["name"], h_pt=b["handle"]["pt"].lstrip("@"),
                                h_en=b["handle"]["en"].lstrip("@"),
                                today=dt.date.today().isoformat(), days=days_to_release())
    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        system=system,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": "Escreva o post (BR e US) para esta notícia:\n\n"
                                              + _story_brief(story)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError("o modelo recusou esta notícia")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("resposta cortada (max_tokens)")
    text = next(blk.text for blk in resp.content if blk.type == "text")
    return json.loads(text)


def _short_text(text: str, limit: int) -> str:
    """Encurta o texto no limite de uma palavra, sem cortar nomes ao meio."""
    text = re.sub(r"\s+", " ", htmlmod.unescape(str(text or ""))).strip()
    if len(text) <= limit:
        return text
    words = text.split()
    kept = []
    for word in words:
        if len(" ".join([*kept, word])) > limit - 1:
            break
        kept.append(word)
    return " ".join(kept).rstrip(" ,;:-") + "…"


def _story_words(story: dict) -> str:
    return " ".join(str(story.get(key) or "") for key in
                    ("title", "title_pt", "title_en", "summary")).lower()


def _game_topic(story: dict) -> str:
    text = _story_words(story)
    if re.search(r"\bgta\s*(?:vi|6)\b", text):
        return "GTA VI"
    if re.search(r"\bgta\s*online\b", text):
        return "GTA Online"
    if re.search(r"\bgta\s*(?:v|5)\b", text):
        return "GTA V"
    return "GTA VI"


def image_hint(story: dict, hint: str = "") -> str:
    """Identifica o assunto antes de recorrer ao cenário genérico de Vice City."""
    text = _story_words(story)
    if re.search(r"\blucia\b", text) and re.search(r"\bjason\b", text):
        return "Jason_and_Lucia"
    if re.search(r"\blucia\b", text):
        return "Lucia_Caminos"
    if re.search(r"\bjason\b", text):
        return "Jason_Duval"
    groups = ("Leonida_Keys", "Grassrivers", "Port_Gellhorn", "Ambrosia",
              "Mount_Kalaga_National_Park", "Vice_City")
    for group in groups:
        if group.replace("_", " ").lower() in text:
            return group
    allowed = (*groups, "Jason_Duval", "Lucia_Caminos", "Jason_and_Lucia")
    return next((group for group in allowed if group.lower() == str(hint).lower()), "Vice_City")


def draft_template(story: dict) -> dict:
    """Sem IA: rascunho curto para revisão, sem repetir conteúdo explícito do feed."""
    en = story.get("title_en") or story["title"]
    pt = story.get("title_pt") or story["title"]
    text = _story_words(story)
    game = _game_topic(story)
    explicit = re.search(r"\b(?:naked|nude|nudity|nudes|nudez|nu[as]?|nus|pelad[oa]s?|porn\w*|sexualmente|sexual\w*)\b", text)
    if explicit:
        pt, en = f"Relato não confirmado sobre {game}", f"Unconfirmed {game} report"
        summ = "O relato precisa de verificação antes da publicação."
        summ_en = "The report needs verification before publication."
    else:
        summ = _short_text(story.get("summary") or "", 115)
        summ_en = summ
    leaked = bool(re.search(r"\b(?:leak\w*|vaza\w*|vazou)\b", text))
    rumored = bool(re.search(r"\b(?:rumo(?:r|res)\w*|unconfirmed|não confirmado|nao confirmado)\b", text))
    tag = "vazamento" if leaked else "rumor" if (rumored or explicit) else "analise"
    return {
        "tag": tag,
        "image_hint": image_hint(story),
        "needs_review": True,
        "pt": {"kicker": game, "headline": _short_text(pt, 70), "summary": summ,
               "caption": f"{pt}\n\nO que você acha? Comenta aí 👇", "hashtags": [], "facts": []},
        "en": {"kicker": game, "headline": _short_text(en, 70), "summary": summ_en,
               "caption": f"{en}\n\nThoughts? Drop them below 👇", "hashtags": [], "facts": []},
    }


def _official_image(url: str) -> bool:
    parsed = urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    trusted = host == "rockstargames.com" or host.endswith(".rockstargames.com") \
        or host == "media-rockstargames-com.akamaized.net"
    return parsed.scheme == "https" and trusted and not parsed.username and not parsed.password


def _library_candidates(story: dict, hint: str) -> list[str]:
    """Rotação determinística dentro do assunto, seguida apenas de cenários de Vice City."""
    if _game_topic(story) != "GTA VI":
        return []   # a biblioteca é exclusivamente de GTA VI, não ilustra GTA Online/GTA V
    try:
        items = media.sync_rockstar_library()
    except Exception:
        return []
    group = image_hint(story, hint)
    selected = []
    try:
        index = int(str(story.get("id") or "0"), 16)
    except ValueError:
        index = sum(str(story.get("id") or "").encode("utf-8"))
    for requested in dict.fromkeys((group, "Vice_City")):
        pool = sorted({item.get("url") for item in items
                       if str(item.get("group") or "").lower() == requested.lower()
                       and _official_image(item.get("url"))})
        if not pool:
            continue
        shift = index % len(pool)
        selected.extend(url for url in [*pool[shift:], *pool[:shift]] if url not in selected)
    return selected


def pick_image(story: dict, hint: str) -> str:
    """Screenshot oficial pertinente; imagem oficial da matéria apenas como alternativa."""
    candidates = _library_candidates(story, hint)
    if candidates:
        return candidates[0]
    for s in story.get("sources") or []:
        if "news.google.com" in s["url"] or "reddit.com" in s["url"]:
            continue
        try:
            meta = media.page_meta(s["url"])
            url = meta.get("image")
            if not _official_image(url):
                continue
            from PIL import Image
            with Image.open(media.fetch(url)) as im:
                if im.width >= 1200 and im.height >= 600:
                    return url
        except Exception:
            continue
    return ""


def pick_visuals(story: dict, hint: str, cover_image: str, limit: int = 3) -> list[dict]:
    """Imagens distintas para novas cenas; são ilustrações oficiais, não prova do relato."""
    urls = [url for url in _library_candidates(story, hint) if url != cover_image]
    return [{"image": url, "credit": "Rockstar Games", "label": "Imagem oficial ilustrativa"}
            for url in urls[:max(0, limit)]]


def _available_post_id(base: str) -> str:
    """Uma nova proposta não substitui um rascunho ou uma entrega anterior."""
    candidate = base
    version = 2
    while (post_dir(candidate) / "post.yaml").exists():
        candidate = f"{base}-v{version}"
        version += 1
    return candidate


def story_to_post(story: dict, use_llm: bool | None = None) -> dict:
    if use_llm is None:
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    draft = draft_with_claude(story) if use_llm else draft_template(story)
    date = dt.date.today().isoformat()
    lead = story["sources"][0]
    hint = image_hint(story, draft.get("image_hint", ""))
    image = pick_image(story, hint)
    post = {
        "id": _available_post_id(f"{date}-{slugify(draft['en']['headline'].replace('*', ''), 48)}"),
        "date": date,
        "tag": draft["tag"],
        "image": image,
        "layout": "card",
        "cutout": False,
        "foto_limpa": False,
        "visuals": pick_visuals(story, hint, image),
        "source": {"name": lead["name"].split(" (")[0], "url": lead["url"]},
        "radar_id": story["id"],
    }
    if draft.get("needs_review"):
        post["needs_review"] = True
    for lang in ("pt", "en"):
        loc = draft[lang]
        entry = {k: loc[k] for k in ("kicker", "headline", "summary", "caption", "hashtags")}
        if loc.get("facts"):
            title = "O que *sabemos*" if lang == "pt" else "What we *know*"
            entry["slides"] = [{"type": "list", "title": title, "items": loc["facts"][:4]}]
        post[lang] = entry
    save(post)
    return post
