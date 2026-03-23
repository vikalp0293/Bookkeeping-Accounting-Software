"""
Payee normalization for all bank statement types.

Uses config rules first (deterministic, no API), then optional OpenAI fallback
when no rule matches. Single layer used by Huntington, Chase, US Bank, generic, etc.
"""

import json
import re
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Lazy-loaded rules (path resolved relative to backend/)
_rules: Optional[List[Dict[str, Any]]] = None
_rules_path: Optional[Path] = None


def _get_rules_path() -> Path:
    """Resolve path to payee_normalization_rules.json (backend/config/)."""
    global _rules_path
    if _rules_path is not None:
        return _rules_path
    # app/services/payee_normalizer.py -> backend/app/services -> backend/app -> backend
    backend_root = Path(__file__).resolve().parent.parent.parent
    _rules_path = backend_root / "config" / "payee_normalization_rules.json"
    return _rules_path


def _load_rules() -> List[Dict[str, Any]]:
    """Load rules from JSON config. Returns empty list on error."""
    global _rules
    if _rules is not None:
        return _rules
    path = _get_rules_path()
    try:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                _rules = json.load(f)
            logger.debug(f"Loaded {len(_rules)} payee normalization rules from {path}")
        else:
            logger.warning(f"Payee normalization rules not found at {path}")
            _rules = []
    except Exception as e:
        logger.warning(f"Failed to load payee normalization rules: {e}")
        _rules = []
    return _rules


def normalize(
    description: Optional[str],
    extracted_payee: Optional[str] = None,
    use_openai_fallback: Optional[bool] = None,
) -> Optional[str]:
    """
    Normalize payee from transaction description (all bank statement types).

    - Tries config rules first (ordered; first match wins).
    - If no rule matches and use_openai_fallback is True, calls OpenAI to extract payee.
    - Otherwise returns extracted_payee (e.g. from rule-based extract_payee_from_description).

    Args:
        description: Raw transaction description (as in statement).
        extracted_payee: Payee already derived by rule-based extraction (fallback).
        use_openai_fallback: If True, call OpenAI when no rule matches. Default from settings.

    Returns:
        Correct payee name, or extracted_payee, or None.
    """
    if not description or not str(description).strip():
        return extracted_payee

    desc_upper = str(description).upper().strip()
    rules = _load_rules()

    for rule in rules:
        patterns = rule.get("patterns") or []
        payee = rule.get("payee")
        if not payee:
            continue
        for pattern in patterns:
            if not pattern:
                continue
            # Support regex if pattern starts with "regex:"
            if str(pattern).upper().startswith("REGEX:"):
                try:
                    re_pattern = str(pattern)[6:].strip()
                    if re.search(re_pattern, desc_upper, re.IGNORECASE):
                        return payee
                except re.error:
                    continue
            elif str(pattern).upper() in desc_upper:
                return payee

    # No rule matched: optional OpenAI fallback
    if use_openai_fallback is None:
        try:
            from app.core.config import settings
            use_openai_fallback = getattr(
                settings, "USE_OPENAI_FOR_PAYEE_FALLBACK", True
            ) and bool(getattr(settings, "OPENAI_API_KEY", None))
        except Exception:
            use_openai_fallback = False

    if use_openai_fallback:
        try:
            from app.services.bank_statement_ai_extractor import BankStatementAIExtractor
            ai_payee = BankStatementAIExtractor.extract_payee_from_description(
                str(description).strip()
            )
            if ai_payee and ai_payee.strip():
                return ai_payee.strip()
        except Exception as e:
            logger.debug(f"OpenAI payee fallback failed: {e}")

    return extracted_payee
