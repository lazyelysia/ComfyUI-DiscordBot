#!/bin/bash

echo "Setting up virtual environment..."
python3 -m venv .venv

echo "Installing requirements..."
./.venv/bin/python -m pip install -r requirements.txt

echo "DiscordBot setup complete! Configure 'config.properties' and restart to run the bot."
