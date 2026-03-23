const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const pythonDir = path.join(__dirname, '../python');
const requirementsFile = path.join(pythonDir, 'requirements.txt');

console.log('Preparing Python for build...');

// Check if requirements.txt exists
if (!fs.existsSync(requirementsFile)) {
  console.warn('requirements.txt not found, skipping Python preparation');
  process.exit(0);
}

// Create a requirements file with pinned versions for production
// This helps ensure consistency
console.log('Python scripts will be bundled with the app.');
console.log('Note: Python 3.8+ must be installed on the target system.');
console.log('Python dependencies will be installed on first run if needed.');

// Create a simple installer script that will be bundled
const installScript = `@echo off
echo Installing Python dependencies for QB Accounting SDK...
echo.

REM Check if Python is installed
where python >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Python is not installed or not in PATH
    echo Please install Python 3.8+ from https://www.python.org/
    echo Make sure to check "Add Python to PATH" during installation
    pause
    exit /b 1
)

REM Get the directory where this script is located
set SCRIPT_DIR=%~dp0
set PYTHON_DIR=%SCRIPT_DIR%python

echo Installing dependencies from %PYTHON_DIR%...
cd /d "%PYTHON_DIR%"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if %ERRORLEVEL% EQU 0 (
    echo.
    echo Python dependencies installed successfully!
) else (
    echo.
    echo ERROR: Failed to install Python dependencies
    pause
    exit /b 1
)
`;

const installScriptPath = path.join(pythonDir, 'install_dependencies.bat');
fs.writeFileSync(installScriptPath, installScript);
console.log('Created install_dependencies.bat');

console.log('Python preparation complete!');

