@echo off
REM Двойной клик по start.bat запускает всё приложение
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0start.ps1" %*
if errorlevel 1 pause
