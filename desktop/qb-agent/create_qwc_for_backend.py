"""
Create QuickBooks Web Connector .qwc file pointing to backend API

This creates a .qwc file that points to your hosted backend API.
"""

import uuid
from pathlib import Path
from datetime import datetime

def create_qwc_file():
    """Create .qwc file for backend API"""
    
    file_id = str(uuid.uuid4())
    owner_id = str(uuid.uuid4())
    
    # Backend API URL
    backend_url = "https://dev-sync-api.kylientlabs.com"
    
    qwc_content = f"""<?xml version="1.0"?>
<QBWCXML>
    <AppName>Sync Accounting</AppName>
    <AppID>sync-accounting</AppID>
    <AppURL>{backend_url}/qbwc</AppURL>
    <AppSupport>{backend_url}</AppSupport>
    <UserName>admin</UserName>
    <OwnerID>{{{owner_id}}}</OwnerID>
    <FileID>{{{file_id}}}</FileID>
    <QBType>QBFS</QBType>
    <Style>Document</Style>
    <AppDescription>Sync Accounting - Automated bank statement and check data sync to QuickBooks Desktop</AppDescription>
    <Scheduler>
        <RunEveryNMinutes>5</RunEveryNMinutes>
    </Scheduler>
</QBWCXML>"""
    
    qwc_file = Path(__file__).parent / "sync_accounting.qwc"
    with open(qwc_file, 'w', encoding='utf-8') as f:
        f.write(qwc_content)
    
    print("=" * 60)
    print("QuickBooks Web Connector Configuration File Created")
    print("=" * 60)
    print()
    print(f"File: {qwc_file}")
    print(f"Service URL: {backend_url}/qbwc")
    print()
    print("Next steps:")
    print("1. Ensure your backend API is deployed and accessible")
    print("2. Test the WSDL endpoint:")
    print(f"   {backend_url}/qbwc?wsdl")
    print("3. Double-click sync_accounting.qwc to add to QB Web Connector")
    print("4. Enter password: admin")
    print("5. Click 'Update'")
    print()
    print("=" * 60)
    
    return qwc_file

if __name__ == "__main__":
    create_qwc_file()

