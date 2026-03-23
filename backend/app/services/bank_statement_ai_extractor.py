"""
AI-Enhanced Bank Statement Extractor using OpenAI GPT-4.
Improves date parsing, payee extraction, and balance extraction.
Also provides AI-powered format-agnostic bank statement extraction.
"""
import json
import re
import base64
import io
import logging
import hashlib
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

# Simple in-memory cache for AI extraction results
# Key: (file_hash, page_num), Value: extraction_result
_ai_extraction_cache: Dict[tuple, Dict[str, Any]] = {}
_cache_max_size = 100  # Limit cache size to prevent memory issues

# Try to import OpenAI
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
    _openai_client = None
    
    def get_openai_client():
        global _openai_client
        if _openai_client is None:
            if settings.OPENAI_API_KEY:
                _openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
                logger.info("OpenAI client initialized for bank statement extraction")
            else:
                return None
        return _openai_client
except ImportError:
    OPENAI_AVAILABLE = False
    def get_openai_client():
        return None


class BankStatementAIExtractor:
    """AI-enhanced extraction for bank statements using GPT-4."""
    
    @staticmethod
    def classify_transaction_types_ai(
        transactions: List[Dict[str, Any]],
        statement_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use AI to classify transaction types (DEPOSIT, WITHDRAWAL, FEE) for all transactions.
        This is more accurate than rule-based classification and works across all bank formats.
        
        Args:
            transactions: List of transactions with description, amount, and optional current type
            statement_context: Optional context like statement period, bank name, business type
            
        Returns:
            List of transactions with AI-classified transaction_type
        """
        if not OPENAI_AVAILABLE:
            logger.debug("OpenAI not available, returning original transactions")
            return transactions
        
        client = get_openai_client()
        if client is None:
            logger.debug("OpenAI client not initialized, returning original transactions")
            return transactions
        
        if not transactions:
            return transactions
        
        try:
            # Prepare context for AI
            context_info = ""
            if statement_context:
                if statement_context.get("statement_period_start"):
                    context_info += f"Statement period: {statement_context.get('statement_period_start')} to {statement_context.get('statement_period_end', '')}\n"
                if statement_context.get("bank_name"):
                    context_info += f"Bank: {statement_context.get('bank_name')}\n"
                if statement_context.get("business_type"):
                    context_info += f"Business type: {statement_context.get('business_type')}\n"
            
            # Process transactions in batches (to avoid token limits and improve speed)
            batch_size = 30  # Larger batch for type classification (simpler task)
            classified_transactions = []
            
            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i + batch_size]
                
                # Prepare simplified transaction data for AI (only what's needed for classification)
                batch_data = []
                for trans in batch:
                    batch_data.append({
                        "description": trans.get("description", ""),
                        "amount": trans.get("amount", 0),
                        "current_type": trans.get("transaction_type", "UNKNOWN")  # Current classification
                    })
                
                transactions_json = json.dumps(batch_data, indent=2)
                
                system_prompt = """You are an expert at classifying bank statement transactions.
Your task is to determine the correct transaction type (DEPOSIT, WITHDRAWAL, or FEE) based on the description and amount.

Transaction Type Classification Rules:

DEPOSIT (Money coming INTO the account):
- Payment processing: STRIPE, BANKCARD, Square, PayPal, payment processor names
- Delivery service payments: DoorDash, Grubhub, Uber Eats, Beyond Menu (these are deposits for restaurants receiving payments)
- Direct deposits, payroll, ACH credits
- Refunds, returns, credits
- Interest earned
- Transfers IN

WITHDRAWAL (Money going OUT of the account):
- Purchases: Kroger, Walmart, Target, Amazon, Costco, Home Depot, Lowe's, etc.
- Utility payments: FirstEnergy, City utilities, water, gas, electric
- Restaurant expenses (when paying for supplies, not receiving payments)
- ACH debits, electronic payments
- Transfers OUT
- Checks paid

FEE (Bank charges):
- Service fees, monthly fees
- Overdraft fees, NSF fees
- ATM fees, transaction fees
- Any description containing "FEE", "CHARGE", "SERVICE CHARGE"

Important Context:
- For restaurant businesses: DoorDash, Grubhub, Uber Eats payments are DEPOSITS (money coming in from customers)
- For retail businesses: Payment processor transactions (STRIPE, BANKCARD) are DEPOSITS (sales revenue)
- Purchases at stores (Kroger, Walmart) are WITHDRAWALS (expenses)
- Utility bills are WITHDRAWALS (expenses)

Return a JSON array with the same structure, but with "transaction_type" field updated to the correct classification.
Only return the transaction_type field for each transaction, or return the full transaction with updated type.

Example response format:
[
  {"transaction_type": "DEPOSIT"},
  {"transaction_type": "WITHDRAWAL"},
  {"transaction_type": "FEE"}
]

Or return full transactions:
[
  {"description": "...", "amount": 100.00, "transaction_type": "DEPOSIT"},
  ...
]"""
                
                user_prompt = f"""Context:
{context_info}

Transactions to classify:
{transactions_json}

Classify each transaction as DEPOSIT, WITHDRAWAL, or FEE based on the description.
Return only valid JSON array with transaction_type for each transaction."""
                
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o",
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        temperature=0.1,  # Low temperature for consistent classification
                        max_tokens=2000
                    )
                    
                    result_text = response.choices[0].message.content.strip()
                    
                    # Remove markdown if present
                    result_text = re.sub(r'^```json\s*\n', '', result_text)
                    result_text = re.sub(r'^```\s*\n', '', result_text)
                    result_text = re.sub(r'\n```$', '', result_text)
                    result_text = result_text.strip()
                    
                    # Parse JSON response
                    try:
                        if result_text.startswith('['):
                            ai_results = json.loads(result_text)
                        else:
                            # Try to extract JSON array from text
                            json_match = re.search(r'\[.*\]', result_text, re.DOTALL)
                            if json_match:
                                ai_results = json.loads(json_match.group(0))
                            else:
                                # Single object wrapped in array
                                ai_results = [json.loads(result_text)]
                    except:
                        logger.warning(f"Could not parse AI response for transaction classification: {result_text[:200]}")
                        # Fallback: keep original types
                        classified_transactions.extend(batch)
                        continue
                    
                    # Merge AI classifications back into original transactions
                    for idx, trans in enumerate(batch):
                        if idx < len(ai_results):
                            ai_result = ai_results[idx]
                            # Update transaction type if AI provided it
                            if isinstance(ai_result, dict) and "transaction_type" in ai_result:
                                trans["transaction_type"] = ai_result["transaction_type"]
                            elif isinstance(ai_result, str):
                                # If AI returned just the type string
                                trans["transaction_type"] = ai_result
                        
                        classified_transactions.append(trans)
                    
                    logger.debug(f"AI classified {len(batch)} transactions")
                    
                except Exception as e:
                    logger.warning(f"AI transaction classification failed for batch: {e}")
                    # Fallback: keep original transactions
                    classified_transactions.extend(batch)
            
            logger.info(f"AI classified transaction types for {len(classified_transactions)} transactions")
            return classified_transactions
            
        except Exception as e:
            logger.error(f"Error in AI transaction type classification: {e}")
            return transactions
    
    @staticmethod
    def enhance_transaction_extraction(
        transactions: List[Dict[str, Any]],
        statement_context: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Use GPT-4 to enhance transaction extraction:
        - Better date parsing and normalization
        - Improved payee/vendor extraction from descriptions
        - Better transaction type detection
        
        Args:
            transactions: List of raw transactions from PDF extraction
            statement_context: Optional context like statement period, bank name
            
        Returns:
            List of enhanced transactions
        """
        if not OPENAI_AVAILABLE:
            logger.debug("OpenAI not available, returning original transactions")
            return transactions
        
        client = get_openai_client()
        if client is None:
            logger.debug("OpenAI client not initialized, returning original transactions")
            return transactions
        
        if not transactions:
            return transactions
        
        try:
            # Prepare context for AI
            context_info = ""
            if statement_context:
                if statement_context.get("statement_period_start"):
                    context_info += f"Statement period: {statement_context.get('statement_period_start')} to {statement_context.get('statement_period_end', '')}\n"
                if statement_context.get("bank_name"):
                    context_info += f"Bank: {statement_context.get('bank_name')}\n"
            
            # Process transactions in batches (to avoid token limits)
            batch_size = 20
            enhanced_transactions = []
            
            for i in range(0, len(transactions), batch_size):
                batch = transactions[i:i + batch_size]
                
                # Prepare transaction data for AI
                transactions_json = json.dumps(batch, indent=2)
                
                system_prompt = """You are an expert at parsing bank statement transactions. 
Your task is to enhance transaction data by:
1. Normalizing dates to YYYY-MM-DD format (use statement period context if dates are partial)
2. Extracting clear payee/vendor names from transaction descriptions
3. Correctly identifying transaction types (DEPOSIT, WITHDRAWAL, FEE) based on description and context
4. Cleaning up descriptions while preserving important details

Return a JSON array of enhanced transactions with these fields:
- date: Normalized date in YYYY-MM-DD format
- amount: Numeric amount (positive for deposits, negative for withdrawals)
- description: Cleaned description
- payee: Extracted vendor/payee name (or null if not extractable)
- transaction_type: DEPOSIT, WITHDRAWAL, or FEE
- reference_number: Any transaction ID or reference number found

Transaction Type Classification Rules:
- DEPOSIT: Money coming INTO the account
  * Payment processing (STRIPE, BANKCARD, Square, PayPal)
  * Delivery service payments (DoorDash, Grubhub, Uber Eats) - these are deposits for restaurants
  * Direct deposits, payroll, ACH credits
  * Refunds, returns, credits
  * Interest earned
  * Transfers IN

- WITHDRAWAL: Money going OUT of the account
  * Purchases (Kroger, Walmart, Target, Amazon, etc.)
  * Utility payments (FirstEnergy, City utilities, etc.)
  * Restaurant expenses (when paying for supplies, not receiving payments)
  * ACH debits, electronic payments
  * Transfers OUT

- FEE: Bank charges
  * Service fees, monthly fees
  * Overdraft fees, NSF fees
  * ATM fees, transaction fees

Important Context:
- For restaurant businesses: DoorDash, Grubhub, Uber Eats payments are DEPOSITS (money coming in)
- For retail businesses: Payment processor transactions (STRIPE, BANKCARD) are DEPOSITS
- Purchases at stores (Kroger, Walmart) are WITHDRAWALS (money going out)
- Utility bills are WITHDRAWALS (money going out)

Preserve original data if enhancement is not possible.
Dates should be normalized using statement period context when available."""
                
                user_prompt = f"""Context:
{context_info}

Raw transactions to enhance:
{transactions_json}

Enhance these transactions with better date parsing, payee extraction, and transaction type detection. 
Return only valid JSON array, no additional text."""
                
                try:
                    response = client.chat.completions.create(
                        model="gpt-4o",  # or "gpt-4-turbo-preview"
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,  # Low temperature for consistent extraction
                        max_tokens=4000
                    )
                    
                    result_text = response.choices[0].message.content
                    
                    # Parse JSON response
                    try:
                        result_data = json.loads(result_text)
                        # Handle different response formats
                        if isinstance(result_data, dict):
                            if "transactions" in result_data:
                                enhanced_batch = result_data["transactions"]
                            elif "data" in result_data:
                                enhanced_batch = result_data["data"]
                            else:
                                # Try to find array in dict values
                                enhanced_batch = next((v for v in result_data.values() if isinstance(v, list)), batch)
                        elif isinstance(result_data, list):
                            enhanced_batch = result_data
                        else:
                            # Fallback: use original batch
                            enhanced_batch = batch
                        
                        enhanced_transactions.extend(enhanced_batch)
                        logger.info(f"Enhanced {len(enhanced_batch)} transactions with GPT-4")
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to parse GPT-4 JSON response: {e}")
                        enhanced_transactions.extend(batch)  # Fallback to original
                
                except Exception as e:
                    logger.error(f"Error enhancing transaction batch with GPT-4: {e}")
                    enhanced_transactions.extend(batch)  # Fallback to original
            
            return enhanced_transactions if enhanced_transactions else transactions
        
        except Exception as e:
            logger.error(f"Error in AI-enhanced transaction extraction: {e}")
            return transactions
    
    @staticmethod
    def enhance_balance_extraction(
        raw_text: str,
        extracted_balances: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Use GPT-4 to extract and validate balance information from bank statement text.
        
        Args:
            raw_text: Raw text from bank statement
            extracted_balances: Previously extracted balances to validate/enhance
            
        Returns:
            Dictionary with enhanced balance information
        """
        if not OPENAI_AVAILABLE:
            return extracted_balances or {}
        
        client = get_openai_client()
        if client is None:
            return extracted_balances or {}
        
        try:
            # Extract relevant text (first 5000 chars should contain balance info)
            relevant_text = raw_text[:5000] if len(raw_text) > 5000 else raw_text
            
            system_prompt = """You are an expert at extracting balance information from bank statements.
Extract the following information:
- beginning_balance: Starting balance for the statement period
- ending_balance: Final balance at end of statement period
- total_deposits: Total of all deposits/credits
- total_withdrawals: Total of all withdrawals/debits
- statement_period_start: Start date of statement period (YYYY-MM-DD)
- statement_period_end: End date of statement period (YYYY-MM-DD)

Return a JSON object with these fields. Use null for fields that cannot be determined.
Dates should be normalized to YYYY-MM-DD format."""
            
            user_prompt = f"""Extract balance and period information from this bank statement text:

{relevant_text}

Return only valid JSON object with balance information, no additional text."""
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=1000
            )
            
            result_text = response.choices[0].message.content
            ai_balances = json.loads(result_text)
            
            # Merge with existing balances (AI values take precedence if they exist)
            if extracted_balances:
                for key in ["beginning_balance", "ending_balance", "total_deposits", 
                           "total_withdrawals", "statement_period_start", "statement_period_end"]:
                    if key in ai_balances and ai_balances[key] is not None:
                        extracted_balances[key] = ai_balances[key]
                return extracted_balances
            else:
                return ai_balances
        
        except Exception as e:
            logger.error(f"Error in AI-enhanced balance extraction: {e}")
            return extracted_balances or {}
    
    @staticmethod
    def extract_payee_from_description(description: str) -> Optional[str]:
        """
        Use GPT-4 to intelligently extract payee/vendor name from transaction description.
        
        Args:
            description: Transaction description text
            
        Returns:
            Extracted payee name or None
        """
        if not OPENAI_AVAILABLE or not description:
            return None
        
        client = get_openai_client()
        if client is None:
            return None
        
        try:
            system_prompt = """You are an expert at extracting vendor/payee names from bank transaction descriptions.
Extract the actual business or vendor name from the description, removing transaction IDs, dates, and other noise.
Return only the vendor name, or null if no clear vendor can be identified."""
            
            user_prompt = f"""Extract the vendor/payee name from this transaction description:
{description}

Return only the vendor name (e.g., "DoorDash", "Stripe", "Walmart") or null if unclear."""
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=50
            )
            
            payee = response.choices[0].message.content.strip()
            
            # Clean up response (remove quotes, "null", etc.)
            if payee.lower() in ["null", "none", "n/a", ""]:
                return None
            
            payee = payee.strip('"\'')
            return payee if payee else None
        
        except Exception as e:
            logger.debug(f"Error extracting payee with GPT-4: {e}")
            return None
    
    @staticmethod
    def normalize_date(
        date_str: str,
        statement_period_start: Optional[str] = None,
        statement_period_end: Optional[str] = None
    ) -> Optional[str]:
        """
        Use GPT-4 to normalize dates from various formats to YYYY-MM-DD.
        
        Args:
            date_str: Date string in any format
            statement_period_start: Statement period start for context
            statement_period_end: Statement period end for context
            
        Returns:
            Normalized date in YYYY-MM-DD format or None
        """
        if not OPENAI_AVAILABLE or not date_str:
            return None
        
        client = get_openai_client()
        if client is None:
            return None
        
        try:
            context = ""
            if statement_period_start:
                context += f"Statement period: {statement_period_start} to {statement_period_end or ''}\n"
            
            system_prompt = """You are an expert at parsing and normalizing dates from bank statements.
Convert dates to YYYY-MM-DD format. Use statement period context to determine year if date is partial (e.g., "01/15").
Return only the normalized date in YYYY-MM-DD format, or null if date cannot be parsed."""
            
            user_prompt = f"""{context}Normalize this date: {date_str}
Return only the date in YYYY-MM-DD format."""
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                max_tokens=20
            )
            
            normalized = response.choices[0].message.content.strip()
            
            # Validate it's a date format
            if re.match(r'^\d{4}-\d{2}-\d{2}$', normalized):
                return normalized
            
            return None
        
        except Exception as e:
            logger.debug(f"Error normalizing date with GPT-4: {e}")
            return None
    
    @staticmethod
    def extract_bank_statement_with_ai(file_path: str, max_pages: int = 5) -> Dict[str, Any]:
        """
        Use GPT-4 Vision to extract bank statement data in a format-agnostic way.
        AI understands the bank statement format and extracts all transactions, balances, etc.
        
        Args:
            file_path: Path to bank statement PDF
            max_pages: Maximum number of pages to process (for performance)
            
        Returns:
            Dictionary with extracted bank statement data
        """
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI not available for AI bank statement extraction")
            return {"error": "OpenAI not available"}
        
        client = get_openai_client()
        if client is None:
            return {"error": "OpenAI client not initialized"}
        
        try:
            import pdf2image
            from PIL import Image
            import concurrent.futures
            import threading
            
            # OPTIMIZATION: Convert pages on-demand instead of all at once
            # First, convert only first page for header info
            logger.info("Converting first page to image for header extraction...")
            first_page_images = pdf2image.convert_from_path(
                file_path,
                first_page=1,
                last_page=1,
                dpi=200
            )
            
            if not first_page_images:
                return {"error": "Failed to convert first page to image"}
            
            # Process first page for header info
            all_transactions = []
            statement_info = {}
            
            # Generate cache key for file
            file_hash = BankStatementAIExtractor._get_file_hash(file_path)
            
            logger.info("Extracting header information from first page...")
            first_page_result = BankStatementAIExtractor._extract_page_with_ai(
                client, first_page_images[0], is_first_page=True, cache_key=(file_hash, 1)
            )
            
            if first_page_result and not first_page_result.get("error"):
                statement_info.update({
                    "bank_name": first_page_result.get("bank_name"),
                    "account_number": first_page_result.get("account_number"),
                    "account_name": first_page_result.get("account_name"),
                    "statement_period_start": first_page_result.get("statement_period_start"),
                    "statement_period_end": first_page_result.get("statement_period_end"),
                    "beginning_balance": first_page_result.get("beginning_balance"),
                    "ending_balance": first_page_result.get("ending_balance"),
                    "total_deposits": first_page_result.get("total_deposits"),
                    "total_withdrawals": first_page_result.get("total_withdrawals"),
                })
                if first_page_result.get("transactions"):
                    all_transactions.extend(first_page_result["transactions"])
            
            # OPTIMIZATION: Process remaining pages in parallel (concurrent API calls)
            # Process ALL pages, not just 10, to ensure complete extraction
            max_pages_to_process = min(max_pages, 20)  # Limit to 20 pages max for performance (most statements are < 20 pages)
            if max_pages_to_process > 1:
                logger.info(f"Processing remaining {max_pages_to_process - 1} pages in parallel (max 5 concurrent)...")
                
                def process_page(page_num):
                    """Convert and process a single page."""
                    try:
                        # Check cache first
                        cache_key = (file_hash, page_num)
                        if cache_key in _ai_extraction_cache:
                            logger.info(f"Using cached result for page {page_num}")
                            return _ai_extraction_cache[cache_key].copy()
                        
                        logger.info(f"Converting page {page_num} to image...")
                        page_images = pdf2image.convert_from_path(
                            file_path,
                            first_page=page_num,
                            last_page=page_num,
                            dpi=200
                        )
                        if not page_images:
                            return None
                        
                        logger.info(f"Extracting transactions from page {page_num}...")
                        page_result = BankStatementAIExtractor._extract_page_with_ai(
                            client, page_images[0], is_first_page=False, cache_key=cache_key
                        )
                        return page_result
                    except Exception as e:
                        logger.error(f"Error processing page {page_num}: {e}")
                        return None
                
                # Process pages 2-N in parallel (max 5 concurrent to avoid rate limits)
                # Use ThreadPoolExecutor for true parallelization
                import time
                start_time = time.time()
                with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                    future_to_page = {
                        executor.submit(process_page, page_num): page_num 
                        for page_num in range(2, max_pages_to_process + 1)
                    }
                    
                    for future in concurrent.futures.as_completed(future_to_page):
                        page_num = future_to_page[future]
                        try:
                            page_result = future.result()
                            if page_result and not page_result.get("error"):
                                if page_result.get("transactions"):
                                    all_transactions.extend(page_result["transactions"])
                                    logger.info(f"Page {page_num}: Extracted {len(page_result['transactions'])} transactions")
                        except Exception as e:
                            logger.error(f"Page {page_num} processing failed: {e}")
                
                elapsed = time.time() - start_time
                logger.info(f"Parallel page processing completed in {elapsed:.1f}s for {max_pages_to_process - 1} pages")
            
            # Combine results
            result = {
                "document_type": "bank_statement",
                **statement_info,
                "transactions": all_transactions
            }
            
            logger.info(f"AI extraction complete: {len(all_transactions)} transactions extracted")
            return result
        
        except Exception as e:
            logger.error(f"AI bank statement extraction failed: {e}", exc_info=True)
            return {"error": str(e)}
    
    @staticmethod
    def extract_fifth_third_transactions_from_text(
        raw_text: str,
        statement_period_end: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Use AI to extract transactions from Fifth Third bank statement raw text.
        AI understands section headers (Deposits/Credits, Withdrawals/Debits, Checks) and row formats.
        Returns transactions with date (YYYY-MM-DD), amount, description, transaction_type (DEPOSIT/WITHDRAWAL/CHECK), reference_number.
        """
        if not OPENAI_AVAILABLE:
            logger.warning("OpenAI not available for Fifth Third AI extraction")
            return []

        client = get_openai_client()
        if client is None:
            return []

        try:
            year_hint = ""
            if statement_period_end:
                year_hint = f" Statement period ends {statement_period_end}; use that year for MM/DD dates."

            system_prompt = """You are an expert at parsing Fifth Third Bank statements from raw text.

CRITICAL: Fifth Third statements have THREE sections. You MUST extract from ALL three. Do not skip any section.

Sections (look for these headers; they may have spaces between letters like "D e p o s i t s / C r e d i t s"):

1. "Deposits / Credits" or "Deposits / Credits - continued"
   - Rows: MM/DD  AMOUNT  DESCRIPTION (e.g. 04/01 4,621.61 Citizens NET SETLMT...)
   - transaction_type: DEPOSIT
   - Extract EVERY row under this section.

2. "Withdrawals / Debits" or "Withdrawals / Debits - continued"
   - Rows: MM/DD  AMOUNT  DESCRIPTION
   - transaction_type: WITHDRAWAL
   - Extract EVERY row under this section.

3. "Checks" or "Checks - continued"
   - Rows: CHECK_NUMBER  i or s  MM/DD  AMOUNT (e.g. 1323 i 04/03 31.18) — no description column
   - transaction_type: CHECK
   - reference_number: the check number
   - description: "Check #" + check number
   - Extract EVERY row under this section.

Rules:
- Section header decides type. All rows after that header use that type until the next section header.
- Skip summary lines ("35 items totaling", "72 checks totaling") and column headers ("Date Amount Description", "Number Date Paid Amount").
- Amount: positive number. Date: YYYY-MM-DD (use statement year for MM/DD).
- Return ALL transactions from ALL three sections in one array. Do not omit the Deposits section."""

            user_prompt = f"""Extract EVERY transaction from this Fifth Third bank statement. You MUST include (1) all DEPOSIT transactions from Deposits/Credits section, (2) all WITHDRAWAL transactions from Withdrawals/Debits section, (3) all CHECK transactions from Checks section.{year_hint}

Return a JSON object with a single key "transactions" whose value is an array of objects. Each object must have:
- "date": "YYYY-MM-DD"
- "amount": number (positive)
- "description": string (full description for deposits/withdrawals; "Check #N" for checks)
- "transaction_type": "DEPOSIT" | "WITHDRAWAL" | "CHECK"
- "reference_number": string or null (check number for CHECK, null otherwise)
- "payee": string or null (optional, extract vendor if obvious)

Raw statement text:

{raw_text}

Return only valid JSON with key "transactions", no additional text."""

            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=16000
            )

            result_text = response.choices[0].message.content
            data = json.loads(result_text)
            transactions = data.get("transactions") or []

            # Normalize to our standard shape (payee optional)
            out = []
            for t in transactions:
                out.append({
                    "date": t.get("date") or "",
                    "amount": float(t.get("amount", 0)) if t.get("amount") is not None else 0,
                    "description": t.get("description") or "",
                    "payee": t.get("payee") if t.get("payee") else None,
                    "transaction_type": t.get("transaction_type") or "WITHDRAWAL",
                    "reference_number": t.get("reference_number"),
                })
            logger.info(f"Fifth Third AI extraction: {len(out)} transactions from text")
            return out

        except json.JSONDecodeError as e:
            logger.warning(f"Fifth Third AI extraction: JSON parse failed: {e}")
            return []
        except Exception as e:
            logger.warning(f"Fifth Third AI extraction failed: {e}", exc_info=True)
            return []

    @staticmethod
    def _get_file_hash(file_path: str) -> str:
        """Generate a hash of the file for caching purposes."""
        try:
            stat = os.stat(file_path)
            # Use file size and modification time as cache key
            return hashlib.md5(f"{file_path}:{stat.st_size}:{stat.st_mtime}".encode()).hexdigest()
        except:
            return hashlib.md5(file_path.encode()).hexdigest()
    
    @staticmethod
    def _extract_page_with_ai(client, image, is_first_page: bool = False, cache_key: Optional[tuple] = None) -> Dict[str, Any]:
        """
        Extract data from a single page using GPT-4 Vision.
        Uses caching to avoid re-processing identical pages.
        
        Args:
            client: OpenAI client
            image: PIL Image object
            is_first_page: Whether this is the first page (contains header info)
            cache_key: Optional cache key (file_hash, page_num) to check cache
            
        Returns:
            Dictionary with extracted data
        """
        # Check cache first
        if cache_key and cache_key in _ai_extraction_cache:
            logger.info(f"Using cached AI extraction result for page {cache_key[1]}")
            return _ai_extraction_cache[cache_key].copy()
        
        try:
            # Convert PIL image to base64
            img_buffer = io.BytesIO()
            image.save(img_buffer, format='PNG')
            img_buffer.seek(0)
            image_data = img_buffer.read()
            base64_image = base64.b64encode(image_data).decode('utf-8')
            
            if is_first_page:
                system_prompt = """You are an expert at extracting bank statement information.
Analyze this bank statement page and extract:

1. Bank name
2. Account number (may be masked, extract what's visible)
3. Account name/type
4. Statement period (start and end dates in YYYY-MM-DD format)
5. Beginning balance
6. Ending balance
7. Total deposits/credits (if shown)
8. Total withdrawals/debits (if shown)
9. Any transactions visible on this page

For transactions, extract:
- Date (normalize to YYYY-MM-DD)
- Amount (positive for deposits, negative for withdrawals)
- Description
- Payee/vendor name (if extractable from description)
- Transaction type: DEPOSIT, WITHDRAWAL, or FEE
- Reference number (if any)

IMPORTANT:
- Credits/Deposits = money coming IN (positive amounts)
- Debits/Withdrawals = money going OUT (negative amounts or marked as withdrawal)
- ATM deposits that look like checks are still DEPOSITS (credits)
- Identify transaction type by section label, not just appearance

Return JSON:
{
  "bank_name": "string or null",
  "account_number": "string or null",
  "account_name": "string or null",
  "statement_period_start": "YYYY-MM-DD or null",
  "statement_period_end": "YYYY-MM-DD or null",
  "beginning_balance": number or null,
  "ending_balance": number or null,
  "total_deposits": number or null,
  "total_withdrawals": number or null,
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "amount": number (positive for deposits, negative for withdrawals),
      "description": "string",
      "payee": "string or null",
      "transaction_type": "DEPOSIT" | "WITHDRAWAL" | "FEE",
      "reference_number": "string or null"
    }
  ]
}"""
            else:
                system_prompt = """You are an expert at extracting transactions from bank statement pages.
Extract all transactions from this page.

For each transaction, extract:
- Date (normalize to YYYY-MM-DD using statement period context)
- Amount (positive for deposits, negative for withdrawals)
- Description
- Payee/vendor name (if extractable)
- Transaction type: DEPOSIT, WITHDRAWAL, or FEE
- Reference number (if any)

IMPORTANT:
- Identify transaction type by section (Credits/Deposits vs Debits/Withdrawals)
- ATM deposits are DEPOSITS even if they have check numbers
- Use section labels to determine type, not just amount sign

Return JSON:
{
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "amount": number,
      "description": "string",
      "payee": "string or null",
      "transaction_type": "DEPOSIT" | "WITHDRAWAL" | "FEE",
      "reference_number": "string or null"
    }
  ]
}"""
            
            user_prompt = "Extract all bank statement information from this page. Return only valid JSON, no additional text."
            
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_prompt},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            }
                        ]
                    }
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=4000
            )
            
            result_text = response.choices[0].message.content
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                
                # Normalize amounts: ensure withdrawals are negative
                if "transactions" in result:
                    for trans in result["transactions"]:
                        amount = trans.get("amount", 0)
                        trans_type = trans.get("transaction_type", "")
                        
                        # If it's a withdrawal but amount is positive, make it negative
                        if trans_type in ["WITHDRAWAL", "FEE"] and amount > 0:
                            trans["amount"] = -abs(amount)
                        # If it's a deposit but amount is negative, make it positive
                        elif trans_type == "DEPOSIT" and amount < 0:
                            trans["amount"] = abs(amount)
                
                # Cache the result if cache_key is provided and no error
                if cache_key and not result.get("error"):
                    # Limit cache size
                    if len(_ai_extraction_cache) >= _cache_max_size:
                        # Remove oldest entry (simple FIFO)
                        oldest_key = next(iter(_ai_extraction_cache))
                        del _ai_extraction_cache[oldest_key]
                    
                    _ai_extraction_cache[cache_key] = result.copy()
                    logger.debug(f"Cached AI extraction result for page {cache_key[1]}")
                
                return result
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse AI response JSON: {e}")
                logger.debug(f"Response text: {result_text[:500]}")
                return {"error": f"JSON parsing failed: {e}"}
                
        except Exception as e:
            logger.error(f"Error extracting page with AI: {e}")
            return {"error": str(e)}
            
            return result

