"""
Validators module for data validation and quality checks.
"""

import logging
import pandas as pd
from datetime import datetime
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class DataValidator:
    """Data validation and quality checking."""
    
    def __init__(self, config):
        self.config = config
    
    def validate_data_integrity(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate data integrity."""
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
    
    def validate_business_logic(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate business logic."""
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
    
    def validate_amounts(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate transaction amounts."""
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
            for pattern in self.config.validation_rules["suspicious_patterns"]:
                suspicious = df[df['Narrative'].str.contains(pattern, case=False, na=False)]
                if len(suspicious) > 0:
                    results["suspicious_amounts"].append({
                        "pattern": pattern,
                        "count": len(suspicious)
                    })
        
        return results
    
    def validate_dates(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate transaction dates."""
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
    
    def validate_narratives(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate transaction narratives."""
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
    
    def validate_balances(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Validate balance calculations."""
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
    
    def generate_statistics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Generate statistical analysis."""
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
    
    def generate_validation_summary(self, validation_results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate validation summary."""
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