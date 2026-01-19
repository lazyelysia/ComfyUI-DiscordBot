@echo off

echo Setting up virtual environment...
python -m venv ./.venv

echo Installing requirements...
"./.venv/Scripts/python.exe" -m pip install -r requirements.txt

echo Installation complete!
pause
