from typing import List, Dict, Any
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.logging import get_logger

logger = get_logger(__name__)

class ExecutionRouter:
    """Determines execution targets for trading signals."""
    
    def __init__(self, settings: Settings, db_manager: DatabaseManager):
        self.settings = settings
        self.db_manager = db_manager
        self.logger = get_logger(__name__)
    
    async def get_target_namespaces(self, strategy_id: str) -> List[str]:
        """Determine which execution namespaces to target."""
        namespaces = []
        
        # Paper trading (if enabled globally)
        if self.settings.paper_trading.enabled:
            namespaces.append("paper")
        
        # Live trading (if enabled for strategy)
        strategy_config = await self._get_strategy_config(strategy_id)
        if (strategy_config.get("zerodha_trading_enabled", False) and 
            self.settings.zerodha.enabled):
            namespaces.append("zerodha")
        
        return namespaces
    
    async def _get_strategy_config(self, strategy_id: str) -> Dict[str, Any]:
        """Fetch strategy configuration from database."""
        from core.database.models import StrategyConfiguration
        from sqlalchemy import select

        try:
            async with self.db_manager.get_session() as session:
                result = await session.execute(
                    select(StrategyConfiguration).where(StrategyConfiguration.id == strategy_id)
                )
                config = result.scalar_one_or_none()

                if config:
                    return {
                        "zerodha_trading_enabled": config.zerodha_trading_enabled,
                        "is_active": config.is_active,
                        "strategy_type": config.strategy_type,
                        "parameters": config.parameters
                    }
                else:
                    self.logger.warning("Strategy config not found", strategy_id=strategy_id)
                    return {"zerodha_trading_enabled": False}

        except Exception as e:
            self.logger.error("Error fetching strategy config", 
                            strategy_id=strategy_id,
                            error=str(e))
            return {"zerodha_trading_enabled": False}