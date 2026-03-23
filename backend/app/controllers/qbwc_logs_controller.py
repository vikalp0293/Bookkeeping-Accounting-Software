"""
QuickBooks Web Connector Logs Controller

Provides endpoint to view QB Web Connector logs.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import PlainTextResponse, HTMLResponse, JSONResponse
from app.dependencies.auth import get_current_user
from app.models.user import User
from pathlib import Path
import os
from datetime import datetime
from app.services.qbxml_service import QBXMLService

router = APIRouter(tags=["QuickBooks Web Connector"])

# Find log file - try multiple locations
LOG_FILE = None

# 1. Check if LOG_DIR environment variable is set
if os.getenv("LOG_DIR"):
    potential_log = Path(os.getenv("LOG_DIR")) / "qb_web_connector.log"
    if potential_log.exists():
        LOG_FILE = potential_log

# 2. Try relative to current working directory
if not LOG_FILE:
    potential_log = Path("logs") / "qb_web_connector.log"
    if potential_log.exists():
        LOG_FILE = potential_log.resolve()

# 3. Try relative to backend directory (backend/logs)
if not LOG_FILE:
    backend_dir = Path(__file__).parent.parent.parent
    potential_log = backend_dir / "logs" / "qb_web_connector.log"
    if potential_log.exists():
        LOG_FILE = potential_log

# 4. Try common server locations
if not LOG_FILE:
    common_paths = [
        Path("/var/log/sync-accounting/qb_web_connector.log"),
        Path("/app/logs/qb_web_connector.log"),
        Path("/tmp/logs/qb_web_connector.log"),
    ]
    for path in common_paths:
        if path.exists():
            LOG_FILE = path
            break

# 5. Default to backend/logs if nothing found (will create it)
if not LOG_FILE:
    backend_dir = Path(__file__).parent.parent.parent
    LOG_FILE = backend_dir / "logs" / "qb_web_connector.log"


@router.get("/logs/info")
async def get_log_file_info():
    """Get information about where the log file is located"""
    import os
    from pathlib import Path
    
    info = {
        "log_file_path": str(LOG_FILE) if LOG_FILE else "Not found",
        "log_file_exists": LOG_FILE.exists() if LOG_FILE else False,
        "current_working_directory": os.getcwd(),
        "log_dir_env": os.getenv("LOG_DIR"),
        "checked_paths": []
    }
    
    # List all paths we checked
    if os.getenv("LOG_DIR"):
        info["checked_paths"].append(str(Path(os.getenv("LOG_DIR")) / "qb_web_connector.log"))
    info["checked_paths"].append(str(Path("logs") / "qb_web_connector.log"))
    backend_dir = Path(__file__).parent.parent.parent
    info["checked_paths"].append(str(backend_dir / "logs" / "qb_web_connector.log"))
    
    return info


@router.get("/logs", response_class=HTMLResponse)
async def get_qbwc_logs_html(
    lines: int = Query(500, ge=1, le=5000)
    # Note: Authentication removed for easier debugging - add back in production if needed
    # current_user: User = Depends(get_current_user)
):
    """
    View QuickBooks Web Connector logs in browser.
    
    Args:
        lines: Number of lines to return (default: 500, max: 5000)
    
    Returns:
        HTML page with logs
    """
    if not LOG_FILE or not LOG_FILE.exists():
        # Try to create the directory and file
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        # Create empty log file with initial message
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            # datetime is already imported at top of file
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - qb_web_connector_controller - INFO - Log file created. Waiting for QB Web Connector requests...\n")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>QB Web Connector Logs</title>
            <style>
                body {{ font-family: monospace; padding: 20px; background: #1e1e1e; color: #d4d4d4; }}
                .info {{ color: #4ec9b0; padding: 20px; background: #1e3a3a; border: 1px solid #4ec9b0; border-radius: 5px; }}
                .steps {{ margin-top: 20px; padding: 15px; background: #252526; border-radius: 5px; }}
                .steps ol {{ margin-left: 20px; }}
                .steps li {{ margin: 10px 0; }}
            </style>
        </head>
        <body>
            <div class="info">
                <h2>📋 Log file not found</h2>
                <p><strong>Expected log file path:</strong> {LOG_FILE if LOG_FILE else 'Not determined'}</p>
                <p><strong>Current working directory:</strong> {os.getcwd()}</p>
                <p>No logs have been generated yet, or log file is in a different location.</p>
                <p>Check <a href="/api/v1/qbwc/logs/info" style="color: #4ec9b0;">/api/v1/qbwc/logs/info</a> for diagnostic information.</p>
            </div>
            <div class="steps">
                <h3>To generate logs:</h3>
                <ol>
                    <li>Ensure QuickBooks Desktop Pro 2018 is running</li>
                    <li>Open QuickBooks Web Connector</li>
                    <li>Add your application using the .qwc file</li>
                    <li>QB Web Connector will start polling your API</li>
                    <li>Logs will appear here automatically</li>
                </ol>
                <p style="margin-top: 15px;"><strong>Test the connection:</strong></p>
                <ul>
                    <li>WSDL: <a href="/qbwc?wsdl" style="color: #4ec9b0;">/qbwc?wsdl</a></li>
                    <li>Health: <a href="/qbwc" style="color: #4ec9b0;">/qbwc</a></li>
                </ul>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html)
    
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            # Get last N lines
            last_lines = all_lines[-lines:]
            log_content = ''.join(last_lines)
            
            # Escape HTML special characters
            log_content = log_content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            
            # Add syntax highlighting for log levels
            log_content = log_content.replace(' - INFO -', ' <span style="color: #4ec9b0;">- INFO -</span>')
            log_content = log_content.replace(' - ERROR -', ' <span style="color: #f48771;">- ERROR -</span>')
            log_content = log_content.replace(' - WARNING -', ' <span style="color: #dcdcaa;">- WARNING -</span>')
            log_content = log_content.replace(' - DEBUG -', ' <span style="color: #569cd6;">- DEBUG -</span>')
            
            # Highlight separators
            log_content = log_content.replace('===', '<span style="color: #ce9178; font-weight: bold;">===</span>')
            
            # Get current timestamp for display (compute before f-string)
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            html = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <title>QB Web Connector Logs</title>
                <meta http-equiv="refresh" content="30">
                <style>
                    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                    body {{ 
                        font-family: 'Consolas', 'Monaco', 'Courier New', monospace; 
                        background: #1e1e1e; 
                        color: #d4d4d4; 
                        padding: 20px;
                        font-size: 13px;
                        line-height: 1.6;
                    }}
                    .header {{
                        background: #252526;
                        padding: 15px 20px;
                        margin: -20px -20px 20px -20px;
                        border-bottom: 1px solid #3e3e42;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }}
                    .header h1 {{
                        color: #4ec9b0;
                        font-size: 18px;
                    }}
                    .controls {{
                        display: flex;
                        gap: 10px;
                        align-items: center;
                    }}
                    .controls input {{
                        background: #3c3c3c;
                        border: 1px solid #3e3e42;
                        color: #d4d4d4;
                        padding: 5px 10px;
                        border-radius: 3px;
                        width: 80px;
                    }}
                    .controls button {{
                        background: #0e639c;
                        border: none;
                        color: white;
                        padding: 5px 15px;
                        border-radius: 3px;
                        cursor: pointer;
                    }}
                    .controls button:hover {{
                        background: #1177bb;
                    }}
                    .controls button.clear-btn {{
                        background: #c41e3a;
                    }}
                    .controls button.clear-btn:hover {{
                        background: #d42e4a;
                    }}
                    .log-container {{
                        background: #1e1e1e;
                        border: 1px solid #3e3e42;
                        border-radius: 5px;
                        padding: 15px;
                        max-height: calc(100vh - 150px);
                        overflow-y: auto;
                        white-space: pre-wrap;
                        word-wrap: break-word;
                    }}
                    .log-line {{
                        margin-bottom: 2px;
                    }}
                    .timestamp {{
                        color: #808080;
                    }}
                    .auto-refresh {{
                        color: #808080;
                        font-size: 11px;
                        margin-left: 10px;
                    }}
                    .stats {{
                        color: #808080;
                        font-size: 11px;
                        margin-top: 10px;
                    }}
                </style>
                <script>
                    function refreshLogs() {{
                        const lines = document.getElementById('lines').value;
                        window.location.href = `/api/v1/qbwc/logs?lines=${{lines}}`;
                    }}
                    
                    function downloadLogs() {{
                        window.location.href = `/api/v1/qbwc/logs/download`;
                    }}
                    
                    async function clearLogs() {{
                        if (!confirm('Are you sure you want to clear all logs? This action cannot be undone.')) {{
                            return;
                        }}
                        
                        try {{
                            const response = await fetch('/api/v1/qbwc/logs/clear', {{
                                method: 'POST',
                                headers: {{
                                    'Content-Type': 'application/json'
                                }}
                            }});
                            
                            if (response.ok) {{
                                // Reload the page to show cleared logs
                                window.location.href = `/api/v1/qbwc/logs?lines=${{document.getElementById('lines').value}}`;
                            }} else {{
                                const error = await response.json();
                                alert('Error clearing logs: ' + (error.detail || 'Unknown error'));
                            }}
                        }} catch (error) {{
                            alert('Error clearing logs: ' + error.message);
                        }}
                    }}
                </script>
            </head>
            <body>
                <div class="header">
                    <h1>📋 QuickBooks Web Connector Logs</h1>
                    <div class="controls">
                        <label style="color: #808080;">Lines:</label>
                        <input type="number" id="lines" value="{lines}" min="1" max="5000" onchange="refreshLogs()">
                        <button onclick="refreshLogs()">Refresh</button>
                        <button onclick="downloadLogs()">Download</button>
                        <button onclick="clearLogs()" class="clear-btn">Clear Logs</button>
                        <span class="auto-refresh">Auto-refresh: 30s</span>
                    </div>
                </div>
                <div class="log-container">
{log_content}
                </div>
                <div class="stats">
                    Showing last {lines} lines | Total lines in file: {len(all_lines)} | Last updated: {current_time}
                </div>
            </body>
            </html>
            """
            return HTMLResponse(content=html)
    except Exception as e:
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>QB Web Connector Logs - Error</title>
            <style>
                body {{ font-family: monospace; padding: 20px; background: #1e1e1e; color: #d4d4d4; }}
                .error {{ color: #f48771; padding: 20px; background: #3c1e1e; border: 1px solid #f48771; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="error">
                <h2>Error reading log file</h2>
                <p>{str(e)}</p>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html)


@router.get("/logs/raw")
async def get_qbwc_logs_raw(
    lines: int = Query(100, ge=1, le=1000)
    # Note: Authentication removed for easier debugging - add back in production if needed
    # current_user: User = Depends(get_current_user)
):
    """
    Get QuickBooks Web Connector logs as plain text (for API).
    
    Args:
        lines: Number of lines to return (default: 100, max: 1000)
    
    Returns:
        Log file contents as plain text
    """
    if not LOG_FILE.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    try:
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            # Get last N lines
            last_lines = all_lines[-lines:]
            return PlainTextResponse(''.join(last_lines))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading log file: {str(e)}")


@router.get("/logs/download")
async def download_qbwc_logs(
    # Note: Authentication removed for easier debugging - add back in production if needed
    # current_user: User = Depends(get_current_user)
):
    """
    Download full QuickBooks Web Connector log file.
    """
    if not LOG_FILE.exists():
        raise HTTPException(status_code=404, detail="Log file not found")
    
    from fastapi.responses import FileResponse
    return FileResponse(
        path=str(LOG_FILE),
        filename="qb_web_connector.log",
        media_type="text/plain"
    )


@router.post("/logs/clear")
async def clear_qbwc_logs(
    # Note: Authentication removed for easier debugging - add back in production if needed
    # current_user: User = Depends(get_current_user)
):
    """
    Clear QuickBooks Web Connector log file.
    Removes all content from the log file and creates a new entry with timestamp.
    """
    try:
        if not LOG_FILE:
            raise HTTPException(status_code=404, detail="Log file path not determined")
        
        # Ensure directory exists
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Clear the log file and write a new header message
        with open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} - qbwc_logs_controller - INFO - Log file cleared. Waiting for QB Web Connector requests...\n")
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "message": "Log file cleared successfully",
                "log_file_path": str(LOG_FILE),
                "cleared_at": datetime.now().isoformat()
            }
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=f"Permission denied: Cannot write to log file: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing log file: {str(e)}")


@router.get("/test/qbxml/account-query")
async def test_account_query_xml():
    """
    Test endpoint to generate and preview AccountQuery qbXML in different formats.
    This helps debug XML format issues without going through the full Web Connector flow.
    
    Returns:
        JSON with different XML format variations for testing
    """
    try:
        # Generate AccountQuery XML (with explicit tags conversion)
        account_query_xml = QBXMLService.generate_account_query(request_id="test-query-1")
        
        # Generate variations for comparison
        import xml.etree.ElementTree as ET
        import re
        
        # Create the same query but manually format it to show the difference
        qbxml = ET.Element('QBXML')
        msgs_rq = ET.SubElement(qbxml, 'QBXMLMsgsRq')
        msgs_rq.set('onError', 'stopOnError')
        account_query_rq = ET.SubElement(msgs_rq, 'AccountQueryRq')
        account_query_rq.set('requestID', 'test-query-1')
        
        # Original (with self-closing tags)
        xml_str_original = ET.tostring(qbxml, encoding='unicode', xml_declaration=False)
        
        # Converted (with explicit tags)
        xml_str_converted = QBXMLService._convert_self_closing_to_explicit(xml_str_original)
        
        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "formats": {
                    "current_format": {
                        "description": "Current format (with explicit tags conversion)",
                        "xml": account_query_xml,
                        "first_120_chars": repr(account_query_xml[:120]),
                        "length": len(account_query_xml)
                    },
                    "original_self_closing": {
                        "description": "Original format (self-closing tags - may cause 0x80040400)",
                        "xml": f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>{xml_str_original}',
                        "first_120_chars": repr(xml_str_original[:120]),
                        "length": len(xml_str_original),
                        "note": "ElementTree generates self-closing tags by default for empty elements"
                    },
                    "converted_explicit": {
                        "description": "Converted format (explicit tags)",
                        "xml": f'<?qbxml version="{QBXMLService.QBXML_VERSION}"?>{xml_str_converted}',
                        "first_120_chars": repr(xml_str_converted[:120]),
                        "length": len(xml_str_converted),
                        "note": "Self-closing tags converted to explicit open/close tags"
                    }
                },
                "validation": {
                    "has_xml_declaration": account_query_xml.lstrip().startswith("<?xml"),
                    "starts_with_qbxml": account_query_xml.lstrip().startswith("<?qbxml"),
                    "has_self_closing_tags": "/>" in xml_str_original and "/>" not in xml_str_converted,
                    "status": "PASS" if account_query_xml.lstrip().startswith("<?qbxml") and not account_query_xml.lstrip().startswith("<?xml") else "FAIL"
                },
                "notes": [
                    "QuickBooks Desktop REQUIRES qbXML to start with ONLY <?qbxml version=\"13.0\"?>",
                    "QuickBooks Desktop WILL REJECT (HRESULT 0x80040400) qbXML that starts with <?xml version=\"1.0\"?>",
                    "Some QuickBooks queries may require explicit tags (not self-closing) for certain elements",
                    "This endpoint is for debugging - the actual Web Connector uses the current_format"
                ]
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating test XML: {str(e)}")

