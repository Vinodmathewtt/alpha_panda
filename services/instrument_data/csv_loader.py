"""
CSV file loading utilities for instrument data.
"""

import csv
import os
from pathlib import Path
from typing import List, Dict, Iterator, Optional, Any
import structlog

logger = structlog.get_logger(__name__)


class InstrumentCSVLoader:
    """
    Utility class for loading and parsing instrument CSV files.
    
    Handles the specific format used in services/market_feed/instruments.csv
    and provides validation and error handling.
    """
    
    def __init__(self, csv_file_path: str):
        """
        Initialize CSV loader with file path.
        
        Args:
            csv_file_path: Path to the CSV file
        """
        self.csv_file_path = Path(csv_file_path)
        self.validate_file_exists()
    
    def validate_file_exists(self) -> None:
        """Validate that the CSV file exists and is readable."""
        if not self.csv_file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_file_path}")
        
        if not self.csv_file_path.is_file():
            raise ValueError(f"Path is not a file: {self.csv_file_path}")
        
        if not os.access(self.csv_file_path, os.R_OK):
            raise PermissionError(f"Cannot read CSV file: {self.csv_file_path}")
    
    def load_instruments(self) -> List[Dict[str, Any]]:
        """
        Load all instruments from CSV file.
        
        Returns:
            List of dictionaries containing instrument data
            
        Raises:
            FileNotFoundError: If CSV file doesn't exist
            ValueError: If CSV format is invalid
        """
        instruments = []
        
        try:
            with open(self.csv_file_path, 'r', encoding='utf-8') as file:
                # Skip comment lines at the beginning
                lines = []
                for line in file:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        lines.append(line)
                
                if not lines:
                    logger.warning(f"No data found in CSV file: {self.csv_file_path}")
                    return []
                
                # Check if first non-comment line looks like a header
                first_line = lines[0] if lines else ""
                has_header = 'instrument_token' in first_line.lower()
                
                if has_header:
                    # First line is a header
                    csv_reader = csv.DictReader(lines)
                else:
                    # No header, use default field names from comment
                    fieldnames = ['instrument_token', 'tradingsymbol', 'name', 'exchange']
                    csv_reader = csv.DictReader(lines, fieldnames=fieldnames)
                
                for row_num, row in enumerate(csv_reader, start=1):
                    try:
                        # Validate required fields
                        if not self._validate_row(row, row_num):
                            continue
                        
                        # Clean and normalize row data
                        cleaned_row = self._clean_row(row)
                        instruments.append(cleaned_row)
                        
                    except Exception as e:
                        logger.error(f"Error processing CSV row {row_num}", error=str(e))
                        continue
                
                logger.info(f"Successfully loaded {len(instruments)} instruments from {self.csv_file_path}")
                return instruments
                
        except Exception as e:
            logger.error(f"Failed to load CSV file {self.csv_file_path}", error=str(e))
            raise
    
    def load_instruments_iterator(self) -> Iterator[Dict[str, Any]]:
        """
        Load instruments as an iterator for memory-efficient processing.
        
        Yields:
            Dictionary containing instrument data for each row
        """
        try:
            with open(self.csv_file_path, 'r', encoding='utf-8') as file:
                # Skip comment lines
                lines = []
                for line in file:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        lines.append(line)
                
                if not lines:
                    logger.warning(f"No data found in CSV file: {self.csv_file_path}")
                    return
                
                # Check if first non-comment line looks like a header
                first_line = lines[0] if lines else ""
                has_header = 'instrument_token' in first_line.lower()
                
                if has_header:
                    # First line is a header
                    csv_reader = csv.DictReader(lines)
                else:
                    # No header, use default field names from comment
                    fieldnames = ['instrument_token', 'tradingsymbol', 'name', 'exchange']
                    csv_reader = csv.DictReader(lines, fieldnames=fieldnames)
                
                for row_num, row in enumerate(csv_reader, start=1):
                    try:
                        if self._validate_row(row, row_num):
                            yield self._clean_row(row)
                    except Exception as e:
                        logger.error(f"Error processing CSV row {row_num}", error=str(e))
                        continue
                        
        except Exception as e:
            logger.error(f"Failed to iterate CSV file {self.csv_file_path}", error=str(e))
            raise
    
    def _validate_row(self, row: Dict[str, str], row_num: int) -> bool:
        """
        Validate a CSV row has required fields.
        
        Args:
            row: Dictionary containing row data
            row_num: Row number for error reporting
            
        Returns:
            True if row is valid, False otherwise
        """
        required_fields = ['instrument_token', 'tradingsymbol', 'name', 'exchange']
        
        for field in required_fields:
            if field not in row or not row[field].strip():
                logger.warning(f"Row {row_num}: Missing or empty required field '{field}'")
                return False
        
        # Validate instrument_token is numeric
        try:
            int(row['instrument_token'].strip())
        except ValueError:
            logger.warning(f"Row {row_num}: Invalid instrument_token '{row['instrument_token']}'")
            return False
        
        return True
    
    def _clean_row(self, row: Dict[str, str]) -> Dict[str, Any]:
        """
        Clean and normalize row data.
        
        Args:
            row: Raw row data from CSV
            
        Returns:
            Cleaned row data with proper types
        """
        cleaned = {}
        
        for key, value in row.items():
            # Strip whitespace and handle empty values
            cleaned_value = value.strip() if value else ''
            
            # Convert empty strings to None for optional fields
            if not cleaned_value and key not in ['instrument_token', 'tradingsymbol', 'name', 'exchange']:
                cleaned_value = None
            
            # Convert instrument_token to integer
            if key.strip().lower() == 'instrument_token' and cleaned_value:
                try:
                    cleaned_value = int(cleaned_value)
                except ValueError:
                    pass  # Keep as string if conversion fails
            
            cleaned[key.strip().lower()] = cleaned_value
        
        return cleaned
    
    def get_file_info(self) -> Dict[str, any]:
        """
        Get information about the CSV file.
        
        Returns:
            Dictionary containing file metadata
        """
        stat = self.csv_file_path.stat()
        
        return {
            'file_path': str(self.csv_file_path),
            'file_name': self.csv_file_path.name,
            'file_size': stat.st_size,
            'modified_time': stat.st_mtime,
            'exists': self.csv_file_path.exists(),
            'readable': os.access(self.csv_file_path, os.R_OK)
        }
    
    def count_instruments(self) -> int:
        """
        Count the number of valid instruments in the CSV file.
        
        Returns:
            Number of valid instrument rows
        """
        count = 0
        try:
            for _ in self.load_instruments_iterator():
                count += 1
        except Exception as e:
            logger.error(f"Error counting instruments", error=str(e))
            
        return count
    
    @staticmethod
    def get_default_csv_path() -> str:
        """
        Get the default path to the instruments CSV file.
        
        Returns:
            Path to services/market_feed/instruments.csv
        """
        # Get the project root directory
        current_file = Path(__file__)
        project_root = current_file.parent.parent.parent  # Go up to project root from services/instrument_data/
        
        csv_path = project_root / 'services' / 'market_feed' / 'instruments.csv'
        return str(csv_path)
    
    @classmethod
    def from_default_path(cls) -> 'InstrumentCSVLoader':
        """
        Create CSV loader using the default instruments.csv path.
        
        Returns:
            InstrumentCSVLoader instance
        """
        return cls(cls.get_default_csv_path())


def load_default_instruments() -> List[Dict[str, Any]]:
    """
    Convenience function to load instruments from default CSV file.
    
    Returns:
        List of instrument dictionaries
    """
    loader = InstrumentCSVLoader.from_default_path()
    return loader.load_instruments()


def count_default_instruments() -> int:
    """
    Convenience function to count instruments in default CSV file.
    
    Returns:
        Number of instruments
    """
    loader = InstrumentCSVLoader.from_default_path()
    return loader.count_instruments()