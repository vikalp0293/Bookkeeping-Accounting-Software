#!/bin/bash
# Build script for macOS/Linux (for development/testing)
# Note: Windows executable can only be built on Windows

echo "Building Sync Accounting Desktop SDK..."
echo ""

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "ERROR: Node.js is not installed or not in PATH"
    echo "Please install Node.js from https://nodejs.org/"
    exit 1
fi

# Check if npm is installed
if ! command -v npm &> /dev/null; then
    echo "ERROR: npm is not installed or not in PATH"
    exit 1
fi

echo "Step 1: Installing Node.js dependencies..."
npm install
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to install Node.js dependencies"
    exit 1
fi

echo ""
echo "Step 2: Building frontend..."
npm run build:frontend
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to build frontend"
    exit 1
fi

echo ""
echo "Step 3: Copying frontend to desktop app..."
npm run copy:frontend
if [ $? -ne 0 ]; then
    echo "ERROR: Failed to copy frontend"
    exit 1
fi

echo ""
echo "Step 4: Preparing Python scripts..."
npm run prepare:python
if [ $? -ne 0 ]; then
    echo "WARNING: Python preparation had issues, continuing anyway..."
fi

echo ""
echo "========================================"
echo "Build preparation complete!"
echo "========================================"
echo ""
echo "NOTE: Windows executable (.exe) can only be built on Windows."
echo "To build the Windows installer, run on a Windows machine:"
echo "  cd desktop-qbsdk"
echo "  scripts\\build-exe.bat"
echo ""
echo "Or use electron-builder directly:"
echo "  npm run build:win"
echo ""


