"""
Test script to generate IIF file from queued transactions.
This allows testing IIF import in QuickBooks Desktop.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from app.db.base import SessionLocal
from app.models.qb_transaction_queue import QBTransactionQueue
from app.models.workspace import Workspace
from app.services.quickbooks_service import QuickBooksService
from datetime import datetime

def test_iif_export(workspace_id: int = 1, limit: int = 5):
    """
    Generate IIF file from queued transactions for testing.
    
    Args:
        workspace_id: Workspace ID to export transactions from
        limit: Maximum number of transactions to include
    """
    db: Session = SessionLocal()
    
    try:
        # Get workspace to find account name
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not workspace:
            print(f"❌ Workspace {workspace_id} not found")
            return
        
        bank_account = workspace.quickbooks_account_name or "Checking"
        print(f"✓ Using bank account: '{bank_account}'")
        
        # Get queued transactions
        transactions = db.query(QBTransactionQueue).filter(
            QBTransactionQueue.workspace_id == workspace_id,
            QBTransactionQueue.status.in_(['queued', 'failed'])
        ).order_by(QBTransactionQueue.created_at.asc()).limit(limit).all()
        
        if not transactions:
            print(f"❌ No queued transactions found for workspace {workspace_id}")
            return
        
        print(f"✓ Found {len(transactions)} transactions")
        
        # Convert to IIF format
        iif_transactions = []
        for qb_trans in transactions:
            trans_data = qb_trans.transaction_data
            
            # Extract transaction data
            iif_trans = {
                'date': trans_data.get('date'),
                'amount': float(trans_data.get('amount', 0)),
                'payee': trans_data.get('payee', 'Bank Deposits'),
                'memo': trans_data.get('description', trans_data.get('memo', '')),
                'transaction_type': trans_data.get('transaction_type', 'DEPOSIT')
            }
            
            iif_transactions.append(iif_trans)
            print(f"  - Transaction {qb_trans.id}: {iif_trans['transaction_type']} ${iif_trans['amount']:.2f} on {iif_trans['date']}")
        
        # Generate IIF file
        iif_content = QuickBooksService.generate_iif_file(
            transactions=iif_transactions,
            bank_account_name=bank_account,
            income_account_name="Sales"
        )
        
        # Save to file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"test_export_{workspace_id}_{timestamp}.iif"
        filepath = os.path.join(os.path.dirname(__file__), filename)
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(iif_content)
        
        print(f"\n✓ IIF file generated: {filepath}")
        print(f"\n=== IIF File Content ===")
        print(iif_content)
        print(f"\n=== End of IIF Content ===")
        print(f"\n📋 To test in QuickBooks Desktop:")
        print(f"   1. Open QuickBooks Desktop")
        print(f"   2. Go to File → Utilities → Import → IIF Files")
        print(f"   3. Select the file: {filename}")
        print(f"   4. Review the import results")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        db.close()

if __name__ == "__main__":
    workspace_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    
    print(f"Testing IIF export for workspace {workspace_id} (limit: {limit})")
    print("=" * 60)
    test_iif_export(workspace_id, limit)
