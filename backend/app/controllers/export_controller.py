from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from typing import Optional
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.workspace import Workspace
from app.services.extraction_service import ExtractionService
from app.services.quickbooks_service import QuickBooksService
from app.services.qb_queue_service import QBQueueService
from app.services.activity_log_service import ActivityLogService
from app.models.user_activity_log import ActivityActionType
from datetime import datetime
import os
import tempfile

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/quickbooks/{file_id}")
async def export_to_quickbooks(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export extracted data to QuickBooks .IIF format.
    
    Downloads a .IIF file that can be imported directly into QuickBooks.
    """
    try:
        # Get extraction data
        extracted_data = ExtractionService.get_extraction_by_file_id(db, file_id)
        
        if extracted_data.extraction_status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Extraction not completed yet"
            )
        
        # Convert to transactions
        transactions = QuickBooksService.convert_extracted_data_to_transactions(
            extracted_data.processed_data or extracted_data.raw_data
        )
        
        if not transactions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No transactions found in extracted data"
            )
        
        # Generate IIF file
        filepath = QuickBooksService.export_to_iif_file(transactions)
        
        if not os.path.exists(filepath):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to generate export file"
            )
        
        filename = os.path.basename(filepath)
        
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )


@router.get("/quickbooks/queued/{workspace_id}")
async def export_queued_transactions_to_iif(
    request: Request,
    workspace_id: int,
    file_id: Optional[int] = Query(None, description="Optional: File ID to export transactions from. If not provided, exports all files in workspace."),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum number of transactions to export"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Export extracted transactions from workspace to QuickBooks .IIF format.
    
    This endpoint exports transactions as an IIF file that can be manually imported 
    into QuickBooks Desktop. Uses the workspace's configured QuickBooks account name.
    
    Args:
        workspace_id: Workspace ID to export transactions from
        file_id: Optional file ID. If provided, only exports transactions from that file.
                 If not provided, exports all transactions from all files in the workspace.
        limit: Maximum number of transactions to include (default: 1000, max: 10000)
    
    Returns:
        IIF file download
    """
    try:
        # Verify workspace exists and user has access
        workspace = db.query(Workspace).filter(Workspace.id == workspace_id).first()
        if not workspace:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workspace not found"
            )
        
        # Check if user has access to this workspace
        if workspace.owner_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to this workspace"
            )
        
        # Get bank account name from workspace
        bank_account = workspace.quickbooks_account_name
        if not bank_account:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QuickBooks account name not configured for this workspace. Please set it in workspace settings."
            )
        
        # Get files in workspace with completed extractions
        from app.models.file import File
        from app.models.extracted_data import ExtractedData
        
        # If file_id is provided, only export from that specific file
        if file_id:
            files = db.query(File).filter(
                File.id == file_id,
                File.workspace_id == workspace_id,
                File.status == 'completed'
            ).all()
            
            if not files:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"File {file_id} not found or extraction not completed."
                )
        else:
            # Export from all files in workspace
            files = db.query(File).filter(
                File.workspace_id == workspace_id,
                File.status == 'completed'
            ).all()
            
            if not files:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No completed extractions found for this workspace."
                )
        
        # Collect all transactions from all extracted files
        iif_transactions = []
        files_processed = 0
        
        for file in files:
            # Get extraction data for this file
            extracted_data = db.query(ExtractedData).filter(
                ExtractedData.file_id == file.id,
                ExtractedData.extraction_status == 'completed'
            ).first()
            
            if not extracted_data:
                continue
            
            # Get transactions from processed_data or raw_data
            transactions_data = extracted_data.processed_data or extracted_data.raw_data
            
            if not transactions_data:
                continue
            
            # Handle different data structures
            transactions = []
            if isinstance(transactions_data, dict):
                if 'transactions' in transactions_data:
                    transactions = transactions_data['transactions']
                elif 'raw_data' in transactions_data and isinstance(transactions_data['raw_data'], dict):
                    # Single transaction in raw_data
                    transactions = [transactions_data['raw_data']]
                elif transactions_data.get('date') or transactions_data.get('amount'):
                    # Single transaction at root level
                    transactions = [transactions_data]
            elif isinstance(transactions_data, list):
                transactions = transactions_data
            
            # Convert to IIF format
            for trans in transactions:
                if len(iif_transactions) >= limit:
                    break
                
                # Extract transaction data with proper None handling
                trans_date = trans.get('date')
                trans_amount_raw = trans.get('amount')
                
                # Handle None or invalid amount
                if trans_amount_raw is None:
                    continue
                try:
                    trans_amount = float(trans_amount_raw)
                except (ValueError, TypeError):
                    continue
                
                # Skip if amount is zero
                if trans_amount == 0:
                    continue
                
                trans_payee = trans.get('payee', trans.get('vendor', 'Bank Deposits'))
                trans_memo = trans.get('description', trans.get('memo', ''))
                trans_type = trans.get('transaction_type', 'DEPOSIT' if trans_amount >= 0 else 'WITHDRAWAL')
                
                # Skip if missing essential data
                if not trans_date:
                    continue
                
                # Filter out balance activity entries and invalid transactions using shared utility
                from app.utils.transaction_filter import is_balance_activity_entry
                
                # Get statement period for filtering
                stmt_start = None
                stmt_end = None
                if extracted_data.processed_data:
                    stmt_start = extracted_data.processed_data.get('statement_period_start')
                    stmt_end = extracted_data.processed_data.get('statement_period_end')
                
                # Skip if this is a balance activity entry
                if is_balance_activity_entry(trans, stmt_start, stmt_end):
                    continue
                
                iif_trans = {
                    'date': trans_date,
                    'amount': trans_amount,
                    'payee': trans_payee,
                    'memo': trans_memo,
                    'transaction_type': trans_type
                }
                
                iif_transactions.append(iif_trans)
            
            files_processed += 1
            if len(iif_transactions) >= limit:
                break
        
        if not iif_transactions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No transactions found in {files_processed} extracted file(s) for this workspace."
            )
        
        # Generate IIF content
        iif_content = QuickBooksService.generate_iif_file(
            transactions=iif_transactions,
            bank_account_name=bank_account,
            income_account_name="Sales"
        )
        
        # Create temporary file
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"quickbooks_export_{workspace_id}_{timestamp}.iif"
        
        # Use tempfile for cross-platform compatibility
        with tempfile.NamedTemporaryFile(mode='w', suffix='.iif', delete=False, encoding='utf-8') as tmp_file:
            tmp_file.write(iif_content)
            filepath = tmp_file.name
        
        # Log activity
        ActivityLogService.log_activity_from_request(
            db=db,
            user_id=current_user.id,
            action_type=ActivityActionType.EXPORT_DATA.value,
            request=request,
            resource_type="workspace",
            resource_id=workspace_id,
            workspace_id=workspace_id,
            details={
                "file_id": file_id,
                "transaction_count": len(iif_transactions),
                "export_type": "iif"
            }
        )
        
        return FileResponse(
            path=filepath,
            filename=filename,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Export failed: {str(e)}"
        )

