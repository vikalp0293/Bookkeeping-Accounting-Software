"""
QuickBooks Transaction Queue Controller
API endpoints for managing the transaction queue
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel

from app.db.base import get_db
from app.dependencies.auth import get_current_user
from app.models.user import User
from app.models.qb_transaction_queue import QBTransactionQueue, QBTransactionStatus
from app.services.qb_queue_service import QBQueueService
from app.services.activity_log_service import ActivityLogService
from app.models.user_activity_log import ActivityActionType
from app.models.workspace import Workspace
from app.services.workspace_access_service import require_workspace_access

router = APIRouter(prefix="/qb-queue", tags=["QuickBooks Queue"])


class QueueTransactionRequest(BaseModel):
    file_id: int
    transaction_data: dict
    transaction_index: Optional[int] = None
    transaction_id: Optional[str] = None
    company_file: Optional[str] = None  # QuickBooks company file path (multi-company desktop)


class CheckUnmappedPayeesRequest(BaseModel):
    file_ids: Optional[List[int]] = None
    transaction_list: Optional[List[dict]] = None  # [{ payee, transaction_type }, ...]


class ApproveTransactionsRequest(BaseModel):
    queue_ids: List[int]


class UpdateStatusRequest(BaseModel):
    queue_id: int
    status: str
    error_message: Optional[str] = None
    response_xml: Optional[str] = None
    qb_transaction_id: Optional[str] = None


class QueueTransactionResponse(BaseModel):
    id: int
    file_id: int
    status: str
    created_at: str
    
    class Config:
        from_attributes = True


@router.post("/check-unmapped-payees")
async def check_unmapped_payees(
    request: CheckUnmappedPayeesRequest,
    workspace_id: int = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check if all withdrawal/check/fee payees have a QuickBooks expense account mapped.
    Used before sync to block and show "Map these payees" when any are unmapped.
    """
    require_workspace_access(db, current_user, workspace_id)
    unmapped, missing_payee_txns = QBQueueService.get_unmapped_payees(
        db=db,
        workspace_id=workspace_id,
        file_ids=request.file_ids,
        transaction_list=request.transaction_list
    )
    return {
        "unmapped_payees": unmapped,
        "missing_payee_transactions": missing_payee_txns,
        "all_mapped": len(unmapped) == 0 and len(missing_payee_txns) == 0
    }


@router.post("/queue", response_model=QueueTransactionResponse)
async def queue_transaction(
    request: QueueTransactionRequest,
    workspace_id: int = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Add a transaction to the queue for QuickBooks sync.
    For withdrawal/check/fee transactions, payee must have qb_expense_account_name set; otherwise returns 400.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        require_workspace_access(db, current_user, workspace_id)
        
        # Verify file exists
        from app.models.file import File
        file = db.query(File).filter(File.id == request.file_id).first()
        if not file:
            logger.error(f"File not found: {request.file_id}")
            raise HTTPException(status_code=404, detail="File not found")
        
        # Resolve payee → expense account for withdrawal/check/fee; block queue if unmapped
        resolved_data, err = QBQueueService.resolve_expense_account_for_transaction(
            db=db,
            workspace_id=workspace_id,
            transaction_data=request.transaction_data
        )
        if err:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": err, "code": "unmapped_payee"}
            )
        
        queue_entry = QBQueueService.queue_transaction(
            db=db,
            workspace_id=workspace_id,
            file_id=request.file_id,
            transaction_data=resolved_data,
            transaction_index=request.transaction_index,
            transaction_id=request.transaction_id,
            company_file=request.company_file
        )
        
        return QueueTransactionResponse(
            id=queue_entry.id,
            file_id=queue_entry.file_id,
            status=queue_entry.status,  # status is now a string, not enum
            created_at=queue_entry.created_at.isoformat()
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error queueing transaction: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/approve")
async def approve_transactions(
    http_request: Request,
    request: ApproveTransactionsRequest,
    workspace_id: int = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Approve transactions for syncing (move to QUEUED status).
    """
    require_workspace_access(db, current_user, workspace_id)
    
    # Verify all queue entries belong to this workspace
    queue_entries = db.query(QBTransactionQueue).filter(
        QBTransactionQueue.id.in_(request.queue_ids),
        QBTransactionQueue.workspace_id == workspace_id
    ).all()
    
    if len(queue_entries) != len(request.queue_ids):
        raise HTTPException(status_code=400, detail="Some queue entries not found or don't belong to workspace")
    
    approved = QBQueueService.approve_transactions(db, request.queue_ids)
    
    # Log activity
    ActivityLogService.log_activity_from_request(
        db=db,
        user_id=current_user.id,
        action_type=ActivityActionType.TRANSACTION_SYNC.value,
        request=http_request,
        resource_type="transaction",
        resource_id=None,
        workspace_id=workspace_id,
        details={"approved_count": len(approved), "queue_ids": request.queue_ids}
    )
    
    return {
        "success": True,
        "approved_count": len(approved),
        "queue_ids": [entry.id for entry in approved]
    }


@router.delete("/reject/{queue_id}")
async def reject_transaction(
    queue_id: int,
    workspace_id: int = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reject a transaction (remove from queue).
    """
    require_workspace_access(db, current_user, workspace_id)
    
    # Verify queue entry belongs to this workspace
    queue_entry = db.query(QBTransactionQueue).filter(
        QBTransactionQueue.id == queue_id,
        QBTransactionQueue.workspace_id == workspace_id
    ).first()
    
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    QBQueueService.reject_transaction(db, queue_id)
    
    return {"success": True, "message": "Transaction rejected"}


@router.get("/list")
async def list_queue(
    workspace_id: int = Query(..., description="Workspace ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List transactions in the queue.
    """
    require_workspace_access(db, current_user, workspace_id)
    
    query = db.query(QBTransactionQueue).filter(
        QBTransactionQueue.workspace_id == workspace_id
    )
    
    if status:
        # Validate status is a valid value
        valid_statuses = ['pending', 'queued', 'syncing', 'synced', 'failed']
        if status.lower() not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}. Must be one of: {valid_statuses}")
        query = query.filter(QBTransactionQueue.status == status.lower())
    
    queue_entries = query.order_by(QBTransactionQueue.created_at.desc()).limit(limit).all()
    
    return {
        "count": len(queue_entries),
        "transactions": [
            {
                "id": entry.id,
                "file_id": entry.file_id,
                "status": entry.status,  # status is now a string, not enum
                "transaction_data": entry.transaction_data,
                "error_message": entry.error_message,
                "sync_attempts": entry.sync_attempts,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "synced_at": entry.synced_at.isoformat() if entry.synced_at else None,
            }
            for entry in queue_entries
        ]
    }


@router.get("/stats")
async def get_queue_stats(
    workspace_id: int = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get queue statistics for a workspace.
    """
    require_workspace_access(db, current_user, workspace_id)
    
    stats = QBQueueService.get_queue_stats(db, workspace_id)
    
    return {
        "workspace_id": workspace_id,
        "stats": stats,
        "total": sum(stats.values())
    }


@router.post("/update-status")
async def update_transaction_status(
    request: UpdateStatusRequest,
    workspace_id: int = Query(..., description="Workspace ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update transaction status (for SDK-based sync).
    Allows desktop app using QuickBooks SDK to update transaction status directly.
    """
    require_workspace_access(db, current_user, workspace_id)
    
    # Verify queue entry belongs to this workspace
    queue_entry = db.query(QBTransactionQueue).filter(
        QBTransactionQueue.id == request.queue_id,
        QBTransactionQueue.workspace_id == workspace_id
    ).first()
    
    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")
    
    # Validate status
    valid_statuses = ['syncing', 'synced', 'failed']
    if request.status not in valid_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status: {request.status}. Must be one of: {valid_statuses}"
        )
    
    # Update status based on request
    if request.status == 'syncing':
        QBQueueService.mark_syncing(db, request.queue_id)
    elif request.status == 'synced':
        QBQueueService.mark_synced(
            db,
            request.queue_id,
            request.response_xml or '',
            request.qb_transaction_id
        )
    elif request.status == 'failed':
        QBQueueService.mark_failed(
            db,
            request.queue_id,
            request.error_message or 'Unknown error'
        )
    
    return {
        "success": True,
        "queue_id": request.queue_id,
        "status": request.status
    }


@router.post("/reset-failed")
async def reset_failed_transactions(
    workspace_id: int = Query(..., description="Workspace ID"),
    max_retries: int = Query(3, ge=1, le=10, description="Maximum retry attempts"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Reset failed transactions back to queued status for retry.
    Only resets transactions that haven't exceeded max_retries.
    """
    require_workspace_access(db, current_user, workspace_id)
    
    reset_count = QBQueueService.reset_failed_transactions(db, workspace_id, max_retries)
    
    return {
        "success": True,
        "reset_count": reset_count,
        "message": f"Reset {reset_count} failed transactions back to queued status"
    }

