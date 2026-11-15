@echo off
rem Mes revisions - installation (a lancer une seule fois).
rem Fichier volontairement sans accents : la console Windows les affiche mal.
setlocal EnableExtensions
cd /d "%~dp0"
title Mes revisions - installation

echo ============================================================
echo   Mes revisions - installation
echo ============================================================
echo.

rem --- 1. Trouver Python (3.13 de preference) ---------------------
set "PY="
for %%V in (3.13 3.12 3.11 3.14 3.10) do (
  if not defined PY (
    py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
  )
)
if not defined PY python -c "import sys; raise SystemExit(sys.version_info[:2] < (3, 10))" >nul 2>&1 && set "PY=python"
if not defined PY goto :install_python
echo Python trouve : %PY%

rem --- 2. Environnement et composants -----------------------------
if not exist ".venv\Scripts\python.exe" (
  echo Creation de l'environnement de l'application...
  %PY% -m venv .venv
  if errorlevel 1 goto :fail
)
echo Installation des composants. Cela prend quelques minutes la premiere fois...
".venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
".venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
if errorlevel 1 goto :fail
rem Photos d'iPhone au format HEIC : facultatif, on continue si cela echoue.
".venv\Scripts\python.exe" -m pip install pillow-heif >nul 2>&1

rem --- 3. Fichier .env avec les cles ------------------------------
if exist ".env" goto :shortcut
copy /y ".env.example" ".env" >nul
echo.
echo Le fichier .env vient d'etre cree et s'ouvre dans le Bloc-notes.
echo Colle ta cle Gemini apres GEMINI_API_KEY= puis enregistre et ferme le Bloc-notes.
start /wait notepad ".env"

rem --- 4. Raccourci sur le bureau ---------------------------------
:shortcut
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\raccourci.ps1"

echo.
echo ============================================================
echo   Installation terminee.
echo   Double-clique sur "Mes revisions" sur le bureau pour commencer.
echo ============================================================
pause
exit /b 0

:install_python
echo Python n'est pas installe sur cet ordinateur.
echo Installation de Python avec winget...
winget install -e --id Python.Python.3.13 --accept-package-agreements --accept-source-agreements
if errorlevel 1 goto :no_python
echo.
echo Python vient d'etre installe.
echo Ferme cette fenetre, puis relance installer.bat.
pause
exit /b 0

:no_python
echo.
echo Impossible d'installer Python automatiquement.
echo Installe Python 3.13 depuis https://www.python.org/downloads/
echo en cochant la case "Add python.exe to PATH", puis relance installer.bat.
pause
exit /b 1

:fail
echo.
echo L'installation a echoue. Verifie la connexion internet, puis relance installer.bat.
pause
exit /b 1
