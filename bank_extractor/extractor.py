"""
Main extractor module that orchestrates all components.
"""

import os
import re
import json
import logging
import pdfplumber
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from .config import ExtractorConfig
from .parsers import SBIParser, UniversalParser, PNBParser
from .validators import DataValidator

logger = logging.getLogger(__name__)

class CompleteBankExtractor:
    """Complete bank statement extractor with modular architecture."""
    
    def __init__(self):
        """Initialize the extractor with configuration and components."""
        self.config = ExtractorConfig()
        self.sbi_parser = SBIParser(self.config)
        self.universal_parser = UniversalParser(self.config)
        self.pnb_parser = PNBParser(self.config)
        self.validator = DataValidator(self.config)
    
    def _detect_currency(self, text: str) -> Tuple[str, str]:
        """Detect currency from text"""
        for currency, info in self.config.currencies.items():
            for pattern in info["patterns"]:
                if re.search(pattern, text):
                    return currency, info["symbol"]
        return "INR", "₹"  # Default to INR
    
    def _is_transaction_line(self, line: str) -> bool:
        """Strictly check if line is a real transaction (date, amount, balance present)"""
        # Must have a date, an amount, and a balance
        has_date = any(re.search(pattern, line) for pattern in self.config.date_patterns)
        has_amount = any(re.search(pattern, line) for pattern in self.config.amount_patterns)
        has_balance = bool(re.search(r'[0-9,]+\.\d{2}(\s|$)', line))
        # Must not be a header or info row
        is_not_header = not re.match(r'^(Account|Branch|CRN|IFSC|MICR|Elint|TRANSACTION|#|\s*$)', line, re.IGNORECASE)
        return has_date and has_amount and has_balance and is_not_header
    
    def _is_multi_line_transaction(self, lines: List[str], line_index: int) -> bool:
        """Check if current line is part of a multi-line transaction"""
        if line_index + 1 >= len(lines):
            return False
        
        current_line = lines[line_index].strip()
        next_line = lines[line_index + 1].strip()
        
        # Check if next line is a continuation (contains date in parentheses)
        if re.search(r'\([0-9]{2}-[A-Za-z]{3}-[0-9]{2,4}\)', next_line):
            return True
        
        return False
    
    def extract_and_fix_transactions(self, pdf_path: str, output_dir: str = "output") -> str:
        """Extract and fix transactions from PDF."""
        try:
            # Create output directory if it doesn't exist
            os.makedirs(output_dir, exist_ok=True)
            
            # Generate output file names
            base_name = os.path.splitext(os.path.basename(pdf_path))[0]
            final_csv = os.path.join(output_dir, f"{base_name}_complete.csv")
            validation_report = os.path.join(output_dir, f"{base_name}_validation_report.txt")
            
            logger.info(f"🔄 Extracting and fixing transactions from {pdf_path}")
            
            transactions = []
            currency = "INR"
            symbol = "₹"
            
            # Extract text from PDF
            with pdfplumber.open(pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    logger.info(f"Processing page {page_num}")
                    
                    text = page.extract_text()
                    if not text:
                        continue
                    
                    lines = text.split('\n')
                    # If PNB is detected in the file name or first page, use PNBParser
                    if ("pnb" in base_name.lower()) or ("punjab national bank" in text.lower()):
                        logger.info("Detected PNB statement, using PNBParser.")
                        transactions.extend(self.pnb_parser.parse_pnb_transactions(lines))
                        continue
                    i = 0
                    
                    while i < len(lines):
                        line_content = lines[i].strip()
                        if not line_content:
                            i += 1
                            continue

                        if not transactions:
                            currency, symbol = self._detect_currency(line_content)
                            logger.info(f"Detected currency: {currency} ({symbol})")

                        # Try SBI parser first
                        transaction = self.sbi_parser.parse_multi_line_transaction(line_content, lines, i)
                        
                        if transaction:
                            transactions.append(transaction)
                            logger.debug(f"Found SBI transaction: {transaction}")
                            # Skip next line for SBI multi-line format
                            sbi_line1_pattern = self.config.sbi_patterns["line1"]
                            if re.match(sbi_line1_pattern, line_content):
                                i += 2
                                continue
                        else:
                            # Try traditional SBI format
                            transaction = self.sbi_parser.parse_traditional_format(line_content)
                            if transaction:
                                transactions.append(transaction)
                                logger.debug(f"Found traditional SBI transaction: {transaction}")
                            else:
                                # Try universal parser
                                transaction = self.universal_parser.parse_with_patterns(line_content, lines, i)
                                if transaction:
                                    transactions.append(transaction)
                                    logger.debug(f"Found universal transaction: {transaction}")
                                else:
                                    # Try enhanced fallback parsing
                                    transaction = self.universal_parser.enhanced_fallback_parsing(line_content, lines, i)
                                    if transaction:
                                        transactions.append(transaction)
                                        logger.debug(f"Found fallback transaction: {transaction}")

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
    
    def _apply_comprehensive_fixes(self, df: pd.DataFrame, currency: str, symbol: str) -> pd.DataFrame:
        """Apply comprehensive data quality fixes."""
        logger.info("🔧 Applying comprehensive data quality fixes...")
        
        # Standardize columns
        df = self._standardize_columns(df, currency, symbol)
        
        # Fix balance calculations
        df = self._fix_balance_calculations(df)
        
        # Clean narratives
        df = self._clean_narratives(df)
        
        # Remove suspicious transactions
        df = self._remove_suspicious_transactions(df)
        
        # Standardize dates
        df = self._standardize_dates(df)
        
        logger.info(f"📈 Data quality improvements completed: {len(df)} transactions")
        return df
    
    def _standardize_columns(self, df: pd.DataFrame, currency: str, symbol: str) -> pd.DataFrame:
        """Standardize column names and formats."""
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
        """Fix balance calculations - use extracted balance from PDF."""
        logger.info("💰 Using balance as extracted from PDF (no recalculation)")
        return df
    
    def _clean_narratives(self, df: pd.DataFrame) -> pd.DataFrame:
        """Clean and improve narrative descriptions."""
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
        """Clean individual narrative text."""
        if not text or text == 'nan':
            return ''
        
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common parsing artifacts
        text = re.sub(r'^\d+\s*', '', text)  # Remove leading numbers
        text = re.sub(r'[^\w\s\-\./]', '', text)  # Keep only alphanumeric, spaces, hyphens, dots, slashes
        
        return text.strip()
    
    def _remove_suspicious_transactions(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove transactions that are likely parsing errors."""
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
        """Standardize date formats."""
        date_columns = ['Transaction Date']
        
        for col in date_columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce')
                df[col] = df[col].dt.strftime('%Y-%m-%d')
        
        logger.info("📅 Standardized date formats")
        return df
    
    def _apply_comprehensive_validation(self, df: pd.DataFrame, file_name: str) -> Dict[str, Any]:
        """Apply comprehensive validation checks."""
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
        validation_results["checks"]["data_integrity"] = self.validator.validate_data_integrity(df)
        
        # 2. Business Logic Validation
        validation_results["checks"]["business_logic"] = self.validator.validate_business_logic(df)
        
        # 3. Amount Validation
        validation_results["checks"]["amount_validation"] = self.validator.validate_amounts(df)
        
        # 4. Date Validation
        validation_results["checks"]["date_validation"] = self.validator.validate_dates(df)
        
        # 5. Narrative Validation
        validation_results["checks"]["narrative_validation"] = self.validator.validate_narratives(df)
        
        # 6. Balance Validation
        validation_results["checks"]["balance_validation"] = self.validator.validate_balances(df)
        
        # 7. Statistical Analysis
        validation_results["checks"]["statistics"] = self.validator.generate_statistics(df)
        
        # Generate summary
        validation_results["summary"] = self.validator.generate_validation_summary(validation_results)
        
        logger.info("✅ Validation completed")
        return validation_results
    
    def _save_validation_report(self, validation_results: Dict[str, Any], report_path: str):
        """Save detailed validation report."""
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
        """Process all PDFs in the data directory."""
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