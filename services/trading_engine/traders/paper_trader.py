import random
import uuid
from typing import Dict, Any, Optional

from core.config.settings import Settings
from core.schemas.events import OrderFilled, SignalType, TradingSignal, ExecutionMode
from core.logging import get_logger
from ..interfaces.trader_interface import Trader

class PaperTrader(Trader):
    """
    Simulated trading execution implementing Trader interface.

    This class is a stateless simulation engine. It calculates slippage and
    commission to provide a realistic simulation of an order fill and returns
    the resulting data, but it does not publish any events itself.
    """
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.logger = get_logger(__name__)
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize paper trader (always succeeds)."""
        self._initialized = True
        self.logger.info("Paper trader initialized")
        return True

    async def shutdown(self) -> None:
        """Cleanup paper trader resources."""
        self.logger.info("Paper trader shutdown")

    def get_execution_mode(self) -> str:
        return ExecutionMode.PAPER.value

    async def execute_order(self, signal: TradingSignal, last_price: Optional[float]) -> Dict[str, Any]:
        """Execute simulated order."""
        if not self._initialized:
            raise RuntimeError("PaperTrader not initialized")
            
        # Use unified log architecture: prefer signal price, fallback to reasonable default
        if last_price is None:
            if signal.price is not None:
                last_price = float(signal.price)
                self.logger.info("Using signal price for execution", 
                               instrument_token=signal.instrument_token, 
                               price=last_price)
            else:
                # Fallback for paper trading: use a reasonable default price
                last_price = 100.0  # Default price for simulation
                self.logger.warning("No price available, using default for paper trading", 
                                  instrument_token=signal.instrument_token, 
                                  default_price=last_price)

        # 1. Simulate Slippage
        # Slippage is the difference between the expected price and the actual fill price.
        slippage_pct = self.settings.paper_trading.slippage_percent / 100
        # FIX: Compare with enum value (string) instead of enum object to avoid type mismatch
        price_direction = 1 if signal.signal_type == SignalType.BUY else -1
        slippage_amount = last_price * slippage_pct * random.uniform(0.5, 1.5)
        fill_price = last_price + (price_direction * slippage_amount)

        # 2. Simulate Commission
        order_value = signal.quantity * fill_price
        commission_pct = self.settings.paper_trading.commission_percent / 100
        commission = order_value * commission_pct

        # 3. Create the OrderFilled data model (not the full envelope)
        # This ensures the data structure is consistent with your schemas.
        fill_data = OrderFilled(
            strategy_id=signal.strategy_id,
            instrument_token=signal.instrument_token,
            signal_type=signal.signal_type,
            quantity=signal.quantity,
            fill_price=fill_price,
            order_id=f"paper_{signal.strategy_id}_{signal.instrument_token}_{str(uuid.uuid4())[:8]}",
            execution_mode=ExecutionMode.PAPER,
            timestamp=signal.timestamp,
            fees=commission,
            broker="paper"  # CRITICAL FIX: Add required broker field
        )

        self.logger.info("PAPER TRADE (SIMULATED)", 
                          signal_type=signal.signal_type.value, 
                          strategy_id=signal.strategy_id, 
                          fill_price=fill_price,
                          slippage=slippage_amount,
                          commission=commission)

        # 4. Return the structured data payload
        return fill_data.model_dump(mode='json')

    def _create_failure_payload(self, signal: TradingSignal, error_message: str) -> Dict[str, Any]:
        """Create failure event payload."""
        from core.schemas.events import OrderFailed
        
        failed_event_data = OrderFailed(
            strategy_id=signal.strategy_id,
            instrument_token=signal.instrument_token,
            signal_type=signal.signal_type,
            quantity=signal.quantity,
            price=signal.price,
            order_id="N/A",
            execution_mode=ExecutionMode.PAPER,
            error_message=error_message,
            timestamp=signal.timestamp,
            broker="paper"  # CRITICAL FIX: Add required broker field
        )
        return failed_event_data.model_dump(mode='json')