@echo off
title Vidorq (modo debug - con consola)
cd /d "%~dp0"
echo Arrancando el motor local (puerto 9877) si no esta ya encendido...
"C:\proyectos\davinci-resolve-mcp\venv\Scripts\python.exe" -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9877/health',timeout=2)" 2>nul
if errorlevel 1 start "Vidorq Engine" /min cmd /c "..\engine\start_engine.bat"
echo.
echo Arrancando la app en modo dev (compila siempre lo ultimo)...
pnpm tauri dev
pause
