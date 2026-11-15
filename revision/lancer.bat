@echo off
rem Mes revisions - lance l'application et ouvre le navigateur.
rem Cree aussi le raccourci sur le bureau s'il n'existe pas encore.
setlocal EnableExtensions
cd /d "%~dp0"
title Mes revisions

if exist ".venv\Scripts\python.exe" goto :run
echo Premiere utilisation : installation...
call "%~dp0installer.bat"
if not exist ".venv\Scripts\python.exe" exit /b 1

:run
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\raccourci.ps1" -SiAbsent >nul 2>&1

cd /d "%~dp0backend"
"..\.venv\Scripts\python.exe" -m app.launcher
if not errorlevel 1 exit /b 0
echo.
echo L'application s'est arretee avec une erreur. Le message est juste au-dessus.
pause
exit /b 1
