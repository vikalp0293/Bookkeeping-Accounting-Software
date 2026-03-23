#!/usr/bin/env python3
"""
Analyze sample PDF files to understand their structure.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import PDF libraries
try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    print("⚠️  PyPDF2 not installed. Install with: pip install PyPDF2")

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False
    print("⚠️  pdfplumber not installed. Install with: pip install pdfplumber")

def analyze_pdf_pypdf2(filepath):
    """Analyze PDF using PyPDF2."""
    try:
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            num_pages = len(pdf_reader.pages)
            print(f"   Pages: {num_pages}")
            
            # Extract text from first page
            if num_pages > 0:
                first_page = pdf_reader.pages[0]
                text = first_page.extract_text()
                print(f"   First page text length: {len(text)} characters")
                if text:
                    lines = text.split('\n')[:10]  # First 10 lines
                    print("   First few lines:")
                    for i, line in enumerate(lines[:5], 1):
                        if line.strip():
                            print(f"      {i}. {line.strip()[:80]}")
    except Exception as e:
        print(f"   Error: {e}")

def analyze_pdf_pdfplumber(filepath):
    """Analyze PDF using pdfplumber."""
    try:
        with pdfplumber.open(filepath) as pdf:
            num_pages = len(pdf.pages)
            print(f"   Pages: {num_pages}")
            
            # Extract text from first page
            if num_pages > 0:
                first_page = pdf.pages[0]
                text = first_page.extract_text()
                print(f"   First page text length: {len(text)} characters")
                
                # Try to extract tables
                tables = first_page.extract_tables()
                if tables:
                    print(f"   Found {len(tables)} table(s) on first page")
                
                if text:
                    lines = text.split('\n')[:10]
                    print("   First few lines:")
                    for i, line in enumerate(lines[:5], 1):
                        if line.strip():
                            print(f"      {i}. {line.strip()[:80]}")
    except Exception as e:
        print(f"   Error: {e}")

def main():
    samples_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'samples')
    
    if not os.path.exists(samples_dir):
        print(f"❌ Samples directory not found: {samples_dir}")
        return
    
    pdf_files = [f for f in os.listdir(samples_dir) if f.endswith('.pdf')]
    
    if not pdf_files:
        print("❌ No PDF files found in samples directory")
        return
    
    print(f"📄 Found {len(pdf_files)} PDF file(s) in samples directory\n")
    
    for pdf_file in sorted(pdf_files):
        filepath = os.path.join(samples_dir, pdf_file)
        file_size = os.path.getsize(filepath) / 1024  # KB
        print(f"📋 {pdf_file} ({file_size:.1f} KB)")
        
        if HAS_PDFPLUMBER:
            analyze_pdf_pdfplumber(filepath)
        elif HAS_PYPDF2:
            analyze_pdf_pypdf2(filepath)
        else:
            print("   ⚠️  No PDF library available for analysis")
        
        print()

if __name__ == '__main__':
    main()

