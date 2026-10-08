"""Linha de comando do Leonida Studio.

  python -m leonida radar                 # busca notícias novas de GTA VI
  python -m leonida rascunho 1            # cria o post.yaml da notícia nº 1 do radar
  python -m leonida build <post-id>       # renderiza capa, carrossel, vídeo e legendas (BR + US)
  python -m leonida auto                  # radar -> redação (Claude) -> render -> envio, tudo sozinho
  python -m leonida contagem              # post diário "faltam X dias"
  python -m leonida corte URL 0:10 0:25 --pt "..." --en "..."
  python -m leonida serve                 # abre o app web (http://localhost:8000)
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

from . import config


def cmd_radar(a):
    from . import radar
    data = radar.scan(max_age_hours=a.hours)
    for err in data["errors"]:
        print(f"  ! {err}")
    print(f"\n📡 {data['count']} histórias (últimas {a.hours:.0f}h)\n")
    for i, s in enumerate(data["stories"][:a.top], 1):
        flags = ("⭐" if s["official"] else " ") + ("🎬" if s["video"] else " ") + ("🆕" if s["is_new"] else "  ")
        print(f"{i:2d}. [{s['score']:5.0f}] {flags} {s['title'][:90]}")
        if s.get("title_pt") and s["title_pt"] != s["title"]:
            print(f"              🇧🇷 {s['title_pt'][:88]}")
        print(f"              {s['coverage']} matérias · {s['sources'][0]['name']} · id {s['id']}")
    print(f"\nPainel salvo em {config.OUT_DIR / 'RADAR.md'}")


def _story(ref: str):
    from . import radar
    stories = radar.load_radar()["stories"]
    if ref.isdigit() and int(ref) <= len(stories):
        return stories[int(ref) - 1]
    for s in stories:
        if s["id"] == ref:
            return s
    sys.exit(f"História '{ref}' não encontrada no radar. Rode `python -m leonida radar` antes.")


def cmd_rascunho(a):
    from . import radar, writer
    s = _story(a.story)
    post = writer.story_to_post(s, use_llm=None if not a.sem_ia else False)
    radar.mark_seen([s["id"]], "drafted")
    print(f"✍️  posts/{post['id']}/post.yaml criado" + (" (revisar: feito sem IA)" if post.get("needs_review") else ""))


def cmd_novo(a):
    from . import post
    print(f"📝 {post.new(a.titulo, a.data)}")


def cmd_build(a):
    from . import gallery, notify, post
    for ref in a.posts:
        print(f"🎨 {ref}")
        out = post.build(ref, video=not a.sem_video)
        print(f"✅ {out}")
        if a.enviar:
            print(f"   enviado: {notify.send(out) or 'nenhum canal configurado'}")
    gallery.build()


def cmd_build_all(a):
    from . import gallery, post
    date = a.data or dt.date.today().isoformat()
    for d in sorted(config.POSTS_DIR.glob(f"{date}-*")):
        out = config.OUT_DIR / date / d.name
        if (out / "post.json").exists() and not a.forcar:
            continue
        print(f"🎨 {d.name}")
        try:
            print(f"✅ {post.build(d, video=not a.sem_video)}")
        except ValueError as exc:
            print(f"⏭️  {exc}")
    gallery.build()


def cmd_auto(a):
    """Ciclo completo — ideal para rodar a cada 1-2 h (GitHub Actions ou agendador do Windows)."""
    from . import gallery, notify, post, radar
    data = radar.scan(max_age_hours=a.hours)
    seen = radar.load_seen()
    fresh = [s for s in data["stories"] if not radar.is_seen(s, seen) and s["score"] >= a.min_score
             and not s.get("community")]
    print(f"📡 {len(fresh)} histórias novas acima de {a.min_score}")
    if a.check:
        # modo leve (CI): só informa se há trabalho, sem renderizar nada
        out = os.environ.get("GITHUB_OUTPUT")
        if out:
            with open(out, "a") as fh:
                fh.write(f"new={len(fresh)}\n")
        return
    has_llm = bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    for s in fresh[: a.max]:
        print(f"✍️  {s['title'][:90]}")
        if not has_llm:
            radar.mark_seen([s["id"]], "pending_writer")
            notify.alert(f"🆕 Notícia nova de GTA VI (score {s['score']:.0f})\n\n{s['title']}"
                         + (f"\n🇧🇷 {s['title_pt']}" if s.get("title_pt") else "")
                         + f"\n\n{s['sources'][0]['url']}\n\nPeça ao Codex/Claude: \"cria o post da notícia {s['id']}\"")
            print("   (sem ANTHROPIC_API_KEY: alerta enviado; o post fica para o Codex/Claude escrever)")
            continue
        try:
            from . import writer
            p = writer.story_to_post(s)
            out = post.build(p["id"], video=not a.sem_video)
            radar.mark_seen([s["id"]], "published")
            print(f"✅ {out}  enviado: {notify.send(out) or '-'}")
        except Exception as exc:  # noqa: BLE001
            print(f"❌ {exc}")
            radar.mark_seen([s["id"]], "error")
    gallery.build()


def cmd_contagem(a):
    """Post diário de contagem regressiva com uma screenshot oficial diferente a cada dia."""
    from . import gallery, media, notify, post
    today = dt.date.fromisoformat(a.data) if a.data else dt.date.today()
    days = config.days_to_release(today)
    if days < 0:
        sys.exit("GTA VI já foi lançado 🎉")
    # personagens primeiro: o número gigante fica atrás deles (efeito profundidade)
    groups = ["Jason_and_Lucia", "Lucia_Caminos", "Jason_Duval", "Jason_and_Lucia", "Vice_City",
              "Leonida_Keys", "Lucia_Caminos", "Jason_Duval", "Grassrivers"]
    img = media.library_pick(groups[days % len(groups)], days) or ""
    pid = f"{today.isoformat()}-contagem-{days}-dias"
    d_pt = "dia" if days == 1 else "dias"
    d_en = "day" if days == 1 else "days"
    spec = {
        "id": pid, "date": today.isoformat(), "tag": "contagem", "image": img, "kicker_without_cutout": True,
        "source": {"name": "Rockstar Games", "url": "https://www.rockstargames.com/VI"},
        "pt": {"kicker": f"{days}", "headline": f"Faltam *{days} {d_pt}* para GTA VI",
               "summary": "Lançamento em 19 de novembro de 2026 no PS5 e Xbox Series X|S.",
               "caption": f"⏳ Faltam {days} {d_pt} para GTA VI!\n\nDia 19/11 a gente volta pra Vice City. "
                          f"Já tá com o PS5/Xbox pronto?\n\nComenta o que você vai fazer primeiro em Leonida 👇",
               "hashtags": ["#contagemregressiva", "#vicecity", "#leonida"]},
        "en": {"kicker": f"{days}", "headline": f"*{days} {d_en}* until GTA VI",
               "summary": "Launching November 19, 2026 on PS5 and Xbox Series X|S.",
               "caption": f"⏳ {days} {d_en} until GTA VI.\n\nNovember 19 we're back in Vice City. "
                          f"What's the first thing you're doing in Leonida? 👇",
               "hashtags": ["#countdown", "#vicecity", "#leonida"]},
    }
    post.save(spec)
    out = post.build(pid, video=not a.sem_video, today=today)
    print(f"✅ {out}")
    if a.enviar:
        print(f"   enviado: {notify.send(out) or '-'}")
    gallery.build()


def cmd_corte(a):
    from . import clips, gallery
    out = clips.make_clip(a.fonte_video, a.inicio, a.fim, headline={"pt": a.pt, "en": a.en}, tag=a.tag,
                          source=a.credito, subtitles=a.legendas, music_on=not a.sem_musica)
    print(f"✅ {out}")
    gallery.build()


def cmd_editar(a):
    from . import edit, gallery
    head = {k: v for k, v in (("pt", a.pt), ("en", a.en)) if v}
    out = edit.make_edit(a.fonte_video, start=a.inicio, end=a.fim, duration=a.duracao, style=a.estilo,
                         layout=a.formato, headline=head, tag=a.tag, source=a.credito, subtitles=a.legendas,
                         audio=not a.sem_audio, music_on=not a.sem_musica, engine=a.motor)
    print(f"✅ {out}")
    gallery.build()


def cmd_publicacao(a):
    import json as _json
    from . import publish
    if a.marcar:
        for item in a.marcar:
            sub, _, ref = item.partition(":")
            publish.mark(a.post_id, sub, ref)
        print(f"✅ registrado em {publish.PUBLISHED}")
        return
    print(_json.dumps(publish.package(a.post_id), ensure_ascii=False, indent=1))


def cmd_musica(a):
    from . import music
    if a.arquivo:
        import shutil
        from .config import ROOT
        dst = ROOT / (config.brand().get("music") or {}).get("file", "assets/music/tema.mp3")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(a.arquivo, dst)
        print(f"🎵 música tema copiada para {dst}")
        return
    print(f"🎵 {music.download(a.url, a.inicio, a.duracao)}")


def cmd_galeria(a):
    from . import gallery
    print(f"🖼️  {gallery.build()}")


def cmd_enviar(a):
    from pathlib import Path
    from . import notify
    print(notify.send(Path(a.pasta)) or "nenhum canal configurado (TELEGRAM_* / DISCORD_WEBHOOK_URL)")


def cmd_biblioteca(a):
    from . import media
    items = media.sync_rockstar_library(force=True)
    groups = {}
    for it in items:
        groups[it["group"]] = groups.get(it["group"], 0) + 1
    print(f"📚 {len(items)} screenshots oficiais")
    for g, n in sorted(groups.items()):
        print(f"   {g}: {n}")


def cmd_serve(a):
    import uvicorn
    print(f"🌴 Leonida Studio em http://localhost:{a.port}")
    uvicorn.run("leonida.server:app", host=a.host, port=a.port, reload=False)


def main(argv=None):
    config.ensure_dirs()
    p = argparse.ArgumentParser(prog="leonida", description="Leonida Studio — posts de GTA VI para TikTok")
    sp = p.add_subparsers(dest="cmd", required=True)

    r = sp.add_parser("radar", help="busca e ranqueia notícias")
    r.add_argument("--hours", type=float, default=72)
    r.add_argument("--top", type=int, default=15)
    r.set_defaults(fn=cmd_radar)

    r = sp.add_parser("rascunho", aliases=["draft"], help="cria post.yaml a partir do radar")
    r.add_argument("story", help="posição no radar (1, 2, ...) ou id")
    r.add_argument("--sem-ia", action="store_true")
    r.set_defaults(fn=cmd_rascunho)

    r = sp.add_parser("novo", aliases=["new"], help="post.yaml em branco")
    r.add_argument("titulo")
    r.add_argument("--data")
    r.set_defaults(fn=cmd_novo)

    r = sp.add_parser("build", help="renderiza um ou mais posts")
    r.add_argument("posts", nargs="+")
    r.add_argument("--sem-video", action="store_true")
    r.add_argument("--enviar", action="store_true", help="manda no Telegram/Discord")
    r.set_defaults(fn=cmd_build)

    r = sp.add_parser("build-all", help="renderiza todos os posts do dia ainda não renderizados")
    r.add_argument("--data")
    r.add_argument("--sem-video", action="store_true")
    r.add_argument("--forcar", action="store_true")
    r.set_defaults(fn=cmd_build_all)

    r = sp.add_parser("auto", help="ciclo automático completo")
    r.add_argument("--hours", type=float, default=24)
    r.add_argument("--min-score", type=float, default=110)
    r.add_argument("--max", type=int, default=3)
    r.add_argument("--sem-video", action="store_true")
    r.add_argument("--check", action="store_true", help="só verifica se há notícia nova (para CI)")
    r.set_defaults(fn=cmd_auto)

    r = sp.add_parser("contagem", help="post diário de contagem regressiva")
    r.add_argument("--data")
    r.add_argument("--sem-video", action="store_true")
    r.add_argument("--enviar", action="store_true")
    r.set_defaults(fn=cmd_contagem)

    r = sp.add_parser("corte", aliases=["clip"], help="corte 9:16 de um vídeo")
    r.add_argument("fonte_video", help="URL (YouTube, X, Reddit...) ou arquivo local")
    r.add_argument("inicio")
    r.add_argument("fim")
    r.add_argument("--pt", required=True)
    r.add_argument("--en", default="", help="manchete US (só se o perfil US estiver ativo)")
    r.add_argument("--tag", default="viral")
    r.add_argument("--credito", default="")
    r.add_argument("--legendas", action="store_true", help="legenda automática (faster-whisper)")
    r.add_argument("--sem-musica", action="store_true", help="não colocar a música tema por baixo")
    r.set_defaults(fn=cmd_corte)

    r = sp.add_parser("editar", aliases=["edit"],
                      help="edição 9:16 de um vídeo: movimentos de câmera, transições, grade e marca")
    r.add_argument("fonte_video", help="URL (YouTube, X, Reddit, TikTok...) ou arquivo local")
    r.add_argument("--inicio", default="0", help="usar o vídeo a partir daqui (ex.: 0:30)")
    r.add_argument("--fim", default=None, help="usar o vídeo até aqui (ex.: 2:10)")
    r.add_argument("--duracao", type=float, default=20, help="duração da edição em segundos (padrão 20)")
    r.add_argument("--estilo", default="hype", choices=["hype", "cinema", "noticia"])
    r.add_argument("--formato", default="cheio", choices=["cheio", "janela"],
                   help="cheio = tela toda reenquadrada no personagem; janela = 16:9 com fundo desfocado")
    r.add_argument("--pt", default="", help="manchete BR (*destaque*)")
    r.add_argument("--en", default="", help="manchete US (*highlight*)")
    r.add_argument("--tag", default="viral")
    r.add_argument("--credito", default="", help="crédito do vídeo (padrão: canal do YouTube)")
    r.add_argument("--legendas", action="store_true", help="legenda automática (faster-whisper)")
    r.add_argument("--sem-audio", action="store_true", help="descarta o áudio original")
    r.add_argument("--sem-musica", action="store_true", help="não colocar a música tema")
    r.add_argument("--motor", default=None, choices=["auto", "hyperframes", "ffmpeg"])
    r.set_defaults(fn=cmd_editar)

    r = sp.add_parser("publicacao", help="pacote para publicar no TikTok via Metricool (links + legenda)")
    r.add_argument("post_id")
    r.add_argument("--marcar", nargs="+", metavar="PERFIL:REF",
                   help="registra como publicado, ex.: br:123 us:456")
    r.set_defaults(fn=cmd_publicacao)

    r = sp.add_parser("musica", help="baixa/define a música tema usada nos vídeos")
    r.add_argument("url", nargs="?", help="URL do YouTube (ex.: trailer oficial)")
    r.add_argument("--inicio", default="0", help="ponto de início, ex.: 0:12")
    r.add_argument("--duracao", type=float, default=120)
    r.add_argument("--arquivo", help="usar um mp3/m4a que você já tem")
    r.set_defaults(fn=cmd_musica)

    r = sp.add_parser("galeria", help="gera prontos/index.html")
    r.set_defaults(fn=cmd_galeria)
    r = sp.add_parser("enviar", help="envia uma pasta pronta para Telegram/Discord")
    r.add_argument("pasta")
    r.set_defaults(fn=cmd_enviar)
    r = sp.add_parser("biblioteca", help="lista screenshots oficiais da Rockstar")
    r.set_defaults(fn=cmd_biblioteca)
    r = sp.add_parser("serve", help="abre o app web")
    r.add_argument("--port", type=int, default=8000)
    r.add_argument("--host", default="127.0.0.1")
    r.set_defaults(fn=cmd_serve)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
