@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title Extractor de Imagenes Chainsaw Man
cd /d "%~dp0"

echo ============================================================
echo   EXTRACTOR DE IMAGENES - CHAINSAW MAN
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

echo [ERROR] No se pudo encontrar Python en el sistema.
pause
exit /b 1

:run_python
"%PYTHON_EXE%" "%~dp0extraer_chainsaw_man.py" %*

echo.
echo ============================================================
echo Extraccion finalizada. Presione cualquier tecla para salir...
pause >nul
