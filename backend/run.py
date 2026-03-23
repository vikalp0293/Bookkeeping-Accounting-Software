#!/usr/bin/env python3
"""
Development server runner for Sync Accounting Software backend.
Usage: python run.py
"""
import os
import sys
import subprocess

def main():
    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(script_dir, 'venv', 'bin', 'python3')
    venv_uvicorn = os.path.join(script_dir, 'venv', 'bin', 'uvicorn')
    
    # Check if venv exists
    if not os.path.exists(venv_python):
        print("Error: Virtual environment not found. Please run: python3 -m venv venv")
        sys.exit(1)
    
    # Run uvicorn
    os.chdir(script_dir)
    cmd = [venv_uvicorn, 'app.main:app', '--reload', '--port', '5208']
    subprocess.run(cmd)

if __name__ == '__main__':
    main()

