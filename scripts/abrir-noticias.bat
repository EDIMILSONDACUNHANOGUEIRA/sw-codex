@echo off
REM Aplicativo exclusivo das noticias diarias. O editor de cortes usa outra porta.
cd /d "%~dp0\.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
REM Abre o navegador quando o servidor responder (antes disso a pagina daria erro).
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0esperar-e-abrir.ps1" -Url http://127.0.0.1:8768/
python -m uvicorn apps.noticias.app:app --host 127.0.0.1 --port 8768
pause
