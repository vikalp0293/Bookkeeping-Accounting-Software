"""
Filter out statement-line check transactions using configurable rules.

Statement checks (e.g. "Check #1234") are excluded so check transactions
come only from uploaded check PDFs. Rules are loaded from
backend/config/statement_check_filter_rules.json.
"""

import json
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

_config: Optional[Dict[str, Any]] = None
_compiled: Optional[List[Dict[str, Any]]] = None


def _get_config_path() -> Path:
    """Resolve path to statement_check_filter_rules.json (backend/config/)."""
    # app/utils/statement_check_filter.py -> app -> backend
    backend_root = Path(__file__).resolve().parent.parent.parent
    return backend_root / "config" / "statement_check_filter_rules.json"


def _load_config() -> Dict[str, Any]:
    """Load rules from JSON config. Returns empty structure on error."""
    global _config
    if _config is not None:
        return _config
    path = _get_config_path()
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                _config = json.load(f)
            logger.debug(f"Loaded statement check filter rules from {path}")
        else:
            logger.warning(f"Statement check filter rules not found at {path}")
            _config = {"description_patterns": []}
    except Exception as e:
        logger.warning(f"Failed to load statement check filter rules: {e}")
        _config = {"description_patterns": []}
    return _config


def _get_compiled_rules() -> List[Dict[str, Any]]:
    """Compile regex patterns from config; cache result."""
    global _compiled
    if _compiled is not None:
        return _compiled
    cfg = _load_config()
    patterns = cfg.get("description_patterns") or []
    _compiled = []
    for entry in patterns:
        pat = entry.get("pattern")
        if not pat:
            continue
        flags = 0
        if not entry.get("case_sensitive", True):
            flags |= re.IGNORECASE
        try:
            _compiled.append({
                "re": re.compile(pat, flags),
                "max_description_length": entry.get("max_description_length"),
            })
        except re.error as e:
            logger.warning(f"Invalid statement check filter pattern '{pat}': {e}")
    return _compiled


def get_check_number_from_transaction(trans: Dict[str, Any]) -> Optional[str]:
    """
    Extract check number from a transaction (for matching to check images).
    Returns normalized check number string (digits) or None.
    Uses description/memo first, then reference_number (US Bank and others put check # there).
    """
    # Many banks (e.g. US Bank) store check number in reference_number (e.g. "5495" or "5727*")
    ref = trans.get("reference_number")
    if ref is not None and str(ref).strip():
        ref_str = re.sub(r"\D", "", str(ref).strip())
        if 3 <= len(ref_str) <= 6:
            return ref_str.lstrip("0") or "0"
    # Also try reference_number when description is "Check #1234" (redundant but ensures we match)
    desc = trans.get("description") or trans.get("memo") or ""
    if not desc or not str(desc).strip():
        return None
    text = str(desc).strip()
    # "Check #1234" or "Check 1234" or just "1234"
    m = re.search(r"Check\s*#?\s*(\d{3,6})\b", text, re.IGNORECASE)
    if m:
        return m.group(1).lstrip("0") or "0"
    if re.match(r"^\s*\d{3,6}\s*$", text):
        return text.strip().lstrip("0") or "0"
    return None


def is_statement_check_transaction(trans: Dict[str, Any]) -> bool:
    """
    Return True if this transaction should be excluded as a statement-line check.

    Uses description (or memo) and rules from statement_check_filter_rules.json.
    """
    desc = trans.get("description") or trans.get("memo") or ""
    if not desc or not str(desc).strip():
        return False
    text = str(desc).strip()
    rules = _get_compiled_rules()
    for rule in rules:
        max_len = rule.get("max_description_length")
        if max_len is not None and len(text) >= max_len:
            continue
        if rule["re"].match(text):
            return True
    return False


def filter_statement_check_transactions(
    transactions: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Remove transactions that match statement check filter rules.

    Returns filtered list and does not modify the input list.
    """
    if not transactions:
        return []
    rules = _get_compiled_rules()
    if not rules:
        return list(transactions)
    return [t for t in transactions if not is_statement_check_transaction(t)]
