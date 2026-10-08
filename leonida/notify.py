"""Envia os posts prontos para o seu celular (Telegram e/ou Discord).

Telegram: crie um bot com @BotFather, pegue o token e o seu chat id (ex.: via @userinfobot)
  TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...
Discord: webhook de um canal
  DISCORD_WEBHOOK_URL=...
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import requests


def _post_files(folder: Path) -> dict:
    manifest = json.loads((folder / "post.json").read_text(encoding="utf-8"))
    out = {}
    for sub in ("br", "us"):
        d = folder / sub
        if not d.exists():
            continue
        imgs = sorted(d.glob("*.png"))
        cap = next(iter(list(d.glob("legenda.txt")) + list(d.glob("caption.txt"))), None)
        vid = next(iter(list(d.glob("*.mp4"))), None)
        out[sub] = {"images": imgs, "caption": cap.read_text(encoding="utf-8") if cap else "", "video": vid}
    return {"manifest": manifest, "langs": out}


def telegram(folder: Path) -> bool:
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return False
    api = f"https://api.telegram.org/bot{token}"
    data = _post_files(folder)
    for sub, item in data["langs"].items():
        flag = "🇧🇷 PERFIL BR" if sub == "br" else "🇺🇸 PERFIL US"
        media, files = [], {}
        for i, img in enumerate(item["images"][:10]):
            key = f"f{i}"
            files[key] = open(img, "rb")
            media.append({"type": "photo", "media": f"attach://{key}"})
        if media:
            media[0]["caption"] = f"{flag}\n\n{item['caption']}"[:1024]
            requests.post(f"{api}/sendMediaGroup", data={"chat_id": chat, "media": json.dumps(media)},
                          files=files, timeout=120).raise_for_status()
        for fh in files.values():
            fh.close()
        if item["video"]:
            with open(item["video"], "rb") as fh:
                requests.post(f"{api}/sendVideo", data={"chat_id": chat, "caption": f"{flag} — vídeo"},
                              files={"video": fh}, timeout=300).raise_for_status()
        # legenda separada, fácil de copiar
        requests.post(f"{api}/sendMessage", data={"chat_id": chat, "text": item["caption"][:4096]},
                      timeout=60).raise_for_status()
    return True


def discord(folder: Path) -> bool:
    hook = os.environ.get("DISCORD_WEBHOOK_URL")
    if not hook:
        return False
    data = _post_files(folder)
    for sub, item in data["langs"].items():
        flag = "🇧🇷 PERFIL BR" if sub == "br" else "🇺🇸 PERFIL US"
        files = {}
        for i, p in enumerate(item["images"][:9]):
            files[f"file{i}"] = (p.name, open(p, "rb"), "image/png")
        if item["video"] and item["video"].stat().st_size < 24_000_000:
            files["file9"] = (item["video"].name, open(item["video"], "rb"), "video/mp4")
        payload = {"content": f"**{flag}**\n```\n{item['caption'][:1800]}\n```"}
        requests.post(hook, data={"payload_json": json.dumps(payload)}, files=files, timeout=300).raise_for_status()
        for _, fh, _ in files.values():
            fh.close()
    return True


def send(folder: Path) -> list[str]:
    sent = []
    for name, fn in (("telegram", telegram), ("discord", discord)):
        try:
            if fn(folder):
                sent.append(name)
        except Exception as exc:  # noqa: BLE001
            print(f"  [notify] {name} falhou: {exc}")
    return sent


def alert(text: str) -> list[str]:
    """Mensagem curta (ex.: 'notícia nova no radar') para Telegram/Discord."""
    sent = []
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    try:
        if token and chat:
            requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                          data={"chat_id": chat, "text": text[:4096], "disable_web_page_preview": "true"},
                          timeout=30).raise_for_status()
            sent.append("telegram")
        if os.environ.get("DISCORD_WEBHOOK_URL"):
            requests.post(os.environ["DISCORD_WEBHOOK_URL"], json={"content": text[:1900]},
                          timeout=30).raise_for_status()
            sent.append("discord")
    except Exception as exc:  # noqa: BLE001
        print(f"  [notify] alerta falhou: {exc}")
    return sent
