#!/usr/bin/env bash
set -o errexit

pip install --upgrade pip
pip install -r requirements.txt
pip install gunicorn==23.0.0

# Initialize the database
python -c "from app.db import init_db; init_db()"
