@echo off
echo ================================================
echo Spanish Sentence Miner - EXE Builder
echo ================================================
echo.

REM Check if virtual environment exists
if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Virtual environment not found!
    echo Please make sure .venv folder exists in the current directory.
    echo.
    pause
    exit /b 1
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo.
echo Installing required packages...
pip install -r requirements.txt
pip install pyinstaller

echo.
echo Building executable with PyInstaller...
echo.

REM Check if icon exists
if exist "app_icon.ico" (
    echo Found app_icon.ico - using custom icon
    pyinstaller sentence_miner.spec
) else (
    echo WARNING: app_icon.ico not found - using default icon
    echo To add a custom icon, place an .ico file named 'app_icon.ico' in this folder
    echo.
    pyinstaller sentence_miner.spec
)

echo.
echo ================================================
echo Build Complete!
echo ================================================
echo.
echo Your executable is located at:
echo dist\SpanishSentenceMiner.exe
echo.
echo You can now run the application by double-clicking the .exe file
echo.

pause
