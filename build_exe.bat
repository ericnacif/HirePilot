@echo off
setlocal EnableExtensions

cd /d "%~dp0"

echo.
echo  ========================================
echo   Vaga em Vista - gerando executaveis Windows
echo  ========================================
echo.

where python >nul 2>&1
if errorlevel 1 (
  echo [ERRO] Python nao encontrado. Instale Python 3.10+ de python.org
  pause
  exit /b 1
)

echo [1/8] Dependencias de build...
python -m pip install -q pyinstaller pillow
if errorlevel 1 goto :fail
python -m pip install -q -r requirements-build.txt
if errorlevel 1 goto :fail
python -m pip install -q -r requirements-build-full.txt
if errorlevel 1 goto :fail
python -m pip install -q -e ".[dev]"
if errorlevel 1 goto :fail

echo [2/8] Validando o projeto...
python -m compileall -q cv_apply build_support run_app.py scripts
if errorlevel 1 goto :fail
python -m pytest
if errorlevel 1 goto :fail
python -m ruff check .
if errorlevel 1 goto :fail

echo [3/8] Gerando icone...
python scripts/generate_icon.py
if errorlevel 1 goto :fail

echo [4/8] Limpando build anterior...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [5/8] Empacotando Leve (Vaga em Vista.exe)...
python -m PyInstaller hirepilot.spec --noconfirm
if errorlevel 1 goto :fail

echo [6/8] Empacotando Completo (Vaga em Vista-Full.exe)...
python -m PyInstaller hirepilot-full.spec --noconfirm
if errorlevel 1 goto :fail

echo [7/8] Criando ZIP portatil...
mkdir dist\portable 2>nul
copy /y "dist\Vaga em Vista.exe" dist\portable\ >nul
if errorlevel 1 goto :fail
copy /y LEIA-ME.txt dist\portable\ >nul
if errorlevel 1 goto :fail
powershell -NoProfile -Command "Compress-Archive -Path 'dist/portable/*' -DestinationPath 'dist/Vaga-em-Vista-portable.zip' -Force"
if errorlevel 1 goto :fail

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC (
  echo [8/8] Gerando instalador...
  "%ISCC%" installer\hirepilot.iss
  if errorlevel 1 goto :fail
) else (
  echo [8/8] Inno Setup nao encontrado; instalador ignorado.
)

echo Gerando SHA256SUMS.txt...
powershell -NoProfile -Command "$dist = (Resolve-Path 'dist').Path; Get-ChildItem -Path 'dist' -File | Where-Object { $_.Extension -in '.exe','.zip' } | Get-FileHash -Algorithm SHA256 | ForEach-Object { '{0}  {1}' -f $_.Hash, $_.Path.Substring($dist.Length + 1) } | Set-Content -Encoding ascii (Join-Path $dist 'SHA256SUMS.txt')"
if errorlevel 1 goto :fail

echo.
echo  Pronto:
echo    dist\Vaga em Vista.exe
echo    dist\Vaga em Vista-Full.exe
echo    dist\Vaga-em-Vista-portable.zip
echo    dist\SHA256SUMS.txt
if defined ISCC echo    dist\Vaga-em-Vista-Setup.exe
echo.
pause
goto :eof

:fail
echo.
echo [ERRO] O build foi interrompido. Verifique a mensagem acima.
pause
exit /b 1
