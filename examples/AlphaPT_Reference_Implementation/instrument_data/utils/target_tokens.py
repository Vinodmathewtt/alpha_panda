from pathlib import Path
from typing import List, Set, Optional
import asyncio
from core.logging.logger import get_logger

logger = get_logger(__name__)


class TargetTokenManager:
    """Manages target instrument tokens for focused processing."""
    
    def __init__(self, tokens_file_path: str):
        self.tokens_file_path = Path(tokens_file_path)
        self._cached_tokens: Optional[Set[int]] = None
        self._last_modified: Optional[float] = None
    
    async def load_target_tokens(self, force_reload: bool = False) -> List[int]:
        """Load target tokens from file with caching."""
        try:
            # Check if file exists
            if not self.tokens_file_path.exists():
                logger.warning(f"Target tokens file not found: {self.tokens_file_path}")
                return []
            
            # Check if reload is needed
            current_modified = self.tokens_file_path.stat().st_mtime
            
            if (not force_reload and 
                self._cached_tokens is not None and 
                self._last_modified == current_modified):
                logger.debug("Using cached target tokens")
                return list(self._cached_tokens)
            
            # Load tokens from file
            tokens = set()
            
            with open(self.tokens_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    
                    # Parse token (may have comment after space/tab)
                    token_part = line.split()[0] if line.split() else ''
                    
                    try:
                        token = int(token_part)
                        tokens.add(token)
                    except ValueError:
                        logger.warning(f"Invalid token on line {line_num}: '{token_part}' in {self.tokens_file_path}")
                        continue
            
            # Update cache
            self._cached_tokens = tokens
            self._last_modified = current_modified
            
            logger.info(f"Loaded {len(tokens)} target tokens from {self.tokens_file_path}")
            return list(tokens)
            
        except Exception as e:
            logger.error(f"Error loading target tokens from {self.tokens_file_path}: {e}")
            return []
    
    async def validate_tokens_file(self) -> dict:
        """Validate tokens file format and accessibility."""
        issues = []
        
        try:
            # Check file existence
            if not self.tokens_file_path.exists():
                issues.append(f"File does not exist: {self.tokens_file_path}")
                return {"valid": False, "issues": issues, "token_count": 0}
            
            # Check file readability
            if not self.tokens_file_path.is_file():
                issues.append(f"Path is not a file: {self.tokens_file_path}")
                return {"valid": False, "issues": issues, "token_count": 0}
            
            # Try to read and validate content
            tokens = await self.load_target_tokens(force_reload=True)
            
            if not tokens:
                issues.append("No valid tokens found in file")
            
            # Additional validations
            if len(tokens) > 10000:
                issues.append(f"Too many tokens ({len(tokens)}), consider limiting for performance")
            
            # Check for duplicates (though set() removes them)
            with open(self.tokens_file_path, 'r', encoding='utf-8') as f:
                lines = [line.strip() for line in f if line.strip() and not line.strip().startswith('#')]
                tokens_in_file = []
                
                for line in lines:
                    token_part = line.split()[0] if line.split() else ''
                    try:
                        tokens_in_file.append(int(token_part))
                    except ValueError:
                        pass
                
                if len(tokens_in_file) != len(set(tokens_in_file)):
                    issues.append("File contains duplicate tokens")
            
            return {
                "valid": len(issues) == 0,
                "issues": issues,
                "token_count": len(tokens),
                "file_path": str(self.tokens_file_path),
                "file_size": self.tokens_file_path.stat().st_size,
                "last_modified": self.tokens_file_path.stat().st_mtime
            }
            
        except Exception as e:
            issues.append(f"Error validating file: {e}")
            return {"valid": False, "issues": issues, "token_count": 0}
    
    async def is_target_token(self, token: int) -> bool:
        """Check if token is in target list."""
        if self._cached_tokens is None:
            await self.load_target_tokens()
        
        return token in (self._cached_tokens or set())
    
    async def get_target_count(self) -> int:
        """Get number of target tokens."""
        if self._cached_tokens is None:
            await self.load_target_tokens()
        
        return len(self._cached_tokens or set())
    
    async def watch_for_changes(self, callback) -> None:
        """Watch tokens file for changes (simple polling implementation)."""
        logger.info(f"Starting file watcher for {self.tokens_file_path}")
        
        last_modified = None
        if self.tokens_file_path.exists():
            last_modified = self.tokens_file_path.stat().st_mtime
        
        while True:
            try:
                await asyncio.sleep(10)  # Check every 10 seconds
                
                if not self.tokens_file_path.exists():
                    if last_modified is not None:
                        logger.warning(f"Target tokens file was deleted: {self.tokens_file_path}")
                        last_modified = None
                        if callback:
                            await callback("file_deleted", [])
                    continue
                
                current_modified = self.tokens_file_path.stat().st_mtime
                
                if last_modified is None or current_modified != last_modified:
                    logger.info(f"Target tokens file changed, reloading...")
                    tokens = await self.load_target_tokens(force_reload=True)
                    last_modified = current_modified
                    
                    if callback:
                        await callback("file_changed", tokens)
                
            except Exception as e:
                logger.error(f"Error in file watcher: {e}")
                await asyncio.sleep(30)  # Wait longer on error


async def create_default_target_tokens_file(file_path: str) -> bool:
    """Create a default target tokens file with common instruments."""
    try:
        path = Path(file_path)
        
        # Create directory if it doesn't exist
        path.parent.mkdir(parents=True, exist_ok=True)
        
        # Default content with common instruments
        default_content = """# AlphaPT Target Trading Instruments
# Format: instrument_token [optional_comment]
# Lines starting with # are ignored

# Indices
256265    # NIFTY 50
260105    # NIFTY BANK

# Large Cap Stocks
738561    # RELIANCE
2714625   # ICICIBANK
1270529   # HDFCBANK
4267265   # TCS
1895425   # ITC

# Banking Stocks
341249    # AXISBANK
81153     # KOTAKBANK
2058499   # INDUSINDBK

# IT Stocks
3924777   # INFY
3532289   # WIPRO
4454913   # TECHM

# Auto Stocks
4267523   # MARUTI
884737    # M&M
348929    # TATAMOTORS

# FMCG Stocks
356865    # HINDUNILVR
6386689   # NESTLEIND
975873    # BRITANNIA

# Add more target instruments as needed
# Maximum recommended: 100-200 instruments for optimal performance
"""
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(default_content)
        
        logger.info(f"Created default target tokens file: {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Error creating default target tokens file: {e}")
        return False