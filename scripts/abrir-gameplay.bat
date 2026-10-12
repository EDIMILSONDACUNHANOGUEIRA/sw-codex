@echo off
REM Aplicativo exclusivo dos cortes e das legendas da fala. Sem radar de noticias.
cd /d "%~dp0\.."
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
start "" http://127.0.0.1:8769/
python -m uvicorn apps.gameplay.app:app --host 127.0.0.1 --port 8769
pause
