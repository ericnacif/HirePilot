@echo off

setlocal EnableExtensions

cd /d "%~dp0"



echo.

echo  ========================================

echo   HirePilot - gerando executaveis Windows

echo  ========================================

echo.



where python >nul 2>&1

if errorlevel 1 (

  echo [ERRO] Python nao encontrado. Instale Python 3.10+ de python.org

  pause

  exit /b 1

)



echo [1/6] Dependencias de build...

python -m pip install -q pyinstaller pillow

python -m pip install -q -r requirements-build.txt

python -m pip install -q -r requirements-build-full.txt

python -m pip install -q -e .



echo [2/6] Gerando icone...

python scripts/generate_icon.py



echo [3/6] Limpando build anterior...

if exist build rmdir /s /q build

if exist dist rmdir /s /q dist



echo [4/6] Empacotando Leve (HirePilot.exe)...

python -m PyInstaller hirepilot.spec --noconfirm

if errorlevel 1 goto :fail



echo [5/6] Empacotando Completo (HirePilot-Full.exe)...

python -m PyInstaller hirepilot-full.spec --noconfirm

if errorlevel 1 goto :fail



echo [6/6] ZIP portatil...

mkdir dist\portable 2>nul

copy /y dist\HirePilot.exe dist\portable\ >nul

copy /y LEIA-ME.txt dist\portable\ >nul

powershell -Command "Compress-Archive -Path 'dist/portable/*' -DestinationPath 'dist/HirePilot-portable.zip' -Force"



echo.

echo  Pronto:

echo    dist\HirePilot.exe

echo    dist\HirePilot-Full.exe

echo    dist\HirePilot-portable.zip

echo.

echo  Instalador: abra installer\hirepilot.iss no Inno Setup (se instalado).

echo.

pause

goto :eof



:fail

echo [ERRO] Falha no PyInstaller.

pause

exit /b 1

endlocal

