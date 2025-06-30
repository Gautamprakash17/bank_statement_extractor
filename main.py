#!/usr/bin/env python3
"""
Main script for the Bank Statement Extractor.
Simple entry point to use the modular extractor.
"""

import sys
import logging
from bank_extractor import CompleteBankExtractor

def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

def main():
    """Main function to run the bank statement extractor."""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Create extractor instance
    extractor = CompleteBankExtractor()
    
    # Check command line arguments
    if len(sys.argv) > 1:
        # Process specific PDF file
        pdf_path = sys.argv[1]
        logger.info(f"Processing single file: {pdf_path}")
        result = extractor.extract_and_fix_transactions(pdf_path)
        if result:
            logger.info(f"✅ Successfully processed: {result}")
        else:
            logger.error("❌ Failed to process PDF")
    else:
        # Process all PDFs in data directory
        logger.info("Processing all PDFs in data directory")
        extractor.process_all_pdfs()

if __name__ == "__main__":
    main() 