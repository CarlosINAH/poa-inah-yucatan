@echo off
chcp 65001 >nul
title Plataforma POA - Conservacion - Centro INAH Yucatan
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo  No encuentro el entorno de Python en .venv
  echo  Corre primero: python -m venv .venv
  echo                 .venv\Scripts\python.exe -m pip install -r servidor_poa\requirements.txt
  echo                 .venv\Scripts\python.exe servidor_poa\inicializar.py
  echo.
  pause
  exit /b 1
)

echo.
echo  ====================================================
echo   PLATAFORMA POA
echo   Seccion de Conservacion y Restauracion
echo   Centro INAH Yucatan
echo  ====================================================
echo.
echo   En este equipo:  http://localhost:8000
echo.
echo   Para tus companeros, desde su navegador:
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
  for /f "tokens=1" %%b in ("%%a") do echo      http://%%b:8000
)
echo.
echo   No cierres esta ventana: mientras este abierta, la
echo   plataforma esta encendida. Para apagarla, Ctrl+C.
echo.

cd servidor_poa
"..\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
pause
