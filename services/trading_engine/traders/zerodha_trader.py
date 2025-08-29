from typing import Dict, Any, Optional
from kiteconnect import KiteConnect

from core.config.settings import Settings
from core.schemas.events import TradingSignal, OrderPlaced, OrderFailed, SignalType, ExecutionMode
from core.logging import get_logger
from services.auth.kite_client import kite_client
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from ..interfaces.trader_interface import Trader

logger = get_logger(__name__)

class ZerodhaTrader(Trader):
    """
    Executes live trades using the Zerodha Kite Connect API.
    This class is a stateless client and does not publish events directly.
    """
    
    def __init__(self, settings: Settings, instrument_service: Optional[InstrumentRegistryService]):
        self.settings = settings
        self.kite_http_client: Optional[KiteConnect] = None
        self.instrument_service = instrument_service
        self._initialized = False

    async def initialize(self) -> bool:
        """Initialize the trader by getting the authenticated KiteConnect instance."""
        if not self.settings.zerodha.enabled:
            logger.warning("Zerodha trading is disabled in settings.")
            return False

        self.kite_http_client = kite_client.get_kite_instance()
        if self.kite_http_client:
            logger.info("Zerodha Trader initialized and authenticated.")
            self._initialized = True
            return True
        else:
            logger.error("Zerodha Trader could not be initialized. Kite client not available.")
            return False

    async def shutdown(self) -> None:
        """Cleanup trader resources."""
        logger.info("Zerodha trader shutdown")
        self._initialized = False

    def get_execution_mode(self) -> str:
        return ExecutionMode.ZERODHA.value

    async def execute_order(self, signal: TradingSignal, last_price: Optional[float]) -> Dict[str, Any]:
        """
        Places a live order with Zerodha and returns the resulting event data.

        Args:
            signal: The validated trading signal as a Pydantic model.
            last_price: The last known price for the instrument (not used for market orders).

        Returns:
            A dictionary payload for either an OrderPlaced or OrderFailed event.
        """
        if not self._initialized or not self.kite_http_client:
            logger.error("Zerodha Trader is not initialized. Cannot place order.")
            return self._create_failure_payload(signal, "Trader not initialized")

        try:
            # FIX: Look up the instrument details using InstrumentRegistryService
            if not self.instrument_service:
                return self._create_failure_payload(signal, "Instrument service not available - cannot resolve trading symbol")
            
            instrument = await self.instrument_service.get_instrument_by_token(signal.instrument_token)
            if not instrument:
                return self._create_failure_payload(signal, f"Instrument not found for token {signal.instrument_token}")

            order_id = self.kite_http_client.place_order(
                variety=self.kite_http_client.VARIETY_REGULAR,
                exchange=instrument.get('exchange', 'NSE'),  # Use actual exchange
                tradingsymbol=instrument['tradingsymbol'],  # Use actual trading symbol
                transaction_type=(
                    self.kite_http_client.TRANSACTION_TYPE_BUY
                    if signal.signal_type == SignalType.BUY
                    else self.kite_http_client.TRANSACTION_TYPE_SELL
                ),
                quantity=signal.quantity,
                product=self.kite_http_client.PRODUCT_MIS,  # Example: make dynamic
                order_type=self.kite_http_client.ORDER_TYPE_MARKET,
            )

            logger.info(f"LIVE TRADE: Placed order for {signal.strategy_id}. Order ID: {order_id}")

            # Create a structured data payload for the success event
            placed_event_data = OrderPlaced(
                strategy_id=signal.strategy_id,
                instrument_token=signal.instrument_token,
                signal_type=signal.signal_type,
                quantity=signal.quantity,
                price=signal.price,
                order_id=order_id,
                execution_mode=ExecutionMode.ZERODHA,
                timestamp=signal.timestamp,
                broker="zerodha",  # CRITICAL FIX: Add required broker field
                status="PLACED"    # CRITICAL FIX: Add required status field
            )
            return placed_event_data.model_dump(mode='json')

        except Exception as e:
            logger.error(f"LIVE TRADE FAILED for {signal.strategy_id}: {e}")
            return self._create_failure_payload(signal, str(e))

    def _create_failure_payload(self, signal: TradingSignal, error_message: str) -> Dict[str, Any]:
        """Creates a structured data payload for a failed order event."""
        failed_event_data = OrderFailed(
            strategy_id=signal.strategy_id,
            instrument_token=signal.instrument_token,
            signal_type=signal.signal_type,
            quantity=signal.quantity,
            price=signal.price,
            order_id="N/A",
            execution_mode=ExecutionMode.ZERODHA,
            error_message=error_message,
            timestamp=signal.timestamp,
            broker="zerodha"  # CRITICAL FIX: Add required broker field
        )
        return failed_event_data.model_dump(mode='json')