from typing import Dict
from core.config.settings import Settings
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from core.logging import get_logger
from ..interfaces.trader_interface import Trader
from .paper_trader import PaperTrader
from .zerodha_trader import ZerodhaTrader

logger = get_logger(__name__)

class TraderFactory:
    """Factory for creating and managing trader instances."""
    
    def __init__(self, settings: Settings, instrument_service: InstrumentRegistryService):
        self._settings = settings
        self._instrument_service = instrument_service
        self._traders: Dict[str, Trader] = {}
        self._initialized = False
    
    async def initialize(self) -> None:
        """Initialize all available traders."""
        if self._initialized:
            return
            
        # Create trader instances
        self._traders = {
            "paper": PaperTrader(self._settings),
            "zerodha": ZerodhaTrader(self._settings, self._instrument_service),
        }
        
        # Initialize each trader
        for namespace, trader in self._traders.items():
            try:
                success = await trader.initialize()
                if not success:
                    logger.warning(f"Failed to initialize {namespace} trader")
            except Exception as e:
                logger.error(f"Error initializing {namespace} trader: {e}")
        
        self._initialized = True
    
    def get_trader(self, namespace: str) -> Trader:
        """Get trader instance for namespace."""
        if not self._initialized:
            raise RuntimeError("TraderFactory not initialized")
            
        trader = self._traders.get(namespace)
        if not trader:
            raise ValueError(f"No trader found for namespace: {namespace}")
        return trader
    
    async def shutdown(self) -> None:
        """Shutdown all traders."""
        for trader in self._traders.values():
            await trader.shutdown()