#!/usr/bin/env python3
"""
Check if poppler is installed and available for pdf2image.
"""
import sys

def check_poppler():
    """Check if poppler utilities are installed."""
    try:
        import pdf2image
        from pdf2image.exceptions import PDFInfoNotInstalledError
        
        # Try to get PDF info (this will fail if poppler is not installed)
        try:
            from pdf2image import pdfinfo_from_path
            import tempfile
            import os
            
            # Create a dummy test
            # We can't test without a real PDF, so we'll just check if the module loads
            print("✅ pdf2image module is installed")
            
            # Try to import poppler utilities
            try:
                from pdf2image import convert_from_path
                print("✅ pdf2image.convert_from_path is available")
            except ImportError as e:
                print(f"❌ Error importing convert_from_path: {e}")
                return False
            
            # Check if poppler is in PATH by trying to run pdftoppm
            import subprocess
            try:
                result = subprocess.run(
                    ['pdftoppm', '-h'],
                    capture_output=True,
                    timeout=5
                )
                if result.returncode == 0 or result.returncode == 1:  # -h usually returns 1
                    print("✅ poppler utilities (pdftoppm) found in PATH")
                    return True
                else:
                    print("❌ pdftoppm returned error code:", result.returncode)
                    return False
            except FileNotFoundError:
                print("❌ poppler utilities (pdftoppm) not found in PATH")
                print("\n💡 To install poppler:")
                print("  - Ubuntu/Debian: sudo apt-get install poppler-utils")
                print("  - macOS: brew install poppler")
                print("  - Windows: Download from https://github.com/oschwartz10612/poppler-windows/releases")
                return False
            except subprocess.TimeoutExpired:
                print("⚠️  pdftoppm check timed out")
                return False
            except Exception as e:
                print(f"❌ Error checking poppler: {e}")
                return False
                
        except Exception as e:
            print(f"❌ Error checking pdf2image: {e}")
            return False
            
    except ImportError:
        print("❌ pdf2image module is not installed")
        print("💡 Install with: pip install pdf2image")
        return False

if __name__ == "__main__":
    print("🔍 Checking poppler installation...\n")
    success = check_poppler()
    print()
    if success:
        print("✅ Poppler is properly installed and configured!")
        sys.exit(0)
    else:
        print("❌ Poppler is not properly installed or configured.")
        sys.exit(1)

