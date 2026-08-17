@echo off
title Vidorq Engine
rem Vidorq Engine launcher - uses the davinci-resolve-mcp venv (has faster-whisper, PyAV, Pillow)
"C:\proyectos\davinci-resolve-mcp\venv\Scripts\python.exe" "%~dp0server.py"
rem Only hold the window open when something went wrong. A clean stop should not
rem leave a dead console sitting there waiting for a key.
if errorlevel 1 pause
