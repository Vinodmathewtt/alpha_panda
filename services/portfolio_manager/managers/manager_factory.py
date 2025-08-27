from typing import Dict
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.logging import get_trading_logger_safe
from ..interfaces.base_portfolio_manager import BasePortfolioManager


class PortfolioManagerFactory:
    """Factory for creating portfolio managers by execution mode."""
    
    def __init__(self, settings: Settings, redis_client, db_manager: DatabaseManager):
        self._settings = settings
        self._redis_client = redis_client
        self._db_manager = db_manager
        self._managers: Dict[str, BasePortfolioManager] = {}
        self._initialized = False
        self.logger = get_trading_logger_safe("portfolio_manager_factory")
    
    async def initialize(self) -> None:
        """Initialize all portfolio managers."""
        if self._initialized:
            return
        
        # Import managers here to avoid circular imports
        from .paper_manager import PaperPortfolioManager
        from .zerodha_manager import ZerodhaPortfolioManager
        
        # Create manager instances
        from core.schemas.events import ExecutionMode
        self._managers = {
            ExecutionMode.PAPER.value: PaperPortfolioManager(
                self._settings, 
                self._redis_client
            ),
            ExecutionMode.ZERODHA.value: ZerodhaPortfolioManager(
                self._settings, 
                self._redis_client, 
                self._db_manager
            ),
        }
        
        # Initialize each manager
        for execution_mode, manager in self._managers.items():
            await manager.start()
            self.logger.info(f"Initialized {execution_mode} portfolio manager")
        
        self._initialized = True
    
    def get_manager(self, execution_mode: str) -> BasePortfolioManager:
        """Get manager for execution mode."""
        if not self._initialized:
            raise RuntimeError("PortfolioManagerFactory not initialized")
            
        manager = self._managers.get(execution_mode)
        if not manager:
            raise ValueError(f"No portfolio manager for execution mode: {execution_mode}")
        return manager
    
    async def shutdown(self) -> None:
        """Shutdown all managers."""
        for manager in self._managers.values():
            await manager.stop()
        self.logger.info("All portfolio managers shut down")