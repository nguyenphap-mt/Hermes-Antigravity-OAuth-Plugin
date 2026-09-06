@echo off
title Google Flow Login - Hermes
cd /d "%~dp0"
cls
echo ====================================================================
echo        DANG NHAP GOOGLE FLOW (MEDIA ^& VIDEOFX) CHO HERMES
echo ====================================================================
echo.
echo [*] Dang khoi chay trinh duyet...
echo.
python manage.py flow-login
echo.
pause
