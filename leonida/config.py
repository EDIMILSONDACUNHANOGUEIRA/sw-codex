"""Caminhos do projeto e leitura das configs YAML."""
from __future__ import annotations

import datetime as dt
import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
FONTS_DIR = ROOT / "assets" / "fonts"
POSTS_DIR = ROOT / "posts"          # especificações dos posts (post.yaml)
OUT_DIR = ROOT / "prontos"          # posts renderizados, prontos para publicar
STATE_DIR = ROOT / "state"          # radar.json, seen.json (histórico do radar)
CACHE_DIR = Path(os.environ.get("LEONIDA_CACHE", ROOT / ".cache"))
HF_DIR = Path(__file__).resolve().parent / "hyperframes"

LANGS = ("pt", "en")
# Pasta de saída por idioma: br = perfil brasileiro, us = perfil americano
LANG_FOLDER = {"pt": "br", "en": "us"}

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def _load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@lru_cache(maxsize=1)
def brand() -> dict:
    return _load_yaml("brand.yaml")


@lru_cache(maxsize=1)
def sources() -> dict:
    return _load_yaml("sources.yaml")


def days_to_release(today: dt.date | None = None) -> int:
    today = today or dt.date.today()
    release = dt.date.fromisoformat(str(brand()["release_date"]))
    return (release - today).days


def ensure_dirs() -> None:
    for d in (POSTS_DIR, OUT_DIR, STATE_DIR, CACHE_DIR):
        d.mkdir(parents=True, exist_ok=True)
