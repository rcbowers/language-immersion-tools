@echo off
REM Spanish Sentence Miner Runner Script
REM This script runs the spanish_sentence_miner.py script

echo ============================================================
echo Spanish Sentence Mining - Anki Card Creator
echo ============================================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed or not in PATH
    echo Please install Python 3 and try again
    pause
    exit /b 1
)

REM Check if the script exists
if not exist "spanish_sentence_miner.py" (
    echo Error: spanish_sentence_miner.py not found
    echo Please make sure you're running this script from the correct directory
    pause
    exit /b 1
)

REM Check if input file exists
if not exist "words_to_process.txt" (
    echo Warning: words_to_process.txt not found
    echo Creating an empty file...
    type nul > words_to_process.txt
    echo.
)

REM Run the Python script
echo Running spanish_sentence_miner.py...
echo.
python spanish_sentence_miner.py

REM Check exit code
if errorlevel 1 (
    echo.
    echo Script execution failed with an error
) else (
    echo.
    echo Script execution completed
)

echo.
pause
