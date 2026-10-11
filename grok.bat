@echo off
REM Wrapper Windows: grok.bat harvest -n 3
setlocal
set DIR=%~dp0
"%DIR%.venv\Scripts\python.exe" "%DIR%grok.py" %*
