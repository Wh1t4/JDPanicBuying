@echo off
setlocal
cd /d "%~dp0"
if not exist "jd-conda-env\python.exe" (
  echo Missing jd-conda-env. Create it with:
  echo conda --no-plugins create --solver classic -p "%~dp0jd-conda-env" python=3.11 -y
  exit /b 1
)
"%~dp0jd-conda-env\python.exe" -m pip install -r requirements.txt
