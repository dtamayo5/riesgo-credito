@echo off
REM Demostracion: crea las dos entidades ficticias y genera sus informes.
cd /d "%~dp0"
if not exist venv\Scripts\activate.bat goto sin_instalar
call venv\Scripts\activate.bat
python herramientas\generar_datos_demo.py
if errorlevel 1 goto fallo
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
echo Algo fallo. Lea el mensaje de arriba.
pause
exit /b 1
