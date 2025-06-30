"""
Configuration module for bank statement extractor.
Contains all patterns, formats, and settings.
"""

import re
import json
import os
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class ExtractorConfig:
    """Configuration class for the bank statement extractor."""
    
    def __init__(self, config_file: str = None):
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
    
    @property
    def date_formats(self):
        return self.config["date_formats"]
    
    @property
    def transaction_patterns(self):
        return self.config["transaction_patterns"]
    
    @property
    def validation_rules(self):
        return self.config["validation_rules"]
    
    @property
    def currencies(self):
        return self.config["currencies"]
    
    @property
    def sbi_patterns(self):
        return {
            "line1": r'^(\d{2}-\w{3}-\d{2,4})\s+(TO|BY)\s+(.+?)\s+([0-9,]+\.\d{2})\s+([+-]?[0-9,]+\.\d{2})$',
            "line2": r'^\((\d{2}-\w{3}-\d{2,4})\)\s*(.*)$',
            "traditional": r'^(\d{2}-\w{3}-\d{2,4})\s*\((\d{2}-\w{3}-\d{2,4})\)\s+(.+?)\s+([\w/-]+)\s+([0-9,]+\.\d{2}|-)\s+([0-9,]+\.\d{2}|-)\s+([+-]?[0-9,]+\.\d{2})$'
        }
    
    def get_config(self) -> Dict[str, Any]:
        """Get complete configuration as dictionary."""
        config = self.config.copy()
        config["sbi_patterns"] = self.sbi_patterns
        return config 