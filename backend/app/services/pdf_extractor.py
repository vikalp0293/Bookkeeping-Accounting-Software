"""
PDF extraction service using pdfplumber.
Extracts data from bank statements and checks.
"""
import pdfplumber
import re
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
try:
    from dateutil.relativedelta import relativedelta
except ImportError:
    # Fallback if dateutil is not available
    relativedelta = None
from app.services.bank_statement_ai_extractor import BankStatementAIExtractor
from app.services.ai_correction_service import AICorrectionService
from app.services.payee_normalizer import normalize as normalize_payee
from app.utils.statement_check_filter import filter_statement_check_transactions

logger = logging.getLogger(__name__)


class PDFExtractor:
    """Extract data from PDF bank statements and checks."""
    
    # Common debit/withdrawal keywords (case-insensitive matching)
    DEBIT_KEYWORDS = [
        "WITHDRAWAL", "FEE", "CHARGE", "SERVICE CHARGE", "SERVICEFEE",
        "PURCHASE", "PAYMENT", "DEBIT", "PAY", "TRANSFER OUT", "TRANSFEROUT",
        "ATM", "WITHDRAW", "AUTOMATIC PAYMENT", "AUTO PAY", "AUTOPAY",
        "ONLINE PAYMENT", "BILL PAY", "BILLPAY", "ACH DEBIT", "ACHDEBIT",
        "POS", "POINT OF SALE", "MERCHANT", "PURCHASE", "PAYMENT TO",
        "WIRE TRANSFER", "WIRETRANSFER", "OVERDRAFT", "OVERDRAFTFEE",
        "NSF", "NON-SUFFICIENT FUNDS", "RETURNED ITEM", "RETURNEDITEM"
    ]
    
    # Common credit/deposit keywords
    CREDIT_KEYWORDS = [
        "DEPOSIT", "CREDIT", "TRANSFER IN", "TRANSFERIN", "REFUND",
        "INTEREST", "DIVIDEND", "PAYROLL", "DIRECT DEPOSIT", "DIRECTDEPOSIT",
        "ACH CREDIT", "ACHCREDIT", "WIRE RECEIVED", "WIRERECEIVED"
    ]
    
    # Words to skip when extracting vendor names
    SKIP_VENDOR_WORDS = {
        "BANKCARD", "ELECTRONIC", "DEPOSIT", "WITHDRAWAL", "TRANSFER",
        "PAYMENT", "FEE", "CHARGE", "SERVICE", "ST-", "INC", "LLC", "CORP",
        "FROM", "TO", "THE", "AND", "OR", "OF", "FOR", "BY", "WITH"
    }
    
    @staticmethod
    def detect_transaction_section(text: str) -> Optional[str]:
        """
        Detect if text is in a Credits or Debits section.
        Uses comprehensive pattern matching to handle all 9 bank statement formats.
        
        Patterns detected:
        - Sign-based: "(+)" for credits, "(-)" for debits (Huntington)
        - Word-based: "PLUS" for credits, "MINUS" for debits (1st Source Bank)
        - Descriptive: "Deposits and Additions" vs "Withdrawals" (Chase, PNC)
        - Simple: "Other Deposits" vs "Other Withdrawals" (US Bank)
        """
        text_upper = text.upper()
        
        # Pattern 1: Look for explicit signs (+ or -) in section headers
        # Examples: "Other Credits (+)", "Other Debits (-)", "Checks (-)" (Huntington)
        if re.search(r'\([+\+]', text_upper) or re.search(r'\s[+\+]\s', text_upper):
            # Found (+) sign - this is a credits section
            return "CREDITS"
        if re.search(r'\([-]', text_upper) or re.search(r'\s[-]\s', text_upper):
            # Found (-) sign - this is a debits section
            return "DEBITS"
        
        # Pattern 2: Look for "PLUS" or "MINUS" keywords (1st Source Bank format)
        # "PLUS ... DEPOSITS AND OTHER CREDITS" → CREDITS
        # "MINUS ... CHECKS, WITHDRAWALS, OTHER DEBITS" → DEBITS
        if re.search(r'\bPLUS\b.*\b(CREDITS|DEPOSITS)\b', text_upper):
            return "CREDITS"
        if re.search(r'\bMINUS\b.*\b(DEBITS|WITHDRAWALS|CHECKS)\b', text_upper):
            return "DEBITS"
        
        # Pattern 3: Look for descriptive section headers
        # "Deposits and Additions" or "Deposits and Other Additions" → CREDITS (Chase, PNC)
        # "Electronic Withdrawals" or "Other Withdrawals" → DEBITS (Chase, US Bank)
        # "Checks Paid" or "Checks and Other Deductions" → DEBITS (Chase, PNC, US Bank)
        credit_patterns = [
            r'DEPOSITS\s+AND\s+(OTHER\s+)?(ADDITIONS|CREDITS)',
            r'OTHER\s+DEPOSITS',
            r'DEPOSITS\s+AND\s+ADDITIONS',
            r'OTHER\s+CREDITS',
            r'CREDITS\s+\([+\+]',
            r'CREDIT\s+TRANSACTIONS'
        ]
        for pattern in credit_patterns:
            if re.search(pattern, text_upper):
                return "CREDITS"
        
        debit_patterns = [
            r'ELECTRONIC\s+WITHDRAWALS',
            r'OTHER\s+WITHDRAWALS',
            r'WITHDRAWALS',
            r'CHECKS\s+PAID',
            r'CHECKS\s+AND\s+(OTHER\s+)?(DEDUCTIONS|SUBSTITUTE)',
            r'OTHER\s+DEBITS',
            r'DEBITS\s+\([-]',
            r'CHECKS\s+\([-]',
            r'DEBIT\s+TRANSACTIONS'
        ]
        for pattern in debit_patterns:
            if re.search(pattern, text_upper):
                return "DEBITS"
        
        # Pattern 4: Look for section header keywords with context (fallback)
        # Credits: Any line containing "CREDITS" or "DEPOSITS" (but not "DEBITS")
        if re.search(r'\b(CREDITS|DEPOSITS|ADDITIONS)\b', text_upper):
            # Make sure it's not a debit section (e.g., "Debits and Credits" would be ambiguous)
            if not re.search(r'\b(DEBITS|WITHDRAWALS|CHECKS)\b', text_upper):
                return "CREDITS"
        
        # Debits: Any line containing "DEBITS" or "WITHDRAWALS" or "CHECKS" (but not "CREDITS")
        if re.search(r'\b(DEBITS|WITHDRAWALS|CHECKS|DEDUCTIONS|CHARGES)\b', text_upper):
            # Make sure it's not a credit section
            if not re.search(r'\b(CREDITS|DEPOSITS)\b', text_upper):
                return "DEBITS"
        
        return None
    
    @staticmethod
    def determine_transaction_type(
        description: str,
        amount: float,
        section: Optional[str] = None,
        bank_type: Optional[str] = None
    ) -> str:
        """
        Determine transaction type (DEPOSIT, WITHDRAWAL, FEE, CHECK) based on:
        - For Fifth Third: section only (no keyword/amount logic).
        - Otherwise: description keywords, section context, amount sign.
        """
        # Fifth Third fast-path: trust section only, skip all keyword/amount logic
        if bank_type == "fifth_third" and section:
            s = (section or "").strip().upper()
            if s in ("DEBITS", "WITHDRAWAL"):
                return "WITHDRAWAL"
            if s in ("CREDITS", "DEPOSIT"):
                return "DEPOSIT"
            if s in ("CHECKS", "CHECK"):
                return "CHECK"
        # Chase fast-path: DEPOSITS AND ADDITIONS (and continued) = DEPOSIT; ELECTRONIC/OTHER WITHDRAWALS, CHECKS PAID = WITHDRAWAL
        if bank_type == "chase" and section:
            s = (section or "").strip().upper()
            if s == "CREDITS":
                return "DEPOSIT"
            if s in ("DEBITS", "CHECKS"):
                return "WITHDRAWAL"
        # Normalize description for keyword matching (handle concatenated text)
        desc_upper = description.upper()
        desc_normalized = desc_upper.replace(',', ' ').replace('.', ' ')
        
        # Check for known deposit vendors FIRST (before fee check)
        # This ensures STRIPE, BANKCARD, DoorDash are correctly identified as deposits
        deposit_vendors = [
            "STRIPE", "BANKCARD", "DEP", "DIRECT DEPOSIT", "DIRECTDEPOSIT", "PAYROLL",
            "DOORDASH", "BEYOND MENU", "BEYONDMENU",  # Restaurant delivery service payments (deposits)
            "INTEREST PAYMENT", "INTERESTPAYMENT", "INTEREST"  # Interest income = deposit (not "PAYMENT" withdrawal)
        ]
        has_deposit_vendor_check = any(vendor in desc_upper for vendor in deposit_vendors) or \
                                   any(vendor in desc_normalized for vendor in deposit_vendors) or \
                                   "STRIPE" in desc_upper or "BANKCARD" in desc_upper
        
        # Check for fee/charge (but skip if it's a known deposit vendor)
        # Note: "TRANSFER" in "STRIPE TRANSFER" should not trigger fee detection
        if not has_deposit_vendor_check:
            fee_keywords = ["FEE", "CHARGE", "SERVICE CHARGE", "SERVICEFEE", 
                           "OVERDRAFT", "OVERDRAFTFEE", "NSF", "NON-SUFFICIENT"]
            # Only check for fees if description contains fee keywords AND not part of a deposit vendor name
            if any(keyword in desc_upper for keyword in fee_keywords):
                # Make sure it's not a false positive (e.g., "TRANSFER" matching "FEE" in "SERVICEFEE")
                if "TRANSFER" not in desc_upper or "STRIPE" in desc_upper:
                    return "FEE"
        
        # Check description keywords FIRST (highest priority - handles known vendors)
        # Known deposit vendors (check these FIRST before withdrawal vendors)
        # Handle concatenated text (e.g., "STRIPETRANSFER" should match "STRIPE")
        # Note: DoorDash and BeyondMenu are DEPOSITS for restaurants (money coming in from delivery services)
        deposit_vendors = [
            "STRIPE", "BANKCARD", "DEP", "DIRECT DEPOSIT", "DIRECTDEPOSIT", "PAYROLL",
            "DOORDASH", "BEYOND MENU", "BEYONDMENU",  # Restaurant delivery service payments (deposits)
            "INTEREST PAYMENT", "INTERESTPAYMENT", "INTEREST"  # Interest income = deposit
        ]
        
        # Known withdrawal vendors (even if concatenated)
        # Note: These are expenses/purchases (money going out)
        withdrawal_vendors = [
            "FIRSTENERGY", "CITYOFSPRINGFIELD", "CITYOF", "KROGER", "SUBWAY", 
            "RESTAURANT", "ECHECK", "OPCO", "PURCHASE", "WALMART", "TARGET", 
            "AMAZON", "COSTCO", "HOME DEPOT", "LOWES", "LOWE'S",
            "ATT*BILL", "ATT*", "BILL PAYMENT", "BILLPAY", "MEIJER", "HP *INSTANT"
        ]
        
        # Check for deposit vendors FIRST (STRIPE, BANKCARD are always deposits)
        # Check both original and normalized (normalized handles concatenated text better)
        has_deposit_vendor = any(vendor in desc_upper for vendor in deposit_vendors) or \
                            any(vendor in desc_normalized for vendor in deposit_vendors) or \
                            "STRIPE" in desc_upper or "BANKCARD" in desc_upper  # Explicit check for concatenated
        
        # Check both original and normalized description for withdrawal keywords/vendors
        has_withdrawal_keyword = any(keyword in desc_upper for keyword in PDFExtractor.DEBIT_KEYWORDS) or \
                                 any(keyword in desc_normalized for keyword in PDFExtractor.DEBIT_KEYWORDS) or \
                                 any(vendor in desc_upper or vendor in desc_normalized for vendor in withdrawal_vendors)
        
        # Check for deposit keywords (but not "TRANSFER OUT" which is a withdrawal)
        has_deposit_keyword = (any(keyword in desc_upper for keyword in PDFExtractor.CREDIT_KEYWORDS) or \
                              any(keyword in desc_normalized for keyword in PDFExtractor.CREDIT_KEYWORDS)) and \
                              "TRANSFER OUT" not in desc_upper and "TRANSFEROUT" not in desc_upper
        
        # Check amount sign
        is_debit_from_amount = amount < 0
        if amount < 0:
            amount = abs(amount)  # Normalize for processing
        
        # Determine transaction type: amount sign > known deposit vendors (STRIPE, BANKCARD) > section > withdrawal keywords
        # Known deposit vendors are always DEPOSIT; "TRANSFER" alone does not mean withdrawal (e.g. STRIPE TRANSFER = deposit).
        is_debit = False
        
        # PRIORITY 1: Amount sign - negative amount is almost always a debit (overrides wrong section detection)
        if is_debit_from_amount and not has_deposit_vendor:
            is_debit = True
        # PRIORITY 2: Section context - but known deposit vendors (STRIPE, BANKCARD, etc.) are always deposits
        # "TRANSFER" alone does not mean withdrawal (e.g. STRIPE TRANSFER = deposit)
        elif has_deposit_vendor:
            is_debit = False  # STRIPE, BANKCARD, DoorDash, etc. = deposit regardless of section
        elif section == "DEBITS":
            is_debit = True
        elif section == "CREDITS":
            # If description clearly indicates withdrawal (PURCHASE, BILL PAYMENT, KROGER, ATT, etc.), treat as debit
            if has_withdrawal_keyword:
                is_debit = True
            else:
                is_debit = False
        # PRIORITY 3: Known deposit vendors (only if section is unclear)
        elif has_deposit_vendor:
            # Known deposit vendor (STRIPE, BANKCARD, DoorDash) - deposit
            is_debit = False
        # PRIORITY 3: Withdrawal keywords
        elif has_withdrawal_keyword:
            # Description clearly indicates withdrawal
            is_debit = True
        # PRIORITY 4: Deposit keywords
        elif has_deposit_keyword:
            # Description clearly indicates deposit
            is_debit = False
        elif is_debit_from_amount:
            # Amount sign indicates debit
            is_debit = True
        else:
            # Default to deposit if unclear
            is_debit = False
        
        # Determine final type
        if is_debit:
            # Check if it's a fee or regular withdrawal
            if any(keyword in desc_upper for keyword in ["FEE", "CHARGE", "SERVICE"]):
                return "FEE"
            return "WITHDRAWAL"
        else:
            return "DEPOSIT"
    
    @staticmethod
    def sanitize_ocr_description(text: Optional[str]) -> str:
        """
        Sanitize description/payee text from OCR: strip leading/trailing junk,
        collapse spaces, remove common OCR artifacts. Use for OCR-sourced statements (e.g. WesBanco).
        """
        if not text or not isinstance(text, str):
            return (text or "").strip() or ""
        s = text.strip()
        # Strip leading/trailing quotes, apostrophes, underscores, backslashes (OCR noise)
        while s and s[0] in "'\"\\_ \t":
            s = s[1:]
        while s and s[-1] in "'\"\\_ \t-.":
            s = s[:-1]
        # Collapse multiple spaces and strip again
        s = re.sub(r"\s+", " ", s).strip()
        return s[:300] if len(s) > 300 else s
    
    @staticmethod
    def extract_payee_from_description(description: str) -> Optional[str]:
        """
        Extract payee/vendor name from transaction description.
        Uses multiple patterns to work with various bank formats.
        """
        if not description or len(description.strip()) < 3:
            return None
        
        desc_original = description
        desc_upper = description.upper()
        desc_lower = description.lower()
        
        # Priority 0: Handle special cases first (BANKCARD, STRIPE, etc.)
        if "BANKCARD" in desc_upper and ("DEP" in desc_upper or "DEPOSIT" in desc_upper):
            return "Bank Card"
        if "STRIPE" in desc_upper or "STRIPE TRANSFER" in desc_upper:
            return "Stripe"
        if "DOORDASH" in desc_upper:
            return "DoorDash"
        if "BEYOND MENU" in desc_upper or "BEYONDMENU" in desc_upper:
            return "Beyond Menu"
        # Known withdrawal merchants (substring in description -> canonical name)
        withdrawal_known = [
            ("KROGER", "Kroger"), ("SPEEDWAY", "Speedway"), ("GFSSTORE", "GFS"), ("GFS STORE", "GFS"),
            ("RESTAURANTDEP", "Restaurant"), ("RESTAURANT DEP", "Restaurant"), ("WM.COM", "Walmart"),
            ("SPECTRUM", "Spectrum"), ("PATRIOTSOFTWARE", "Patriot Software"), ("NATIONALTAXACCO", "National Tax Accountant"),
            ("OHIOBWC", "Ohio BWC"), ("COACH", "Coach"), ("PARKTOSHOP", "Park to Shop"), ("TORYBURCH", "Tory Burch"),
        ]
        for key, canonical in withdrawal_known:
            if key in desc_upper.replace(" ", ""):
                return canonical
        
        # Priority 1: Handle "PURCHASE" prefix (common in bank statements)
        # With space: "PURCHASE KROGER #7 2899..." -> "Kroger"
        # Without space (concatenated): "PURCHASEKROGERFU2989 KROGERFU2989SPRINGFIELDOH..." -> "Kroger"
        purchase_match = re.search(r'PURCHASE\s+([A-Z][A-Z0-9\s&\-\.]{2,40}?)(?:\s+#|\s+\d{4,}|\s+DEP|\s+ST-|INC|LLC|CORP|$)', desc_upper)
        if not purchase_match:
            # Concatenated: PURCHASE immediately followed by vendor name (no space)
            purchase_match = re.search(r'PURCHASE([A-Z][A-Z0-9]{2,30}?)(?=[A-Z0-9]{4,}|\s|$)', desc_upper)
        if purchase_match:
            vendor = purchase_match.group(1).strip()
            # Clean up: remove store numbers, trailing digits/codes (e.g. FU2989), normalize spacing
            vendor = re.sub(r'\s+#\s*\d+', '', vendor)
            vendor = re.sub(r'\s+\d{4,}', '', vendor)
            vendor = re.sub(r'\s+DEP\s*$', '', vendor, flags=re.IGNORECASE)
            # Remove trailing alphanumeric codes (e.g. FU2989, 2989)
            vendor = re.sub(r'[A-Z]{1,3}\d{4,}\s*$', '', vendor, flags=re.IGNORECASE)
            vendor = re.sub(r'\d{4,}\s*$', '', vendor)
            vendor = re.sub(r'\s+', ' ', vendor).strip()
            # Take only first word if multiple words (e.g., "RESTAURANT DEP" -> "Restaurant")
            words = vendor.split()
            if len(words) > 1 and words[1].upper() in ['DEP', 'DEPOSIT', 'PAYMENT', 'CHARGE']:
                vendor = words[0]
            # Known merchants: map concatenated form to canonical name
            known_merchants_upper = {
                'KROGER': 'Kroger', 'KROGERFU': 'Kroger', 'SUBWAY': 'Subway', 'WALMART': 'Walmart',
                'TARGET': 'Target', 'AMAZON': 'Amazon', 'COSTCO': 'Costco', 'HOMEDEPOT': 'Home Depot',
                'LOWES': "Lowe's", 'FIRSTENERGY': 'FirstEnergy', 'BEYONDMENU': 'Beyond Menu',
            }
            for key, canonical in known_merchants_upper.items():
                if key in vendor.upper() or vendor.upper().startswith(key) or vendor.upper().replace(' ', '').startswith(key):
                    vendor = canonical
                    break
            else:
                if vendor.isupper() and len(vendor) > 3:
                    vendor = vendor.title()
            if (len(vendor) > 2 and
                not any(skip_word in vendor.upper() for skip_word in PDFExtractor.SKIP_VENDOR_WORDS) and
                not re.match(r'^\d+$', vendor)):
                return vendor
        
        # Priority 2: Extract all-caps company names (common in utility/ACH payments)
        # Examples: "FIRSTENERGY OPCO FE ECHECK..." -> "FirstEnergy"
        #           "CITYOFSPRINGFIELDUTILITY..." -> "City Of Springfield Utility"
        
        # Special handling for known concatenated patterns FIRST
        # CITYOFSPRINGFIELDUTILITY -> CITY OF SPRINGFIELD UTILITY
        if desc_upper.startswith('CITYOF') or 'CITYOFSPRINGFIELD' in desc_upper:
            city_match = re.search(r'^(CITYOFSPRINGFIELDUTILITY|CITYOFSPRINGFIELD|CITYOF[A-Z]+UTILITY)', desc_upper)
            if city_match:
                vendor = city_match.group(1)
                # Split: CITYOFSPRINGFIELDUTILITY -> CITY OF SPRINGFIELD UTILITY
                vendor = re.sub(r'CITYOF', 'CITY OF ', vendor)
                vendor = re.sub(r'SPRINGFIELD', ' SPRINGFIELD', vendor)
                vendor = re.sub(r'UTILITY', ' UTILITY', vendor)
                vendor = re.sub(r'\s+', ' ', vendor).strip()
                vendor = vendor.title()
                if len(vendor) > 3:
                    return vendor
        
        # Special handling for FIRSTENERGY (compound word, don't split)
        if desc_upper.startswith('FIRSTENERGY'):
            firstenergy_match = re.search(r'^(FIRSTENERGY)(?:\s+[A-Z]+|\s+ECHECK|\s+\d|$)', desc_upper)
            if firstenergy_match:
                return 'FirstEnergy'
        
        all_caps_match = re.search(r'^([A-Z]{4,}(?:\s+[A-Z]+)*?)(?:\s+[A-Z]{1,3}\s+|\s+ECHECK|\s+\d{10,}|$)', desc_upper)
        if all_caps_match:
            vendor = all_caps_match.group(1).strip()
            
            # Handle FIRSTENERGY - keep as compound word (don't split)
            if vendor.startswith('FIRSTENERGY'):
                vendor = 'FIRSTENERGY'  # Take only the company name, skip "OPCO" etc.
            
            # Handle other concatenated all-caps words
            # Known word patterns to split on
            word_patterns = [
                (r'CITY([A-Z]{4,})', r'CITY \1'),  # CITYSPRINGFIELD -> CITY SPRINGFIELD
                (r'([A-Z]{4,})OF([A-Z]{4,})', r'\1 OF \2'),  # CITYOFSPRINGFIELD -> CITY OF SPRINGFIELD
                (r'SPRINGFIELD', 'SPRINGFIELD'),  # Keep as is
                (r'UTILITY', 'UTILITY'),  # Keep as is
                (r'([A-Z]{4,})(UTILITY)', r'\1 \2'),  # Split before UTILITY
                (r'([A-Z]{4,})(ENERGY)', r'\1 \2'),  # Split before ENERGY (but not FIRSTENERGY)
            ]
            
            vendor_split = vendor
            for pattern, replacement in word_patterns:
                # Skip FIRSTENERGY splitting
                if 'FIRSTENERGY' in vendor_split and 'ENERGY' in replacement:
                    continue
                vendor_split = re.sub(pattern, replacement, vendor_split)
            
            # If still all caps and long without spaces, try intelligent word boundary detection
            if vendor_split.isupper() and len(vendor_split) > 10 and ' ' not in vendor_split:
                # Try to detect word boundaries by looking for common patterns
                # Insert space before common suffixes/words
                vendor_split = re.sub(r'([A-Z]{4,})(UTILITY|ENERGY|BANK|CABLE|WIRELESS|MOBILITY)', 
                                     r'\1 \2', vendor_split)
                # Insert space after common prefixes
                vendor_split = re.sub(r'(CITY|FIRST|NEW|OLD|NORTH|SOUTH|EAST|WEST)([A-Z]{4,})', 
                                     r'\1 \2', vendor_split)
            
            vendor = vendor_split
            
            # Split camelCase-like all caps (CITYOF -> CITY OF) - but only if not already split
            if ' ' not in vendor:
                vendor = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', vendor)  # CITYOF -> CITY OF
            vendor = re.sub(r'([a-z])([A-Z])', r'\1 \2', vendor)  # Handle mixed case
            
            # Title case for readability (but preserve FIRSTENERGY as compound)
            if vendor.upper() == 'FIRSTENERGY':
                vendor = 'FirstEnergy'
            else:
                vendor = vendor.title()
            
            # Clean up: remove extra spaces, take first 3 words max for readability
            vendor = re.sub(r'\s+', ' ', vendor).strip()
            words = vendor.split()
            if len(words) > 3:
                vendor = ' '.join(words[:3])  # Limit to first 3 words
            
            if (len(vendor) > 3 and 
                not any(skip_word in vendor.upper() for skip_word in PDFExtractor.SKIP_VENDOR_WORDS)):
                return vendor
        
        # Priority 3: Extract vendor name at start (before transaction IDs, dates, or common separators)
        # Matches: "VENDOR NAME" followed by space + number, ST-, INC, LLC, etc.
        vendor_patterns = [
            r'^([A-Z][A-Z0-9\s&\-\.]+?)(?:\s+\d{4,}|ST-|INC|LLC|CORP|\.\s|$)',
            r'^([A-Z][A-Za-z0-9\s&\-\.]{2,30}?)(?:\s+\d|ST-|INC|LLC|CORP|$)',
        ]
        
        for pattern in vendor_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                potential_vendor = match.group(1).strip()
                # Filter out non-vendor words (but allow BANKCARD if it's the main identifier)
                if (len(potential_vendor) > 2 and 
                    not any(skip_word in potential_vendor.upper() for skip_word in PDFExtractor.SKIP_VENDOR_WORDS) and
                    not re.match(r'^\d+$', potential_vendor)):  # Not just numbers
                    # Title case if all caps
                    if potential_vendor.isupper() and len(potential_vendor) > 3:
                        potential_vendor = potential_vendor.title()
                    return potential_vendor
        
        # Pattern 2: Extract from "From X" or "To X" patterns
        from_to_patterns = [
            r'(?:FROM|TO)\s+([A-Z][A-Z0-9\s&\-\.]+?)(?:\s+\d|ST-|INC|LLC|CORP|\.|$)',
            r'(?:FROM|TO):\s*([A-Z][A-Z0-9\s&\-\.]+?)(?:\s|$)',
        ]
        
        for pattern in from_to_patterns:
            match = re.search(pattern, description, re.IGNORECASE)
            if match:
                potential_vendor = match.group(1).strip()
                if len(potential_vendor) > 2:
                    return potential_vendor
        
        # Pattern 3: Extract from transaction ID patterns (e.g., "VENDOR ST-XXXXX")
        if "ST-" in description or "REF:" in description or "ID:" in description:
            # Split by common transaction ID markers
            parts = re.split(r'(?:ST-|REF:|ID:|\d{4,})', description, maxsplit=1)
            if parts and len(parts[0].strip()) > 3:
                potential_vendor = parts[0].strip()
                if not any(skip_word in potential_vendor.upper() for skip_word in PDFExtractor.SKIP_VENDOR_WORDS):
                    return potential_vendor
        
        # Pattern 4: Extract first meaningful words (skip common transaction words)
        words = description.split()
        meaningful_words = []
        for word in words[:8]:  # Check first 8 words
            word_upper = word.upper().strip('.,;:')
            if (len(word_upper) > 2 and 
                word_upper not in PDFExtractor.SKIP_VENDOR_WORDS and
                not re.match(r'^\d+$', word_upper) and
                not re.match(r'^\d{2}/\d{2}$', word_upper)):  # Skip dates
                meaningful_words.append(word.strip('.,;:'))
                if len(meaningful_words) >= 3:  # Take up to 3 meaningful words
                    break
        
        if meaningful_words:
            payee = " ".join(meaningful_words)
            # Clean up common suffixes
            payee = re.sub(r'\s+(INC|LLC|CORP|LTD|CO)\.?$', '', payee, flags=re.IGNORECASE)
            return payee if len(payee) > 2 else None
        
        return None
    
    @staticmethod
    def detect_bank_type(text: str) -> Optional[str]:
        """Detect bank type from PDF text. Check Ohio State Bank (and similar) before Huntington so
        transaction text like 'HUNTINGTON BP MERCH PMT' on an Ohio State Bank statement does not misidentify the bank."""
        text_upper = text.upper()
        if "CHASE" in text_upper or "JPMORGAN" in text_upper:
            return "chase"
        elif "OHIO STATE BANK" in text_upper or "BANKATOSB" in text_upper:
            return "ohio_state_bank"
        elif "HUNTINGTON" in text_upper:
            return "huntington"
        elif "US BANK" in text_upper or "U.S. BANK" in text_upper:
            return "us_bank"
        elif "FIFTH THIRD" in text_upper or "5/3" in text_upper or "FTCSTMT" in text_upper:
            return "fifth_third"
        elif "1ST SOURCE" in text_upper or "1STSOURCE" in text_upper:
            return "first_source"
        elif "WESBANCO" in text_upper:
            return "wesbanco"
        return None
    
    @staticmethod
    def apply_ai_enhancements(result: Dict[str, Any], full_text: str, skip_if_complete: bool = False) -> Dict[str, Any]:
        """
        Apply AI enhancements to bank statement extraction results.
        Enhances balances, dates, payees, and transaction types.
        Optimized to only enhance payees for transactions that need it (N/A or unclear).
        
        Args:
            result: Extraction result dictionary
            full_text: Full text from PDF for balance extraction
            skip_if_complete: If True, skip AI enhancements if extraction appears complete
            
        Returns:
            Enhanced result dictionary
        """
        # OPTIMIZATION: Skip AI enhancements if extraction is complete and has all transactions
        if skip_if_complete:
            transactions = result.get("transactions", [])
            has_deposits = any(t.get("transaction_type") == "DEPOSIT" for t in transactions)
            has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in transactions)
            
            # If we have both deposits and withdrawals, and reasonable transaction count, skip AI
            if has_deposits and has_withdrawals and len(transactions) >= 5:
                logger.info(f"Skipping AI enhancements - PDF extraction complete ({len(transactions)} transactions, deposits: {has_deposits}, withdrawals: {has_withdrawals})")
                return result
        
        try:
            # Use AI to enhance balance extraction
            enhanced_balances = BankStatementAIExtractor.enhance_balance_extraction(
                full_text,
                {
                    "beginning_balance": result.get("beginning_balance"),
                    "ending_balance": result.get("ending_balance"),
                    "total_deposits": result.get("total_deposits"),
                    "total_withdrawals": result.get("total_withdrawals"),
                    "statement_period_start": result.get("statement_period_start"),
                    "statement_period_end": result.get("statement_period_end")
                }
            )
            result.update(enhanced_balances)
            logger.info("Enhanced balance extraction with GPT-4")
        except Exception as e:
            logger.warning(f"AI balance enhancement failed: {e}")
        
        # Use AI to enhance transaction extraction (dates, payees, types)
        # OPTIMIZATION: Only enhance transactions that need it (N/A payees or unclear)
        if result.get("transactions"):
            try:
                # First, improve payees using simple patterns (fast)
                for trans in result["transactions"]:
                    if not trans.get("payee") or trans.get("payee") == "N/A":
                        desc = trans.get("description", "")
                        raw_payee = PDFExtractor.extract_payee_from_description(desc)
                        payee = normalize_payee(desc, raw_payee) or raw_payee
                        if payee:
                            trans["payee"] = payee
                
                # OPTIMIZATION: Use AI to classify transaction types for ALL transactions
                # Skip for Fifth Third: types are section-only (Deposits/Credits, Withdrawals/Debits, Checks).
                transactions = result["transactions"]
                bank_name = result.get("bank_name") or ""
                skip_ai_types = "fifth third" in bank_name.lower() or "5/3" in bank_name or "FIFTH THIRD" in bank_name.upper()
                if transactions and len(transactions) > 0 and not skip_ai_types:
                    logger.info(f"Using AI to classify transaction types for {len(transactions)} transactions...")
                    try:
                        statement_context = {
                            "statement_period_start": result.get("statement_period_start"),
                            "statement_period_end": result.get("statement_period_end"),
                            "bank_name": result.get("bank_name"),
                            "business_type": "restaurant"  # Default assumption, can be made configurable
                        }
                        
                        # AI classification for all transactions
                        ai_classified = BankStatementAIExtractor.classify_transaction_types_ai(
                            transactions,
                            statement_context
                        )
                        
                        # Update transaction types
                        for i, trans in enumerate(transactions):
                            if i < len(ai_classified) and ai_classified[i].get("transaction_type"):
                                trans["transaction_type"] = ai_classified[i]["transaction_type"]
                        
                        logger.info(f"AI classified transaction types for {len(transactions)} transactions")
                    except Exception as e:
                        logger.warning(f"AI transaction type classification failed: {e}, using rule-based classification")
                elif skip_ai_types and transactions:
                    logger.info(f"Skipping AI transaction type classification for Fifth Third ({len(transactions)} transactions use section-only types)")
                
                # OPTIMIZATION: Batch normalize concatenated descriptions (only if needed)
                # This prevents timeout by batching API calls instead of calling per transaction
                if len(transactions) > 10:
                    logger.info(f"Batch normalizing descriptions for {len(transactions)} transactions...")
                    try:
                        # Collect descriptions that need normalization (concatenated text)
                        descriptions_to_normalize = []
                        desc_indices = []
                        
                        for idx, trans in enumerate(transactions):
                            desc = trans.get("description", "")
                            # Only normalize if it looks concatenated (all caps, no spaces, or has patterns)
                            if desc and len(desc) > 5:
                                desc_upper = desc.upper()
                                # Check if it looks concatenated
                                is_concatenated = (
                                    desc_upper == desc and len(desc) > 10 and ' ' not in desc[:20]  # All caps, no spaces
                                ) or (
                                    any(pattern in desc_upper for pattern in ['STRIPETRANSFER', 'DOORDASH,INC', 'BANKCARD8076', 'CITYOFSPRINGFIELD', 'FIRSTENERGY'])
                                )
                                
                                if is_concatenated:
                                    descriptions_to_normalize.append(desc)
                                    desc_indices.append(idx)
                        
                        # Batch normalize (limit to 50 to avoid timeout)
                        if descriptions_to_normalize and len(descriptions_to_normalize) <= 50:
                            normalized_descriptions = AICorrectionService.normalize_transaction_descriptions_batch(
                                descriptions_to_normalize[:50], 
                                batch_size=20
                            )
                            
                            # Update transactions with normalized descriptions
                            for i, idx in enumerate(desc_indices[:len(normalized_descriptions)]):
                                if i < len(normalized_descriptions):
                                    normalized_desc = normalized_descriptions[i]
                                    if normalized_desc and len(normalized_desc) > len(descriptions_to_normalize[i]) * 0.8:
                                        old_desc = transactions[idx]["description"]
                                        transactions[idx]["description"] = normalized_desc
                                        # Re-extract payee with normalized description
                                        new_payee = PDFExtractor.extract_payee_from_description(normalized_desc)
                                        payee = normalize_payee(normalized_desc, new_payee) or new_payee
                                        if payee:
                                            transactions[idx]["payee"] = payee
                                        # Re-determine transaction type with normalized description
                                        transactions[idx]["transaction_type"] = PDFExtractor.determine_transaction_type(
                                            normalized_desc, transactions[idx]["amount"], None
                                        )
                                        logger.debug(f"Batch normalized: '{old_desc[:40]}' -> '{normalized_desc[:40]}'")
                            logger.info(f"Batch normalized {len(descriptions_to_normalize)} concatenated descriptions")
                        elif len(descriptions_to_normalize) > 50:
                            logger.info(f"Skipping AI normalization - too many concatenated descriptions ({len(descriptions_to_normalize)}), would timeout")
                    except Exception as e:
                        logger.warning(f"Batch description normalization failed: {e}, continuing without normalization")
                
                # Use AI enhancement for transactions with missing/generic/unclean payees (sanitize + improve with OpenAI)
                _generic_payee_prefixes = ("ACH DEPOSIT", "ACH WITHDRAWAL", "POS PURCHASE", "POS REFUND", "CONVERTED CHECK", "CHECK #", "CHECK ")
                def _payee_needs_ai(t):
                    payee = (t.get("payee") or "").strip()
                    desc = (t.get("description") or "").strip()
                    if not desc:
                        return False
                    if not payee or payee == "N/A":
                        return True
                    # OCR junk: leading quote/apostrophe
                    if payee and payee[0] in "'\"\\_":
                        return True
                    # Generic bank labels that don't identify the actual vendor
                    payee_upper = payee.upper()
                    if any(payee_upper.startswith(p) or p in payee_upper for p in _generic_payee_prefixes):
                        return True
                    return False
                transactions_needing_ai = [
                    t for t in result["transactions"]
                    if _payee_needs_ai(t)
                ][:40]  # Limit to 40 to balance quality vs latency
                
                if transactions_needing_ai:
                    logger.info(f"Using AI to enhance {len(transactions_needing_ai)} transactions with unclear payees...")
                    statement_context = {
                        "statement_period_start": result.get("statement_period_start"),
                        "statement_period_end": result.get("statement_period_end"),
                        "bank_name": result.get("bank_name")
                    }
                    
                    enhanced_transactions = BankStatementAIExtractor.enhance_transaction_extraction(
                        transactions_needing_ai,
                        statement_context
                    )
                    
                    # Merge enhanced payees back (by index first, then by description for any extras)
                    if enhanced_transactions:
                        for i, trans in enumerate(transactions_needing_ai):
                            if i < len(enhanced_transactions) and enhanced_transactions[i].get("payee"):
                                raw = enhanced_transactions[i]["payee"]
                                desc = trans.get("description", "")
                                trans["payee"] = normalize_payee(desc, raw) or raw
                                if enhanced_transactions[i].get("description"):
                                    trans["description"] = enhanced_transactions[i]["description"]
                        logger.info(f"Enhanced {len(transactions_needing_ai)} transactions with GPT-4")
            except Exception as e:
                logger.warning(f"AI transaction enhancement failed: {e}")
        
        return result
    
    @staticmethod
    def extract_chase_statement(file_path: str) -> Dict[str, Any]:
        """Extract data from Chase bank statement."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "Chase",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": []
        }
        
        try:
            with pdfplumber.open(file_path) as pdf:
                full_text = ""
                # Limit to first 5 pages for header info (balances are usually on first page)
                header_pages = min(5, len(pdf.pages))
                for page in pdf.pages[:header_pages]:
                    full_text += page.extract_text() or ""
                
                # Extract account number
                account_match = re.search(r'Account Number:\s*(\d+)', full_text, re.IGNORECASE)
                if account_match:
                    result["account_number"] = account_match.group(1)
                
                # Extract account name/type
                account_name_match = re.search(r'(Chase\s+\w+\s+Checking)', full_text, re.IGNORECASE)
                if account_name_match:
                    result["account_name"] = account_name_match.group(1)
                
                # Extract statement period (format: January 01, 2025 through January 31, 2025)
                # Also handle: March 01, 2025throughMarch 31, 2025 (no space between "through")
                period_patterns = [
                    r'(\w+\s+\d{1,2},\s+\d{4})\s+through\s+(\w+\s+\d{1,2},\s+\d{4})',  # With space
                    r'(\w+\s+\d{1,2},\s+\d{4})through(\w+\s+\d{1,2},\s+\d{4})',  # No space
                    r'(\w+\s+\d{1,2},\s+\d{4})\s+to\s+(\w+\s+\d{1,2},\s+\d{4})',  # "to" instead of "through"
                ]
                
                for pattern in period_patterns:
                    period_match = re.search(pattern, full_text, re.IGNORECASE)
                    if period_match:
                        try:
                            start_str = period_match.group(1).strip()
                            end_str = period_match.group(2).strip()
                            
                            # Try different date formats
                            date_formats = ["%B %d, %Y", "%b %d, %Y", "%B %d,%Y", "%b %d,%Y"]
                            
                            start_date = None
                            end_date = None
                            
                            for fmt in date_formats:
                                try:
                                    start_date = datetime.strptime(start_str, fmt)
                                    break
                                except:
                                    continue
                            
                            for fmt in date_formats:
                                try:
                                    end_date = datetime.strptime(end_str, fmt)
                                    break
                                except:
                                    continue
                            
                            if start_date and end_date:
                                result["statement_period_start"] = start_date.strftime("%Y-%m-%d")
                                result["statement_period_end"] = end_date.strftime("%Y-%m-%d")
                                break
                        except Exception as e:
                            logger.debug(f"Error parsing statement period: {e}")
                            continue
                
                # Extract beginning balance
                beg_balance_match = re.search(r'Beginning Balance\s+\$?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
                if beg_balance_match:
                    result["beginning_balance"] = float(beg_balance_match.group(1).replace(',', ''))
                
                # Extract ending balance
                # Priority 1: Extract from "CHECKING SUMMARY" section (most reliable for Chase)
                # Format: "Ending Balance" with instances count and amount
                checking_summary_match = re.search(
                    r'CHECKING SUMMARY.*?Ending Balance.*?(\d+).*?\$?\s*([\d,]+\.\d{2})',
                    full_text, re.IGNORECASE | re.DOTALL
                )
                if checking_summary_match:
                    instances = checking_summary_match.group(1)
                    balance_value = float(checking_summary_match.group(2).replace(',', ''))
                    # Validate: ending balance should be reasonable compared to beginning balance
                    if result.get("beginning_balance"):
                        beg_bal = result["beginning_balance"]
                        # Accept if within reasonable range (0.1x to 10x beginning balance)
                        if 0.1 * beg_bal <= balance_value <= 10 * beg_bal:
                            result["ending_balance"] = balance_value
                            logger.debug(f"Extracted ending balance from CHECKING SUMMARY: ${balance_value:,.2f} (instances: {instances})")
                
                # Priority 2: Extract from "DAILY ENDING BALANCE" section (last date entry)
                # This is reliable for statements with daily balance tracking
                if result["ending_balance"] is None:
                    daily_balance_section = re.search(r'DAILY ENDING BALANCE.*?(?=IN CASE OF ERRORS|$)', full_text, re.IGNORECASE | re.DOTALL)
                    if daily_balance_section:
                        # Find all date-amount pairs in the daily balance section
                        daily_balances = re.findall(r'(\d{2}/\d{2})\s+\$?\s*([\d,]+\.\d{2})', daily_balance_section.group(0), re.IGNORECASE)
                        if daily_balances:
                            # Get the last entry (most recent date = ending balance)
                            last_date, last_balance = daily_balances[-1]
                            balance_value = float(last_balance.replace(',', ''))
                            # Validate against beginning balance
                            if result.get("beginning_balance"):
                                beg_bal = result["beginning_balance"]
                                if 0.1 * beg_bal <= balance_value <= 10 * beg_bal:
                                    result["ending_balance"] = balance_value
                                    logger.debug(f"Extracted ending balance from DAILY ENDING BALANCE: ${balance_value:,.2f} (date: {last_date})")
                            else:
                                result["ending_balance"] = balance_value
                
                # Priority 3: Look for "Ending Balance" in summary/account summary section
                if result["ending_balance"] is None:
                    summary_patterns = [
                        r'Account Summary.*?Ending Balance[^\d]*\$?\s*([\d,]+\.\d{2})',
                        r'Summary.*?Ending Balance[^\d]*\$?\s*([\d,]+\.\d{2})'
                    ]
                    for pattern in summary_patterns:
                        summary_match = re.search(pattern, full_text, re.IGNORECASE | re.DOTALL)
                        if summary_match:
                            balance_value = float(summary_match.group(1).replace(',', ''))
                            # Validate against beginning balance
                            if result.get("beginning_balance"):
                                beg_bal = result["beginning_balance"]
                                if balance_value > 100 and (0.1 * beg_bal <= balance_value <= 10 * beg_bal):
                                    result["ending_balance"] = balance_value
                                    break
                            elif balance_value > 100:
                                result["ending_balance"] = balance_value
                                break
                
                # Priority 4: Fallback - look for "Ending Balance" with dollar amount (more specific pattern)
                if result["ending_balance"] is None:
                    # Pattern: "Ending Balance" followed by optional text, then dollar sign and amount
                    end_balance_patterns = [
                        r'Ending Balance[^\d]*\$?\s*([\d,]+\.\d{2})',
                        r'Ending Balance[:\s]+\$?\s*([\d,]+\.\d{2})',
                        r'Ending\s+Balance[^\d]*\$?\s*([\d,]+\.\d{2})'
                    ]
                    
                    for pattern in end_balance_patterns:
                        end_balance_matches = re.findall(pattern, full_text, re.IGNORECASE)
                        if end_balance_matches:
                            # Filter out small values (likely counts, not dollar amounts)
                            # The actual ending balance should be similar in magnitude to beginning balance
                            ending_balances = [float(m.replace(',', '')) for m in end_balance_matches]
                            
                            # Get the largest value that makes sense
                            # If we have a beginning balance, prefer values close to it
                            if result.get("beginning_balance"):
                                beg_bal = result["beginning_balance"]
                                # Accept balances within reasonable range (0.1x to 10x beginning balance)
                                valid_balances = [b for b in ending_balances if b > 100 and (0.1 * beg_bal <= b <= 10 * beg_bal)]
                                if valid_balances:
                                    result["ending_balance"] = max(valid_balances)
                                    break
                            else:
                                # No beginning balance to compare, use largest reasonable value
                                valid_balances = [b for b in ending_balances if b > 100]
                                if valid_balances:
                                    result["ending_balance"] = max(valid_balances)
                                    break
                
                # Extract total deposits
                deposits_match = re.search(r'Deposits and Additions\s+\d+\s+([\d,]+\.?\d*)', full_text, re.IGNORECASE)
                if deposits_match:
                    result["total_deposits"] = float(deposits_match.group(1).replace(',', ''))
                
                # Extract total withdrawals
                # Chase format: "Electronic Withdrawals 21 -23,819.39" or "Electronic Withdrawals 21 23,819.39"
                # Also check for "Other Withdrawals" and "Checks Paid"
                total_withdrawals = 0.0
                
                # Electronic Withdrawals
                electronic_match = re.search(r'Electronic Withdrawals\s+\d+\s+-?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
                if electronic_match:
                    total_withdrawals += float(electronic_match.group(1).replace(',', ''))
                
                # Checks Paid
                checks_match = re.search(r'Checks Paid\s+\d+\s+-?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
                if checks_match:
                    total_withdrawals += float(checks_match.group(1).replace(',', ''))
                
                # Other Withdrawals
                other_match = re.search(r'Other Withdrawals\s+\d+\s+-?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
                if other_match:
                    total_withdrawals += float(other_match.group(1).replace(',', ''))
                
                if total_withdrawals > 0:
                    result["total_withdrawals"] = total_withdrawals
                else:
                    # Fallback to single pattern if combined didn't work
                    withdrawals_match = re.search(r'Electronic Withdrawals\s+\d+\s+-?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
                    if withdrawals_match:
                        result["total_withdrawals"] = float(withdrawals_match.group(1).replace(',', ''))
                
                # Extract transactions from ALL pages (no limit to ensure complete extraction)
                max_pages = len(pdf.pages)
                current_section = None  # Track current section (CREDITS or DEBITS)
                
                for page in pdf.pages:
                    page_text = page.extract_text() or ""
                    
                    # Section headers: DEPOSITS AND ADDITIONS (and continued) = CREDITS; ELECTRONIC/OTHER WITHDRAWALS, CHECKS PAID = DEBITS
                    page_upper = page_text.upper()
                    if "DEPOSITS AND ADDITIONS" in page_upper:
                        current_section = "CREDITS"
                        logger.debug(f"Found 'Deposits and Additions' section on page {pdf.pages.index(page) + 1}")
                    elif "ELECTRONIC WITHDRAWALS" in page_upper:
                        current_section = "DEBITS"
                        logger.debug(f"Found 'Electronic Withdrawals' section on page {pdf.pages.index(page) + 1}")
                    elif "OTHER WITHDRAWALS" in page_upper:
                        current_section = "DEBITS"
                        logger.debug(f"Found 'Other Withdrawals' section on page {pdf.pages.index(page) + 1}")
                    elif "CHECKS PAID" in page_upper:
                        current_section = "DEBITS"
                        logger.debug(f"Found 'Checks Paid' section on page {pdf.pages.index(page) + 1}")
                    
                    # Line-by-line section updates (critical for multi-section pages so first row and deposits are correct)
                    lines = page_text.split('\n')
                    for line in lines:
                        line_upper = line.upper().strip()
                        if "DEPOSITS AND ADDITIONS" in line_upper:
                            current_section = "CREDITS"
                        elif "ELECTRONIC WITHDRAWALS" in line_upper:
                            current_section = "DEBITS"
                        elif "OTHER WITHDRAWALS" in line_upper:
                            current_section = "DEBITS"
                        elif "CHECKS PAID" in line_upper:
                            current_section = "DEBITS"
                    
                    # Use line-by-line parsing only so section (DEPOSITS AND ADDITIONS vs ELECTRONIC/OTHER WITHDRAWALS) is correct per row
                    tables = []
                    for table in tables:
                        if not table or len(table) < 2:
                            continue
                        
                        headers = [str(cell).upper() if cell else "" for cell in table[0]]
                        if "DATE" in str(headers) and "AMOUNT" in str(headers):
                            date_col = None
                            desc_col = None
                            amount_col = None
                            
                            # Find column indices
                            for i, header in enumerate(headers):
                                if "DATE" in header:
                                    date_col = i
                                elif "DESCRIPTION" in header:
                                    desc_col = i
                                elif "AMOUNT" in header:
                                    amount_col = i
                            
                            if date_col is not None and amount_col is not None:
                                for row in table[1:]:
                                    if not row or len(row) <= max(date_col or 0, amount_col or 0):
                                        continue
                                    
                                    # Skip section header rows
                                    row_text = ' '.join([str(cell) for cell in row if cell]).upper()
                                    if "DEPOSITS" in row_text and "ADDITIONS" in row_text:
                                        continue
                                    if "ELECTRONIC" in row_text and "WITHDRAWALS" in row_text:
                                        continue
                                    if "CHECKS" in row_text and "PAID" in row_text:
                                        continue
                                    
                                    date_cell = str(row[date_col]).strip() if date_col < len(row) and row[date_col] else ""
                                    desc_cell = str(row[desc_col]).strip() if desc_col and desc_col < len(row) and row[desc_col] else ""
                                    amount_cell = str(row[amount_col]).strip() if amount_col < len(row) and row[amount_col] else ""
                                    
                                    # Extract date (format: 01/02 or January 2, 2025)
                                    date_match = re.search(r'(\d{1,2}/\d{1,2})|(\w+\s+\d{1,2},\s+\d{4})', date_cell)
                                    if not date_match:
                                        continue
                                    
                                    # Extract amount (may be negative for withdrawals)
                                    amount_match = re.search(r'([-]?[\d,]+\.\d{2})', amount_cell)
                                    if not amount_match:
                                        continue
                                    
                                    try:
                                        # Parse date
                                        if "/" in date_match.group(0):
                                            # Format: 01/02 - convert to full date
                                            month_day = date_match.group(0)
                                            if result["statement_period_start"]:
                                                year = result["statement_period_start"][:4]
                                                date_str = f"{year}-{month_day.replace('/', '-')}"
                                            else:
                                                date_str = month_day
                                        else:
                                            # Format: January 2, 2025
                                            date_obj = datetime.strptime(date_match.group(0), "%B %d, %Y")
                                            date_str = date_obj.strftime("%Y-%m-%d")
                                        
                                        amount_str = amount_match.group(1).replace(',', '')
                                        amount = float(amount_str)
                                        original_amount = amount
                                        
                                        # Normalize amount (store as positive, use type to indicate direction)
                                        if amount < 0:
                                            amount = abs(amount)
                                        
                                        # Get description
                                        description = desc_cell if desc_cell else ""
                                        
                                        # Determine transaction type from section only (Chase: DEPOSITS AND ADDITIONS = DEPOSIT, etc.)
                                        trans_type = PDFExtractor.determine_transaction_type(
                                            description, original_amount, current_section, bank_type="chase"
                                        )
                                        
                                        # Extract payee/vendor from description
                                        raw_payee = PDFExtractor.extract_payee_from_description(description)
                                        payee = normalize_payee(description, raw_payee) or raw_payee or "N/A"
                                        
                                        # Extract reference number if available
                                        ref_match = re.search(r'Trace#:\s*(\d+)', description)
                                        ref_number = ref_match.group(1) if ref_match else None
                                        
                                        result["transactions"].append({
                                            "date": date_str,
                                            "amount": amount,
                                            "description": description[:300],  # Longer for Chase
                                            "payee": payee or "N/A",
                                            "transaction_type": trans_type,
                                            "reference_number": ref_number
                                        })
                                    except Exception as e:
                                        logger.debug(f"Error parsing transaction row: {e}")
                                        continue
                    
                    # Fallback: line-by-line so section is correct for each transaction (fixes deposits shown as withdrawal)
                    # Section headers: DEPOSITS AND ADDITIONS (and continued) = CREDITS; ELECTRONIC/OTHER WITHDRAWALS, CHECKS PAID = DEBITS
                    # Amount may have leading $ (e.g. $2,496.30) so allow \$? in regex
                    chase_txn_re = re.compile(r'^(\d{1,2}/\d{1,2})\s+(.+?)\s+\$?([-]?[\d,]+\.\d{2})\s*$')
                    lines_list = page_text.split('\n')
                    for line in lines_list:
                        line_stripped = line.strip()
                        line_upper = line_stripped.upper()
                        # Update section from header lines (so first row after "DEPOSITS AND ADDITIONS" is DEPOSIT)
                        if "DEPOSITS AND ADDITIONS" in line_upper:
                            current_section = "CREDITS"
                            continue
                        if "ELECTRONIC WITHDRAWALS" in line_upper:
                            current_section = "DEBITS"
                            continue
                        if "OTHER WITHDRAWALS" in line_upper:
                            current_section = "DEBITS"
                            continue
                        if "CHECKS PAID" in line_upper:
                            current_section = "DEBITS"
                            continue
                        # Skip column header line
                        if line_upper.startswith("DATE") and "DESCRIPTION" in line_upper and "AMOUNT" in line_upper:
                            continue
                        # Skip section summary lines (e.g. "Total Deposits and Additions")
                        if "TOTAL" in line_upper and ("DEPOSITS" in line_upper or "WITHDRAWALS" in line_upper or "CHECKS" in line_upper):
                            continue
                        m = chase_txn_re.match(line_stripped)
                        if m and current_section:
                            try:
                                date_str, description, amount_str = m.group(1), m.group(2).strip(), m.group(3).replace(',', '')
                                amount = float(amount_str)
                                original_amount = amount
                                if amount < 0:
                                    amount = abs(amount)
                                if result["statement_period_start"]:
                                    year = result["statement_period_start"][:4]
                                    date_str_full = f"{year}-{date_str.replace('/', '-')}"
                                else:
                                    date_str_full = date_str
                                trans_type = PDFExtractor.determine_transaction_type(
                                    description, original_amount, current_section, bank_type="chase"
                                )
                                raw_payee = PDFExtractor.extract_payee_from_description(description)
                                payee = normalize_payee(description, raw_payee) or raw_payee or "N/A"
                                result["transactions"].append({
                                    "date": date_str_full,
                                    "amount": amount,
                                    "description": description[:300],
                                    "payee": payee or "N/A",
                                    "transaction_type": trans_type,
                                    "reference_number": None
                                })
                            except Exception:
                                pass
                # Apply AI enhancements (balances, payees, transaction types); skip if extraction is complete
                full_text_all = ""
                for page in pdf.pages:
                    full_text_all += page.extract_text() or ""
                transactions = result.get("transactions", [])
                has_deposits = any(t.get("transaction_type") == "DEPOSIT" for t in transactions)
                has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in transactions)
                skip_ai = has_deposits and has_withdrawals and len(transactions) >= 5
                result = PDFExtractor.apply_ai_enhancements(result, full_text_all, skip_if_complete=skip_ai)
        except Exception as e:
            result["error"] = f"Error extracting Chase statement: {str(e)}"
        
        return result
    
    @staticmethod
    def extract_huntington_statement(file_path: str, skip_statement_check_filter: bool = False) -> Dict[str, Any]:
        """Extract data from Huntington bank statement. If skip_statement_check_filter=True, check lines are kept (for statement+checks flow)."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "Huntington",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": []
        }
        
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() or ""
            
            # Extract account number (masked format: -----4497)
            account_match = re.search(r'Account:\s*-+(\d{4})', full_text, re.IGNORECASE)
            if account_match:
                result["account_number"] = account_match.group(1)
            
            # Extract account name/type
            account_name_match = re.search(r'(Huntington\s+\w+\s+Checking)', full_text, re.IGNORECASE)
            if account_name_match:
                result["account_name"] = account_name_match.group(1)
            
            # Extract statement period (format: 01/01/25 to 01/31/25)
            period_match = re.search(r'(\d{2}/\d{2}/\d{2})\s+to\s+(\d{2}/\d{2}/\d{2})', full_text)
            if period_match:
                try:
                    start_date = datetime.strptime(period_match.group(1), "%m/%d/%y")
                    end_date = datetime.strptime(period_match.group(2), "%m/%d/%y")
                    result["statement_period_start"] = start_date.strftime("%Y-%m-%d")
                    result["statement_period_end"] = end_date.strftime("%Y-%m-%d")
                except:
                    pass
            
            # Extract beginning balance
            beg_balance_match = re.search(r'Beginning Balance\s+\$?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if beg_balance_match:
                result["beginning_balance"] = float(beg_balance_match.group(1).replace(',', ''))
            
            # Extract ending balance
            end_balance_match = re.search(r'Ending Balance\s+\$?([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if end_balance_match:
                result["ending_balance"] = float(end_balance_match.group(1).replace(',', ''))
            
            # Extract total deposits (Credits)
            credits_match = re.search(r'Credits\s+\(\+\)\s+([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if credits_match:
                result["total_deposits"] = float(credits_match.group(1).replace(',', ''))
            
            # Extract total withdrawals (Debits)
            debits_match = re.search(r'Debits\s+\(-\)\s+([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if debits_match:
                result["total_withdrawals"] = float(debits_match.group(1).replace(',', ''))
            
            # Extract transactions from ALL pages (no limit to ensure complete extraction)
            # Look for "Other Credits (+)" or "Other Debits (-)" sections
            max_pages = len(pdf.pages)  # Process ALL pages to get all transactions
            current_section = None  # Track if we're in Credits or Debits section
            
            # Use a set to track seen transactions for better duplicate detection
            # Key: (date_mmdd, amount_rounded, description_hash)
            seen_transactions = set()
            
            def normalize_date_for_key(date_str: str) -> str:
                """Normalize date string to MM-DD format for duplicate detection."""
                # Extract MM/DD from various formats
                date_match = re.search(r'(\d{1,2})/(\d{1,2})', date_str)
                if date_match:
                    month = date_match.group(1).zfill(2)
                    day = date_match.group(2).zfill(2)
                    return f"{month}-{day}"
                return date_str[:5] if len(date_str) >= 5 else date_str
            
            def get_transaction_key(date_str: str, amount: float, description: str) -> tuple:
                """Generate a unique key for duplicate detection."""
                date_key = normalize_date_for_key(date_str)
                amount_rounded = round(amount, 2)  # Round to 2 decimals
                desc_hash = description[:50].upper().strip()  # First 50 chars, uppercase
                return (date_key, amount_rounded, desc_hash)
            
            for page_idx, page in enumerate(pdf.pages[:max_pages]):
                page_text = page.extract_text() or ""
                
                # Detect which section we're in based on page text
                # For Huntington, check for "Other Credits (+)" or "Other Debits (-)" explicitly
                # Reset section detection per page to handle pages with both sections
                page_section = None
                if 'Other Credits (+)' in page_text or 'Credits (+)' in page_text:
                    page_section = "CREDITS"
                elif 'Other Debits (-)' in page_text or 'Debits (-)' in page_text:
                    page_section = "DEBITS"
                else:
                    # Fallback to pattern-based detection
                    page_section = PDFExtractor.detect_transaction_section(page_text)
                
                if page_section:
                    current_section = page_section
                    logger.debug(f"Page {page_idx + 1}: Detected section = {current_section}")
                
                # Track transactions found from tables on this page
                transactions_from_tables_this_page = 0
                
                # Use find_tables() to get section per table (text above each table)
                tables_found = page.find_tables()
                if not tables_found:
                    tables_found = []
                tables = [t.extract() for t in tables_found] if tables_found else page.extract_tables()
                table_bboxes = [t.bbox for t in tables_found] if tables_found else [None] * len(tables)
                logger.debug(f"Page {page_idx + 1}: Found {len(tables)} tables")
                
                for table_idx, table in enumerate(tables):
                    if not table or len(table) < 2:
                        continue
                    # Section per table: text above this table (not whole page)
                    table_section = current_section
                    if table_idx < len(table_bboxes) and table_bboxes[table_idx] is not None:
                        try:
                            bbox = table_bboxes[table_idx]
                            cropped = page.crop((0, 0, page.width, bbox[1]))
                            text_above = (cropped.extract_text() or "").strip()
                            if 'Other Credits (+)' in text_above or 'Credits (+)' in text_above:
                                table_section = "CREDITS"
                            elif 'Other Debits (-)' in text_above or 'Debits (-)' in text_above:
                                table_section = "DEBITS"
                            elif 'Checks (-)' in text_above:
                                table_section = "CHECKS"
                            else:
                                table_section = PDFExtractor.detect_transaction_section(text_above) or current_section
                            logger.debug(f"Page {page_idx + 1} table {table_idx + 1}: section = {table_section}")
                        except Exception:
                            pass
                    # Also detect section from first row of table (e.g. "Other Debits (-)" in merged header cell)
                    if table and table[0]:
                        first_row_text = " ".join(str(c or "") for c in table[0]).upper()
                        if 'OTHER DEBITS (-)' in first_row_text or 'DEBITS (-)' in first_row_text:
                            table_section = "DEBITS"
                            logger.debug(f"Page {page_idx + 1} table {table_idx + 1}: section = DEBITS (from first row)")
                        elif 'OTHER CREDITS (+)' in first_row_text or 'CREDITS (+)' in first_row_text:
                            table_section = "CREDITS"
                            logger.debug(f"Page {page_idx + 1} table {table_idx + 1}: section = CREDITS (from first row)")
                        elif 'CHECKS (-)' in first_row_text:
                            table_section = "CHECKS"
                            logger.debug(f"Page {page_idx + 1} table {table_idx + 1}: section = CHECKS (from first row)")
                    # Skip Checks (-) section entirely: add check transactions only from check PDFs, not statement
                    if table_section == "CHECKS":
                        logger.info(f"Skipping Checks (-) table on page {page_idx + 1} (add from check PDFs)")
                        continue
                    
                    # If first row is section header ("Other Debits (-)") and second row is column header, use row 1 as header
                    header_row_idx = 0
                    data_start_idx = 1
                    if len(table) >= 3 and table[0]:
                        first_row_text = " ".join(str(c or "") for c in table[0]).upper()
                        second_has_header = any(
                            "date" in str(c).lower() or "amount" in str(c).lower()
                            for c in (table[1] if len(table) > 1 else []) if c
                        )
                        if ("OTHER DEBITS" in first_row_text or "OTHER CREDITS" in first_row_text or "DEBITS (-)" in first_row_text or "CREDITS (+)" in first_row_text) and second_has_header:
                            header_row_idx = 1
                            data_start_idx = 2
                            logger.debug(f"Page {page_idx + 1} table {table_idx + 1}: using row 1 as header (row 0 is section title)")
                    header_row = table[header_row_idx] if header_row_idx < len(table) else table[0]
                    data_rows = table[data_start_idx:] if data_start_idx < len(table) else table[1:]
                    has_date_col = any("date" in str(cell).lower() for cell in header_row if cell)
                    has_amount_col = any("amount" in str(cell).lower() or "$" in str(cell) for cell in header_row if cell)
                    has_desc_col = any("description" in str(cell).lower() or "desc" in str(cell).lower() or "detail" in str(cell).lower() for cell in header_row if cell)
                    is_transaction_table = (
                        (has_date_col and has_amount_col) or 
                        (len(header_row) >= 3 and has_date_col) or
                        (len(table) > 5 and len(header_row) >= 2)
                    )
                    
                    if is_transaction_table:
                        logger.info(f"Processing transaction table {table_idx + 1} on page {page_idx + 1} with {len(data_rows)} rows (section={table_section})")
                        row_section = table_section  # Per-row section (table may contain multiple sections)
                        for row_idx, row in enumerate(data_rows, data_start_idx):
                            if not row or len(row) < 2:
                                continue
                            # Per-row section: if this row is a section header, update section and skip row
                            row_text = " ".join(str(c or "") for c in row).upper()
                            if 'OTHER DEBITS (-)' in row_text or ('DEBITS (-)' in row_text and len(row_text) < 60):
                                row_section = "DEBITS"
                                continue
                            if 'OTHER CREDITS (+)' in row_text or ('CREDITS (+)' in row_text and len(row_text) < 60):
                                row_section = "CREDITS"
                                continue
                            if 'CHECKS (-)' in row_text:
                                row_section = "CHECKS"
                                continue
                            if row_section == "CHECKS":
                                continue  # Skip check rows (add from check PDFs only)
                            # Find date, amount, and description columns dynamically
                            # Try to find columns by content pattern
                            date_col_idx = None
                            amount_col_idx = None
                            desc_col_idx = None
                            
                            # Find date column (look for MM/DD pattern)
                            for col_idx, cell in enumerate(row):
                                if cell and re.search(r'\d{1,2}/\d{1,2}', str(cell)):
                                    date_col_idx = col_idx
                                    break
                            
                            # Find amount column (look for $ or decimal numbers)
                            for col_idx, cell in enumerate(row):
                                if cell and (re.search(r'[\d,]+\.\d{2}', str(cell)) or '$' in str(cell)):
                                    amount_col_idx = col_idx
                                    break
                            
                            # Find description column (usually the longest text column that's not date/amount)
                            for col_idx, cell in enumerate(row):
                                if cell and col_idx != date_col_idx and col_idx != amount_col_idx:
                                    cell_str = str(cell).strip()
                                    if len(cell_str) > 10:  # Description should be longer
                                        desc_col_idx = col_idx
                                        break
                            
                            # Fallback: use column positions if detection failed
                            if date_col_idx is None:
                                date_col_idx = 0
                            if amount_col_idx is None:
                                amount_col_idx = 1 if len(row) > 1 else 0
                            if desc_col_idx is None:
                                desc_col_idx = 2 if len(row) > 2 else (1 if amount_col_idx != 1 else 0)
                            
                            # Get date, amount, description from row
                            date_cell = str(row[date_col_idx]).strip() if date_col_idx < len(row) and row[date_col_idx] else ""
                            amount_cell = str(row[amount_col_idx]).strip() if amount_col_idx < len(row) and row[amount_col_idx] else ""
                            desc_cell = str(row[desc_col_idx]).strip() if desc_col_idx < len(row) and row[desc_col_idx] else ""
                            
                            # Skip if not a valid transaction row
                            if not date_cell or not amount_cell:
                                continue
                            
                            # Extract date (format: 01/02 or 1/2 or MM/DD/YY)
                            date_match = re.search(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)', date_cell)
                            if not date_match:
                                continue
                            
                            # Extract amount (format: 1,455.41 or 1455.41 or -1,455.41)
                            # Check for negative amounts (debits)
                            amount_match = re.search(r'([-]?[\d,]+\.\d{2})', amount_cell)
                            if not amount_match:
                                continue
                            
                            try:
                                date_str = date_match.group(1)
                                # Convert to full date using statement period year
                                # Fix date parsing: handle MM/DD format and add 1 day if needed
                                if result["statement_period_start"]:
                                    year = result["statement_period_start"][:4]
                                    # Parse the date properly
                                    date_parts = date_str.split('/')
                                    if len(date_parts) == 2:
                                        month = date_parts[0].zfill(2)
                                        day = date_parts[1].zfill(2)
                                        # For Huntington, dates might be off by one - check statement period
                                        # If the date is before the statement start, it might be in the next month
                                        try:
                                            parsed_date = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                                            # If date is before statement start, it's likely in the next month
                                            stmt_start = datetime.strptime(result["statement_period_start"], "%Y-%m-%d")
                                            if parsed_date < stmt_start and relativedelta:
                                                # Try next month
                                                parsed_date = parsed_date + relativedelta(months=1)
                                            date_str_full = parsed_date.strftime("%Y-%m-%d")
                                        except:
                                            date_str_full = f"{year}-{month}-{day}"
                                    else:
                                        date_str_full = f"{year}-{date_str.replace('/', '-')}"
                                else:
                                    date_str_full = date_str
                                
                                amount_str = amount_match.group(1).replace(',', '')
                                amount = float(amount_str)
                                
                                # Get description
                                description = desc_cell if desc_cell else ""
                                
                                # Check for duplicates using improved key
                                trans_key = get_transaction_key(date_str, abs(amount), description)
                                if trans_key in seen_transactions:
                                    continue  # Skip duplicate
                                seen_transactions.add(trans_key)
                                
                                # Normalize amount (store as positive, use type to indicate direction)
                                original_amount = amount
                                if amount < 0:
                                    amount = abs(amount)
                                
                                # Determine transaction type: section is primary (Other Credits (+)=deposit, Other Debits (-)=withdrawal)
                                trans_type = PDFExtractor.determine_transaction_type(
                                    description, original_amount, row_section
                                )
                                
                                raw_payee = PDFExtractor.extract_payee_from_description(description)
                                payee = normalize_payee(description, raw_payee) or raw_payee or "N/A"
                                date_str_full = result.get("statement_period_end") or date_str_full
                                
                                result["transactions"].append({
                                    "date": date_str_full,
                                    "amount": amount,
                                    "description": description[:200],
                                    "payee": payee or "N/A",
                                    "transaction_type": trans_type,
                                    "reference_number": None
                                })
                                transactions_from_tables_this_page += 1
                                
                                # Limit transactions to prevent memory issues (max 500)
                                if len(result["transactions"]) >= 500:
                                    break
                            except Exception as e:
                                logger.debug(f"Error processing table row: {e}")
                                continue
                        
                        # Break if we've hit the limit
                        if len(result["transactions"]) >= 500:
                            break
                
                # Fallback: Extract from text when few or no transactions from tables (catch missing rows)
                if transactions_from_tables_this_page < 3:
                    logger.debug(f"Trying text-based extraction for page {page_idx + 1} (got {transactions_from_tables_this_page} from tables)")
                    
                    # Look for transaction pattern: MM/DD Amount Description
                    # Pattern: Date (01/02 or 1/2) followed by amount and description
                    # More flexible patterns - but be more specific to avoid false matches
                    transaction_patterns = [
                        # Pattern 1: MM/DD amount description; include * and # (e.g. ATT*BILL, KROGER#7)
                        re.compile(r'(\d{1,2}/\d{1,2})\s+([-]?[\d,]+\.\d{2})\s+([A-Za-z0-9\s,\-\.\*#]+?)(?=\n\s*\d{1,2}/\d{1,2}|\n\n|$)', re.MULTILINE),
                        # Pattern 2: More permissive (any non-newline)
                        re.compile(r'(\d{1,2}/\d{1,2})\s+([-]?[\d,]+\.\d{2})\s+([^\n]+?)(?=\n\d{1,2}/\d{1,2}|\n\n|$)', re.MULTILINE),
                    ]
                    
                    matches = []
                    for pattern in transaction_patterns:
                        matches = pattern.findall(page_text)
                        if matches:
                            logger.info(f"Found {len(matches)} transaction matches using text pattern on page {page_idx + 1}")
                            break
                    
                    for match in matches:
                        try:
                            date_str = match[0]
                            amount_str = match[1].replace(',', '')
                            description = match[2].strip()
                            
                            # Skip empty matches
                            if not date_str or not amount_str:
                                continue
                            
                            amount = float(amount_str)
                            
                            # Check for duplicates using improved key
                            trans_key = get_transaction_key(date_str, abs(amount), description)
                            if trans_key in seen_transactions:
                                continue  # Skip duplicate
                            
                            # Convert to full date (same logic as table extraction)
                            if result["statement_period_start"]:
                                year = result["statement_period_start"][:4]
                                date_parts = date_str.split('/')
                                if len(date_parts) == 2:
                                    month = date_parts[0].zfill(2)
                                    day = date_parts[1].zfill(2)
                                    try:
                                        parsed_date = datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d")
                                        stmt_start = datetime.strptime(result["statement_period_start"], "%Y-%m-%d")
                                        if parsed_date < stmt_start and relativedelta:
                                            parsed_date = parsed_date + relativedelta(months=1)
                                        date_str_full = parsed_date.strftime("%Y-%m-%d")
                                    except:
                                        date_str_full = f"{year}-{month}-{day}"
                                else:
                                    date_str_full = f"{year}-{date_str.replace('/', '-')}"
                            else:
                                date_str_full = date_str
                            
                            # Normalize amount (store as positive, use type to indicate direction)
                            original_amount = amount
                            if amount < 0:
                                amount = abs(amount)
                            
                            # Mark as seen before adding
                            seen_transactions.add(trans_key)
                            
                            # Huntington: use statement period end date
                            date_str_full = result.get("statement_period_end") or date_str_full
                            trans_type = PDFExtractor.determine_transaction_type(
                                description, original_amount, current_section
                            )
                            raw_payee = PDFExtractor.extract_payee_from_description(description)
                            payee = normalize_payee(description, raw_payee) or raw_payee or "N/A"
                            result["transactions"].append({
                                "date": date_str_full,
                                "amount": amount,
                                "description": description[:200],
                                "payee": payee,
                                "transaction_type": trans_type,
                                "reference_number": None
                            })
                            if len(result["transactions"]) >= 500:
                                break
                        except Exception as e:
                            logger.debug(f"Error processing text match: {e}")
                            continue
                else:
                    logger.debug(f"Skipping text extraction for page {page_idx + 1} (found {transactions_from_tables_this_page} from tables)")
                
                # Break if we've hit the limit
                if len(result["transactions"]) >= 500:
                    break
            
            # Huntington: filter out statement-line check transactions (payee from check PDFs; rules in config)
            # Skip when statement+checks flow will enrich check lines from attached check images
            if not skip_statement_check_filter:
                before_count = len(result["transactions"])
                result["transactions"] = filter_statement_check_transactions(result["transactions"])
                filtered_count = before_count - len(result["transactions"])
                if filtered_count > 0:
                    logger.info(f"Huntington: filtered out {filtered_count} check-only transaction(s) (add from check PDFs)")

            # Huntington: set every transaction date to statement period end (last day of month)
            stmt_end = result.get("statement_period_end")
            if stmt_end:
                for t in result["transactions"]:
                    t["date"] = stmt_end
                logger.debug(f"Huntington: set all transaction dates to statement end {stmt_end}")

            # Apply AI enhancements (skip if extraction is complete)
            has_deposits = any(t.get("transaction_type") == "DEPOSIT" for t in result.get("transactions", []))
            has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in result.get("transactions", []))
            skip_ai = has_deposits and has_withdrawals and len(result.get("transactions", [])) >= 5
            result = PDFExtractor.apply_ai_enhancements(result, full_text, skip_if_complete=skip_ai)
        
        return result
    
    @staticmethod
    def extract_us_bank_statement(file_path: str) -> Dict[str, Any]:
        """Extract data from US Bank statement."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "US Bank",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": []
        }
        
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() or ""
            
            # Extract account number (format: 1 301 1962 3960 or 1-301-1962-3960)
            account_match = re.search(r'Account Number:\s*([\d\s-]+)', full_text, re.IGNORECASE)
            if account_match:
                result["account_number"] = account_match.group(1).strip().replace(' ', '')
            
            # Extract account name/type
            account_name_match = re.search(r'(SILVER BUSINESS CHECKING|GOLD BUSINESS CHECKING|BUSINESS CHECKING)', full_text, re.IGNORECASE)
            if account_name_match:
                result["account_name"] = account_name_match.group(1)
            
            # Extract statement period (format: Jan 2, 2025 through Jan 31, 2025)
            period_match = re.search(r'(\w+\s+\d{1,2},\s+\d{4})\s+through\s+(\w+\s+\d{1,2},\s+\d{4})', full_text, re.IGNORECASE)
            if period_match:
                try:
                    start_date = datetime.strptime(period_match.group(1), "%b %d, %Y")
                    end_date = datetime.strptime(period_match.group(2), "%b %d, %Y")
                    result["statement_period_start"] = start_date.strftime("%Y-%m-%d")
                    result["statement_period_end"] = end_date.strftime("%Y-%m-%d")
                except:
                    pass
            
            # Extract beginning balance
            beg_balance_match = re.search(r'Beginning Balance on \w+\s+\d+\s+\$\s*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if beg_balance_match:
                result["beginning_balance"] = float(beg_balance_match.group(1).replace(',', ''))
            
            # Extract ending balance
            end_balance_match = re.search(r'Ending Balance on \w+\s+\d+,\s+\d{4}\s+\$\s*([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if end_balance_match:
                result["ending_balance"] = float(end_balance_match.group(1).replace(',', ''))
            
            # Extract total deposits
            customer_deposits_match = re.search(r'Customer Deposits\s+\d+\s+([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            other_deposits_match = re.search(r'Other Deposits\s+\d+\s+([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if customer_deposits_match and other_deposits_match:
                result["total_deposits"] = float(customer_deposits_match.group(1).replace(',', '')) + float(other_deposits_match.group(1).replace(',', ''))
            
            # Extract total withdrawals
            withdrawals_match = re.search(r'Other Withdrawals\s+\d+\s+([\d,]+\.?\d*)', full_text, re.IGNORECASE)
            if withdrawals_match:
                result["total_withdrawals"] = float(withdrawals_match.group(1).replace(',', ''))
            
            # US Bank: line-by-line extraction using section state machine (extract_text only, no tables)
            # Section headers: Other Deposits / (continued), Other Withdrawals / (continued), Checks Presented...
            # Type from section + amount sign (amount ending with "-" = withdrawal)
            AMOUNT_REGEX = re.compile(r"^\$?\s*\d{1,3}(,\d{3})*\.\d{2}\s*$")  # deposit: amount only, no minus
            WITHDRAW_AMOUNT_REGEX = re.compile(r"^\$?\s*\d{1,3}(,\d{3})*\.\d{2}\s*-\s*$")  # withdrawal: amount-
            MONTH_PATTERN = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            _us_bank_check_data_line_re = re.compile(
                r"^\d{4,6}\*?\s+" + MONTH_PATTERN + r"\s+\d{1,2}\s+[\dA-Za-z]+\s+[\d,]+\.\d{2}",
                re.IGNORECASE,
            )
            CHECK_REGEX = re.compile(
                r"^\d{4,6}\*?\s+" + MONTH_PATTERN + r"\s+\d{1,2}\s+[\dA-Z]+\s+\d{1,3}(,\d{3})*\.\d{2}\s*$",
                re.IGNORECASE,
            )
            current_section = None
            buffer = []
            seen_us_bank = set()

            def parse_date_from_buffer(buf, year_str):
                """Parse date from first buffer line (e.g. 'Feb 18 Electronic Deposit')."""
                if not buf:
                    return None
                first = buf[0].strip()
                m = re.search(r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})", first, re.I)
                if not m or not year_str:
                    return None
                try:
                    dt = datetime.strptime(f"{m.group(1)} {m.group(2)} {year_str}", "%b %d %Y")
                    return dt.strftime("%Y-%m-%d")
                except Exception:
                    return None

            def parse_ref_from_buffer(buf):
                """Extract REF=... from buffer lines."""
                for line in buf:
                    ref_m = re.search(r"REF=([A-Z0-9]+)", line, re.I)
                    if ref_m:
                        return ref_m.group(1)
                return None

            def parse_payee_from_buffer(buf, prefix="From"):
                """Extract payee from 'From X' or 'To X' line in buffer."""
                for line in buf:
                    line = line.strip()
                    if line.upper().startswith(prefix.upper() + " "):
                        return line[len(prefix) :].strip()
                return None

            year_str = (result["statement_period_start"] or "")[:4] or None

            for page in pdf.pages:
                page_text = page.extract_text() or ""
                lines = page_text.split("\n")

                for line in lines:
                    line_stripped = line.strip()
                    if not line_stripped:
                        continue

                    # 1. Detect section (do not add section header to buffer; do not overwrite check section)
                    if (current_section != "check") and (
                        "Other Deposits" in line_stripped
                        or ("continued" in line_stripped.lower() and "deposit" in line_stripped.lower() and "other" in line_stripped.lower())
                    ):
                        current_section = "deposit"
                        buffer = []
                        continue
                    if (current_section != "check") and (
                        "Other Withdrawals" in line_stripped
                        or ("continued" in line_stripped.lower() and "withdrawal" in line_stripped.lower() and "other" in line_stripped.lower())
                    ):
                        current_section = "withdrawal"
                        buffer = []
                        continue
                    # Enter check section: section title ("Checks Presented"), table header ("Check Date" + "Ref Number"/"Amount"), or "Checks Paid" header
                    if (
                        "Checks Presented" in line_stripped
                        or ("Check Date" in line_stripped and ("Ref Number" in line_stripped or "Amount" in line_stripped))
                        or ("Checks Paid" in line_stripped and "Check Date" in line_stripped)
                    ):
                        current_section = "check"
                        buffer = []
                        logger.debug("US Bank: entered check section")
                        continue
                    # Fallback: line looks like conventional check data (e.g. "5494 Apr 10 8912273496 105.68 ...")
                    if _us_bank_check_data_line_re.match(line_stripped):
                        current_section = "check"
                        buffer = []
                        # fall through to check section processing below (do not continue)

                    # 2. Deposit section
                    if current_section == "deposit":
                        # Single-line format: "Feb 5 Electronic Deposit From MERCHANT BNKCD 2,895.91" or "Feb 6 ... From DoorDash, Inc. 215.65"
                        one_line_dep = re.match(
                            r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+Electronic Deposit From\s+(.+)\s+([\d,]+\.\d{2})\s*$",
                            line_stripped,
                            re.IGNORECASE,
                        )
                        if one_line_dep and year_str:
                            try:
                                date_str = one_line_dep.group(1) + " " + one_line_dep.group(2)
                                payee = one_line_dep.group(3).strip()
                                amount = float(one_line_dep.group(4).replace(",", ""))
                                dt = datetime.strptime(f"{date_str} {year_str}", "%b %d %Y")
                                date_str_full = dt.strftime("%Y-%m-%d")
                                description = f"Electronic Deposit From {payee}"
                                payee = normalize_payee(description, payee) or payee
                                key = (date_str_full, round(amount, 2), description[:50])
                                if key not in seen_us_bank:
                                    seen_us_bank.add(key)
                                    result["transactions"].append({
                                        "date": date_str_full,
                                        "amount": amount,
                                        "description": description[:300],
                                        "payee": payee,
                                        "transaction_type": "DEPOSIT",
                                        "reference_number": None,
                                    })
                            except Exception:
                                pass
                            continue
                        # Multi-line: buffer until amount-only line
                        amount_only = re.sub(r"[\$\s]", "", line_stripped)
                        is_amount_line = bool(re.match(r"^\d{1,3}(,\d{3})*\.\d{2}$", amount_only)) and "-" not in line_stripped
                        if is_amount_line and buffer:
                            amt_m = re.search(r"([\d,]+\.\d{2})", line_stripped)
                            if amt_m:
                                try:
                                    amount = float(amt_m.group(1).replace(",", ""))
                                    date_str_full = parse_date_from_buffer(buffer, year_str)
                                    if date_str_full:
                                        ref_number = parse_ref_from_buffer(buffer)
                                        payee = parse_payee_from_buffer(buffer, "From")
                                        description = " ".join(buffer).replace("\n", " ").strip()[:300]
                                        payee = normalize_payee(description, payee) or payee
                                        key = (date_str_full, round(amount, 2), (description or "")[:50])
                                        if key not in seen_us_bank:
                                            seen_us_bank.add(key)
                                            result["transactions"].append({
                                                "date": date_str_full,
                                                "amount": amount,
                                                "description": description or "Electronic Deposit",
                                                "payee": payee,
                                                "transaction_type": "DEPOSIT",
                                                "reference_number": ref_number,
                                            })
                                except Exception:
                                    pass
                            buffer = []
                        elif not is_amount_line:
                            buffer.append(line_stripped)
                        continue

                    # 3. Withdrawal section
                    if current_section == "withdrawal":
                        # If this line looks like check data (e.g. "5494 Apr 10 8912273496 105.68 ..."), switch to check section
                        if _us_bank_check_data_line_re.match(line_stripped):
                            current_section = "check"
                            buffer = []
                            # fall through to check section (do not continue)
                        else:
                            # Single-line format: "Feb 6 Electronic Withdrawal To AES OHIO 1,560.40-"
                            one_line_wdraw = re.match(
                                r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+Electronic Withdrawal To\s+(.+)\s+([\d,]+\.\d{2})\s*-\s*$",
                                line_stripped,
                                re.IGNORECASE,
                            )
                            if one_line_wdraw and year_str:
                                try:
                                    date_str = one_line_wdraw.group(1) + " " + one_line_wdraw.group(2)
                                    payee = one_line_wdraw.group(3).strip()
                                    amount = float(one_line_wdraw.group(4).replace(",", ""))
                                    dt = datetime.strptime(f"{date_str} {year_str}", "%b %d %Y")
                                    date_str_full = dt.strftime("%Y-%m-%d")
                                    description = f"Electronic Withdrawal To {payee}"
                                    payee = normalize_payee(description, payee) or payee
                                    key = (date_str_full, round(amount, 2), description[:50])
                                    if key not in seen_us_bank:
                                        seen_us_bank.add(key)
                                        result["transactions"].append({
                                            "date": date_str_full,
                                            "amount": amount,
                                            "description": description[:300],
                                            "payee": payee,
                                            "transaction_type": "WITHDRAWAL",
                                            "reference_number": None,
                                        })
                                except Exception:
                                    pass
                                continue
                            if WITHDRAW_AMOUNT_REGEX.match(line_stripped.replace(",", "").replace("$", "").strip()) or (re.search(r"[\d,]+\.\d{2}\s*-\s*$", line_stripped) and buffer):
                                amt_m = re.search(r"([\d,]+)\.(\d{2})\s*-\s*$", line_stripped)
                                if amt_m and buffer:
                                    try:
                                        amount = float(amt_m.group(1).replace(",", "") + "." + amt_m.group(2))
                                        date_str_full = parse_date_from_buffer(buffer, year_str)
                                        if date_str_full:
                                            ref_number = parse_ref_from_buffer(buffer)
                                            payee = parse_payee_from_buffer(buffer, "To")
                                            description = " ".join(buffer).replace("\n", " ").strip()[:300]
                                            payee = normalize_payee(description, payee) or payee
                                            key = (date_str_full, round(amount, 2), (description or "")[:50])
                                            if key not in seen_us_bank:
                                                seen_us_bank.add(key)
                                                result["transactions"].append({
                                                    "date": date_str_full,
                                                    "amount": amount,
                                                    "description": description or "Electronic Withdrawal",
                                                    "payee": payee,
                                                    "transaction_type": "WITHDRAWAL",
                                                    "reference_number": ref_number,
                                                })
                                    except Exception:
                                        pass
                                buffer = []
                            else:
                                buffer.append(line_stripped)
                            continue

                    # 4. Check section: conventional (one or two checks per line) or electronic (one per line)
                    if current_section == "check":
                        # Skip section headers / column headers
                        if "Check Date" in line_stripped and "Ref Number" in line_stripped and "Amount" in line_stripped:
                            continue
                        if "Checks Presented" in line_stripped or "Gap in check" in line_stripped or "Conventional Checks Paid" in line_stripped:
                            continue
                        # Conventional: "5376 Feb 3 8013138533 900.00 5410* Feb 3 9214095420 2,349.00" (one or two checks per line)
                        check_block = re.compile(
                            r"(\d{4,6})\*?\s+(" + MONTH_PATTERN + r")\s+(\d{1,2})\s+([\dA-Za-z]+)\s+([\d,]+\.\d{2})",
                            re.IGNORECASE,
                        )
                        for m in check_block.finditer(line_stripped):
                            try:
                                check_num = m.group(1).rstrip("*")
                                # MONTH_PATTERN has one pair of parens, so (MONTH) adds a second; groups: 1=check_num, 2=month, 3=month(inner), 4=day, 5=ref, 6=amount
                                date_str = m.group(2) + " " + m.group(4)
                                amount = float(m.group(6).replace(",", ""))
                                if year_str:
                                    try:
                                        dt = datetime.strptime(f"{date_str} {year_str}", "%b %d %Y")
                                        date_str_full = dt.strftime("%Y-%m-%d")
                                    except Exception:
                                        continue
                                else:
                                    continue
                                key = (date_str_full, round(amount, 2), "Check " + check_num)
                                if key not in seen_us_bank:
                                    seen_us_bank.add(key)
                                    result["transactions"].append({
                                        "date": date_str_full,
                                        "amount": amount,
                                        "description": f"Check #{check_num}",
                                        "payee": None,
                                        "transaction_type": "WITHDRAWAL",
                                        "reference_number": check_num,
                                    })
                            except Exception:
                                pass
                        # Electronic: "5383 Feb 7 49.99 CHECK PYMT CHARTER COMMUNIC" (check_num date amount desc)
                        elec_check = re.match(
                            r"^(\d{4,6})\*?\s+(" + MONTH_PATTERN + r")\s+(\d{1,2})\s+([\d,]+\.\d{2})\s+(.+)$",
                            line_stripped,
                            re.IGNORECASE,
                        )
                        if elec_check and year_str:
                            try:
                                check_num = elec_check.group(1).rstrip("*")
                                # (MONTH_PATTERN) gives groups 2 and 3; group 4 = day, 5 = amount, 6 = desc
                                date_str = elec_check.group(2) + " " + elec_check.group(4)
                                amount = float(elec_check.group(5).replace(",", ""))
                                desc = elec_check.group(6).strip()[:200]
                                dt = datetime.strptime(f"{date_str} {year_str}", "%b %d %Y")
                                date_str_full = dt.strftime("%Y-%m-%d")
                                key = (date_str_full, round(amount, 2), "Check " + check_num)
                                if key not in seen_us_bank:
                                    seen_us_bank.add(key)
                                    result["transactions"].append({
                                        "date": date_str_full,
                                        "amount": amount,
                                        "description": desc or f"Check #{check_num}",
                                        "payee": None,
                                        "transaction_type": "WITHDRAWAL",
                                        "reference_number": check_num,
                                    })
                            except Exception:
                                pass
                        continue

                # Apply AI enhancements (balances, payees, transaction types); skip if extraction is complete
                transactions = result.get("transactions", [])
                has_deposits = any(t.get("transaction_type") == "DEPOSIT" for t in transactions)
                has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in transactions)
                skip_ai = has_deposits and has_withdrawals and len(transactions) >= 5
                result = PDFExtractor.apply_ai_enhancements(result, full_text, skip_if_complete=skip_ai)

            logger.info(f"US Bank: extracted {len(result['transactions'])} transactions (section state machine)")
        
        return result
    
    @staticmethod
    def extract_first_source_statement(file_path: str) -> Dict[str, Any]:
        """Extract data from 1st Source Bank statement.
        Format: ACCOUNT ACTIVITY with Date, Description, Deposit/Credit, Withdrawal/Debit.
        CHECKS section on page 1 with No, Date, Amount columns."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "1st Source Bank",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": [],
        }
        try:
            with pdfplumber.open(file_path) as pdf:
                full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
                text_upper = full_text.upper()

            # Metadata
            stmt_date_m = re.search(r"STATEMENT DATE\s+(\d{1,2})-(\d{1,2})-(\d{2,4})", full_text, re.IGNORECASE)
            if stmt_date_m:
                m, d, y = stmt_date_m.group(1), stmt_date_m.group(2), stmt_date_m.group(3)
                year = f"20{y}" if len(y) == 2 else y
                try:
                    result["statement_period_end"] = datetime.strptime(f"{m}-{d}-{year}", "%m-%d-%Y").strftime("%Y-%m-%d")
                except ValueError:
                    pass
            acct_m = re.search(r"ACCOUNT NO\.?\s*(\d+)", full_text, re.IGNORECASE)
            if acct_m:
                result["account_number"] = acct_m.group(1)
            acct_type_m = re.search(r"(BUSINESS VALUE CHECKING|CHECKING)", full_text, re.IGNORECASE)
            if acct_type_m:
                result["account_name"] = acct_type_m.group(1)
            beg_m = re.search(r"BEGINNING BALANCE\s*\.+\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if beg_m:
                result["beginning_balance"] = float(beg_m.group(1).replace(",", ""))
            end_m = re.search(r"ENDING ACCOUNT BALANCE\s*\.+\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if end_m:
                result["ending_balance"] = float(end_m.group(1).replace(",", ""))
            dep_m = re.search(r"PLUS\s+\d+\s+DEPOSITS AND OTHER CREDITS\s*\.+\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if dep_m:
                result["total_deposits"] = float(dep_m.group(1).replace(",", ""))
            wdr_m = re.search(r"MINUS\s+\d+\s+CHECKS, WITHDRAWALS, OTHER DEBITS\s*\.+\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if wdr_m:
                result["total_withdrawals"] = float(wdr_m.group(1).replace(",", ""))

            year_str = (result.get("statement_period_end") or "")[:4] or str(datetime.now().year)
            # 1st Source has columns: Date | Description | Deposit/Credit | Withdrawal/Debit.
            # Use amount word x0: x0 < threshold = Deposit/Credit, else Withdrawal/Debit.
            DEPOSIT_COLUMN_X_MAX = 380
            activity_re = re.compile(r"^(\d{1,2}-\d{1,2})\s+(.+?)\s+([\d,]+\.\d{2})\s*$")
            skip_re = re.compile(
                r"^(Date\s+Description|ACCOUNT ACTIVITY|DAILY BALANCE|CHECKS|No\.\s+Date|STATEMENT DATE|PAGE \d|ACCOUNT NO\.|VISIT |\*--|AS OF |https?://)",
                re.IGNORECASE
            )
            seen_keys = set()
            # Build (date_part, description, amount_str, is_deposit) from word positions
            activity_rows: List[tuple] = []
            with pdfplumber.open(file_path) as pdf:
                in_activity = False
                withdrawal_header_x = None
                for page in pdf.pages:
                    words = page.extract_words() or []
                    if not words:
                        continue
                    from collections import defaultdict
                    by_top = defaultdict(list)
                    for w in words:
                        top = round(w.get("top", 0) / 3) * 3
                        by_top[top].append(w)
                    for top in sorted(by_top.keys()):
                        line_words = sorted(by_top[top], key=lambda w: w.get("x0", 0))
                        line_text = " ".join(w.get("text", "") for w in line_words)
                        if "ACCOUNT" in line_text and "ACTIVITY" in line_text:
                            in_activity = True
                            continue
                        if in_activity and ("DAILY" in line_text and "BALANCE" in line_text):
                            break
                        if in_activity and "Withdrawal" in line_text and "Debit" in line_text:
                            for w in line_words:
                                if w.get("text") and re.match(r"^Withdrawal|Debit", w.get("text", ""), re.I):
                                    withdrawal_header_x = w.get("x0")
                                    break
                            continue
                        if not in_activity:
                            continue
                        date_part = None
                        amount_str = None
                        amount_x0 = None
                        desc_words = []
                        for w in line_words:
                            t = w.get("text", "")
                            if re.match(r"^\d{1,2}-\d{1,2}$", t):
                                date_part = t
                            elif re.match(r"^[\d,]+\.\d{2}$", t):
                                amount_str = t
                                amount_x0 = w.get("x0")
                            elif date_part is not None and amount_str is None:
                                desc_words.append(t)
                        if date_part and amount_str and amount_x0 is not None:
                            desc_part = " ".join(desc_words).strip()
                            if skip_re.match(desc_part) or len(desc_part) < 2:
                                continue
                            if re.match(r"^[\d,]+\.\d{2}\s+\d{1,2}-\d{1,2}\s+[\d,]+\.\d{2}", desc_part):
                                continue
                            threshold = withdrawal_header_x if withdrawal_header_x is not None else DEPOSIT_COLUMN_X_MAX
                            is_deposit = amount_x0 < threshold
                            activity_rows.append((date_part, desc_part, amount_str, is_deposit))
                    if in_activity:
                        page_text = " ".join(w.get("text", "") for w in (page.extract_words() or []))
                        if "DAILY" in page_text and "BALANCE" in page_text:
                            break
            # Build descriptions with continuation lines from full_text, and apply type from activity_rows
            lines = full_text.split("\n")
            i = 0
            row_idx = 0
            while i < len(lines):
                line = lines[i].strip()
                if not line:
                    i += 1
                    continue
                if "ACCOUNT ACTIVITY" in line:
                    i += 1
                    continue
                if "DAILY BALANCE" in line.upper():
                    break
                m = activity_re.match(line)
                if m:
                    date_part, desc_part, amt_str = m.group(1), m.group(2).strip(), m.group(3)
                    if skip_re.match(desc_part) or len(desc_part) < 2:
                        i += 1
                        continue
                    if re.match(r"^[\d,]+\.\d{2}\s+\d{1,2}-\d{1,2}\s+[\d,]+\.\d{2}", desc_part):
                        i += 1
                        continue
                    desc_lines = [desc_part]
                    j = i + 1
                    while j < len(lines):
                        next_line = lines[j].strip()
                        if not next_line or next_line.startswith("http") or "CONTINUED" in next_line:
                            j += 1
                            continue
                        if activity_re.match(next_line):
                            break
                        if re.match(r"^\d{1,2}-\d{1,2}\s+", next_line):
                            break
                        desc_lines.append(next_line)
                        j += 1
                    description = " ".join(desc_lines)[:300]
                    try:
                        amount = float(amt_str.replace(",", ""))
                        mm, dd = date_part.split("-")
                        date_str = datetime.strptime(f"{mm}/{dd}/{year_str}", "%m/%d/%Y").strftime("%Y-%m-%d")
                        is_deposit = False
                        if row_idx < len(activity_rows):
                            r_date, r_desc, r_amt, is_deposit = activity_rows[row_idx]
                            if r_date == date_part and abs(float(r_amt.replace(",", "")) - amount) < 0.01:
                                pass
                            else:
                                for r in activity_rows:
                                    if r[0] == date_part and abs(float(r[2].replace(",", "")) - amount) < 0.01:
                                        is_deposit = r[3]
                                        break
                        else:
                            for r in activity_rows:
                                if r[0] == date_part and abs(float(r[2].replace(",", "")) - amount) < 0.01:
                                    is_deposit = r[3]
                                    break
                        trans_type = "DEPOSIT" if is_deposit else "WITHDRAWAL"
                        row_idx += 1
                        key = (date_str, round(amount, 2), description[:60])
                        if key not in seen_keys:
                            seen_keys.add(key)
                            result["transactions"].append({
                                "date": date_str,
                                "amount": amount,
                                "description": description,
                                "payee": normalize_payee(description, description) or None,
                                "transaction_type": trans_type,
                                "reference_number": None,
                            })
                    except (ValueError, TypeError):
                        pass
                    i = j if j > i + 1 else i + 1
                    continue
                i += 1
            # Fallback: no word-position data, use keyword "DEPOSIT" in description
            if not activity_rows and full_text:
                in_activity = False
                i = 0
                while i < len(lines):
                    line = lines[i].strip()
                    if not line:
                        i += 1
                        continue
                    if "ACCOUNT ACTIVITY" in line:
                        in_activity = True
                        i += 1
                        continue
                    if in_activity and "DAILY BALANCE" in line.upper():
                        break
                    if in_activity:
                        m = activity_re.match(line)
                        if m:
                            date_part, desc_part, amt_str = m.group(1), m.group(2).strip(), m.group(3)
                            if skip_re.match(desc_part) or len(desc_part) < 2:
                                i += 1
                                continue
                            if re.match(r"^[\d,]+\.\d{2}\s+\d{1,2}-\d{1,2}\s+[\d,]+\.\d{2}", desc_part):
                                i += 1
                                continue
                            desc_lines = [desc_part]
                            j = i + 1
                            while j < len(lines):
                                next_line = lines[j].strip()
                                if not next_line or next_line.startswith("http") or "CONTINUED" in next_line:
                                    j += 1
                                    continue
                                if activity_re.match(next_line):
                                    break
                                if re.match(r"^\d{1,2}-\d{1,2}\s+", next_line):
                                    break
                                desc_lines.append(next_line)
                                j += 1
                            description = " ".join(desc_lines)[:300]
                            try:
                                amount = float(amt_str.replace(",", ""))
                                mm, dd = date_part.split("-")
                                date_str = datetime.strptime(f"{mm}/{dd}/{year_str}", "%m/%d/%Y").strftime("%Y-%m-%d")
                                trans_type = "DEPOSIT" if "DEPOSIT" in description.upper() else "WITHDRAWAL"
                                key = (date_str, round(amount, 2), description[:60])
                                if key not in seen_keys:
                                    seen_keys.add(key)
                                    result["transactions"].append({
                                        "date": date_str,
                                        "amount": amount,
                                        "description": description,
                                        "payee": normalize_payee(description, description) or None,
                                        "transaction_type": trans_type,
                                        "reference_number": None,
                                    })
                            except (ValueError, TypeError):
                                pass
                            i = j if j > i + 1 else i + 1
                            continue
                    i += 1

            # CHECKS section: "No. Date..........Amount" then rows like "1 1-22 5000.00 1252 1-16 951.50" (two per line)
            check_triplet_re = re.compile(r"(\d+)\*?\s+(\d{1,2}-\d{1,2})\s+([\d,]+\.\d{2})")
            checks_block_start = full_text.find("CHECKS")
            if checks_block_start >= 0:
                activity_start = full_text.find("ACCOUNT ACTIVITY")
                checks_text = full_text[checks_block_start : activity_start] if activity_start > checks_block_start else full_text[checks_block_start:]
                for line in checks_text.split("\n"):
                    line = line.strip()
                    if not line or ("No." in line and "Date" in line and "Amount" in line) or "DENOTES" in line or "CONTINUED" in line or line.startswith("*") or line.startswith("http"):
                        continue
                    for ch_m in check_triplet_re.finditer(line):
                        check_no, date_part, amt_str = ch_m.group(1), ch_m.group(2), ch_m.group(3)
                        try:
                            amount = float(amt_str.replace(",", ""))
                            mm, dd = date_part.split("-")
                            date_str = datetime.strptime(f"{mm}/{dd}/{year_str}", "%m/%d/%Y").strftime("%Y-%m-%d")
                            key = (date_str, amount, "Check " + check_no)
                            if key not in seen_keys:
                                seen_keys.add(key)
                                result["transactions"].append({
                                    "date": date_str,
                                    "amount": amount,
                                    "description": f"Check #{check_no}",
                                    "payee": None,
                                    "transaction_type": "CHECK",
                                    "reference_number": check_no,
                                })
                        except (ValueError, TypeError):
                            pass

            result["transactions"].sort(key=lambda t: (t.get("date") or "", t.get("amount") or 0))
            logger.info(f"1st Source Bank: extracted {len(result['transactions'])} transactions")
        except Exception as e:
            logger.exception(f"1st Source extraction failed: {e}")
            result["error"] = str(e)
        return result

    @staticmethod
    def _extract_fifth_third_deposit_block(full_text: str) -> Optional[str]:
        """Return the text block between 'Deposits / Credits' and 'Withdrawals / Debits' or 'Checks'."""
        if not full_text:
            return None
        # Find start: "Deposits / Credits" or "Deposits / Credits - continued" (flexible spacing)
        start_re = re.compile(
            r"Deposits\s*/\s*Credits(?:\s*-\s*continued)?",
            re.IGNORECASE
        )
        start_m = start_re.search(full_text)
        if not start_m:
            return None
        start_pos = start_m.end()
        # Find end: first "Withdrawals / Debits" or "Checks" after start
        rest = full_text[start_pos:]
        end_re = re.compile(
            r"Withdrawals\s*/\s*Debits(?:\s*-\s*continued)?|(?:^|\n)\s*Checks(?:\s*-\s*continued)?(?:\s|$)",
            re.IGNORECASE | re.MULTILINE
        )
        end_m = end_re.search(rest)
        end_pos = end_m.start() if end_m else len(rest)
        return rest[:end_pos].strip()

    @staticmethod
    def extract_fifth_third_statement(file_path: str) -> Dict[str, Any]:
        """Extract data from Fifth Third bank statement using PyMuPDF for text and AI for transaction rules."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "Fifth Third",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": [],
        }
        try:
            # Extract text with PyMuPDF (fitz) for Fifth Third; fallback to pdfplumber
            full_text = ""
            try:
                import fitz
                doc = fitz.open(file_path)
                full_text = "\n".join(page.get_text() for page in doc)
                doc.close()
                logger.info("Fifth Third: extracted text with PyMuPDF")
            except Exception as e:
                logger.info(f"Fifth Third: PyMuPDF not used ({e}), using pdfplumber for text")
                with pdfplumber.open(file_path) as pdf:
                    full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)

            # Metadata from full_text (regex)
            period_match = re.search(
                r"Statement Period Date:\s*(\d{1,2}/\d{1,2}/\d{2,4})\s*-\s*(\d{1,2}/\d{1,2}/\d{2,4})",
                full_text,
                re.IGNORECASE,
            )
            if period_match:
                try:
                    start_str, end_str = period_match.group(1).strip(), period_match.group(2).strip()
                    for fmt in ["%m/%d/%Y", "%m/%d/%y"]:
                        try:
                            start_dt = datetime.strptime(start_str, fmt)
                            end_dt = datetime.strptime(end_str, fmt)
                            result["statement_period_start"] = start_dt.strftime("%Y-%m-%d")
                            result["statement_period_end"] = end_dt.strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass

            acct_match = re.search(r"Account Number:\s*(\d+)", full_text, re.IGNORECASE)
            if acct_match:
                result["account_number"] = acct_match.group(1)

            acct_type_match = re.search(r"Account Type:\s*(.+?)(?:\n|$)", full_text, re.IGNORECASE)
            if acct_type_match:
                result["account_name"] = acct_type_match.group(1).strip()

            if result["statement_period_end"]:
                try:
                    end_dt = datetime.strptime(result["statement_period_end"], "%Y-%m-%d")
                    period_end_mmdd = end_dt.strftime("%m/%d")
                    balance_block = ""
                    if "Daily Balance Summary" in full_text or "Daily Balance" in full_text:
                        idx = full_text.upper().find("DAILY BALANCE")
                        if idx >= 0:
                            balance_block = full_text[idx : idx + 1500]
                    search_text = balance_block or full_text
                    end_bal_m = re.search(
                        re.escape(period_end_mmdd) + r"\s+([\d,]+\.\d{2})",
                        search_text,
                    )
                    if end_bal_m:
                        result["ending_balance"] = float(end_bal_m.group(1).replace(",", ""))
                except (ValueError, TypeError):
                    pass

            # AI extraction: use OpenAI to set rules and extract transactions from raw text
            ai_transactions = BankStatementAIExtractor.extract_fifth_third_transactions_from_text(
                full_text,
                result.get("statement_period_end"),
            )
            if ai_transactions:
                result["transactions"] = ai_transactions
                # If AI returned no deposits but text has Deposits/Credits section, parse deposits from text
                deposit_count = sum(1 for t in ai_transactions if t.get("transaction_type") == "DEPOSIT")
                if deposit_count == 0:
                    deposit_block = PDFExtractor._extract_fifth_third_deposit_block(full_text)
                    if deposit_block:
                        year_str = (result.get("statement_period_end") or "")[:4] or str(datetime.now().year)
                        deposit_row_re = re.compile(r"^(\d{1,2}/\d{1,2})\s+([\d,]+\.\d{2})\s+(.+)$")
                        daily_balance_row_re = re.compile(r"\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s+\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}")
                        seen_dep = set()
                        for line in deposit_block.split("\n"):
                            line_stripped = line.strip()
                            if not line_stripped:
                                continue
                            if re.match(r"^\d+\s+items?\s+totaling", line_stripped, re.I):
                                continue
                            if re.match(r"^Date\s+Amount\s+Description", line_stripped, re.I):
                                continue
                            if re.sub(r"\s+", "", line_stripped.upper()) == "DATEAMOUNTDESCRIPTION":
                                continue
                            m = deposit_row_re.match(line_stripped)
                            if m:
                                mmdd, amt_str, desc = m.group(1), m.group(2), m.group(3).strip()
                                if re.match(r"^\d+\s*[is]?\s*$", desc, re.IGNORECASE):
                                    continue
                                if daily_balance_row_re.search(desc):
                                    continue
                                try:
                                    amount = float(amt_str.replace(",", ""))
                                    dt = datetime.strptime(f"{mmdd}/{year_str}", "%m/%d/%Y")
                                    date_str_full = dt.strftime("%Y-%m-%d")
                                    description = " ".join(desc.split())[:300]
                                    key = (date_str_full, round(amount, 2), description[:50])
                                    if key not in seen_dep:
                                        seen_dep.add(key)
                                        result["transactions"].append({
                                            "date": date_str_full,
                                            "amount": amount,
                                            "description": description,
                                            "payee": normalize_payee(description, description) or None,
                                            "transaction_type": "DEPOSIT",
                                            "reference_number": None,
                                        })
                                except (ValueError, TypeError):
                                    pass
                        if seen_dep:
                            result["transactions"].sort(key=lambda t: (t.get("date") or "", t.get("amount") or 0))
                            logger.info(f"Fifth Third: recovered {len(seen_dep)} deposits from text (AI had 0)")
                logger.info(f"Fifth Third: AI extracted {len(result['transactions'])} transactions")
            else:
                # Fallback: rule-based extraction with pdfplumber (page-by-page)
                year_str = (result["statement_period_end"] or "")[:4] or str(datetime.now().year)
                deposit_withdrawal_re = re.compile(r"^(\d{1,2}/\d{1,2})\s+([\d,]+\.\d{2})\s+(.+)$")
                check_row_re = re.compile(r"^(\d+)\s+[is]?\s*(\d{1,2}/\d{1,2})\s+([\d,]+\.\d{2})\s*$", re.IGNORECASE)
                daily_balance_row_re = re.compile(r"\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}\s+\d{1,2}/\d{1,2}\s+[\d,]+\.\d{2}")
                current_section = None
                seen_fifth_third = set()

                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text() or ""
                        for line in page_text.split("\n"):
                            line_stripped = line.strip()
                            if not line_stripped:
                                continue
                            line_upper = line_stripped.upper()
                            line_norm = re.sub(r"\s+", "", line_upper)

                            if "DEPOSITS / CREDITS" in line_upper or ("DEPOSITS" in line_norm and "CREDITS" in line_norm):
                                current_section = "deposit"
                                continue
                            if "WITHDRAWALS / DEBITS" in line_upper or ("WITHDRAWALS" in line_norm and "DEBITS" in line_norm):
                                current_section = "withdrawal"
                                continue
                            if line_upper.startswith("CHECKS") or line_norm.startswith("CHECKS"):
                                current_section = "check"
                                continue

                            if re.match(r"^\d+\s+items?\s+totaling", line_stripped, re.I):
                                continue
                            if re.match(r"^(?:Checks\s+)?\d+\s+checks\s+totaling", line_stripped, re.I):
                                continue
                            if re.match(r"^Date\s+Amount\s+Description\s*$", line_stripped, re.I):
                                continue
                            if re.sub(r"\s+", "", line_upper) == "DATEAMOUNTDESCRIPTION":
                                continue
                            if re.sub(r"\s+", "", line_upper) == "NUMBERI/SDATEPAIDAMOUNT" or (
                                "NUMBER" in line_norm and "PAID" in line_norm and len(line_stripped) < 50
                            ):
                                continue

                            check_m = check_row_re.match(line_stripped)
                            if check_m:
                                if current_section == "check":
                                    try:
                                        check_no, mmdd, amt_str = check_m.group(1), check_m.group(2), check_m.group(3)
                                        amount = float(amt_str.replace(",", ""))
                                        dt = datetime.strptime(f"{mmdd}/{year_str}", "%m/%d/%Y")
                                        date_str_full = dt.strftime("%Y-%m-%d")
                                        key = (date_str_full, round(amount, 2), "Check " + check_no)
                                        if key not in seen_fifth_third:
                                            seen_fifth_third.add(key)
                                            result["transactions"].append({
                                                "date": date_str_full,
                                                "amount": amount,
                                                "description": f"Check #{check_no}",
                                                "payee": None,
                                                "transaction_type": "CHECK",
                                                "reference_number": check_no,
                                            })
                                    except (ValueError, TypeError):
                                        pass
                                continue

                            if current_section in ("deposit", "withdrawal"):
                                m = deposit_withdrawal_re.match(line_stripped)
                                if m:
                                    mmdd, amt_str, desc = m.group(1), m.group(2), m.group(3).strip()
                                    if re.match(r"^\d+\s*[is]?\s*$", desc, re.IGNORECASE):
                                        continue
                                    if daily_balance_row_re.search(desc):
                                        continue
                                    try:
                                        amount = float(amt_str.replace(",", ""))
                                        dt = datetime.strptime(f"{mmdd}/{year_str}", "%m/%d/%Y")
                                        date_str_full = dt.strftime("%Y-%m-%d")
                                        description = " ".join(desc.split())[:300]
                                        key = (date_str_full, round(amount, 2), description[:50])
                                        if key not in seen_fifth_third:
                                            seen_fifth_third.add(key)
                                            result["transactions"].append({
                                                "date": date_str_full,
                                                "amount": amount,
                                                "description": description,
                                                "payee": normalize_payee(description, description) or None,
                                                "transaction_type": "DEPOSIT" if current_section == "deposit" else "WITHDRAWAL",
                                                "reference_number": None,
                                            })
                                    except (ValueError, TypeError):
                                        pass
                                continue

                logger.info(f"Fifth Third: fallback rule-based extracted {len(result['transactions'])} transactions")

            # Apply AI enhancements (balances, payees); skip type reclassification for Fifth Third
            transactions = result.get("transactions", [])
            has_deposits = any(t.get("transaction_type") == "DEPOSIT" for t in transactions)
            has_withdrawals = any(t.get("transaction_type") in ["WITHDRAWAL", "FEE"] for t in transactions)
            skip_ai = has_deposits and has_withdrawals and len(transactions) >= 5
            result = PDFExtractor.apply_ai_enhancements(result, full_text, skip_if_complete=skip_ai)

            logger.info(f"Fifth Third: extracted {len(result['transactions'])} transactions")
        except Exception as e:
            logger.exception(f"Fifth Third extraction failed: {e}")
            result["error"] = str(e)
        return result

    @staticmethod
    def extract_ohio_state_bank_statement(file_path: str) -> Dict[str, Any]:
        """Extract data from Ohio State Bank statement.
        Format: Account Activity with Post Date, Description, Debits, Credits, Balance.
        Rows can be single line (date description amount balance) or two lines (description then date amount balance)."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "Ohio State Bank",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": [],
        }
        try:
            with pdfplumber.open(file_path) as pdf:
                full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)

            # Metadata
            stmt_end = re.search(r"Statement Ending\s+(\d{2}/\d{2}/\d{4})", full_text, re.IGNORECASE)
            if stmt_end:
                try:
                    dt = datetime.strptime(stmt_end.group(1), "%m/%d/%Y")
                    result["statement_period_end"] = dt.strftime("%Y-%m-%d")
                except ValueError:
                    pass
            acct_m = re.search(r"Account Number\s+[X\d]+\s*(\d{4})|XXXXXX(\d{4})", full_text)
            if acct_m:
                result["account_number"] = acct_m.group(1) or acct_m.group(2)
            beg_m = re.search(r"Beginning Balance\s+\$?([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if beg_m:
                result["beginning_balance"] = float(beg_m.group(1).replace(",", ""))
            end_m = re.search(r"Ending Balance\s+\$?([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if end_m:
                # Prefer last occurrence (actual ending balance)
                for m in re.finditer(r"Ending Balance\s+\$?([\d,]+\.\d{2})", full_text, re.IGNORECASE):
                    result["ending_balance"] = float(m.group(1).replace(",", ""))

            # Account Activity: Post Date, Description, Debits, Credits, Balance
            # Row patterns: (1) MM/DD/YYYY description $amount $balance  (2) MM/DD/YYYY $amount $balance (desc on prev line)
            in_activity = False
            prev_description = ""
            seen = set()
            row_with_desc_re = re.compile(
                r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s*$"
            )
            row_amounts_only_re = re.compile(
                r"^(\d{2}/\d{2}/\d{4})\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})\s*$"
            )
            year_str = (result.get("statement_period_end") or "")[:4] or str(datetime.now().year)

            for line in full_text.split("\n"):
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                line_upper = line_stripped.upper()
                if "ACCOUNT ACTIVITY" in line_upper:
                    in_activity = True
                    continue
                if in_activity and "POST DATE" in line_upper and "DEBITS" in line_upper:
                    continue
                if in_activity and ("CHECKS CLEARED" in line_upper or "DAILY BALANCES" in line_upper or "OVERDRAFT" in line_upper):
                    break
                if in_activity:
                    # Skip Beginning/Ending Balance lines (metadata only)
                    if re.match(r"^\d{2}/\d{2}/\d{4}\s+Beginning Balance\s+\$", line_stripped, re.I):
                        continue
                    if re.match(r"^\d{2}/\d{2}/\d{4}\s+Ending Balance\s+\$", line_stripped, re.I):
                        continue
                    m = row_with_desc_re.match(line_stripped)
                    if m:
                        date_str, desc, amt_str, bal_str = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
                        prev_description = desc
                    else:
                        m = row_amounts_only_re.match(line_stripped)
                        if m:
                            date_str, amt_str, bal_str = m.group(1), m.group(2), m.group(3)
                            desc = prev_description
                        else:
                            # Description continuation (no date on this line)
                            if re.match(r"^\d{2}/\d{2}/\d{4}", line_stripped):
                                continue
                            prev_description = line_stripped[:200]
                            continue
                    try:
                        amount = float(amt_str.replace(",", ""))
                        balance = float(bal_str.replace(",", ""))
                        if "Beginning Balance" in desc or "Ending Balance" in desc:
                            continue
                        date_full = f"{year_str}-{date_str.replace('/', '-')}"
                        trans_type = "DEPOSIT" if "DEPOSIT" in desc.upper() else ("CHECK" if "CHECK #" in desc.upper() or "CHECK#" in desc.upper() else "WITHDRAWAL")
                        key = (date_full, round(amount, 2), (desc or "")[:50])
                        if key not in seen:
                            seen.add(key)
                            result["transactions"].append({
                                "date": date_full,
                                "amount": amount,
                                "description": (desc or "")[:300],
                                "payee": normalize_payee(desc, desc) or None,
                                "transaction_type": trans_type,
                                "reference_number": None,
                            })
                    except (ValueError, TypeError):
                        pass
            result["transactions"].sort(key=lambda t: (t.get("date") or "", t.get("amount") or 0))
            logger.info(f"Ohio State Bank: extracted {len(result['transactions'])} transactions")
        except Exception as e:
            logger.exception(f"Ohio State Bank extraction failed: {e}")
            result["error"] = str(e)
        return result

    @staticmethod
    def extract_wesbanco_statement(file_path: str) -> Dict[str, Any]:
        """Extract data from WesBanco bank statement.
        Format: DAILY ACTIVITY with Date, Description, Additions (= deposits), Subtractions (= withdrawals), Balance.
        PDF may be image-based (no text); try pdfplumber then PyMuPDF for text."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "WesBanco",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": [],
        }
        try:
            full_text = ""
            try:
                with pdfplumber.open(file_path) as pdf:
                    full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
            except Exception:
                pass
            if not full_text or len(full_text.strip()) < 50:
                try:
                    import fitz
                    doc = fitz.open(file_path)
                    full_text = "\n".join(page.get_text() for page in doc)
                    doc.close()
                except Exception:
                    pass
            if not full_text or len(full_text.strip()) < 50:
                logger.info("WesBanco: no extractable text (PDF may be image-based)")
                return result
            # Metadata
            period_m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})\s*[-–to through]+\s*(\d{1,2}/\d{1,2}/\d{2,4})", full_text, re.IGNORECASE)
            if period_m:
                try:
                    for fmt in ["%m/%d/%Y", "%m/%d/%y"]:
                        try:
                            s = datetime.strptime(period_m.group(1).strip(), fmt)
                            e = datetime.strptime(period_m.group(2).strip(), fmt)
                            result["statement_period_start"] = s.strftime("%Y-%m-%d")
                            result["statement_period_end"] = e.strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            acct_m = re.search(r"Account\s*(?:Number|#)?\s*[:\s]*([\d\s\-]+)", full_text, re.IGNORECASE)
            if acct_m:
                result["account_number"] = re.sub(r"\s+", "", acct_m.group(1).strip())
            beg_m = re.search(r"Beginning Balance\s*\$?\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if beg_m:
                result["beginning_balance"] = float(beg_m.group(1).replace(",", ""))
            for m in re.finditer(r"Ending Balance\s*\$?\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE):
                result["ending_balance"] = float(m.group(1).replace(",", ""))
            year_str = (result.get("statement_period_end") or "")[:4] or str(datetime.now().year)
            # DAILY ACTIVITY: Additions = deposits, Subtractions = withdrawals
            # Row format: MM-DD description amount balance (amount may be negative for Subtractions)
            in_daily = False
            seen = set()
            # Match: date (MM-DD), description, then amount (optional minus), then balance
            row_re = re.compile(r"^(\d{1,2}-\d{1,2})\s+(.+?)\s+(-?[\d,]+\.\d{2})\s+([\d,]+\.\d{2})\s*$")
            skip_re = re.compile(r"^(Date|Description|Additions|Subtractions|Balance|Beginning balance|Ending balance)", re.I)
            for line in full_text.split("\n"):
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                line_upper = line_stripped.upper()
                if "DAILY ACTIVITY" in line_upper:
                    in_daily = True
                    continue
                if in_daily and ("ADDITIONS" in line_upper and "SUBTRACTIONS" in line_upper):
                    continue
                if in_daily and re.match(r"^\d{1,2}-\d{1,2}\s+Beginning", line_stripped, re.I):
                    continue
                if in_daily and re.match(r"^\d{1,2}-\d{1,2}\s+Ending balance", line_stripped, re.I):
                    continue
                if in_daily:
                    m = row_re.match(line_stripped)
                    if m:
                        date_part, desc, amt_str, bal_str = m.group(1), m.group(2).strip(), m.group(3), m.group(4)
                        if skip_re.match(desc) or len(desc) < 2:
                            continue
                        try:
                            amount = float(amt_str.replace(",", ""))
                            abs_amount = abs(amount)
                            # Additions (positive) = DEPOSIT, Subtractions (negative) = WITHDRAWAL
                            trans_type = "DEPOSIT" if amount >= 0 else "WITHDRAWAL"
                            mm, dd = date_part.split("-")
                            date_full = f"{year_str}-{mm}-{dd}"
                            key = (date_full, round(abs_amount, 2), (desc or "")[:50])
                            if key not in seen:
                                seen.add(key)
                                result["transactions"].append({
                                    "date": date_full,
                                    "amount": abs_amount,
                                    "description": (desc or "")[:300],
                                    "payee": normalize_payee(desc, desc) or None,
                                    "transaction_type": trans_type,
                                    "reference_number": None,
                                })
                        except (ValueError, TypeError):
                            pass
            result["transactions"].sort(key=lambda t: (t.get("date") or "", t.get("amount") or 0))
            logger.info(f"WesBanco: extracted {len(result['transactions'])} transactions")
        except Exception as e:
            logger.exception(f"WesBanco extraction failed: {e}")
            result["error"] = str(e)
        return result

    @staticmethod
    def extract_wesbanco_from_text(raw_text: str) -> Dict[str, Any]:
        """Parse WesBanco statement from raw text (e.g. from OCR). Same format as extract_wesbanco_statement.
        DAILY ACTIVITY: Additions = deposits, Subtractions = withdrawals. Returns result dict with transactions."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "WesBanco",
            "account_number": None,
            "account_name": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "total_deposits": None,
            "total_withdrawals": None,
            "transactions": [],
        }
        if not raw_text or len(raw_text.strip()) < 20:
            return result
        try:
            full_text = raw_text
            period_m = re.search(r"(\d{1,2}/\d{1,2}/\d{2,4})\s*[-–to through]+\s*(\d{1,2}/\d{1,2}/\d{2,4})", full_text, re.IGNORECASE)
            if period_m:
                try:
                    for fmt in ["%m/%d/%Y", "%m/%d/%y"]:
                        try:
                            s = datetime.strptime(period_m.group(1).strip(), fmt)
                            e = datetime.strptime(period_m.group(2).strip(), fmt)
                            result["statement_period_start"] = s.strftime("%Y-%m-%d")
                            result["statement_period_end"] = e.strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            acct_m = re.search(r"Account\s*(?:Number|#)?\s*[:\s]*([\d\s\-]+)", full_text, re.IGNORECASE)
            if acct_m:
                result["account_number"] = re.sub(r"\s+", "", acct_m.group(1).strip())
            beg_m = re.search(r"Beginning Balance\s*\$?\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE)
            if beg_m:
                result["beginning_balance"] = float(beg_m.group(1).replace(",", ""))
            for m in re.finditer(r"Ending Balance\s*\$?\s*([\d,]+\.\d{2})", full_text, re.IGNORECASE):
                result["ending_balance"] = float(m.group(1).replace(",", ""))
            year_str = (result.get("statement_period_end") or "")[:4] or str(datetime.now().year)
            in_daily = False
            seen = set()
            # 4-column: date, description, amount (signed), balance
            row_re = re.compile(r"^(\d{1,2})[-/](\d{1,2})\s+(.+?)\s+\$?\s*(-?[\d,]+\.\d{2})\s+\$?\s*([\d,]+\.\d{2})\s*$")
            # 5-column: date, description, additions, subtractions, balance (WesBanco style)
            row_5_re = re.compile(r"^(\d{1,2})[-/](\d{1,2})\s+(.+?)\s+\$?\s*([\d,]+\.\d{2})\s+\$?\s*([\d,]+\.\d{2})\s+\$?\s*([\d,]+\.\d{2})\s*$")
            skip_re = re.compile(r"^(Date|Description|Additions|Subtractions|Balance|Beginning balance|Ending balance)", re.I)
            # Section headers that start the transaction table (OCR may vary)
            activity_headers = ("DAILY ACTIVITY", "ACCOUNT ACTIVITY", "CHECKING ACTIVITY", "ACTIVITY SUMMARY", "TRANSACTION ACTIVITY")
            for line in full_text.split("\n"):
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                line_upper = line_stripped.upper()
                if any(h in line_upper for h in activity_headers):
                    in_daily = True
                    continue
                if in_daily and ("ADDITIONS" in line_upper and "SUBTRACTIONS" in line_upper):
                    continue
                if in_daily and re.match(r"^\d{1,2}[-/]\d{1,2}\s+Beginning", line_stripped, re.I):
                    continue
                if in_daily and re.match(r"^\d{1,2}[-/]\d{1,2}\s+Ending balance", line_stripped, re.I):
                    continue
                if in_daily:
                    # Try 5-column first (date, desc, additions, subtractions, balance)
                    m5 = row_5_re.match(line_stripped)
                    if m5:
                        mm, dd = m5.group(1), m5.group(2)
                        desc = m5.group(3).strip()
                        add_str, sub_str, _ = m5.group(4), m5.group(5), m5.group(6)
                        if skip_re.match(desc) or len(desc) < 2:
                            continue
                        desc_clean = PDFExtractor.sanitize_ocr_description(desc)
                        payee = normalize_payee(desc_clean, desc_clean) or None
                        try:
                            add_val = float(add_str.replace(",", "").replace("$", ""))
                            sub_val = float(sub_str.replace(",", "").replace("$", ""))
                            date_full = f"{year_str}-{mm}-{dd}"
                            if add_val > 0:
                                key = (date_full, round(add_val, 2), (desc_clean or "")[:50], "D")
                                if key not in seen:
                                    seen.add(key)
                                    result["transactions"].append({
                                        "date": date_full,
                                        "amount": add_val,
                                        "description": (desc_clean or "")[:300],
                                        "payee": payee,
                                        "transaction_type": "DEPOSIT",
                                        "reference_number": None,
                                    })
                            if sub_val > 0:
                                key = (date_full, round(sub_val, 2), (desc_clean or "")[:50], "W")
                                if key not in seen:
                                    seen.add(key)
                                    result["transactions"].append({
                                        "date": date_full,
                                        "amount": sub_val,
                                        "description": (desc_clean or "")[:300],
                                        "payee": payee,
                                        "transaction_type": "WITHDRAWAL",
                                        "reference_number": None,
                                    })
                        except (ValueError, TypeError):
                            pass
                        continue
                    m = row_re.match(line_stripped)
                    if m:
                        mm, dd, desc = m.group(1), m.group(2), m.group(3).strip()
                        amt_str, bal_str = m.group(4), m.group(5)
                        if skip_re.match(desc) or len(desc) < 2:
                            continue
                        desc_clean = PDFExtractor.sanitize_ocr_description(desc)
                        payee = normalize_payee(desc_clean, desc_clean) or None
                        try:
                            amount = float(amt_str.replace(",", "").replace("$", ""))
                            abs_amount = abs(amount)
                            trans_type = "DEPOSIT" if amount >= 0 else "WITHDRAWAL"
                            date_full = f"{year_str}-{mm}-{dd}"
                            key = (date_full, round(abs_amount, 2), (desc_clean or "")[:50])
                            if key not in seen:
                                seen.add(key)
                                result["transactions"].append({
                                    "date": date_full,
                                    "amount": abs_amount,
                                    "description": (desc_clean or "")[:300],
                                    "payee": payee,
                                    "transaction_type": trans_type,
                                    "reference_number": None,
                                })
                        except (ValueError, TypeError):
                            pass
            # Fallback: no section header found but look for 4-column lines anywhere (OCR may miss header)
            if not result["transactions"] and ("Balance" in full_text or "balance" in full_text or "Activity" in full_text):
                for line in full_text.split("\n"):
                    line_stripped = line.strip()
                    if not line_stripped or len(line_stripped) < 15:
                        continue
                    m = row_re.match(line_stripped)
                    if m:
                        mm, dd, desc = m.group(1), m.group(2), m.group(3).strip()
                        amt_str = m.group(4)
                        if skip_re.match(desc) or len(desc) < 2:
                            continue
                        desc_clean = PDFExtractor.sanitize_ocr_description(desc)
                        payee = normalize_payee(desc_clean, desc_clean) or None
                        try:
                            amount = float(amt_str.replace(",", "").replace("$", ""))
                            abs_amount = abs(amount)
                            if abs_amount < 0.01:
                                continue
                            trans_type = "DEPOSIT" if amount >= 0 else "WITHDRAWAL"
                            date_full = f"{year_str}-{mm}-{dd}"
                            key = (date_full, round(abs_amount, 2), (desc_clean or "")[:50])
                            if key not in seen:
                                seen.add(key)
                                result["transactions"].append({
                                    "date": date_full,
                                    "amount": abs_amount,
                                    "description": (desc_clean or "")[:300],
                                    "payee": payee,
                                    "transaction_type": trans_type,
                                    "reference_number": None,
                                })
                        except (ValueError, TypeError):
                            pass
                if result["transactions"]:
                    logger.info(f"WesBanco (from text): fallback parsing extracted {len(result['transactions'])} transactions")
            result["transactions"].sort(key=lambda t: (t.get("date") or "", t.get("amount") or 0))
            logger.info(f"WesBanco (from text): extracted {len(result['transactions'])} transactions")
        except Exception as e:
            logger.warning(f"WesBanco parse from text failed: {e}")
        return result

    @staticmethod
    def extract_from_pdf(file_path: str, original_filename: Optional[str] = None, skip_statement_check_filter: bool = False) -> Dict[str, Any]:
        """
        Main extraction method - detects bank type and extracts accordingly.

        Args:
            file_path: Path to PDF file
            original_filename: Optional original upload filename (used for bank detection when PDF has no text, e.g. image-based WesBanco)
            skip_statement_check_filter: If True, do not filter out check-line transactions (for statement+checks flow)
        Returns:
            Dictionary with extracted data
        """
        try:
            # Read first page to detect bank type
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) == 0:
                    return {"error": "Empty PDF file"}

                first_page_text = pdf.pages[0].extract_text() or ""
                bank_type = PDFExtractor.detect_bank_type(first_page_text)
                # Fallback for image-based PDFs: infer from path or original filename
                if not bank_type:
                    path_lower = (file_path or "").lower()
                    name_lower = (original_filename or "").lower()
                    if "wesbanco" in path_lower or "wesbanco" in name_lower:
                        bank_type = "wesbanco"
                    elif ("ohio" in path_lower and "state" in path_lower and "bank" in path_lower) or (
                        "ohio" in name_lower and "state" in name_lower and "bank" in name_lower
                    ):
                        bank_type = "ohio_state_bank"
            
            # Extract based on bank type
            if bank_type == "chase":
                return PDFExtractor.extract_chase_statement(file_path)
            elif bank_type == "huntington":
                return PDFExtractor.extract_huntington_statement(file_path, skip_statement_check_filter=skip_statement_check_filter)
            elif bank_type == "us_bank":
                return PDFExtractor.extract_us_bank_statement(file_path)
            elif bank_type == "fifth_third":
                return PDFExtractor.extract_fifth_third_statement(file_path)
            elif bank_type == "first_source":
                return PDFExtractor.extract_first_source_statement(file_path)
            elif bank_type == "ohio_state_bank":
                return PDFExtractor.extract_ohio_state_bank_statement(file_path)
            elif bank_type == "wesbanco":
                return PDFExtractor.extract_wesbanco_statement(file_path)
            else:
                # Generic extraction for unknown bank
                return PDFExtractor.extract_generic(file_path)
        
        except Exception as e:
            return {"error": f"Extraction failed: {str(e)}"}
    
    @staticmethod
    def extract_generic(file_path: str) -> Dict[str, Any]:
        """Generic extraction for unknown bank formats."""
        result = {
            "document_type": "bank_statement",
            "bank_name": "Unknown",
            "account_number": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "beginning_balance": None,
            "ending_balance": None,
            "transactions": []
        }
        
        with pdfplumber.open(file_path) as pdf:
            full_text = ""
            for page in pdf.pages:
                full_text += page.extract_text() or ""
            
            # Try to extract any dates
            date_matches = re.findall(r'(\d{1,2}/\d{1,2}/\d{2,4})', full_text)
            # Try to extract any amounts
            amount_matches = re.findall(r'\$?([\d,]+\.\d{2})', full_text)
            
            result["raw_text"] = full_text[:1000]  # Store first 1000 chars for manual review
        
        return result

