# CENTRALIZED topic names and routing rules
# NO wildcard subscriptions - route by topic name only

from typing import Dict, List, Literal


class TopicNames:
    """Centralized topic name definitions with broker segregation"""
    
    # Market data topics (SHARED - quality-based source selection by asset class)
    MARKET_TICKS = "market.ticks"  # Legacy: All instruments (maintained for backward compatibility)
    
    # Asset-class-specific market data topics (multi-source architecture ready)
    MARKET_EQUITY_TICKS = "market.equity.ticks"    # Best equity data source (currently Zerodha)
    MARKET_CRYPTO_TICKS = "market.crypto.ticks"    # Best crypto data source (future: Binance/Coinbase)
    MARKET_OPTIONS_TICKS = "market.options.ticks"  # Best options data source (currently Zerodha)
    MARKET_FOREX_TICKS = "market.forex.ticks"      # Best forex data source (future implementation)
    
    # Legacy broker-specific market topics (DEPRECATED - use MARKET_TICKS instead)
    MARKET_TICKS_PAPER = "market.ticks"      # Points to same topic
    MARKET_TICKS_ZERODHA = "market.ticks"    # Points to same topic
    
    # Dead Letter Queue for poison pill messages
    DEAD_LETTER_QUEUE = "global.dead_letter_queue"
    
    # Helper methods for market data topic selection
    @classmethod
    def get_market_ticks_topic(cls, broker: str = None) -> str:
        """Get market ticks topic (same for all brokers since data comes from Zerodha)"""
        return cls.MARKET_TICKS
    
    @classmethod
    def get_market_topic_by_asset_class(cls, asset_class: str) -> str:
        """Get market data topic based on asset class for quality-based routing"""
        asset_class = asset_class.lower()
        if asset_class in ["equity", "stock", "stocks"]:
            return cls.MARKET_EQUITY_TICKS
        elif asset_class in ["crypto", "cryptocurrency", "bitcoin", "ethereum"]:
            return cls.MARKET_CRYPTO_TICKS
        elif asset_class in ["options", "option", "derivatives"]:
            return cls.MARKET_OPTIONS_TICKS
        elif asset_class in ["forex", "currency", "fx"]:
            return cls.MARKET_FOREX_TICKS
        else:
            # Fallback to legacy topic for unknown asset classes
            return cls.MARKET_TICKS
    
    # Signal topics (broker-segregated)
    TRADING_SIGNALS_RAW_PAPER = "paper.signals.raw"
    TRADING_SIGNALS_RAW_ZERODHA = "zerodha.signals.raw"
    TRADING_SIGNALS_VALIDATED_PAPER = "paper.signals.validated" 
    TRADING_SIGNALS_VALIDATED_ZERODHA = "zerodha.signals.validated"
    TRADING_SIGNALS_REJECTED_PAPER = "paper.signals.rejected"
    TRADING_SIGNALS_REJECTED_ZERODHA = "zerodha.signals.rejected"
    
    # Legacy aliases for backward compatibility
    TRADING_SIGNALS_GENERATED = TRADING_SIGNALS_RAW_PAPER  # Default to paper
    
    # Helper methods for broker-aware topic selection
    @classmethod
    def get_signals_raw_topic(cls, broker: str) -> str:
        """Get raw signals topic for specific broker"""
        if broker == "paper":
            return cls.TRADING_SIGNALS_RAW_PAPER
        elif broker == "zerodha":
            return cls.TRADING_SIGNALS_RAW_ZERODHA
        else:
            raise ValueError(f"Unknown broker: {broker}")
    
    @classmethod  
    def get_signals_validated_topic(cls, broker: str) -> str:
        """Get validated signals topic for specific broker"""
        if broker == "paper":
            return cls.TRADING_SIGNALS_VALIDATED_PAPER
        elif broker == "zerodha":
            return cls.TRADING_SIGNALS_VALIDATED_ZERODHA
        else:
            raise ValueError(f"Unknown broker: {broker}")
    
    @classmethod
    def get_signals_rejected_topic(cls, broker: str) -> str:
        """Get rejected signals topic for specific broker"""
        if broker == "paper":
            return cls.TRADING_SIGNALS_REJECTED_PAPER
        elif broker == "zerodha":
            return cls.TRADING_SIGNALS_REJECTED_ZERODHA
        else:
            raise ValueError(f"Unknown broker: {broker}")
    
    # Order topics (FIXED: zerodha instead of live)
    ORDERS_SUBMITTED_PAPER = "paper.orders.submitted"
    ORDERS_SUBMITTED_ZERODHA = "zerodha.orders.submitted"
    ORDERS_ACK_PAPER = "paper.orders.ack"
    ORDERS_ACK_ZERODHA = "zerodha.orders.ack"
    ORDERS_FILLED_PAPER = "paper.orders.filled"
    ORDERS_FILLED_ZERODHA = "zerodha.orders.filled"  # CRITICAL: Fixed from LIVE
    ORDERS_FAILED_PAPER = "paper.orders.failed"
    ORDERS_FAILED_ZERODHA = "zerodha.orders.failed"  # CRITICAL: Fixed from LIVE
    
    # Portfolio topics
    PNL_SNAPSHOTS_PAPER = "paper.pnl.snapshots"
    PNL_SNAPSHOTS_ZERODHA = "zerodha.pnl.snapshots"
    
    # Dead Letter Queue topics
    @classmethod
    def get_dlq_topic(cls, original_topic: str) -> str:
        """Get DLQ topic for any topic"""
        return f"{original_topic}.dlq"


Broker = Literal["paper", "zerodha"]


class TopicMap:
    """Helper for dynamic topic name generation"""
    def __init__(self, broker: Broker):
        self.broker = broker
        
    def market_ticks(self) -> str:
        return TopicNames.MARKET_TICKS  # Always use shared market ticks (legacy)
    
    def market_ticks_by_asset_class(self, asset_class: str) -> str:
        """Get market data topic by asset class for quality-based routing"""
        return TopicNames.get_market_topic_by_asset_class(asset_class)
        
    def signals_raw(self) -> str:
        return f"{self.broker}.signals.raw"
        
    def signals_validated(self) -> str:
        return f"{self.broker}.signals.validated"
        
    def signals_rejected(self) -> str:
        return f"{self.broker}.signals.rejected"
        
    def orders_submitted(self) -> str:
        return f"{self.broker}.orders.submitted"
        
    def orders_ack(self) -> str:
        return f"{self.broker}.orders.ack"
        
    def orders_filled(self) -> str:
        return f"{self.broker}.orders.filled"
        
    def orders_failed(self) -> str:
        return f"{self.broker}.orders.failed"
        
    def pnl_snapshots(self) -> str:
        return f"{self.broker}.pnl.snapshots"
        
    def dlq(self, base_topic: str) -> str:
        return f"{base_topic}.dlq"
    
    @staticmethod
    def get_broker_from_topic(topic: str) -> str:
        """
        Extract broker from topic name using robust parsing logic.
        
        Args:
            topic: Topic name (e.g., "paper.signals.raw", "market.ticks")
            
        Returns:
            Broker name or 'unknown' for shared topics
            
        Examples:
            "paper.signals.raw" -> "paper"
            "zerodha.orders.filled" -> "zerodha"  
            "market.ticks" -> "unknown" (shared topic)
        """
        if not topic or '.' not in topic:
            return 'unknown'
        
        # Extract first part as potential broker
        parts = topic.split('.')
        first_part = parts[0]
        
        # Check if it's a known broker prefix
        known_brokers = ['paper', 'zerodha']
        if first_part in known_brokers:
            return first_part
        
        # Check for shared topics (market.*, global.*)
        shared_prefixes = ['market', 'global']
        if first_part in shared_prefixes:
            return 'unknown'
        
        # For unknown patterns, return 'unknown' to be safe
        # Could log a warning here in production for monitoring new patterns
        return 'unknown'


class PartitioningKeys:
    """Document partition keys for ordering guarantees"""
    
    @staticmethod
    def market_tick_key(instrument_token: int) -> str:
        """Partition by instrument token for tick ordering"""
        return str(instrument_token)
    
    @staticmethod
    def trading_signal_key(strategy_id: str, instrument_token: int) -> str:
        """Partition by strategy + instrument for signal ordering"""
        return f"{strategy_id}:{instrument_token}"
    
    @staticmethod
    def order_key(strategy_id: str, instrument_token: int, timestamp: str) -> str:
        """Partition by strategy + instrument + timestamp for order ordering"""
        return f"{strategy_id}:{instrument_token}:{timestamp}"


class TopicConfig:
    """Topic configuration with partition counts"""
    CONFIGS = {
        # Shared market data topic (legacy - same for both paper and zerodha)
        TopicNames.MARKET_TICKS: {
            "partitions": 12,
            "replication_factor": 1,
            "config": {"retention.ms": "3600000"}  # 1 hour
        },
        
        # Asset-class-specific market data topics for multi-source architecture
        TopicNames.MARKET_EQUITY_TICKS: {
            "partitions": 8,
            "replication_factor": 1,
            "config": {"retention.ms": "3600000"}  # 1 hour
        },
        TopicNames.MARKET_CRYPTO_TICKS: {
            "partitions": 6,
            "replication_factor": 1,
            "config": {"retention.ms": "3600000"}  # 1 hour
        },
        TopicNames.MARKET_OPTIONS_TICKS: {
            "partitions": 4,
            "replication_factor": 1,
            "config": {"retention.ms": "3600000"}  # 1 hour
        },
        TopicNames.MARKET_FOREX_TICKS: {
            "partitions": 4,
            "replication_factor": 1,
            "config": {"retention.ms": "3600000"}  # 1 hour
        },
        
        # Paper trading topics
        TopicNames.TRADING_SIGNALS_RAW_PAPER: {
            "partitions": 6,
            "replication_factor": 1,
            "config": {"retention.ms": "86400000"}  # 1 day
        },
        TopicNames.TRADING_SIGNALS_VALIDATED_PAPER: {
            "partitions": 6,
            "replication_factor": 1,
            "config": {"retention.ms": "86400000"}  # 1 day
        },
        TopicNames.TRADING_SIGNALS_REJECTED_PAPER: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "86400000"}  # 1 day
        },
        TopicNames.ORDERS_FILLED_PAPER: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        TopicNames.ORDERS_SUBMITTED_PAPER: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        TopicNames.ORDERS_FAILED_PAPER: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        TopicNames.PNL_SNAPSHOTS_PAPER: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        
        # Zerodha trading topics (no separate market ticks - uses shared topic)
        TopicNames.TRADING_SIGNALS_RAW_ZERODHA: {
            "partitions": 6,
            "replication_factor": 1,
            "config": {"retention.ms": "86400000"}  # 1 day
        },
        TopicNames.TRADING_SIGNALS_VALIDATED_ZERODHA: {
            "partitions": 6,
            "replication_factor": 1,
            "config": {"retention.ms": "86400000"}  # 1 day
        },
        TopicNames.TRADING_SIGNALS_REJECTED_ZERODHA: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "86400000"}  # 1 day
        },
        TopicNames.ORDERS_FILLED_ZERODHA: {
            "partitions": 3,
            "replication_factor": 1, 
            "config": {"retention.ms": "2592000000"}  # 30 days
        },
        TopicNames.ORDERS_SUBMITTED_ZERODHA: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "2592000000"}  # 30 days
        },
        TopicNames.ORDERS_FAILED_ZERODHA: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "2592000000"}  # 30 days
        },
        TopicNames.PNL_SNAPSHOTS_ZERODHA: {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "2592000000"}  # 30 days
        },
        
        # DLQ topics - add commonly used ones
        f"{TopicNames.MARKET_TICKS}.dlq": {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        f"{TopicNames.TRADING_SIGNALS_RAW_PAPER}.dlq": {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        f"{TopicNames.TRADING_SIGNALS_RAW_ZERODHA}.dlq": {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        f"{TopicNames.ORDERS_FILLED_PAPER}.dlq": {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
        f"{TopicNames.ORDERS_FILLED_ZERODHA}.dlq": {
            "partitions": 3,
            "replication_factor": 1,
            "config": {"retention.ms": "604800000"}  # 1 week
        },
    }


class ConsumerGroups:
    """UNIQUE consumer group IDs per service and broker"""
    
    @classmethod
    def market_feed(cls, broker: str = "shared") -> str:
        """Market feed is shared, but group by broker for isolation"""
        return f"alpha-panda.market-feed.{broker}"
    
    @classmethod
    def strategy_runner(cls, broker: str) -> str:
        return f"alpha-panda.strategy-runner.{broker}"
    
    @classmethod
    def risk_manager(cls, broker: str) -> str:
        return f"alpha-panda.risk-manager.{broker}"
    
    @classmethod
    def trading_engine(cls, broker: str) -> str:
        return f"alpha-panda.trading-engine.{broker}"
    
    @classmethod
    def portfolio_manager(cls, broker: str) -> str:
        return f"alpha-panda.portfolio-manager.{broker}"
    
    # Legacy constants for backward compatibility (default to paper)
    MARKET_FEED = "alpha-panda.market-feed.shared"
    STRATEGY_RUNNER = "alpha-panda.strategy-runner.paper"
    RISK_MANAGER = "alpha-panda.risk-manager.paper"
    TRADING_ENGINE = "alpha-panda.trading-engine.paper"
    PORTFOLIO_MANAGER = "alpha-panda.portfolio-manager.paper"


class TopicValidator:
    """Validate topic routing and broker consistency"""
    
    @classmethod
    def validate_broker_topic_pair(cls, topic: str, broker: str) -> bool:
        """Validate that topic matches expected broker pattern"""
        if topic.startswith(f"{broker}."):
            return True
        
        # Check if it's a shared topic (market.ticks)
        shared_topics = ["market.ticks", "market.equity.ticks", "market.crypto.ticks"]
        if topic in shared_topics:
            return True
        
        return False
    
    @classmethod
    def get_expected_topic(cls, base_topic: str, broker: str) -> str:
        """Get expected topic name for broker"""
        shared_prefixes = ["market."]
        
        # If it's a shared topic, return as-is
        for prefix in shared_prefixes:
            if base_topic.startswith(prefix):
                return base_topic
        
        # Otherwise, add broker prefix
        if not base_topic.startswith(f"{broker}."):
            return f"{broker}.{base_topic}"
        
        return base_topic