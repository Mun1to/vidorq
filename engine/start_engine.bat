@echo off
title Vidorq Engine
rem Vidorq Engine launcher - uses the davinci-resolve-mcp venv (has faster-whisper, PyAV, Pillow)
"C:\proyectos\davinci-resolve-mcp\venv\Scripts\python.exe" "%~dp0server.py"
pause
