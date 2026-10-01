@echo off
REM Instalacion (una sola vez): crea el entorno virtual e instala las librerias.
cd /d "%~dp0"
echo.
echo === Instalando el motor de riesgo de credito ===
echo.
where python >nul 2>nul
if errorlevel 1 goto sin_python
if not exist venv\Scripts\activate.bat python -m venv venv
if not exist venv\Scripts\activate.bat goto error_venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto error_pip
echo.
echo Instalacion terminada. Siguiente paso: doble clic en demo.bat
echo.
pause
exit /b 0

:sin_python
echo No se encontro Python. Instalelo desde python.org marcando la casilla
echo "Add python.exe to PATH" y vuelva a ejecutar este archivo.
pause
exit /b 1

:error_venv
echo No se pudo crear el entorno virtual (carpeta venv).
pause
exit /b 1

:error_pip
echo Fallo la instalacion de librerias. Revise su conexion a internet y reintente.
pause
exit /b 1
