@echo off
REM Abre o Leonida Studio no navegador (Windows). Dê dois cliques neste arquivo.
cd /d "%~dp0\.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
REM Abre o navegador quando o servidor responder (antes disso a pagina daria erro).
start "" /b powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0esperar-e-abrir.ps1" -Url http://127.0.0.1:8000/
python -m leonida serve
pause
