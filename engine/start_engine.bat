@echo off
title Vidorq Engine
rem Starts the engine on 127.0.0.1:9877.
rem
rem The interpreter is looked for rather than hardcoded, because the engine has
rem to run under one that actually has faster-whisper, PyAV, Pillow, numpy and
rem onnxruntime. Started with the wrong Python it answers /health perfectly and
rem then dies half way through the first job, so it now says which ones are
rem missing instead. Order: Vidorq's own venv, the bridge's venv next door, then
rem whatever `python` is on PATH.
setlocal
set "HERE=%~dp0"
set "PY="

if exist "%HERE%..\.venv\Scripts\python.exe" set "PY=%HERE%..\.venv\Scripts\python.exe"
if not defined PY if exist "%HERE%..\..\davinci-resolve-mcp\venv\Scripts\python.exe" set "PY=%HERE%..\..\davinci-resolve-mcp\venv\Scripts\python.exe"
if not defined PY if exist "C:\proyectos\davinci-resolve-mcp\venv\Scripts\python.exe" set "PY=C:\proyectos\davinci-resolve-mcp\venv\Scripts\python.exe"
if not defined PY set "PY=python"

echo Vidorq engine, using: %PY%
"%PY%" "%HERE%server.py"

rem Only hold the window open when something went wrong. A clean stop should not
rem leave a dead console sitting there waiting for a key.
if errorlevel 1 pause
endlocal
