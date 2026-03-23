"""
Sync Runner
Main entry point for Python sync service
Called from Electron main process
"""

import os
import sys
import logging
from pathlib import Path

# Add current directory to Python path to ensure imports work
# This is important when running from packaged Electron app
current_dir = Path(__file__).parent
if str(current_dir) not in sys.path:
    sys.path.insert(0, str(current_dir))

# Setup logging: use LOG_DIR from Electron (user data) when set; else dev path or temp (Program Files is not writable)
_log_dir = os.environ.get('LOG_DIR')
if _log_dir:
    log_dir = Path(_log_dir)
else:
    if getattr(sys, 'frozen', False):
        import tempfile
        log_dir = Path(tempfile.gettempdir()) / 'qb-accounting' / 'logs'
    else:
        log_dir = Path(__file__).parent.parent / 'logs'

try:
    log_dir.mkdir(parents=True, exist_ok=True)
except PermissionError:
    import tempfile
    log_dir = Path(tempfile.gettempdir()) / 'qb-accounting' / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_dir / 'sync_service.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("QB Accounting SDK - Sync Service")
    logger.info("=" * 60)
    
    # Get configuration from environment
    backend_url = os.getenv('BACKEND_URL', 'https://dev-sync-api.kylientlabs.com')
    api_token = os.getenv('API_TOKEN', '')
    workspace_id = os.getenv('WORKSPACE_ID', '')
    company_file = os.getenv('COMPANY_FILE', '')
    workspace_account_name = os.getenv('WORKSPACE_ACCOUNT_NAME', '')
    
    # Validate configuration
    if not api_token:
        logger.error("API_TOKEN not set")
        sys.exit(1)
    
    if not workspace_id:
        logger.error("WORKSPACE_ID not set")
        sys.exit(1)
    
    try:
        workspace_id = int(workspace_id)
    except ValueError:
        logger.error(f"Invalid WORKSPACE_ID: {workspace_id}")
        sys.exit(1)
    
    if not company_file:
        logger.error("COMPANY_FILE not set")
        sys.exit(1)
    
    if not os.path.exists(company_file):
        logger.error(f"Company file not found: {company_file}")
        sys.exit(1)
    
    logger.info(f"Backend URL: {backend_url}")
    logger.info(f"Workspace ID: {workspace_id}")
    logger.info(f"Company File: {company_file}")
    if workspace_account_name:
        logger.info(f"Workspace Account: {workspace_account_name}")
    
    # Import and start sync service
    try:
        from sync_service import SyncService
        
        sync_service = SyncService(
            backend_url=backend_url,
            api_token=api_token,
            workspace_id=workspace_id,
            company_file=company_file,
            workspace_account_name=workspace_account_name or None
        )
        
        logger.info("Starting sync service...")
        sync_service.start()
        
    except KeyboardInterrupt:
        logger.info("Sync service stopped by user")
    except Exception as e:
        logger.error(f"Sync service error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()

