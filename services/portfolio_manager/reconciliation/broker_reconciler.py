from typing import Dict, Any, Optional, List
from core.config.settings import Settings
from core.logging import get_trading_logger_safe
from ..models import Portfolio, Position


class BrokerReconciler:
    """Reconciles portfolio state with Zerodha broker."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.kite_client = None
        self.logger = get_trading_logger_safe("broker_reconciler")
    
    async def initialize(self) -> bool:
        """Initialize broker connection."""
        try:
            # Import here to avoid circular imports
            from services.auth.kite_client import kite_client
            self.kite_client = kite_client.get_kite_instance()
            return self.kite_client is not None
        except Exception as e:
            self.logger.warning("Could not initialize Zerodha broker connection", error=str(e))
            return False
    
    async def reconcile_portfolio(self, portfolio_id: str, 
                                 app_portfolio: Portfolio) -> Dict[str, Any]:
        """Reconcile app portfolio with broker state."""
        if not self.kite_client:
            return {"status": "no_broker_connection"}
        
        try:
            # Fetch actual positions from Zerodha
            broker_positions = await self._fetch_broker_positions()
            
            # Compare with app portfolio
            discrepancies = self._compare_positions(
                app_portfolio, broker_positions
            )
            
            if discrepancies:
                # Create reconciled portfolio
                reconciled_portfolio = self._create_reconciled_portfolio(
                    app_portfolio, broker_positions
                )
                
                return {
                    "status": "reconciliation_complete",
                    "discrepancies_found": True,
                    "discrepancies": discrepancies,
                    "reconciled_portfolio": reconciled_portfolio
                }
            else:
                return {
                    "status": "reconciliation_complete", 
                    "discrepancies_found": False
                }
                
        except Exception as e:
            self.logger.error("Portfolio reconciliation failed", 
                            portfolio_id=portfolio_id, error=str(e))
            return {
                "status": "reconciliation_failed",
                "error": str(e)
            }
    
    async def _fetch_broker_positions(self) -> Dict[str, Any]:
        """Fetch current positions from Zerodha."""
        try:
            # Use Kite Connect API to get positions
            positions = self.kite_client.positions()
            
            # Transform to our format
            broker_positions = {}
            
            for position_data in positions.get('net', []):
                instrument_token = position_data.get('instrument_token')
                if instrument_token:
                    broker_positions[instrument_token] = {
                        'quantity': position_data.get('quantity', 0),
                        'average_price': position_data.get('average_price', 0.0),
                        'last_price': position_data.get('last_price', 0.0),
                        'pnl': position_data.get('pnl', 0.0)
                    }
            
            return broker_positions
            
        except Exception as e:
            self.logger.error("Failed to fetch broker positions", error=str(e))
            return {}
    
    def _compare_positions(self, app_portfolio: Portfolio, 
                          broker_positions: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Compare app and broker positions."""
        discrepancies = []
        
        # Check positions in app that differ from broker
        for instrument_token, app_position in app_portfolio.positions.items():
            broker_position = broker_positions.get(instrument_token, {})
            
            broker_quantity = broker_position.get('quantity', 0)
            broker_avg_price = broker_position.get('average_price', 0.0)
            
            # Check quantity discrepancy
            if app_position.quantity != broker_quantity:
                discrepancies.append({
                    'type': 'quantity_mismatch',
                    'instrument_token': instrument_token,
                    'app_quantity': app_position.quantity,
                    'broker_quantity': broker_quantity
                })
            
            # Check average price discrepancy (with tolerance for rounding)
            price_diff = abs(app_position.average_price - broker_avg_price)
            if price_diff > 0.01:  # 1 paisa tolerance
                discrepancies.append({
                    'type': 'price_mismatch',
                    'instrument_token': instrument_token,
                    'app_avg_price': app_position.average_price,
                    'broker_avg_price': broker_avg_price,
                    'difference': price_diff
                })
        
        # Check for positions in broker not in app
        for instrument_token, broker_position in broker_positions.items():
            if instrument_token not in app_portfolio.positions:
                if broker_position.get('quantity', 0) != 0:
                    discrepancies.append({
                        'type': 'missing_position',
                        'instrument_token': instrument_token,
                        'broker_quantity': broker_position.get('quantity', 0),
                        'broker_avg_price': broker_position.get('average_price', 0.0)
                    })
        
        return discrepancies
    
    def _create_reconciled_portfolio(self, app_portfolio: Portfolio,
                                   broker_positions: Dict[str, Any]) -> Portfolio:
        """Create reconciled portfolio using broker as source of truth."""
        reconciled_portfolio = Portfolio(
            portfolio_id=app_portfolio.portfolio_id,
            cash=app_portfolio.cash,  # Keep app cash as is
            total_realized_pnl=app_portfolio.total_realized_pnl  # Keep realized PnL
        )
        
        # Rebuild positions from broker data
        for instrument_token, broker_position in broker_positions.items():
            quantity = broker_position.get('quantity', 0)
            if quantity != 0:  # Only include non-zero positions
                position = Position(
                    instrument_token=instrument_token,
                    quantity=quantity,
                    average_price=broker_position.get('average_price', 0.0),
                    last_price=broker_position.get('last_price', 0.0),
                    realized_pnl=0.0  # Reset realized PnL for reconciliation
                )
                position.calculate_unrealized_pnl()
                reconciled_portfolio.positions[instrument_token] = position
        
        # Recalculate totals
        reconciled_portfolio.update_totals()
        reconciled_portfolio.update_last_modified()
        
        return reconciled_portfolio