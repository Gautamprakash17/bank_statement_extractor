import pdfplumber
import pandas as pd
import re
from datetime import datetime, timedelta
import os
import json
from typing import List, Dict, Any, Optional, Tuple
import logging
from collections import defaultdict

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CompleteBankExtractor:
    """
    Complete Bank Statement Extractor with comprehensive validation
    """
    
    def __init__(self, config_file: str = None):
        """Initialize the extractor with enhanced configuration"""
        self.config = self._load_config(config_file)
        self.date_patterns = self._get_date_patterns()
        self.amount_patterns = self._get_amount_patterns()
        self.validation_results = {}
        
    def _load_config(self, config_file: str) -> Dict[str, Any]:
        """Load enhanced bank-specific configuration"""
        default_config = {
            "date_formats": [
                "%d %b %Y",    # 15 Apr 2024
                "%d/%m/%Y",    # 15/04/2024
                "%d-%m-%Y",    # 15-04-2024
                "%d.%m.%Y",    # 15.04.2024
                "%Y-%m-%d",    # 2024-04-15
                "%d/%m/%y",    # 15/04/24
                "%d-%m-%y",    # 15-04-24
            ],
            "currencies": {
                "INR": {"symbol": "₹", "patterns": [r"₹", r"Rs\.", r"INR"]},
                "USD": {"symbol": "$", "patterns": [r"\$", r"USD"]},
                "EUR": {"symbol": "€", "patterns": [r"€", r"EUR"]},
                "GBP": {"symbol": "£", "patterns": [r"£", r"GBP"]},
            },
            "transaction_patterns": [
                # Pattern 1: Standard format with reference number
                r'^(\d+)\s+(\d{2}\s+\w{3}\s+\d{4})\s+(\d{2}\s+\w{3}\s+\d{4})\s+(.+?)\s+([A-Z0-9/]+)\s+([+-]?[0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})$',
                # Pattern 2: Without reference number
                r'^(\d+)\s+(\d{2}\s+\w{3}\s+\d{4})\s+(\d{2}\s+\w{3}\s+\d{4})\s+(.+?)\s+([+-]?[0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})$',
                # Pattern 3: Different date format
                r'^(\d+)\s+(\d{2}/\d{2}/\d{4})\s+(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([+-]?[0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})$',
                # Pattern 4: Minimal format
                r'^(\d+)\s+(\d{2}\s+\w{3}\s+\d{4})\s+(\d{2}\s+\w{3}\s+\d{4})',
                # Pattern 5: New format with separate debit/credit columns
                r'^(\d+)\s+(\d{2}\s+\w{3}\s+\d{4})\s+(.+?)\s+([A-Z0-9/]+)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})$',
                r'^(\d+)\s+(\d{2}\s+\w{3}\s+\d{4})\s+(.+?)\s+([A-Z0-9/]+)\s+([0-9,]+\.\d{2})\s+([0-9,]+\.\d{2})$',
            ],
            "validation_rules": {
                "min_amount": 1.0,
                "max_amount": 1000000000,  # 1 billion
                "max_daily_transactions": 100,
                "suspicious_patterns": [
                    r"test", r"sample", r"dummy", r"placeholder",
                    r"0\.00", r"0\.01", r"999999", r"123456"
                ],
                "required_fields": ["Transaction Date", "Amount", "Narrative"],
                "date_range": {
                    "min_year": 2020,
                    "max_year": 2030
                }
            }
        }
        
        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
                logger.info(f"Loaded configuration from {config_file}")
            except Exception as e:
                logger.warning(f"Failed to load config file: {e}. Using default config.")
        
        return default_config
    
    def _get_date_patterns(self) -> List[str]:
        """Generate regex patterns for different date formats"""
        patterns = []
        for fmt in self.config["date_formats"]:
            if fmt == "%d %b %Y":
                patterns.append(r'\d{2}\s+\w{3}\s+\d{4}')
            elif fmt == "%d/%m/%Y":
                patterns.append(r'\d{2}/\d{2}/\d{4}')
            elif fmt == "%d-%m-%Y":
                patterns.append(r'\d{2}-\d{2}-\d{4}')
            elif fmt == "%d.%m.%Y":
                patterns.append(r'\d{2}\.\d{2}\.\d{4}')
            elif fmt == "%Y-%m-%d":
                patterns.append(r'\d{4}-\d{2}-\d{2}')
            elif fmt == "%d/%m/%y":
                patterns.append(r'\d{2}/\d{2}/\d{2}')
            elif fmt == "%d-%m-%y":
                patterns.append(r'\d{2}-\d{2}-\d{2}')
        return patterns
    
    def _get_amount_patterns(self) -> List[str]:
        """Generate regex patterns for different amount formats"""
        return [
            r'[+-]?[0-9,]+\.\d{2}',  # Standard: +1,234.56 or -1,234.56
            r'[+-]?[0-9]+\.[0-9]{2}',  # Without commas: +1234.56
            r'[+-]?[0-9,]+',  # Without decimals: +1,234
            r'[+-]?[0-9]+',  # Simple: +1234
        ]
    
    def _detect_currency(self, text: str) -> Tuple[str, str]:
        """Detect currency from text"""
        for currency, info in self.config["currencies"].items():
            for pattern in info["patterns"]:
                if re.search(pattern, text):
                    return currency, info["symbol"]
        return "INR", "₹"  # Default to INR
    
    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object"""
        try:
            # Handle various date formats
            date_formats = [
                '%d %b %Y', '%d %b %y', '%d-%b-%Y', '%d-%b-%y',
                '%d/%m/%Y', '%d/%m/%y', '%Y-%m-%d', '%d-%m-%Y', '%d %b %y', '%d-%b-%y'
            ]
            
            # Clean the date string
            date_str = date_str.strip()
            
            for fmt in date_formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None
    
    def _extract_amount(self, text: str) -> Optional[float]:
        """Extract amount from text"""
        for pattern in self.amount_patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    amount_str = match.group(0).replace(',', '')
                    return float(amount_str)
                except ValueError:
                    continue
        return None
    
    def _is_transaction_line(self, line: str) -> bool:
        """Strictly check if line is a real transaction (date, amount, balance present)"""
        # Must have a date, an amount, and a balance
        has_date = any(re.search(pattern, line) for pattern in self.date_patterns)
        has_amount = any(re.search(pattern, line) for pattern in self.amount_patterns)
        has_balance = bool(re.search(r'[0-9,]+\.\d{2}(\s|$)', line))
        # Must not be a header or info row
        is_not_header = not re.match(r'^(Account|Branch|CRN|IFSC|MICR|Elint|TRANSACTION|#|\s*$)', line, re.IGNORECASE)
        return has_date and has_amount and has_balance and is_not_header
    
    def _extract_narrative(self, line: str, date_matches: List) -> str:
        """Extract narrative from transaction line"""
        if len(date_matches) >= 1:
            # Extract text between transaction number and amount
            start_pos = date_matches[0].end()
            end_pos = len(line)
            
            # Find amount position
            for pattern in self.amount_patterns:
                amount_match = re.search(pattern, line[start_pos:])
                if amount_match:
                    end_pos = start_pos + amount_match.start()
                    break
            
            narrative = line[start_pos:end_pos].strip()
            return narrative
        return ""
    
    def extract_and_fix_transactions(self, pdf_path: str, output_dir: str = "output") -> str:
        """
        Extract transactions from PDF and apply data quality fixes in one step
        """
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        base_name = os.path.splitext(os.path.basename(pdf_path))[0]
        final_csv = os.path.join(output_dir, f"{base_name}_complete.csv")
        validation_report = os.path.join(output_dir, f"{base_name}_validation_report.txt")
        
        transactions = []
        currency, symbol = "INR", "₹"
        
        logger.info(f"🔄 Extracting and fixing transactions from {pdf_path}")
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages):
                    logger.info(f"Processing page {page_num + 1}")
                    text = page.extract_text()
                    lines = text.split('\n')
                    
                    i = 0
                    while i < len(lines):
                        line_content = lines[i].strip()
                        if not line_content:
                            i += 1
                            continue

                        if not transactions:
                            currency, symbol = self._detect_currency(line_content)
                            logger.info(f"Detected currency: {currency} ({symbol})")

                        # Try to parse with enhanced patterns
                        transaction = self._parse_with_enhanced_patterns(line_content, lines, i)

                        if transaction:
                            transactions.append(transaction)
                            logger.debug(f"Found transaction with enhanced patterns: {transaction}")
                            # If SBI multi-line, skip the next line
                            sbi_line1_pattern = r'^(\d{2}-\w{3}-\d{2,4})\s+(TO|BY)\s+(.+?)\s+([0-9,]+\.\d{2})\s+([+-]?[0-9,]+\.\d{2})$'
                            if re.match(sbi_line1_pattern, line_content):
                                i += 2
                                continue
                        else:
                            # Fallback parsing
                            transaction = self._enhanced_fallback_parsing(line_content, lines, i)
                            if transaction:
                                transactions.append(transaction)
                                logger.debug(f"Found transaction with fallback: {transaction}")

                        i += 1
            
            # Create DataFrame and apply comprehensive fixes
            if transactions:
                df = pd.DataFrame(transactions)
                logger.info(f"📊 Initial extraction: {len(df)} transactions")
                
                # Apply comprehensive data quality fixes
                df = self._apply_comprehensive_fixes(df, currency, symbol)
                
                # Apply comprehensive validation
                validation_results = self._apply_comprehensive_validation(df, base_name)
                
                # Save final file
                df.to_csv(final_csv, index=False)
                
                # Save validation report
                self._save_validation_report(validation_results, validation_report)
                
                logger.info(f"✅ Complete extraction and fixes: {len(df)} transactions")
                logger.info(f"💾 Saved to: {final_csv}")
                logger.info(f"📋 Validation report: {validation_report}")
                
                return final_csv
            else:
                logger.warning("No transactions found in PDF")
                return ""
                
        except Exception as e:
            logger.error(f"Error processing PDF: {e}")
            return ""
    
    def _parse_with_enhanced_patterns(self, line: str, lines: List[str], line_index: int) -> Optional[Dict]:
        """Parse transaction using enhanced patterns, including SBI multi-line format"""
        # SBI multi-line: line, then (value date) and more narration on next line
        # Example:
        # 06-Sep-24 TO TRANSFER TRANSFER TO 4897695 430.00 -427.92
        # (06-Sep-2024) UPI/DR/425032698980/VIKASH 162091
        sbi_line1_pattern = r'^(\d{2}-\w{3}-\d{2,4})\s+(TO|BY)\s+(.+?)\s+([0-9,]+\.\d{2})\s+([+-]?[0-9,]+\.\d{2})$'
        if re.match(sbi_line1_pattern, line):
            logger.debug(f"SBI pattern matched for line: {line}")
            try:
                m1 = re.match(sbi_line1_pattern, line)
                transaction_date = self._parse_date(m1.group(1).replace('-', ' '))
                transaction_type = m1.group(2)  # TO or BY
                narration1 = m1.group(3).strip()
                amount = float(m1.group(4).replace(',', ''))
                balance = float(m1.group(5).replace(',', ''))
                
                # Look ahead for value date and more narration
                value_date = None
                narration2 = ''
                if line_index + 1 < len(lines):
                    next_line = lines[line_index + 1].strip()
                    m2 = re.match(r'^\((\d{2}-\w{3}-\d{2,4})\)\s*(.*)$', next_line)
                    if m2:
                        value_date = self._parse_date(m2.group(1).replace('-', ' '))
                        narration2 = m2.group(2).strip()
                
                # If value_date not found, fallback to transaction_date
                if not value_date:
                    value_date = transaction_date
                
                # Combine narrations
                narrative = f"{transaction_type} {narration1}"
                if narration2:
                    narrative += f" {narration2}"
                
                return {
                    "Transaction Date": transaction_date,
                    "Narrative": narrative,
                    "Amount": amount,
                    "Balance": balance
                }
            except Exception as e:
                logger.debug(f"SBI multi-line pattern failed: {e}")
                return None
        # Fallback to previous logic
        # SBI pattern: Date (Value Date) | Narration | Ref/Cheque | Debit | Credit | Balance
        sbi_pattern = r'^(\d{2}-\w{3}-\d{2,4})\s*\((\d{2}-\w{3}-\d{2,4})\)\s+(.+?)\s+([\w/-]+)\s+([0-9,]+\.\d{2}|-)\s+([0-9,]+\.\d{2}|-)\s+([+-]?[0-9,]+\.\d{2})$'
        sbi_match = re.match(sbi_pattern, line)
        if sbi_match:
            try:
                transaction_date = self._parse_date(sbi_match.group(1).replace('-', ' '))
                value_date = self._parse_date(sbi_match.group(2).replace('-', ' '))
                narrative = sbi_match.group(3).strip()
                debit = sbi_match.group(5)
                credit = sbi_match.group(6)
                balance = float(sbi_match.group(7).replace(',', ''))
                if debit != '-':
                    amount = -float(debit.replace(',', ''))
                elif credit != '-':
                    amount = float(credit.replace(',', ''))
                else:
                    amount = 0.0
                return {
                    "Transaction Date": transaction_date,
                    "Narrative": narrative,
                    "Amount": amount,
                    "Balance": balance
                }
            except Exception as e:
                logger.debug(f"SBI pattern failed: {e}")
                return None
        # Fallback to existing patterns
        for pattern_idx, pattern in enumerate(self.config["transaction_patterns"]):
            match = re.match(pattern, line)
            if match:
                try:
                    groups = match.groups()
                    if pattern_idx in [0, 1, 2]:
                        value_date = self._parse_date(groups[1])
                        transaction_date = self._parse_date(groups[2])
                        narrative = groups[3].strip() if len(groups) > 3 else ""
                        if len(narrative) < 10 or narrative.upper().endswith('-'):
                            narrative = self._extract_multi_line_narrative(lines, line_index, narrative)
                        amount = self._extract_amount(groups[-2])
                        balance = self._extract_last_numeric_value(line)
                    elif pattern_idx in [4, 5]:
                        transaction_date = self._parse_date(groups[1])
                        value_date = transaction_date
                        narrative = groups[2].strip()
                        if len(narrative) < 10 or narrative.upper().endswith('-'):
                            narrative = self._extract_multi_line_narrative(lines, line_index, narrative)
                        debit_amount = self._extract_amount(groups[4]) if len(groups) > 4 else None
                        credit_amount = self._extract_amount(groups[5]) if len(groups) > 5 else None
                        amount = -debit_amount if debit_amount and debit_amount > 0 else (credit_amount if credit_amount and credit_amount > 0 else None)
                        balance = self._extract_last_numeric_value(line)
                    else:
                        transaction_date = None
                        value_date = None
                        narrative = ""
                        amount = self._extract_amount(line)
                        balance = self._extract_last_numeric_value(line)
                    if amount is not None and transaction_date and balance is not None:
                        return {
                            "Transaction Date": transaction_date,
                            "Narrative": narrative,
                            "Amount": amount,
                            "Balance": balance
                        }
                except Exception as e:
                    logger.debug(f"Pattern {pattern_idx} failed: {e}")
                    continue
        return None
    
    def _extract_multi_line_narrative(self, lines: List[str], line_index: int, initial_narrative: str) -> str:
        """Extract multi-line narrative with improved logic"""
        narrative = initial_narrative
        j = line_index + 1
        
        while j < len(lines):
            next_line = lines[j].strip()
            
            # Stop if next line is a new transaction
            if self._is_transaction_line(next_line):
                break
            
            # Stop if line contains amount and looks like balance
            for pattern in self.amount_patterns:
                if re.search(pattern, next_line):
                    # Check if this looks like a balance line
                    if re.search(r'[0-9,]+\.\d{2}$', next_line):
                        break
            else:
                narrative += " " + next_line
                j += 1
                continue
            break
        
        return narrative.strip()
    
    def _enhanced_fallback_parsing(self, line: str, lines: List[str], line_index: int) -> Optional[Dict]:
        """Enhanced fallback parsing for complex formats, always use last numeric value as balance"""
        try:
            tx_match = re.match(r'^(\d+)', line)
            if not tx_match:
                return None
            date_matches = []
            for pattern in self.date_patterns:
                date_matches.extend(list(re.finditer(pattern, line)))
            if len(date_matches) >= 1:
                transaction_date = self._parse_date(date_matches[0].group())
                if transaction_date:
                    narrative = self._extract_narrative(line, date_matches)
                    if len(narrative) < 10 or narrative.upper().endswith('-'):
                        narrative = self._extract_multi_line_narrative(lines, line_index, narrative)
                    amount = self._extract_amount(line)
                    balance = self._extract_last_numeric_value(line)
                    if amount is not None and balance is not None:
                        return {
                            "Transaction Date": transaction_date,
                            "Narrative": narrative,
                            "Amount": amount,
                            "Balance": balance
                        }
        except Exception as e:
            logger.debug(f"Enhanced fallback parsing failed: {e}")
        return None
    
    def _extract_last_numeric_value(self, line: str) -> Optional[float]:
        """Extract the last numeric value (balance) from a line"""
        matches = re.findall(r'[+-]?[0-9,]+\.\d{2}', line)
        if matches:
            try:
                return float(matches[-1].replace(',', ''))
            except Exception:
                return None
        return None
    
    def _apply_comprehensive_fixes(self, df: pd.DataFrame, currency: str, symbol: str) -> pd.DataFrame:
        """Apply comprehensive data quality fixes"""
        logger.info("🔧 Applying comprehensive data quality fixes...")
        
        # 1. Clean and standardize columns
        df = self._standardize_columns(df, currency, symbol)
        
        # 2. Fix balance calculations
        df = self._fix_balance_calculations(df)
        
        # 3. Clean narratives
        df = self._clean_narratives(df)
        
        # 4. Remove suspicious transactions
        df = self._remove_suspicious_transactions(df)
        
        # 5. Standardize dates
        df = self._standardize_dates(df)
        
        logger.info(f"📈 Data quality improvements completed: {len(df)} transactions")
        
        return df
    
    def _standardize_columns(self, df: pd.DataFrame, currency: str, symbol: str) -> pd.DataFrame:
        """Standardize DataFrame columns with improved cleaning"""
        # Ensure required columns exist
        required_columns = [
            'Transaction Date', 'Narrative', 
            f'Amount ({symbol})', 'Balance'
        ]
        
        # Initialize missing columns
        for col in required_columns:
            if col not in df.columns:
                df[col] = None
        
        # Rename Amount column if it exists
        if 'Amount' in df.columns:
            df[f'Amount ({symbol})'] = df['Amount']
            df = df.drop('Amount', axis=1)
        
        # Reorder columns
        df = df[required_columns]
        
        return df
    
    def _fix_balance_calculations(self, df: pd.DataFrame) -> pd.DataFrame:
        """No-op: Do not recalculate balances, just keep the extracted balance from PDF"""
        logger.info("💰 Using balance as extracted from PDF (no recalculation)")
        return df
    
    def _clean_narratives(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and improve narrative descriptions"""
        if 'Narrative' not in df.columns:
            return df
        
        # Fill missing narratives
        df['Narrative'] = df['Narrative'].fillna('')
        
        # Clean narratives
        df['Narrative'] = df['Narrative'].astype(str).apply(self._clean_narrative_text)
        
        # Remove very short narratives (likely parsing errors)
        df = df[df['Narrative'].str.len() >= 3]
        
        logger.info("📝 Cleaned narrative descriptions")
        return df
    
    def _clean_narrative_text(self, text: str) -> str:
        """Clean individual narrative text"""
        if not text or text == 'nan':
            return ''
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common parsing artifacts
        text = re.sub(r'^\d+\s*', '', text)  # Remove leading numbers
        text = re.sub(r'[^\w\s\-\./]', '', text)  # Keep only alphanumeric, spaces, hyphens, dots, slashes
        
        return text.strip()
    
    def _remove_suspicious_transactions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove transactions that are likely parsing errors"""
        initial_count = len(df)
        
        # Get amount column
        amount_col = None
        for col in df.columns:
            if 'Amount' in col:
                amount_col = col
                break
        
        if amount_col is None:
            return df
        
        # Remove transactions with very small amounts (likely parsing errors)
        df = df[df[amount_col].abs() >= 1.0]
        
        # Remove transactions with extremely large amounts (likely parsing errors)
        df = df[df[amount_col].abs() <= 1000000000]  # 1 billion
        
        # Remove transactions with missing dates
        if 'Transaction Date' in df.columns:
            df = df[df['Transaction Date'].notna()]
        
        final_count = len(df)
        if initial_count != final_count:
            logger.info(f"🚫 Removed {initial_count - final_count} suspicious transactions")
        
        return df
    
    def _standardize_dates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize date formats"""
        date_columns = ['Transaction Date']
        
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                df[col] = df[col].dt.strftime('%Y-%m-%d')
        
        logger.info("📅 Standardized date formats")
        return df
    
    def _apply_comprehensive_validation(self, df: pd.DataFrame, file_name: str) -> Dict[str, Any]:
        """Apply comprehensive validation checks"""
        logger.info("🔍 Applying comprehensive validation...")
        
        validation_results = {
            "file_name": file_name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_transactions": len(df),
            "checks": {},
            "warnings": [],
            "errors": [],
            "summary": {}
        }
        
        if len(df) == 0:
            validation_results["errors"].append("No transactions found in file")
            return validation_results
        
        # 1. Data Integrity Checks
        validation_results["checks"]["data_integrity"] = self._validate_data_integrity(df)
        
        # 2. Business Logic Validation
        validation_results["checks"]["business_logic"] = self._validate_business_logic(df)
        
        # 3. Amount Validation
        validation_results["checks"]["amount_validation"] = self._validate_amounts(df)
        
        # 4. Date Validation
        validation_results["checks"]["date_validation"] = self._validate_dates(df)
        
        # 5. Narrative Validation
        validation_results["checks"]["narrative_validation"] = self._validate_narratives(df)
        
        # 6. Balance Validation
        validation_results["checks"]["balance_validation"] = self._validate_balances(df)
        
        # 7. Statistical Analysis
        validation_results["checks"]["statistics"] = self._generate_statistics(df)
        
        # Generate summary
        validation_results["summary"] = self._generate_validation_summary(validation_results)
        
        logger.info("✅ Validation completed")
        return validation_results
    
    def _validate_data_integrity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate data integrity"""
        results = {
            "missing_values": {},
            "data_types": {},
            "column_count": len(df.columns),
            "row_count": len(df)
        }
        
        # Check for missing values
        for col in df.columns:
            missing_count = df[col].isna().sum()
            if missing_count > 0:
                results["missing_values"][col] = missing_count
        
        # Check data types
        for col in df.columns:
            results["data_types"][col] = str(df[col].dtype)
        
        return results
    
    def _validate_business_logic(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate business logic"""
        results = {
            "date_range": {},
            "transaction_frequency": {},
            "amount_distribution": {}
        }
        
        # Date range validation
        if 'Transaction Date' in df.columns:
            df['Transaction Date'] = pd.to_datetime(df['Transaction Date'])
            results["date_range"]["start"] = df['Transaction Date'].min().strftime('%Y-%m-%d')
            results["date_range"]["end"] = df['Transaction Date'].max().strftime('%Y-%m-%d')
            results["date_range"]["span_days"] = (df['Transaction Date'].max() - df['Transaction Date'].min()).days
        
        # Transaction frequency
        if 'Transaction Date' in df.columns:
            daily_counts = df['Transaction Date'].value_counts()
            results["transaction_frequency"]["max_daily"] = daily_counts.max()
            results["transaction_frequency"]["avg_daily"] = daily_counts.mean()
            results["transaction_frequency"]["high_frequency_days"] = len(daily_counts[daily_counts > 20])
        
        return results
    
    def _validate_amounts(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate transaction amounts"""
        results = {
            "amount_stats": {},
            "suspicious_amounts": [],
            "amount_range": {}
        }
        
        # Get amount column
        amount_col = None
        for col in df.columns:
            if 'Amount' in col:
                amount_col = col
                break
        
        if amount_col:
            amounts = df[amount_col]
            results["amount_stats"]["total_debits"] = len(amounts[amounts < 0])
            results["amount_stats"]["total_credits"] = len(amounts[amounts > 0])
            results["amount_stats"]["total_debit_amount"] = amounts[amounts < 0].sum()
            results["amount_stats"]["total_credit_amount"] = amounts[amounts > 0].sum()
            results["amount_stats"]["net_amount"] = amounts.sum()
            
            results["amount_range"]["min"] = amounts.min()
            results["amount_range"]["max"] = amounts.max()
            results["amount_range"]["mean"] = amounts.mean()
            results["amount_range"]["median"] = amounts.median()
            
            # Check for suspicious amounts
            for pattern in self.config["validation_rules"]["suspicious_patterns"]:
                suspicious = df[df['Narrative'].str.contains(pattern, case=False, na=False)]
                if len(suspicious) > 0:
                    results["suspicious_amounts"].append({
                        "pattern": pattern,
                        "count": len(suspicious)
                    })
        
        return results
    
    def _validate_dates(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate transaction dates"""
        results = {
            "date_issues": [],
            "future_dates": [],
            "invalid_dates": []
        }
        
        if 'Transaction Date' in df.columns:
            df['Transaction Date'] = pd.to_datetime(df['Transaction Date'], errors='coerce')
            
            # Check for future dates
            future_dates = df[df['Transaction Date'] > datetime.now()]
            if len(future_dates) > 0:
                results["future_dates"] = future_dates['Transaction Date'].dt.strftime('%Y-%m-%d').tolist()
            
            # Check for invalid dates
            invalid_dates = df[df['Transaction Date'].isna()]
            if len(invalid_dates) > 0:
                results["invalid_dates"] = len(invalid_dates)
        
        return results
    
    def _validate_narratives(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate transaction narratives"""
        results = {
            "narrative_stats": {},
            "empty_narratives": 0,
            "short_narratives": 0,
            "duplicate_narratives": 0
        }
        
        if 'Narrative' in df.columns:
            narratives = df['Narrative']
            results["narrative_stats"]["avg_length"] = narratives.str.len().mean()
            results["narrative_stats"]["min_length"] = narratives.str.len().min()
            results["narrative_stats"]["max_length"] = narratives.str.len().max()
            
            results["empty_narratives"] = len(narratives[narratives == ''])
            results["short_narratives"] = len(narratives[narratives.str.len() < 5])
            results["duplicate_narratives"] = len(narratives) - len(narratives.unique())
        
        return results
    
    def _validate_balances(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate balance calculations"""
        results = {
            "balance_issues": [],
            "negative_balances": 0,
            "balance_consistency": True
        }
        
        if 'Balance' in df.columns:
            balances = df['Balance']
            results["negative_balances"] = len(balances[balances < 0])
            
            # Check for balance consistency
            if len(balances) > 1:
                for i in range(1, len(balances)):
                    if pd.notna(balances.iloc[i-1]) and pd.notna(balances.iloc[i]):
                        # Balance should be cumulative
                        if balances.iloc[i] < balances.iloc[i-1] and balances.iloc[i] >= 0:
                            results["balance_consistency"] = False
                            results["balance_issues"].append(f"Balance inconsistency at row {i+1}")
        
        return results
    
    def _generate_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate statistical analysis"""
        results = {
            "monthly_summary": {},
            "top_transactions": {},
            "transaction_patterns": {}
        }
        
        if 'Transaction Date' in df.columns:
            df['Transaction Date'] = pd.to_datetime(df['Transaction Date'])
            
            # Monthly summary - fix tuple key issue
            monthly_stats = df.groupby(df['Transaction Date'].dt.to_period('M')).agg({
                'Transaction Date': 'count',
                'Amount (₹)': ['sum', 'mean', 'min', 'max']
            }).round(2)
            
            # Convert to proper dictionary format
            monthly_dict = {}
            for month in monthly_stats.index:
                month_str = str(month)
                monthly_dict[month_str] = {
                    'transaction_count': int(monthly_stats.loc[month, ('Transaction Date', 'count')]),
                    'total_amount': float(monthly_stats.loc[month, ('Amount (₹)', 'sum')]),
                    'avg_amount': float(monthly_stats.loc[month, ('Amount (₹)', 'mean')]),
                    'min_amount': float(monthly_stats.loc[month, ('Amount (₹)', 'min')]),
                    'max_amount': float(monthly_stats.loc[month, ('Amount (₹)', 'max')])
                }
            results["monthly_summary"] = monthly_dict
        
        # Top transactions by amount
        amount_col = None
        for col in df.columns:
            if 'Amount' in col:
                amount_col = col
                break
        
        if amount_col:
            top_debits = df.nlargest(5, amount_col)[['Transaction Date', 'Narrative', amount_col]]
            top_credits = df.nsmallest(5, amount_col)[['Transaction Date', 'Narrative', amount_col]]
            
            results["top_transactions"]["largest_debits"] = top_debits.to_dict('records')
            results["top_transactions"]["largest_credits"] = top_credits.to_dict('records')
        
        return results
    
    def _generate_validation_summary(self, validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate validation summary"""
        summary = {
            "overall_status": "PASS",
            "total_issues": 0,
            "critical_issues": 0,
            "warnings": 0,
            "recommendations": []
        }
        
        # Count issues
        for check_name, check_results in validation_results["checks"].items():
            if isinstance(check_results, dict):
                if "errors" in check_results:
                    summary["total_issues"] += len(check_results["errors"])
                if "warnings" in check_results:
                    summary["warnings"] += len(check_results["warnings"])
        
        # Determine overall status
        if summary["critical_issues"] > 0:
            summary["overall_status"] = "FAIL"
        elif summary["total_issues"] > 0:
            summary["overall_status"] = "WARNING"
        
        # Generate recommendations
        if validation_results["total_transactions"] < 10:
            summary["recommendations"].append("Low transaction count - verify extraction completeness")
        
        if summary["warnings"] > 5:
            summary["recommendations"].append("Multiple warnings detected - review data quality")
        
        return summary
    
    def _save_validation_report(self, validation_results: Dict[str, Any], report_path: str):
        """Save detailed validation report"""
        with open(report_path, 'w') as f:
            f.write("=" * 80 + "\n")
            f.write("BANK STATEMENT VALIDATION REPORT\n")
            f.write("=" * 80 + "\n\n")
            
            f.write(f"File: {validation_results['file_name']}\n")
            f.write(f"Generated: {validation_results['timestamp']}\n")
            f.write(f"Total Transactions: {validation_results['total_transactions']}\n")
            f.write(f"Overall Status: {validation_results['summary']['overall_status']}\n\n")
            
            f.write("SUMMARY\n")
            f.write("-" * 40 + "\n")
            f.write(f"Total Issues: {validation_results['summary']['total_issues']}\n")
            f.write(f"Warnings: {validation_results['summary']['warnings']}\n")
            f.write(f"Critical Issues: {validation_results['summary']['critical_issues']}\n\n")
            
            f.write("DETAILED RESULTS\n")
            f.write("-" * 40 + "\n")
            
            for check_name, check_results in validation_results["checks"].items():
                f.write(f"\n{check_name.upper()}:\n")
                f.write("-" * 20 + "\n")
                f.write(json.dumps(check_results, indent=2, default=str))
                f.write("\n")
            
            if validation_results["summary"]["recommendations"]:
                f.write("\nRECOMMENDATIONS\n")
                f.write("-" * 40 + "\n")
                for rec in validation_results["summary"]["recommendations"]:
                    f.write(f"• {rec}\n")
    
    def process_all_pdfs(self, data_dir: str = "data", output_dir: str = "output"):
        """Process all PDFs in the data directory with complete extraction and fixes"""
        if not os.path.exists(data_dir):
            logger.error(f"Data directory '{data_dir}' not found!")
            return
        
        pdf_files = [f for f in os.listdir(data_dir) if f.lower().endswith('.pdf')]
        
        if not pdf_files:
            logger.warning(f"No PDF files found in '{data_dir}'")
            return
        
        logger.info(f"🚀 Found {len(pdf_files)} PDF files to process")
        
        results = []
        for pdf_file in pdf_files:
            pdf_path = os.path.join(data_dir, pdf_file)
            logger.info(f"\n{'='*60}")
            logger.info(f"📄 Processing: {pdf_file}")
            logger.info(f"{'='*60}")
            
            # Extract and fix in one step
            result = self.extract_and_fix_transactions(pdf_path, output_dir)
            if result:
                results.append(result)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"🎉 Successfully processed {len(results)} PDF files!")
        logger.info(f"📁 All results saved in: {output_dir}")
        logger.info(f"{'='*60}")
        
        return results

def main():
    """Main function to run the complete extractor"""
    extractor = CompleteBankExtractor()
    extractor.process_all_pdfs()

if __name__ == "__main__":
    main() 