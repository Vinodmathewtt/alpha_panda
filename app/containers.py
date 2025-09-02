# COMPLETE DI container - NO MISSING PROVIDERS
from dependency_injector import containers, providers
import asyncio
from core.config.settings import Settings
from core.database.connection import DatabaseManager
from core.streaming.clients import RedpandaProducer, RedpandaConsumer
from core.schemas.topics import ConsumerGroups
# New imports for health checks
from core.health import (
    SystemHealthMonitor,
    DatabaseHealthCheck,
    RedisHealthCheck,
    RedpandaHealthCheck,
    ZerodhaAuthenticationCheck,
)
from core.health.multi_broker_health_checks import BrokerTopicHealthCheck
# Import the new custom checks
from app.pre_trading_checks import (
    ActiveStrategiesCheck,
    BrokerApiHealthCheck,
    MarketHoursCheck,
)
from services.market_feed.service import MarketFeedService
from services.strategy_runner.service import StrategyRunnerService  
from services.risk_manager.service import RiskManagerService
from core.trading.portfolio_cache import PortfolioCache
from services.zerodha_trading.service import ZerodhaTradingService
from services.paper_trading.service import PaperTradingService
from services.auth.service import AuthService
from services.instrument_data.instrument_registry_service import InstrumentRegistryService
from core.monitoring import PipelineMonitor
from core.market_hours.market_hours_checker import MarketHoursChecker
from core.health.health_checker import ServiceHealthChecker
from api.services.dashboard_service import DashboardService
from api.services.log_service import LogService
import redis.asyncio as redis
from prometheus_client import CollectorRegistry
from core.monitoring.prometheus_metrics import PrometheusMetricsCollector


class AppContainer(containers.DeclarativeContainer):
    """Application dependency injection container"""
    
    # Configuration
    settings = providers.Singleton(Settings)

    # --- Observability: Prometheus ---
    # Define Prometheus providers early so downstream providers can reference them
    # Shared registry used by API /metrics endpoint and collectors
    prometheus_registry = providers.Singleton(CollectorRegistry)
    prometheus_metrics = providers.Singleton(
        PrometheusMetricsCollector,
        registry=prometheus_registry,
        settings=settings,
    )
    
    # Database with environment awareness
    db_manager = providers.Singleton(
        DatabaseManager,
        db_url=settings.provided.database.postgres_url,
        environment=settings.provided.environment,
        schema_management=settings.provided.database.schema_management
    )
    
    # Redis cache
    redis_client = providers.Singleton(
        redis.from_url,
        settings.provided.redis.url
    )
    
    # Portfolio cache
    portfolio_cache = providers.Singleton(
        PortfolioCache,
        settings=settings
    )
    
    # Shutdown event for graceful service shutdown
    shutdown_event = providers.Factory(asyncio.Event)
    
    # Market Hours Checker (singleton for consistency across services)
    market_hours_checker = providers.Singleton(MarketHoursChecker)
    
    # Auth service
    auth_service = providers.Singleton(
        AuthService,
        settings=settings,
        db_manager=db_manager,
        shutdown_event=shutdown_event
    )
    
    # Instrument Registry Service
    instrument_registry_service = providers.Singleton(
        InstrumentRegistryService,
        session_factory=db_manager.provided.get_session
    )
    
    # Market Feed Service (now depends on AuthService and InstrumentRegistryService)
    market_feed_service = providers.Singleton(
        MarketFeedService,
        config=settings.provided.redpanda,
        settings=settings,
        auth_service=auth_service,
        instrument_registry_service=instrument_registry_service,
        redis_client=redis_client,
        prometheus_metrics=prometheus_metrics
    )
    
    # Strategy Runner Service
    strategy_runner_service = providers.Singleton(
        StrategyRunnerService,
        config=settings.provided.redpanda,
        settings=settings,
        db_manager=db_manager,
        redis_client=redis_client,
        market_hours_checker=market_hours_checker,
        prometheus_metrics=prometheus_metrics
    )
    
    # Risk Manager Service
    risk_manager_service = providers.Singleton(
        RiskManagerService,
        config=settings.provided.redpanda,
        settings=settings,
        redis_client=redis_client,
        prometheus_metrics=prometheus_metrics
    )
    
    # Legacy trading engine providers removed in Phase 6 cleanup

    # New broker-scoped services (Phase 3 wiring)
    zerodha_trading_service = providers.Singleton(
        ZerodhaTradingService,
        config=settings.provided.redpanda,
        settings=settings,
        redis_client=redis_client,
        prometheus_metrics=prometheus_metrics,
    )

    paper_trading_service = providers.Singleton(
        PaperTradingService,
        config=settings.provided.redpanda,
        settings=settings,
        redis_client=redis_client,
        prometheus_metrics=prometheus_metrics,
    )

    # Legacy portfolio manager provider removed in Phase 6 cleanup
    
    # Pipeline Monitor Service
    pipeline_monitor = providers.Singleton(
        PipelineMonitor,
        settings=settings,
        redis_client=redis_client,
        market_hours_checker=market_hours_checker
    )
    
    # --- Health Check Providers ---
    # Infrastructure Checks
    db_health_check = providers.Singleton(DatabaseHealthCheck, db_manager=db_manager)
    redis_health_check = providers.Singleton(RedisHealthCheck, redis_client=redis_client)
    redpanda_health_check = providers.Singleton(RedpandaHealthCheck, settings=settings)
    broker_topics_check = providers.Singleton(BrokerTopicHealthCheck, settings=settings)

    # Configuration and Logic Checks
    zerodha_auth_check = providers.Singleton(ZerodhaAuthenticationCheck, auth_service=auth_service)
    active_strategies_check = providers.Singleton(ActiveStrategiesCheck, db_manager=db_manager)
    broker_api_check = providers.Singleton(BrokerApiHealthCheck, auth_service=auth_service)
    market_hours_check = providers.Singleton(MarketHoursCheck) # No dependencies

    # Aggregate all checks into a single list - ZERODHA AUTH FIRST (CRITICAL)
    health_checks_list = providers.List(
        # CRITICAL: Zerodha authentication must be first
        zerodha_auth_check,
        # Infrastructure
        db_health_check,
        redis_health_check,
        redpanda_health_check,
        broker_topics_check,
        # Config & Logic
        active_strategies_check,
        broker_api_check,
        market_hours_check,
    )

    system_health_monitor = providers.Singleton(
        SystemHealthMonitor,
        checks=health_checks_list
    )
    
    # --- API-specific services ---
    # Service Health Checker (for API endpoints)
    service_health_checker = providers.Singleton(
        ServiceHealthChecker,
        settings=settings,
        redis_client=redis_client,
        auth_service=auth_service
    )
    
    # Dashboard Service for data aggregation
    dashboard_service = providers.Singleton(
        DashboardService,
        settings=settings,
        redis_client=redis_client,
        health_checker=service_health_checker,
        pipeline_monitor=pipeline_monitor
    )
    
    # Log Service for log management
    log_service = providers.Singleton(
        LogService,
        settings=settings
    )

    # COMPLETE lifespan_services list with all implemented services
    lifespan_services = providers.List(
        auth_service,
        instrument_registry_service,  # Added for proper lifecycle management
        market_feed_service,
        strategy_runner_service,
        risk_manager_service,
        # Phase 3 cutover: start broker-scoped trading services
        paper_trading_service,
        zerodha_trading_service,
        # Do not start old trading_engine/portfolio_manager to avoid double-processing
        pipeline_monitor,
    )
