@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Conversor de Imagenes - Sugoi Posters Assets
cd /d "%~dp0"

echo ============================================================
echo   CONVERSOR DE IMAGENES - SUGOI POSTERS ASSETS
echo   (PNG 100%% Calidad Lossless / WebP)
echo ============================================================
echo.

set "PYTHON_EXE="

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :run_python
)

if exist "C:\Users\Emilio Molina\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=C:\Users\Emilio Molina\AppData\Local\Programs\Python\Python312\python.exe"
    goto :run_python
)

where py >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    goto :run_python
)

where python >nul 2>nul
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    goto :run_python
)

echo [ERROR] No se pudo encontrar Python 3 instalado en el equipo.
echo Por favor asegurese de que Python este instalado.
echo.
pause
exit /b 1

:run_python
if not "%~1"=="" (
    "%PYTHON_EXE%" "%~dp0convertir.py" %*
) else (
    "%PYTHON_EXE%" "%~dp0convertir.py" -i
)

echo.
echo ============================================================
echo Proceso finalizado. Presione cualquier tecla para salir...
pause >nul
