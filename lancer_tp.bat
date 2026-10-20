@echo off
title Hub Web TP ICy - AutoPilot
color 0B
cls
echo ========================================================
echo       HUB WEB DE SALLE DE TP - PROMOTION 3A ICy
echo ========================================================
echo.
echo [1/2] Demarrage du serveur local sur le port 8000...
echo [2/2] Le dashboard sera accessible a :
echo        - En local :   http://localhost:8000
echo        - En reseau :  http://[IP_DE_TON_PC]:8000
echo.
echo Appuyez sur Ctrl+C dans cette fenetre pour arreter le serveur.
echo.

start "" http://localhost:8000
python -m uvicorn src.web.app:app --host 0.0.0.0 --port 8000 --reload

pause
