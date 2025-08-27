from typing import Dict, Any
from core.streaming.patterns.stream_service_builder import StreamServiceBuilder
from core.schemas.topics import TopicMap, TopicNames
from core.schemas.events import EventType, ExecutionMode
from core.config.settings import Settings, RedpandaSettings
from core.database.connection import DatabaseManager
from core.logging import get_trading_logger_safe, get_error_logger_safe
from .managers.manager_factory import PortfolioManagerFactory
from .managers.paper_manager import PaperPortfolioManager
from .managers.zerodha_manager import ZerodhaPortfolioManager


class PortfolioManagerService:
    """Router service that delegates to appropriate portfolio managers."""
    
    def __init__(self, config: RedpandaSettings, settings: Settings, 
                 redis_client, db_manager: DatabaseManager):
        self.settings = settings
        
        # --- ENHANCED: Multi-broker order topic subscription ---
        order_topics = []
        for broker in settings.active_brokers:
            topic_map = TopicMap(broker)
            order_topics.extend([
                topic_map.orders_filled(),
                topic_map.orders_failed(),
                topic_map.orders_submitted()
            ])
        
        
        # --- ENHANCED: Broker-specific portfolio managers ---
        self.portfolio_managers = {}
        for broker in settings.active_brokers:
            if broker == "paper":
                self.portfolio_managers[broker] = PaperPortfolioManager(settings, redis_client)
            elif broker == "zerodha":
                self.portfolio_managers[broker] = ZerodhaPortfolioManager(settings, redis_client, db_manager)
        
        self.logger = get_trading_logger_safe("portfolio_manager_service")
        self.error_logger = get_error_logger_safe("portfolio_manager_errors")
        
        # Build orchestrator
        self.orchestrator = (StreamServiceBuilder("portfolio_manager", config, settings)
            .with_redis(redis_client)
            .with_error_handling()
            .with_metrics()
            .add_producer()
            .add_consumer_handler(
                topics=order_topics,  # All broker order topics
                group_id=f"{settings.redpanda.group_id_prefix}.portfolio_manager.orders",
                handler_func=self._handle_order_event  # Topic-aware
            )
            .build()
        )
    
    async def _get_producer(self):
        """Safely get producer with error handling"""
        if not self.orchestrator.producers:
            raise RuntimeError(f"No producers available for {self.__class__.__name__}")
        
        if len(self.orchestrator.producers) == 0:
            raise RuntimeError(f"Producers list is empty for {self.__class__.__name__}")
        
        return self.orchestrator.producers[0]
    
    async def start(self):
        """Initialize managers and start service."""
        # Initialize all portfolio managers
        for broker, manager in self.portfolio_managers.items():
            await manager.initialize()
        
        await self.orchestrator.start()
        self.logger.info(f"📊 Portfolio Manager started for brokers: {self.settings.active_brokers}")
    
    async def stop(self):
        """Shutdown managers and stop service."""
        await self.orchestrator.stop()
        # Shutdown all portfolio managers
        for broker, manager in self.portfolio_managers.items():
            await manager.shutdown()
        self.logger.info(f"📊 Portfolio Manager stopped for brokers: {self.settings.active_brokers}")
    
    async def _handle_order_event(self, message: Dict[str, Any], topic: str) -> None:
        """Handle order events with broker context."""
        # Extract broker from topic
        broker = topic.split('.')[0]
        
        self.logger.info("Processing order event", 
                        broker=broker, 
                        topic=topic,
                        event_type=message.get('type'))
        
        # Get broker-specific portfolio manager
        manager = self.portfolio_managers.get(broker)
        if not manager:
            self.error_logger.error(f"No portfolio manager for broker: {broker}")
            return
        
        # Route to appropriate handler based on topic suffix
        if topic.endswith(".filled"):
            await manager.process_fill(message.get('data'))
        elif topic.endswith(".failed"):
            await manager.process_failure(message.get('data'))
        elif topic.endswith(".submitted"):
            await manager.process_submission(message.get('data'))
        
        # Emit PnL snapshot to broker-specific topic
        await self._emit_pnl_snapshot(broker, manager.get_current_portfolio())
    
    async def _emit_pnl_snapshot(self, broker: str, portfolio_data: Dict[str, Any]):
        """Emit PnL snapshot to broker-specific topic."""
        try:
            topic_map = TopicMap(broker)
            topic = topic_map.pnl_snapshots()
            
            producer = await self._get_producer()
            
            await producer.send(
                topic=topic,
                key=f"portfolio_snapshot_{broker}",
                data=portfolio_data,
                event_type=EventType.PNL_SNAPSHOT
            )
        except Exception as e:
            self.logger.error(f"Failed to get producer for PnL emission: {e}")
            raise