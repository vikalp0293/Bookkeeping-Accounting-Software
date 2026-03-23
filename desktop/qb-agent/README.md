# QuickBooks Desktop Integration

Desktop application to sync extracted bank statement and check data to QuickBooks Desktop Pro 2018 Release 1.

## Quick Start

### Prerequisites

1. **Windows 10/11** (required - QB SDK is Windows-only)
2. **Python 3.8+**
3. **QuickBooks Desktop Pro 2018 Release 1** installed and activated
4. **QuickBooks company file** (.QBW) for testing

### QuickBooks company file setup (required for sync)

- **Payments (checks/withdrawals):** Create a vendor named **Bank Charges** in QuickBooks (Vendors → Add Vendor → Name: Bank Charges). If this vendor is missing, QuickBooks may return "error parsing the provided XML text stream".
- **Deposits:** Use **DepositAdd** (direct deposit); no Customer or Item required. Ensure at least one Income or Other Income account exists (e.g. Sales, Interest Income) in Chart of Accounts.

### Installation

```powershell
cd desktop\qb-agent
pip install -r requirements.txt
```

### Test Connection

We have two methods to test QuickBooks connection:

#### Method 1: Direct SDK Test (may fail with QB 2018)

```powershell
python test_qb_connection.py
```

**Before running:**
1. Open QuickBooks Desktop Pro 2018
2. Open your company file in QuickBooks
3. Keep QuickBooks open while running the test

**Note:** This test may fail with "Could not start QuickBooks" error on QB 2018. This is a known issue with the direct SDK.

#### Method 2: QuickBooks Web Connector (Recommended for QB 2018)

```powershell
python test_qb_web_connector.py
```

This will:
1. Check if QB Web Connector is installed
2. Create a test service
3. Create a .qwc configuration file

**Then:**
1. Start the test service: `python test_service.py`
2. Double-click `sync_accounting_test.qwc` to add to QB Web Connector
3. Enter password: `admin`
4. Click "Update" - should show "Connected"

**QB Web Connector avoids the SDK "Could not start QuickBooks" error.**

## Next Steps

Once connection test passes:
1. Build folder monitoring functionality
2. Integrate with backend extraction API
3. Create transaction sync to QuickBooks
4. Add user interface (optional)

## Project Structure

```
desktop/qb-agent/
├── qbxml_generator.py            # QB XML generator for SDK app (CheckAdd/DepositAdd, YYYY-MM-DD, AccountRef)
├── qb_request_logger.py          # QB XML request/response logger (debugging)
├── sample_xml/                   # Working sample XMLs (qbXML 13.0, YYYY-MM-DD)
├── test_qb_connection.py         # Test direct SDK connection
├── test_qb_web_connector.py      # Test QB Web Connector (RECOMMENDED)
├── test_service.py                # Test service (created by test_qb_web_connector.py)
├── sync_accounting_test.qwc       # QB Web Connector config (created by test)
├── requirements.txt               # Python dependencies
└── README.md                     # This file
```

## SDK app: qbXML generation (qbxml_generator.py)

For the **SDK app** (desktop sync that talks to QuickBooks via SDK/ProcessRequest), use `qbxml_generator.py` so sync XML matches the working sample XMLs and the backend:

- **TxnDate:** YYYY-MM-DD (QB rejects MM/DD/YYYY with statusCode 3020)
- **CheckAdd:** `AccountRef` for bank (not BankAccountRef); order: AccountRef → PayeeEntityRef → RefNumber → TxnDate → ExpenseLineAdd
- **DepositAdd:** DepositToAccountRef → TxnDate (YYYY-MM-DD) → DepositLineAdd
- **Declaration:** `<?xml version="1.0" ?>` and `<?qbxml version="13.0"?>`

**Usage:** Copy `qbxml_generator.py` into the SDK app’s Python folder (e.g. `resources/python/`). When building XML for a transaction, call:

```python
from qbxml_generator import generate_qbxml_for_single_transaction

qbxml = generate_qbxml_for_single_transaction(
    transaction=trans_dict,
    request_id="trans-123",
    workspace_account_name="kylient",  # QB bank account name
)
# Then: qb.ProcessRequest(session_ticket, qbxml)
```

Transaction dict must include: `transaction_type` (WITHDRAWAL/CHECK/FEE or DEPOSIT), `date`, `amount`, and optionally `description`, `memo`, `reference_number`, `_queue_id`. Ensure the "Bank Charges" vendor and an expense account (e.g. "Miscellaneous Expense") exist in QuickBooks for checks; "Sales" or "Other Income: Interest Income" for deposits.

## QB XML debugging (last_qb_request.xml / last_qb_response.xml)

When testing or syncing, the exact qbXML sent to and returned from QuickBooks can be written to files for debugging:

- **last_qb_request.xml** – exact XML sent to QuickBooks
- **last_qb_response.xml** – exact XML returned (helps diagnose "error parsing the provided XML" etc.)

**test_qb_connection.py** writes these into `desktop/qb-agent/logs/` when you run the direct SDK test.

**Sync service (desktop app):** Copy `qb_request_logger.py` into the sync service Python folder (e.g. `resources/python/`) and in `qb_sdk_service.py` (or equivalent) call `log_qb_request(qbxml, log_dir)` before `ProcessRequest` and `log_qb_response(response, log_dir)` after. Use the same `log_dir` as your sync service logs (e.g. `LOG_DIR`). See docstring in `qb_request_logger.py` for usage.

## Connection Status

✅ **Direct SDK**: Connection works but `BeginSession` fails (known QB 2018 issue)  
✅ **QB Web Connector**: Recommended solution - avoids SDK issues

