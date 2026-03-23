#!/bin/bash
set -e  # Exit immediately if any command fails
 
echo "Starting Deployment Check..."
 
# 1. Run Database Migrations
echo "Running Alembic Migrations..."
alembic upgrade head
 
# 2. Start the Application
echo "Migrations complete. Starting Server..."
 
# Replace this command with whatever you use to run your app.
# Common options:
# Option A (Gunicorn - Production Standard):
#exec gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app --bind 0.0.0.0:8000
# Option B (Uvicorn - Simpler):
# We use exec so uvicorn takes over the process ID (PID 1)
exec uvicorn app.main:app --host 0.0.0.0 --port 8000