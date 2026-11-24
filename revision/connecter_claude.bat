@echo off
rem Mes revisions - branche l'application Claude (pour ordinateur) sur Revision.
rem Claude pourra alors preparer les lecons pendant la nuit.
setlocal EnableExtensions
cd /d "%~dp0"
title Mes revisions - connexion a Claude
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0outils\connecter_claude.ps1"
echo.
pause
