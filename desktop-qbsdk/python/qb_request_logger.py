"""
QuickBooks request/response XML logger for debugging.

Writes the exact qbXML sent to and received from QuickBooks to files
(last_qb_request.xml, last_qb_response.xml) and logs a one-line summary
at INFO and full XML at DEBUG.

Usage:
  Before ProcessRequest(session_ticket, qbxml):
    log_qb_request(qbxml, log_dir)
  After ProcessRequest:
    log_qb_response(response, log_dir)

log_dir: Directory for the XML files (default: LOG_DIR env, or "logs" in cwd, or cwd).
"""

import logging
import os

logger = logging.getLogger(__name__)

REQUEST_FILE = "last_qb_request.xml"
RESPONSE_FILE = "last_qb_response.xml"


def _log_dir(log_dir=None):
    """Resolve log directory: argument, LOG_DIR env, 'logs' in cwd, or cwd."""
    if log_dir and os.path.isabs(log_dir):
        return log_dir
    if log_dir:
        base = os.getcwd()
        out = os.path.join(base, log_dir)
        return out
    if os.environ.get("LOG_DIR"):
        return os.environ.get("LOG_DIR")
    logs_cwd = os.path.join(os.getcwd(), "logs")
    return logs_cwd


def _ensure_dir(path):
    """Create parent directory if it doesn't exist."""
    parent = os.path.dirname(path)
    if parent and not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError:
            pass


def log_qb_request(qbxml_request: str, log_dir=None) -> str:
    """
    Write the qbXML request to last_qb_request.xml and log.

    Args:
        qbxml_request: Exact XML string sent to QuickBooks.
        log_dir: Directory for the file (default: LOG_DIR env or "logs" or cwd).

    Returns:
        Absolute path to the written file.
    """
    if not qbxml_request or not qbxml_request.strip():
        logger.warning("log_qb_request: empty request, skipping")
        return ""
    dir_path = _log_dir(log_dir)
    _ensure_dir(dir_path)
    file_path = os.path.join(dir_path, REQUEST_FILE)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(qbxml_request)
        size = len(qbxml_request)
        logger.info(
            "QB request written (%d bytes). File: %s",
            size,
            os.path.abspath(file_path),
        )
        logger.debug("QB request XML:\n%s", qbxml_request)
        return os.path.abspath(file_path)
    except OSError as e:
        logger.warning("Could not write last_qb_request.xml: %s", e)
        return ""


def log_qb_response(qbxml_response: str, log_dir=None) -> str:
    """
    Write the qbXML response to last_qb_response.xml and log.

    Args:
        qbxml_response: Exact XML string returned from QuickBooks.
        log_dir: Directory for the file (default: LOG_DIR env or "logs" or cwd).

    Returns:
        Absolute path to the written file.
    """
    if not qbxml_response or not qbxml_response.strip():
        logger.warning("log_qb_response: empty response, skipping")
        return ""
    dir_path = _log_dir(log_dir)
    _ensure_dir(dir_path)
    file_path = os.path.join(dir_path, RESPONSE_FILE)
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(qbxml_response)
        size = len(qbxml_response)
        logger.info(
            "QB response written (%d bytes). File: %s",
            size,
            os.path.abspath(file_path),
        )
        logger.debug("QB response XML:\n%s", qbxml_response)
        return os.path.abspath(file_path)
    except OSError as e:
        logger.warning("Could not write last_qb_response.xml: %s", e)
        return ""
