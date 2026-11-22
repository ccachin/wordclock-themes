@echo off
cd /d "%~dp0"
python admin\app.py
if errorlevel 1 pause
