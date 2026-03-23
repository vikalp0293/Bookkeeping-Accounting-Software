from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import LoggingMiddleware
from app.core.file_logging import LOG_DIR  # Initialize file logging
from app.api import api_router

app = FastAPI(
    title=settings.APP_NAME,
    description="Automating Data Entry & Bookkeeping API",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging middleware
app.add_middleware(LoggingMiddleware)

# Include API routes
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# QuickBooks Web Connector - must be at root level (not under /api/v1)
# QB Web Connector expects the endpoint at /qbwc
from app.controllers import qb_web_connector_controller
app.include_router(qb_web_connector_controller.router, prefix="/qbwc")
# Note: QB Web Connector Logs are included in api_router (see app/api/__init__.py)

# Documentation endpoints - at root level for easy access
from app.controllers import docs_controller
app.include_router(docs_controller.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Sync Accounting Software API",
        "version": "1.0.0",
        "docs": "/docs",
        "user_guide": "/docs/user-guide",
        "installer_download": "/docs/download/installer",
        "api_docs": "/docs"  # FastAPI auto-generated docs
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}

