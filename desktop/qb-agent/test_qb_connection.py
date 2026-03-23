"""
Test QuickBooks Desktop Pro 2018 Connection

This script tests if we can connect to QuickBooks Desktop Pro 2018 Release 1.
Run this on Windows with QuickBooks Desktop installed and running.
"""

import sys
import os

def test_qb_connection():
    """Test connection to QuickBooks Desktop"""
    
    print("=" * 60)
    print("QuickBooks Desktop Pro 2018 Connection Test")
    print("=" * 60)
    print()
    
    # Step 1: Check if we're on Windows
    if sys.platform != 'win32':
        print("❌ ERROR: This test requires Windows")
        print("   QuickBooks Desktop SDK only works on Windows")
        return False
    
    print("✓ Running on Windows")
    print()
    
    # Step 2: Check if pywin32 is installed
    try:
        import win32com.client
        print("✓ pywin32 is installed")
    except ImportError:
        print("❌ ERROR: pywin32 is not installed")
        print("   Install with: pip install pywin32")
        return False
    
    print()
    
    # Step 3: Check if QuickBooks is running
    print("Checking if QuickBooks Desktop is running...")
    qb_running = False
    try:
        import psutil
        for proc in psutil.process_iter(['pid', 'name']):
            name = proc.info['name'].lower()
            if 'qbw' in name or 'quickbooks' in name:
                print(f"✓ QuickBooks is running: {proc.info['name']} (PID: {proc.info['pid']})")
                qb_running = True
                break
    except ImportError:
        print("⚠️  psutil not installed - cannot check if QB is running")
        print("   Install with: pip install psutil")
        print("   Please ensure QuickBooks Desktop is open before continuing")
        response = input("   Is QuickBooks Desktop open? (y/n): ").strip().lower()
        qb_running = (response == 'y')
    except Exception as e:
        print(f"⚠️  Could not check processes: {e}")
        response = input("   Is QuickBooks Desktop open? (y/n): ").strip().lower()
        qb_running = (response == 'y')
    
    if not qb_running:
        print()
        print("❌ ERROR: QuickBooks Desktop must be running")
        print("   Please:")
        print("   1. Open QuickBooks Desktop Pro 2018")
        print("   2. Open your company file")
        print("   3. Run this test again")
        return False
    
    print()
    
    # Step 4: Try to create COM object
    print("Attempting to connect to QuickBooks SDK...")
    com_objects_to_try = [
        "QBXMLRP2.RequestProcessor.2",
        "QBXMLRP2.RequestProcessor",
        "QBXMLRP.RequestProcessor",
    ]
    
    qb = None
    com_object_used = None
    
    for com_obj in com_objects_to_try:
        try:
            print(f"   Trying: {com_obj}...")
            qb = win32com.client.Dispatch(com_obj)
            com_object_used = com_obj
            print(f"✓ Successfully created COM object: {com_obj}")
            break
        except Exception as e:
            print(f"   ✗ Failed: {e}")
            continue
    
    if qb is None:
        print()
        print("❌ ERROR: Could not create QuickBooks COM object")
        print("   Possible causes:")
        print("   1. QuickBooks Desktop SDK not installed")
        print("   2. QuickBooks Desktop not properly installed")
        print("   3. Wrong QuickBooks version")
        return False
    
    print()
    
    # Step 5: Try to open connection
    print("Opening connection to QuickBooks...")
    try:
        ticket = qb.OpenConnection("", "Sync Accounting Test")
        print(f"✓ Connection opened (ticket: {ticket})")
    except Exception as e:
        print(f"❌ ERROR: Failed to open connection: {e}")
        return False
    
    print()
    
    # Step 6: Get company file path
    print("Please provide your QuickBooks company file:")
    company_file = input("   Enter full path to .QBW file: ").strip()
    
    if not company_file:
        print("❌ ERROR: No company file provided")
        try:
            qb.CloseConnection("", ticket)
        except:
            pass
        return False
    
    if not os.path.exists(company_file):
        print(f"❌ ERROR: Company file not found: {company_file}")
        try:
            qb.CloseConnection("", ticket)
        except:
            pass
        return False
    
    if not company_file.lower().endswith('.qbw'):
        print("⚠️  WARNING: File doesn't have .qbw extension")
    
    print(f"✓ Company file found: {company_file}")
    print()
    
    # Step 7: Important note for QB 2018
    print("⚠️  IMPORTANT for QuickBooks Desktop Pro 2018:")
    print("   The company file must be OPEN in QuickBooks Desktop!")
    print()
    print("   Please ensure:")
    print("   1. QuickBooks Desktop is open")
    print("   2. Your company file is loaded in QuickBooks")
    print("   3. The file is not locked by another user")
    print()
    input("   Press Enter when company file is open in QuickBooks...")
    print()
    
    # Step 8: Try to begin session
    print("Attempting to start session with QuickBooks...")
    QB_OM_SINGLE_USER = 0  # Single user mode
    
    try:
        session_ticket = qb.BeginSession(company_file, QB_OM_SINGLE_USER)
        print(f"✓ Session started (session ticket: {session_ticket})")
    except Exception as e:
        error_msg = str(e)
        print(f"❌ ERROR: Failed to start session: {error_msg}")
        print()
        
        if "Could not start QuickBooks" in error_msg or "-2147220472" in error_msg:
            print("💡 TROUBLESHOOTING:")
            print("   This error often occurs with QB 2018. Try:")
            print("   1. Ensure company file is OPEN in QuickBooks Desktop")
            print("   2. Close and reopen QuickBooks Desktop")
            print("   3. Try running this script as Administrator")
            print("   4. Check Windows Event Viewer for QuickBooks errors")
            print()
            print("   Alternative: Use QuickBooks Web Connector instead of direct SDK")
        
        try:
            qb.CloseConnection("", ticket)
        except:
            pass
        return False
    
    print()
    
    # Step 9: Try a simple query
    print("Testing query to QuickBooks...")
    try:
        request = """<?xml version="1.0"?>
<?qbxml version="13.0"?>
<QBXML>
    <QBXMLMsgsRq onError="stopOnError">
        <CompanyQueryRq requestID="1">
        </CompanyQueryRq>
    </QBXMLMsgsRq>
</QBXML>"""
        
        # Log request XML for debugging (writes last_qb_request.xml)
        try:
            import qb_request_logger
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            req_path = qb_request_logger.log_qb_request(request, log_dir)
            if req_path:
                print(f"   Request XML written to: {req_path}")
        except Exception as e:
            print(f"   (Could not write request log: {e})")
        
        response = qb.ProcessRequest(session_ticket, request)
        
        # Log response XML for debugging (writes last_qb_response.xml)
        try:
            import qb_request_logger
            log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
            resp_path = qb_request_logger.log_qb_response(response, log_dir)
            if resp_path:
                print(f"   Response XML written to: {resp_path}")
        except Exception as e:
            print(f"   (Could not write response log: {e})")
        
        print("✓ Successfully queried QuickBooks!")
        print(f"   Response preview: {response[:200]}...")
    except Exception as e:
        print(f"❌ ERROR: Query failed: {e}")
        try:
            qb.EndSession(session_ticket)
            qb.CloseConnection("", ticket)
        except:
            pass
        return False
    
    print()
    
    # Step 10: Clean up
    print("Cleaning up...")
    try:
        qb.EndSession(session_ticket)
        print("✓ Session ended")
    except Exception as e:
        print(f"⚠️  Warning: Failed to end session: {e}")
    
    try:
        qb.CloseConnection("", ticket)
        print("✓ Connection closed")
    except Exception as e:
        print(f"⚠️  Warning: Failed to close connection: {e}")
    
    print()
    print("=" * 60)
    print("✅ TEST PASSED: Successfully connected to QuickBooks!")
    print("=" * 60)
    print()
    print("Summary:")
    print(f"  - COM Object: {com_object_used}")
    print(f"  - Company File: {company_file}")
    print(f"  - Connection: ✓ Working")
    print()
    print("Next steps:")
    print("  1. We can now build the sync functionality")
    print("  2. We can create transactions in QuickBooks")
    print("  3. We can query account information")
    
    return True


if __name__ == "__main__":
    try:
        success = test_qb_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

