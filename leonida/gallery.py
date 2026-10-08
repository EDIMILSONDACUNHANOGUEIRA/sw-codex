"""Gera prontos/index.html — galeria para revisar e copiar as legendas (funciona no GitHub Pages)."""
from __future__ import annotations

import html
import json

from .config import OUT_DIR

PAGE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Leonida Wire — Prontos</title>
<style>
  :root {{ --night:#0B0614; --card:#160d24; --line:#2a1c40; --pink:#FF2E88; --orange:#FF8A3D;
          --gold:#FFC857; --cyan:#22D3EE; --ink:#F4EEFF; --muted:#A99BC4; }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; background:var(--night); color:var(--ink); font:15px/1.5 system-ui,-apple-system,"Segoe UI",Inter,sans-serif }}
  header {{ padding:28px 16px 12px; max-width:1200px; margin:auto }}
  h1 {{ margin:0; font-size:30px; letter-spacing:.5px }}
  h1 span {{ background:linear-gradient(90deg,var(--gold),var(--orange),var(--pink)); -webkit-background-clip:text; background-clip:text; color:transparent }}
  .sub {{ color:var(--muted) }}
  main {{ max-width:1200px; margin:auto; padding:0 16px 60px }}
  h2.date {{ color:var(--gold); font-size:14px; letter-spacing:3px; margin:34px 0 10px; text-transform:uppercase }}
  .post {{ background:var(--card); border:1px solid var(--line); border-radius:18px; padding:16px; margin:14px 0 }}
  .post h3 {{ margin:0 0 4px; font-size:19px }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:10px }}
  .tag {{ display:inline-block; padding:2px 10px; border-radius:99px; background:var(--pink); color:#fff; font-weight:800; font-size:11px; letter-spacing:1.5px; margin-right:6px }}
  .cols {{ display:grid; grid-template-columns:1fr 1fr; gap:16px }}
  @media (max-width:760px) {{ .cols {{ grid-template-columns:1fr }} }}
  .lang h4 {{ margin:6px 0; font-size:13px; letter-spacing:2px; color:var(--cyan) }}
  .strip {{ display:flex; gap:8px; overflow-x:auto; padding-bottom:6px }}
  .strip img, .strip video {{ height:280px; border-radius:10px; border:1px solid var(--line); background:#000 }}
  pre {{ white-space:pre-wrap; background:#0f0819; border:1px solid var(--line); border-radius:10px; padding:10px; font:13px/1.45 ui-monospace,monospace; max-height:220px; overflow:auto }}
  button {{ background:linear-gradient(90deg,var(--orange),var(--pink)); border:0; color:#fff; font-weight:800; padding:8px 14px; border-radius:10px; cursor:pointer }}
  a {{ color:var(--cyan) }}
  .dl {{ font-size:13px; margin-left:8px }}
</style>
</head>
<body>
<header><h1><span>LEONIDA WIRE</span> — posts prontos</h1>
<div class="sub">Clique em "Copiar legenda", baixe as imagens/vídeo e publique em cada perfil. Atualizado: {updated}</div></header>
<main>{body}</main>
<script>
function copyCap(id){{ const t=document.getElementById(id).innerText; navigator.clipboard.writeText(t).then(()=>{{
  const b=document.querySelector('[data-for="'+id+'"]'); const o=b.innerText; b.innerText='Copiado ✓'; setTimeout(()=>b.innerText=o,1500);}}); }}
</script>
</body></html>
"""


def build() -> str:
    import datetime as dt
    posts = []
    for mf in OUT_DIR.glob("*/*/post.json"):
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        m["_dir"] = mf.parent
        posts.append(m)
    posts.sort(key=lambda m: (m.get("date", ""), m["_dir"].stat().st_mtime), reverse=True)
    parts, cur_date, n = [], None, 0
    for m in posts:
        d = m["_dir"]
        rel = d.relative_to(OUT_DIR).as_posix()
        if m.get("date") != cur_date:
            cur_date = m.get("date")
            parts.append(f'<h2 class="date">{html.escape(str(cur_date))}</h2>')
        title = m["id"]
        readme = d / "README.md"
        if readme.exists():
            first = readme.read_text(encoding="utf-8").splitlines()[0]
            title = first.lstrip("# ").strip() or title
        src = m.get("source") or {}
        src_html = f'Fonte: <a href="{html.escape(src["url"])}">{html.escape(src.get("name", ""))}</a>' \
            if src.get("url") else ""
        tag = f'<span class="tag">{html.escape(str(m.get("tag") or m.get("type") or ""))}</span>'
        cols = []
        for sub, label in (("br", "🇧🇷 PERFIL BR"), ("us", "🇺🇸 PERFIL US")):
            sd = d / sub
            if not sd.exists():
                continue
            media = []
            for f in sorted(sd.iterdir()):
                url = f"{rel}/{sub}/{f.name}"
                if f.suffix == ".png":
                    media.append(f'<a href="{url}" download><img src="{url}" loading="lazy" alt=""></a>')
                elif f.suffix == ".mp4":
                    media.append(f'<video src="{url}" controls preload="metadata" playsinline></video>')
            cap_file = next(iter(list(sd.glob("legenda.txt")) + list(sd.glob("caption.txt"))), None)
            cap = cap_file.read_text(encoding="utf-8") if cap_file else ""
            n += 1
            cid = f"cap{n}"
            vids = "".join(f'<a class="dl" href="{rel}/{sub}/{f.name}" download>baixar {f.name}</a>'
                           for f in sorted(sd.glob("*.mp4")))
            cols.append(f'<div class="lang"><h4>{label}</h4><div class="strip">{"".join(media)}</div>'
                        f'<pre id="{cid}">{html.escape(cap)}</pre>'
                        f'<button data-for="{cid}" onclick="copyCap(\'{cid}\')">Copiar legenda</button>{vids}</div>')
        parts.append(f'<section class="post"><h3>{html.escape(title)}</h3><div class="meta">{tag}{src_html}</div>'
                     f'<div class="cols">{"".join(cols)}</div></section>')
    body = "\n".join(parts) or "<p>Nenhum post ainda. Rode <code>python -m leonida auto</code>.</p>"
    page = PAGE.format(body=body, updated=dt.datetime.now().strftime("%d/%m/%Y %H:%M"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    return str(OUT_DIR / "index.html")
