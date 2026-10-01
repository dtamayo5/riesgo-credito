@echo off
REM Uso mensual: procesa todas las entidades de la carpeta entrada con el ultimo mes disponible.
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat goto sin_instalar
call venv\Scripts\activate.bat
python generar_informes.py
if errorlevel 1 goto fallo
start "" "%~dp0salidas"
pause
exit /b 0

:sin_instalar
echo Primero ejecute instalar.bat (doble clic).
pause
exit /b 1

:fallo
echo.
echo Algo fallo. Lea el mensaje de arriba. Para mas detalle: python generar_informes.py --debug
pause
exit /b 1
