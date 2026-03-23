#!/bin/bash
# Script to check poppler installation on server

echo "🔍 Checking Poppler Installation on Server"
echo "=========================================="
echo ""

# Check if pdftoppm command exists
echo "1. Checking if pdftoppm is in PATH..."
if command -v pdftoppm &> /dev/null; then
    echo "   ✅ pdftoppm found: $(which pdftoppm)"
    echo "   Version: $(pdftoppm -v 2>&1 | head -1)"
else
    echo "   ❌ pdftoppm NOT found in PATH"
fi
echo ""

# Check for poppler package (Ubuntu/Debian)
echo "2. Checking installed poppler packages (Ubuntu/Debian)..."
if command -v dpkg &> /dev/null; then
    POppler_PACKAGES=$(dpkg -l | grep -i poppler | awk '{print $2}')
    if [ -z "$POppler_PACKAGES" ]; then
        echo "   ❌ No poppler packages found"
    else
        echo "   ✅ Found poppler packages:"
        echo "$POppler_PACKAGES" | sed 's/^/      - /'
    fi
elif command -v rpm &> /dev/null; then
    echo "   Checking with rpm (RedHat/CentOS)..."
    rpm -qa | grep -i poppler
else
    echo "   ⚠️  Cannot check packages (neither dpkg nor rpm found)"
fi
echo ""

# Check common installation paths
echo "3. Checking common poppler installation paths..."
PATHS=("/usr/bin/pdftoppm" "/usr/local/bin/pdftoppm" "/opt/homebrew/bin/pdftoppm")
FOUND=false
for path in "${PATHS[@]}"; do
    if [ -f "$path" ]; then
        echo "   ✅ Found: $path"
        FOUND=true
    fi
done
if [ "$FOUND" = false ]; then
    echo "   ❌ Not found in common paths"
fi
echo ""

# Check Python pdf2image module
echo "4. Checking Python pdf2image module..."
if python3 -c "import pdf2image" 2>/dev/null; then
    echo "   ✅ pdf2image module is installed"
    
    # Try to test if it can use poppler
    echo "   Testing pdf2image with poppler..."
    python3 << 'PYTHON_EOF'
try:
    from pdf2image import convert_from_path
    print("   ✅ pdf2image.convert_from_path is available")
    
    # Try to check if poppler is accessible
    import subprocess
    try:
        result = subprocess.run(['pdftoppm', '-h'], capture_output=True, timeout=2)
        if result.returncode in [0, 1]:  # -h usually returns 1
            print("   ✅ poppler utilities are accessible from Python")
        else:
            print("   ⚠️  pdftoppm returned unexpected code:", result.returncode)
    except FileNotFoundError:
        print("   ❌ poppler utilities NOT accessible from Python")
        print("   💡 Install with: sudo apt-get install poppler-utils")
    except Exception as e:
        print(f"   ⚠️  Error checking poppler: {e}")
except ImportError as e:
    print(f"   ❌ Error importing pdf2image: {e}")
except Exception as e:
    print(f"   ⚠️  Error: {e}")
PYTHON_EOF
else
    echo "   ❌ pdf2image module is NOT installed"
    echo "   💡 Install with: pip install pdf2image"
fi
echo ""

# Summary
echo "=========================================="
echo "📋 SUMMARY:"
echo ""

if command -v pdftoppm &> /dev/null; then
    echo "✅ Poppler appears to be installed"
    echo ""
    echo "💡 If you're still getting errors, check:"
    echo "   - Is the server PATH correct?"
    echo "   - Are you running in a virtual environment?"
    echo "   - Check server logs for the exact error message"
else
    echo "❌ Poppler is NOT installed"
    echo ""
    echo "💡 To install poppler:"
    echo "   Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y poppler-utils"
    echo "   CentOS/RHEL:   sudo yum install poppler-utils"
    echo "   macOS:         brew install poppler"
    echo ""
    echo "   After installation, restart your application server"
fi

