@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo.
echo  ========================================
echo   VagaMatch - gerando executavel Windows
echo  ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao encontrado. Instale Python 3.10+ de python.org
  pause
  exit /b 1
)

echo [1/4] Instalando dependencias de build...
python -m pip install -q pyinstaller
python -m pip install -q -r requirements-web.txt
python -m pip install -q -e .

echo [2/4] Limpando build anterior...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [3/4] Empacotando com PyInstaller (pode levar alguns minutos)...
python -m PyInstaller vagamatch.spec --noconfirm
if errorlevel 1 (
  echo [ERRO] Falha no PyInstaller.
  pause
  exit /b 1
)

echo [4/4] Concluido.
if exist "dist\VagaMatch.exe" (
  echo.
  echo  Executavel pronto: dist\VagaMatch.exe
  echo  Distribua esse arquivo para quem nao tem Python instalado.
  echo.
) else (
  echo [ERRO] dist\VagaMatch.exe nao foi criado.
  pause
  exit /b 1
)

pause
endlocal
