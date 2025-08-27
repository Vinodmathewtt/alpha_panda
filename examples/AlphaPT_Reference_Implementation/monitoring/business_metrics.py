"""Essential business metrics collection for AlphaPT trading system."""

from prometheus_client import Counter, Histogram, Gauge
from typing import Optional
from datetime import datetime

from core.logging.logger import get_logger

logger = get_logger(__name__)


class BusinessMetricsCollector:
    """Collect essential business metrics for trading operations."""
    
    def __init__(self):
        # Trading metrics
        self.orders_total = Counter(
            'alphapt_orders_total', 
            'Total orders placed', 
            ['strategy', 'order_type', 'status']
        )
        
        self.order_fill_time = Histogram(
            'alphapt_order_fill_seconds', 
            'Order fill time in seconds', 
            ['strategy']
        )
        
        # Strategy metrics
        self.strategy_signals = Counter(
            'alphapt_strategy_signals_total', 
            'Strategy signals generated', 
            ['strategy', 'signal_type']
        )
        
        self.strategy_pnl = Gauge(
            'alphapt_strategy_pnl', 
            'Current strategy P&L', 
            ['strategy']
        )
        
        # Market data metrics
        self.ticks_processed = Counter(
            'alphapt_ticks_processed_total', 
            'Market ticks processed'
        )
        
        self.market_data_latency = Histogram(
            'alphapt_market_data_latency_seconds', 
            'Market data processing latency'
        )
        
        # Risk metrics
        self.risk_violations = Counter(
            'alphapt_risk_violations_total', 
            'Risk rule violations', 
            ['strategy', 'violation_type']
        )
        
        logger.info("Business metrics collector initialized")
    
    def record_order(self, strategy: str, order_type: str, status: str):
        """Record order placement."""
        try:
            self.orders_total.labels(
                strategy=strategy, 
                order_type=order_type, 
                status=status
            ).inc()
            logger.debug(f"Recorded order: {strategy} {order_type} {status}")
        except Exception as e:
            logger.error(f"Error recording order metric: {e}")
    
    def record_order_fill(self, strategy: str, fill_time_seconds: float):
        """Record order fill time."""
        try:
            self.order_fill_time.labels(strategy=strategy).observe(fill_time_seconds)
            logger.debug(f"Recorded order fill time: {strategy} {fill_time_seconds}s")
        except Exception as e:
            logger.error(f"Error recording order fill metric: {e}")
    
    def record_strategy_signal(self, strategy: str, signal_type: str):
        """Record strategy signal generation."""
        try:
            self.strategy_signals.labels(
                strategy=strategy, 
                signal_type=signal_type
            ).inc()
            logger.debug(f"Recorded strategy signal: {strategy} {signal_type}")
        except Exception as e:
            logger.error(f"Error recording strategy signal metric: {e}")
    
    def update_strategy_pnl(self, strategy: str, pnl: float):
        """Update strategy P&L."""
        try:
            self.strategy_pnl.labels(strategy=strategy).set(pnl)
            logger.debug(f"Updated strategy P&L: {strategy} {pnl}")
        except Exception as e:
            logger.error(f"Error updating strategy P&L metric: {e}")
    
    def record_tick_processed(self):
        """Record market tick processing."""
        try:
            self.ticks_processed.inc()
        except Exception as e:
            logger.error(f"Error recording tick metric: {e}")
    
    def record_market_data_latency(self, latency_seconds: float):
        """Record market data processing latency."""
        try:
            self.market_data_latency.observe(latency_seconds)
        except Exception as e:
            logger.error(f"Error recording market data latency: {e}")
    
    def record_risk_violation(self, strategy: str, violation_type: str):
        """Record risk violation."""
        try:
            self.risk_violations.labels(
                strategy=strategy, 
                violation_type=violation_type
            ).inc()
            logger.warning(f"Risk violation: {strategy} {violation_type}")
        except Exception as e:
            logger.error(f"Error recording risk violation metric: {e}")


# Global instance for easy access
business_metrics_collector: Optional[BusinessMetricsCollector] = None


def initialize_business_metrics() -> BusinessMetricsCollector:
    """Initialize the global business metrics collector."""
    global business_metrics_collector
    
    if business_metrics_collector is None:
        business_metrics_collector = BusinessMetricsCollector()
        logger.info("Business metrics collector initialized globally")
    
    return business_metrics_collector


def get_business_metrics() -> Optional[BusinessMetricsCollector]:
    """Get the global business metrics collector."""
    return business_metrics_collector