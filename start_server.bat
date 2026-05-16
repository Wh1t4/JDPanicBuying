@echo off
setlocal
cd /d "%~dp0"
if not exist "jd-conda-env\python.exe" (
  echo Missing jd-conda-env. Run setup_env.bat after creating the project conda env.
  exit /b 1
)
"%~dp0jd-conda-env\python.exe" runserver.py
