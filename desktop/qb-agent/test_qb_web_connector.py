"""
Test QuickBooks Web Connector Connection

QuickBooks Web Connector is the official automated solution for QB Desktop.
It avoids the "Could not start QuickBooks" error that occurs with direct SDK.

This test verifies we can set up QB Web Connector properly.
"""

import sys
import os
import subprocess
import winreg
from pathlib import Path

def check_qbwc_installed():
    """Check if QuickBooks Web Connector is installed"""
    print("Checking if QuickBooks Web Connector is installed...")
    
    # Check registry
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Intuit\QBWebConnector"
        )
        winreg.CloseKey(key)
        print("✓ QuickBooks Web Connector is installed (found in registry)")
        return True
    except (FileNotFoundError, OSError):
        pass
    
    # Check common installation paths
    common_paths = [
        r"C:\Program Files (x86)\Common Files\Intuit\QuickBooks\QBWebConnector\QBWebConnector.exe",
        r"C:\Program Files\Common Files\Intuit\QuickBooks\QBWebConnector\QBWebConnector.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            print(f"✓ QuickBooks Web Connector is installed: {path}")
            return True
    
    print("✗ QuickBooks Web Connector is NOT installed")
    return False

def get_qbwc_path():
    """Get QuickBooks Web Connector executable path"""
    common_paths = [
        r"C:\Program Files (x86)\Common Files\Intuit\QuickBooks\QBWebConnector\QBWebConnector.exe",
        r"C:\Program Files\Common Files\Intuit\QuickBooks\QBWebConnector\QBWebConnector.exe",
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            return path
    
    return None

def create_test_service():
    """Create a simple test SOAP service for QB Web Connector"""
    print("\nCreating test service script...")
    
    service_code = '''"""
Simple QuickBooks Web Connector Test Service
Run this service, then configure QB Web Connector to connect to it.
"""

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse
import uvicorn
import xml.etree.ElementTree as ET

app = FastAPI()

@app.post("/qbwc")
async def qbwc_endpoint(request: Request):
    """QB Web Connector SOAP endpoint"""
    body = await request.body()
    content_type = request.headers.get("content-type", "")
    
    if "text/xml" in content_type or "application/soap+xml" in content_type:
        # Handle SOAP request
        try:
            xml_str = body.decode('utf-8')
            root = ET.fromstring(xml_str)
            
            # Find SOAP body
            body_elem = root.find('.//{http://schemas.xmlsoap.org/soap/envelope/}Body')
            if body_elem is None:
                return soap_fault("Invalid SOAP request")
            
            # Handle different methods
            for child in body_elem:
                method_name = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                
                if method_name == "authenticate":
                    return handle_authenticate()
                elif method_name == "sendRequestXML":
                    return handle_send_request()
                elif method_name == "receiveResponseXML":
                    return handle_receive_response()
                elif method_name == "connectionError":
                    return handle_connection_error()
                elif method_name == "getLastError":
                    return handle_get_last_error()
                elif method_name == "closeConnection":
                    return handle_close_connection()
            
            return soap_fault("Unknown method")
        except Exception as e:
            return soap_fault(str(e))
    else:
        return PlainTextResponse("QB Web Connector Service is running")

@app.get("/qbwc")
async def qbwc_get():
    """Health check"""
    return PlainTextResponse("QB Web Connector Service is running")

def handle_authenticate():
    """Handle authentication"""
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<authenticateResponse>
<authenticateResult>
<string>test-ticket</string>
<string>none</string>
</authenticateResult>
</authenticateResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")

def handle_send_request():
    """Handle sendRequestXML - return empty (no pending requests)"""
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<sendRequestXMLResponse>
<sendRequestXMLResult></sendRequestXMLResult>
</sendRequestXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")

def handle_receive_response():
    """Handle receiveResponseXML"""
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<receiveResponseXMLResponse>
<receiveResponseXMLResult>0</receiveResponseXMLResult>
</receiveResponseXMLResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")

def handle_connection_error():
    """Handle connection errors"""
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<connectionErrorResponse>
<connectionErrorResult>done</connectionErrorResult>
</connectionErrorResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")

def handle_get_last_error():
    """Handle getLastError"""
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<getLastErrorResponse>
<getLastErrorResult></getLastErrorResult>
</getLastErrorResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")

def handle_close_connection():
    """Handle closeConnection"""
    response = """<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<closeConnectionResponse>
<closeConnectionResult>OK</closeConnectionResult>
</closeConnectionResponse>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml")

def soap_fault(message):
    """Return SOAP fault"""
    response = f"""<?xml version="1.0"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/">
<SOAP-ENV:Body>
<SOAP-ENV:Fault>
<faultcode>SOAP-ENV:Server</faultcode>
<faultstring>{message}</faultstring>
</SOAP-ENV:Fault>
</SOAP-ENV:Body>
</SOAP-ENV:Envelope>"""
    return PlainTextResponse(response, media_type="text/xml", status_code=500)

if __name__ == "__main__":
    print("Starting QuickBooks Web Connector Test Service...")
    print("Service URL: http://localhost:8080/qbwc")
    print("\\nTo test:")
    print("1. Keep this service running")
    print("2. Install QuickBooks Web Connector (if not installed)")
    print("3. Create a .qwc file pointing to this service")
    print("4. Add it to QB Web Connector")
    uvicorn.run(app, host="0.0.0.0", port=8080)
'''
    
    service_file = Path(__file__).parent / "test_service.py"
    with open(service_file, 'w') as f:
        f.write(service_code)
    
    print(f"✓ Created: {service_file}")
    return service_file

def create_qwc_file():
    """Create a .qwc configuration file for QB Web Connector"""
    print("\nCreating .qwc configuration file...")
    
    import uuid
    file_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    
    qwc_content = f"""<?xml version="1.0"?>
<QBWCXML>
    <AppName>Sync Accounting Test</AppName>
    <AppID>sync-accounting-test</AppID>
    <AppURL>http://localhost:8080/qbwc</AppURL>
    <AppSupport>http://localhost:8080</AppSupport>
    <UserName>admin</UserName>
    <OwnerID>{{{owner_id}}}</OwnerID>
    <FileID>{{{file_id}}}</FileID>
    <QBType>QBFS</QBType>
    <Style>Document</Style>
    <AppDesc>Sync Accounting - Test service for QuickBooks Desktop integration</AppDesc>
    <Scheduler>
        <RunEveryNMinutes>5</RunEveryNMinutes>
    </Scheduler>
</QBWCXML>"""
    
    qwc_file = Path(__file__).parent / "sync_accounting_test.qwc"
    with open(qwc_file, 'w', encoding='utf-8') as f:
        f.write(qwc_content)
    
    print(f"✓ Created: {qwc_file}")
    return qwc_file

def main():
    """Main test function"""
    print("=" * 60)
    print("QuickBooks Web Connector Setup Test")
    print("=" * 60)
    print()
    
    # Check if QB Web Connector is installed
    qbwc_installed = check_qbwc_installed()
    
    if not qbwc_installed:
        print("\n" + "=" * 60)
        print("QuickBooks Web Connector is NOT installed")
        print("=" * 60)
        print("\nTo install:")
        print("1. Download from: https://developer.intuit.com/app/developer/qbdesktop/docs/get-started/install-quickbooks-web-connector")
        print("2. Run the installer")
        print("3. Run this test again")
        print()
        return False
    
    print()
    
    # Check if FastAPI/uvicorn are available
    try:
        import fastapi
        import uvicorn
        print("✓ FastAPI and uvicorn are installed")
    except ImportError:
        print("✗ FastAPI/uvicorn not installed")
        print("  Install with: pip install fastapi uvicorn")
        print()
        response = input("Install now? (y/n): ").strip().lower()
        if response == 'y':
            subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn"])
            print("✓ Installed")
        else:
            return False
    
    print()
    
    # Create test service
    service_file = create_test_service()
    
    # Create QWC file
    qwc_file = create_qwc_file()
    
    print()
    print("=" * 60)
    print("Setup Complete!")
    print("=" * 60)
    print()
    print("Next steps:")
    print()
    print("1. Start the test service:")
    print(f"   python {service_file.name}")
    print()
    print("2. In another terminal, configure QB Web Connector:")
    print(f"   - Double-click: {qwc_file.name}")
    print("   - Or open QB Web Connector and click 'Add an application'")
    print("   - Browse to the .qwc file")
    print("   - Enter password: admin")
    print("   - Click 'Update'")
    print()
    print("3. Check QB Web Connector status:")
    print("   - Should show 'Connected'")
    print("   - Service will be polled every 5 minutes")
    print()
    print("=" * 60)
    print("✅ QB Web Connector setup files created!")
    print("=" * 60)
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

