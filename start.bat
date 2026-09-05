@echo off
cd /d "%~dp0"
echo ==========================================
echo Starte Multi-Posting Web-Dashboard...
echo ==========================================
python -m streamlit run app.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Fehler beim Starten. Druecke eine beliebige Taste zum Schliessen...
    pause
)
