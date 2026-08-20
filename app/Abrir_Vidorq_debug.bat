@echo off
title Vidorq (modo debug - con consola)
cd /d "%~dp0"
setlocal

rem El interprete se busca, no se da por hecho. Antes estaba escrita aqui la
rem ruta de UNA maquina, y en cualquier otra esa linea fallaba siempre: como el
rem fallo se lee como "el motor no contesta", este lanzador abria un motor nuevo
rem cada vez, tambien cuando ya habia uno encendido. Mismo orden que
rem engine\start_engine.bat, que si lo hacia bien.
set "PY="
if exist "%~dp0..\.venv\Scripts\python.exe" set "PY=%~dp0..\.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0..\..\davinci-resolve-mcp\venv\Scripts\python.exe" set "PY=%~dp0..\..\davinci-resolve-mcp\venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo Arrancando el motor local (puerto 9877) si no esta ya encendido...
"%PY%" -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9877/health',timeout=2)" 2>nul
if errorlevel 1 start "Vidorq Engine" /min cmd /c "..\engine\start_engine.bat"
echo.
echo Arrancando la app en modo dev (compila siempre lo ultimo)...
pnpm tauri dev
pause
