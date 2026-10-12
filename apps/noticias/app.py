"""Aplicativo das notícias diárias; os cortes têm servidor e arquivos próprios."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from leonida import server as legacy

WEB = Path(__file__).resolve().parent / "web"
app = FastAPI(title="Leonida Notícias")

# Preserva os contratos e o estado de notícias existentes. Não registra APIs de
# gameplay, cortes manuais ou envio externo nesta interface de entrega local.
for route in legacy.app.routes:
    path = getattr(route, "path", "")
    if path in ("/", "/static", "/api/clips", "/api/posts/{pid}/send") or path.startswith("/api/gameplay"):
        continue
    if path in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"):
        continue
    app.router.routes.append(route)


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/static", StaticFiles(directory=str(WEB), check_dir=False), name="static")
