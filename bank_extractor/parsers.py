"""
Parsers module for different bank statement formats.
Contains parsing logic for various transaction patterns.
"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)

class TransactionParser:
    """Base class for transaction parsing."""
    
    def __init__(self, config):
        self.config = config
    
    def parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date string to datetime object."""
        try:
            date_str = date_str.strip()
            
            for fmt in self.config.date_formats:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None
    
    def extract_amount(self, text: str) -> Optional[float]:
        """Extract amount from text."""
        try:
            for pattern in self.config.amount_patterns:
                matches = re.findall(pattern, text)
                if matches:
                    # Take the last match (usually the amount)
                    amount_str = matches[-1].replace(',', '')
                    return float(amount_str)
            return None
        except Exception:
            return None
    
    def extract_last_numeric_value(self, line: str) -> Optional[float]:
        """Extract the last numeric value from a line (usually balance)."""
        try:
            matches = re.findall(r'[+-]?[0-9,]+\.\d{2}', line)
            if matches:
                return float(matches[-1].replace(',', ''))
            return None
        except Exception:
            return None
    
    def _extract_narrative(self, line: str, date_matches: List) -> str:
        """Extract narrative from transaction line"""
        if len(date_matches) >= 1:
            # Extract text between transaction number and amount
            start_pos = date_matches[0].end()
            end_pos = len(line)
            
            # Find amount position
            for pattern in self.config.amount_patterns:
                amount_match = re.search(pattern, line[start_pos:])
                if amount_match:
                    end_pos = start_pos + amount_match.start()
                    break
            
            narrative = line[start_pos:end_pos].strip()
            return narrative
        return ""
    
    def _is_transaction_line(self, line: str) -> bool:
        """Strictly check if line is a real transaction (date, amount, balance present)"""
        # Must have a date, an amount, and a balance
        has_date = any(re.search(pattern, line) for pattern in self.config.date_patterns)
        has_amount = any(re.search(pattern, line) for pattern in self.config.amount_patterns)
        has_balance = bool(re.search(r'[0-9,]+\.\d{2}(\s|$)', line))
        # Must not be a header or info row
        is_not_header = not re.match(r'^(Account|Branch|CRN|IFSC|MICR|Elint|TRANSACTION|#|\s*$)', line, re.IGNORECASE)
        return has_date and has_amount and has_balance and is_not_header

class SBIParser(TransactionParser):
    """Parser for State Bank of India statements."""
    
    def parse_multi_line_transaction(self, line: str, lines: List[str], line_index: int) -> Optional[Dict]:
        """Parse SBI multi-line transaction format."""
        sbi_line1_pattern = self.config.sbi_patterns["line1"]
        
        if re.match(sbi_line1_pattern, line):
            logger.debug(f"SBI pattern matched for line: {line}")
            try:
                m1 = re.match(sbi_line1_pattern, line)
                transaction_date = self.parse_date(m1.group(1).replace('-', ' '))
                transaction_type = m1.group(2)  # TO or BY
                narration1 = m1.group(3).strip()
                amount = float(m1.group(4).replace(',', ''))
                balance = float(m1.group(5).replace(',', ''))
                
                # Look ahead for value date and more narration
                narration2 = ''
                if line_index + 1 < len(lines):
                    next_line = lines[line_index + 1].strip()
                    m2 = re.match(self.config.sbi_patterns["line2"], next_line)
                    if m2:
                        narration2 = m2.group(2).strip()
                
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
        return None
    
    def parse_traditional_format(self, line: str) -> Optional[Dict]:
        """Parse traditional SBI format with separate debit/credit columns."""
        sbi_pattern = self.config.sbi_patterns["traditional"]
        sbi_match = re.match(sbi_pattern, line)
        
        if sbi_match:
            try:
                transaction_date = self.parse_date(sbi_match.group(1).replace('-', ' '))
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
                logger.debug(f"SBI traditional pattern failed: {e}")
                return None
        return None

class UniversalParser(TransactionParser):
    """Universal parser for various bank formats."""
    
    def parse_with_patterns(self, line: str, lines: List[str], line_index: int) -> Optional[Dict]:
        """Parse transaction using universal patterns."""
        for pattern_idx, pattern in enumerate(self.config.transaction_patterns):
            match = re.match(pattern, line)
            if match:
                try:
                    groups = match.groups()
                    
                    if pattern_idx in [0, 1, 2]:  # Patterns with value date
                        transaction_date = self.parse_date(groups[2])
                        narrative = groups[3].strip() if len(groups) > 3 else ""
                        if len(narrative) < 10 or narrative.upper().endswith('-'):
                            narrative = self._extract_multi_line_narrative(lines, line_index, narrative)
                        amount = self.extract_amount(groups[-2])
                        balance = self.extract_last_numeric_value(line)
                        
                    elif pattern_idx in [4, 5]:  # Patterns with debit/credit
                        transaction_date = self.parse_date(groups[1])
                        narrative = groups[2].strip()
                        if len(narrative) < 10 or narrative.upper().endswith('-'):
                            narrative = self._extract_multi_line_narrative(lines, line_index, narrative)
                        debit_amount = self.extract_amount(groups[4]) if len(groups) > 4 else None
                        credit_amount = self.extract_amount(groups[5]) if len(groups) > 5 else None
                        amount = -debit_amount if debit_amount and debit_amount > 0 else (credit_amount if credit_amount and credit_amount > 0 else None)
                        balance = self.extract_last_numeric_value(line)
                        
                    else:  # Fallback patterns
                        transaction_date = None
                        narrative = ""
                        amount = self.extract_amount(line)
                        balance = self.extract_last_numeric_value(line)
                    
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
    
    def parse_with_enhanced_patterns(self, line: str, lines: List[str], line_index: int) -> Optional[Dict]:
        """Parse transaction using enhanced patterns (same as parse_with_patterns for compatibility)."""
        return self.parse_with_patterns(line, lines, line_index)
    
    def _extract_multi_line_narrative(self, lines: List[str], line_index: int, initial_narrative: str) -> str:
        """Extract multi-line narrative with improved logic."""
        narrative = initial_narrative
        j = line_index + 1
        
        while j < len(lines):
            next_line = lines[j].strip()
            
            # Stop if next line is a new transaction
            if self._is_transaction_line(next_line):
                break
            
            # Stop if line contains amount and looks like balance
            for pattern in self.config.amount_patterns:
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
    
    def enhanced_fallback_parsing(self, line: str, lines: List[str], line_index: int) -> Optional[Dict]:
        """Enhanced fallback parsing for complex formats, always use last numeric value as balance"""
        try:
            tx_match = re.match(r'^(\d+)', line)
            if not tx_match:
                return None
            date_matches = []
            for pattern in self.config.date_patterns:
                date_matches.extend(list(re.finditer(pattern, line)))
            if len(date_matches) >= 1:
                transaction_date = self.parse_date(date_matches[0].group())
                if transaction_date:
                    narrative = self._extract_narrative(line, date_matches)
                    if len(narrative) < 10 or narrative.upper().endswith('-'):
                        narrative = self._extract_multi_line_narrative(lines, line_index, narrative)
                    amount = self.extract_amount(line)
                    balance = self.extract_last_numeric_value(line)
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

class PNBParser(TransactionParser):
    """Parser for Punjab National Bank statements with multi-line narration."""
    def parse_pnb_transactions(self, lines: list) -> list:
        import re
        transactions = []
        current_narration = []
        for line in lines:
            line = line.strip()
            # Check for date at the start of the line
            date_match = re.match(r'(\d{2}/\d{2}/\d{4})', line)
            if date_match:
                # If we have a previous narration, attach it to the last transaction
                if current_narration and transactions:
                    transactions[-1]['Narration'] += ' ' + ' '.join(current_narration)
                    current_narration = []
                # Extract amounts and balance
                amounts = re.findall(r'[\d,]+\.\d{2}', line)
                balance_match = re.search(r'([\d,]+\.\d{2})\s*Cr\.', line)
                # Build transaction dict
                transactions.append({
                    'Date': date_match.group(1),
                    'Withdrawal': amounts[0] if len(amounts) > 0 else '',
                    'Deposit': amounts[1] if len(amounts) > 1 else '',
                    'Balance': balance_match.group(1) if balance_match else '',
                    'Narration': ''
                })
            else:
                # If not a date line, treat as narration
                current_narration.append(line)
        # Attach any remaining narration
        if current_narration and transactions:
            transactions[-1]['Narration'] += ' ' + ' '.join(current_narration)
        return transactions 