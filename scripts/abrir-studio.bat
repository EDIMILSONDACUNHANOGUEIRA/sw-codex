@echo off
REM Abre o Leonida Studio no navegador (Windows). Dê dois cliques neste arquivo.
cd /d "%~dp0\.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
start "" http://localhost:8000
python -m leonida serve
