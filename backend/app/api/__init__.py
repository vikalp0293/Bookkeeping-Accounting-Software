from fastapi import APIRouter
from app.controllers import (
    auth_controller, file_controller, extraction_controller, dashboard_controller,
    export_controller, workspace_controller,
    review_queue_controller, payee_controller,
    vendor_controller, qbwc_logs_controller, qb_queue_controller,
    activity_log_controller, ocr_logs_controller,
    user_management_controller
)

api_router = APIRouter()

api_router.include_router(auth_controller.router)
api_router.include_router(file_controller.router)
api_router.include_router(extraction_controller.router)
api_router.include_router(dashboard_controller.router)
api_router.include_router(export_controller.router)
api_router.include_router(workspace_controller.router)
api_router.include_router(review_queue_controller.router)
api_router.include_router(payee_controller.router)
api_router.include_router(vendor_controller.router)
api_router.include_router(activity_log_controller.router)
api_router.include_router(ocr_logs_controller.router)
# User management (RBAC)
api_router.include_router(user_management_controller.router)
# QB Web Connector Logs - under API for authenticated access
api_router.include_router(qbwc_logs_controller.router, prefix="/qbwc")
# QB Transaction Queue - under API for authenticated access
api_router.include_router(qb_queue_controller.router)
# Note: QB Web Connector SOAP endpoints are in main.py at root level (/qbwc)

