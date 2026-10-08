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

import requests

from . import media
from .config import USER_AGENT, brand, days_to_release
from .post import save, slugify

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


def draft_template(story: dict) -> dict:
    """Sem IA: usa os títulos originais. O post fica marcado como 'revisar'."""
    en = story.get("title_en") or story["title"]
    pt = story.get("title_pt") or story["title"]
    summ = (story.get("summary") or "")[:115]
    return {
        "tag": "urgente",
        "image_hint": "Vice_City",
        "needs_review": True,
        "pt": {"kicker": "GTA VI", "headline": pt[:90], "summary": summ,
               "caption": f"{pt}\n\nO que você acha? Comenta aí 👇", "hashtags": [], "facts": []},
        "en": {"kicker": "GTA VI", "headline": en[:90], "summary": summ,
               "caption": f"{en}\n\nThoughts? Drop them below 👇", "hashtags": [], "facts": []},
    }


def pick_image(story: dict, hint: str) -> str:
    """Imagem da matéria (se for grande) ou screenshot oficial da Rockstar."""
    for s in story["sources"]:
        if "news.google.com" in s["url"] or "reddit.com" in s["url"]:
            continue
        try:
            meta = media.page_meta(s["url"])
            url = meta.get("image")
            if not url:
                continue
            from PIL import Image
            im = Image.open(media.fetch(url))
            if im.width >= 1600:
                return url
        except Exception:
            continue
    return media.library_pick(hint or "Vice_City", int(story["id"], 16)) or ""


def story_to_post(story: dict, use_llm: bool | None = None) -> dict:
    if use_llm is None:
        use_llm = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    draft = draft_with_claude(story) if use_llm else draft_template(story)
    date = dt.date.today().isoformat()
    lead = story["sources"][0]
    post = {
        "id": f"{date}-{slugify(draft['en']['headline'].replace('*', ''), 48)}",
        "date": date,
        "tag": draft["tag"],
        "image": pick_image(story, draft.get("image_hint", "")),
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
