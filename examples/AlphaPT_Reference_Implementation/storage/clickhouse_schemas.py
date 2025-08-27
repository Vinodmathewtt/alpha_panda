"""ClickHouse database schemas for market data and analytics.

This module defines all ClickHouse table schemas, materialized views,
and data structures optimized for high-frequency market data storage
and real-time analytics.
"""

from typing import List, Dict, Any
from dataclasses import dataclass


@dataclass
class TableDefinition:
    """ClickHouse table definition."""
    name: str
    create_sql: str
    description: str
    partition_by: str
    order_by: str
    settings: Dict[str, Any] = None


class ClickHouseSchemas:
    """ClickHouse database schemas and table definitions."""
    
    @staticmethod
    def get_market_ticks_table() -> TableDefinition:
        """Get market ticks table definition for high-frequency data storage."""
        return TableDefinition(
            name="market_ticks",
            description="Real-time market tick data with full depth information",
            partition_by="toYYYYMM(timestamp)",
            order_by="(instrument_token, timestamp)",
            settings={
                "index_granularity": 8192,
                "compress_marks": 1,
                "compress_primary_key": 1,
            },
            create_sql="""
            CREATE TABLE IF NOT EXISTS market_ticks (
                -- Core identification
                timestamp DateTime64(3) CODEC(Delta, LZ4),
                instrument_token UInt32 CODEC(DoubleDelta, LZ4),
                exchange String CODEC(ZSTD(1)),
                tradingsymbol String CODEC(ZSTD(1)),
                
                -- Price data
                last_price Float64 CODEC(DoubleDelta, LZ4),
                last_quantity UInt32 CODEC(DoubleDelta, LZ4),
                average_price Float64 CODEC(DoubleDelta, LZ4),
                volume_traded UInt64 CODEC(DoubleDelta, LZ4),
                
                -- Market sentiment
                buy_quantity UInt64 CODEC(DoubleDelta, LZ4),
                sell_quantity UInt64 CODEC(DoubleDelta, LZ4),
                
                -- OHLC data
                open Float64 CODEC(DoubleDelta, LZ4),
                high Float64 CODEC(DoubleDelta, LZ4),
                low Float64 CODEC(DoubleDelta, LZ4),
                close Float64 CODEC(DoubleDelta, LZ4),
                
                -- Price changes
                net_change Float64 CODEC(DoubleDelta, LZ4),
                percentage_change Float64 CODEC(DoubleDelta, LZ4),
                
                -- Open Interest (F&O)
                oi UInt64 CODEC(DoubleDelta, LZ4),
                oi_day_high UInt64 CODEC(DoubleDelta, LZ4),
                oi_day_low UInt64 CODEC(DoubleDelta, LZ4),
                
                -- Market depth (5 levels each side)
                depth_buy Array(Tuple(price Float64, quantity UInt32, orders UInt16)) CODEC(ZSTD(1)),
                depth_sell Array(Tuple(price Float64, quantity UInt32, orders UInt16)) CODEC(ZSTD(1)),
                
                -- Metadata
                mode String CODEC(ZSTD(1)),
                tradable Bool CODEC(ZSTD(1)),
                exchange_timestamp DateTime64(3) CODEC(Delta, LZ4),
                
                -- Data quality indicators
                data_quality_score Float32 DEFAULT 1.0 CODEC(ZSTD(1)),
                validation_flags UInt32 DEFAULT 0 CODEC(ZSTD(1))
                
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (instrument_token, timestamp)
            SETTINGS 
                index_granularity = 8192,
                compress_marks = 1,
                compress_primary_key = 1,
                enable_mixed_granularity_parts = 1
            """
        )
    
    @staticmethod
    def get_ohlc_1m_table() -> TableDefinition:
        """Get 1-minute OHLC aggregated data table."""
        return TableDefinition(
            name="ohlc_1m",
            description="1-minute OHLC aggregated market data",
            partition_by="toYYYYMM(minute)",
            order_by="(instrument_token, minute)",
            settings={
                "index_granularity": 8192,
            },
            create_sql="""
            CREATE TABLE IF NOT EXISTS ohlc_1m (
                minute DateTime CODEC(Delta, LZ4),
                instrument_token UInt32 CODEC(DoubleDelta, LZ4),
                exchange String CODEC(ZSTD(1)),
                tradingsymbol String CODEC(ZSTD(1)),
                
                -- OHLC
                open Float64 CODEC(DoubleDelta, LZ4),
                high Float64 CODEC(DoubleDelta, LZ4),
                low Float64 CODEC(DoubleDelta, LZ4),
                close Float64 CODEC(DoubleDelta, LZ4),
                
                -- Volume and trades
                volume UInt64 CODEC(DoubleDelta, LZ4),
                trades_count UInt32 CODEC(DoubleDelta, LZ4),
                
                -- Volume weighted average price
                vwap Float64 CODEC(DoubleDelta, LZ4),
                
                -- Market sentiment ratios
                buy_volume_ratio Float32 CODEC(DoubleDelta, LZ4),
                
                -- Volatility indicators
                price_range Float64 CODEC(DoubleDelta, LZ4),
                price_std Float64 CODEC(DoubleDelta, LZ4),
                
                -- Open interest for F&O
                oi_start UInt64 CODEC(DoubleDelta, LZ4),
                oi_end UInt64 CODEC(DoubleDelta, LZ4),
                oi_change Int64 CODEC(DoubleDelta, LZ4)
                
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(minute)
            ORDER BY (instrument_token, minute)
            SETTINGS index_granularity = 8192
            """
        )
    
    @staticmethod
    def get_strategy_signals_table() -> TableDefinition:
        """Get strategy signals table for ML and traditional strategies."""
        return TableDefinition(
            name="strategy_signals",
            description="Trading signals generated by strategies with ML features",
            partition_by="toYYYYMM(timestamp)",
            order_by="(strategy_name, instrument_token, timestamp)",
            create_sql="""
            CREATE TABLE IF NOT EXISTS strategy_signals (
                timestamp DateTime64(3) CODEC(Delta, LZ4),
                strategy_name String CODEC(ZSTD(1)),
                strategy_type Enum('traditional', 'ml', 'hybrid') CODEC(ZSTD(1)),
                instrument_token UInt32 CODEC(DoubleDelta, LZ4),
                exchange String CODEC(ZSTD(1)),
                tradingsymbol String CODEC(ZSTD(1)),
                
                -- Signal information
                signal_type Enum('BUY', 'SELL', 'HOLD') CODEC(ZSTD(1)),
                signal_strength Float64 CODEC(DoubleDelta, LZ4),
                confidence Float64 CODEC(DoubleDelta, LZ4),
                
                -- Price context
                signal_price Float64 CODEC(DoubleDelta, LZ4),
                market_price Float64 CODEC(DoubleDelta, LZ4),
                price_deviation Float64 CODEC(DoubleDelta, LZ4),
                
                -- ML features (JSON for flexibility)
                ml_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Technical indicators
                technical_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Risk metrics
                risk_score Float64 CODEC(DoubleDelta, LZ4),
                volatility_estimate Float64 CODEC(DoubleDelta, LZ4),
                
                -- Performance tracking
                signal_id String CODEC(ZSTD(1)),
                parent_signal_id String CODEC(ZSTD(1)),
                
                -- Metadata
                metadata String CODEC(ZSTD(1)),
                processing_latency_ms UInt32 CODEC(DoubleDelta, LZ4)
                
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (strategy_name, instrument_token, timestamp)
            SETTINGS index_granularity = 8192
            """
        )
    
    @staticmethod
    def get_ml_features_table() -> TableDefinition:
        """Get ML features table for real-time feature storage."""
        return TableDefinition(
            name="ml_features",
            description="Pre-computed ML features for strategy consumption",
            partition_by="toYYYYMM(timestamp)",
            order_by="(instrument_token, feature_set, timestamp)",
            create_sql="""
            CREATE TABLE IF NOT EXISTS ml_features (
                timestamp DateTime64(3) CODEC(Delta, LZ4),
                instrument_token UInt32 CODEC(DoubleDelta, LZ4),
                exchange String CODEC(ZSTD(1)),
                
                -- Feature set identification
                feature_set String CODEC(ZSTD(1)),
                feature_version String CODEC(ZSTD(1)),
                
                -- Price-based features
                price_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Volume-based features
                volume_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Technical indicator features
                technical_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Market microstructure features
                microstructure_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Time-based features
                time_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Cross-asset features
                market_regime_features Map(String, Float64) CODEC(ZSTD(1)),
                
                -- Feature quality metrics
                completeness_score Float32 CODEC(DoubleDelta, LZ4),
                freshness_score Float32 CODEC(DoubleDelta, LZ4),
                stability_score Float32 CODEC(DoubleDelta, LZ4),
                
                -- Computation metadata
                computation_time_ms UInt32 CODEC(DoubleDelta, LZ4),
                feature_count UInt16 CODEC(DoubleDelta, LZ4)
                
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (instrument_token, feature_set, timestamp)
            SETTINGS index_granularity = 8192
            """
        )
    
    @staticmethod
    def get_market_depth_snapshots_table() -> TableDefinition:
        """Get market depth snapshots table for order book analysis."""
        return TableDefinition(
            name="market_depth_snapshots",
            description="Market depth snapshots for order book analysis",
            partition_by="toYYYYMM(timestamp)",
            order_by="(instrument_token, timestamp)",
            create_sql="""
            CREATE TABLE IF NOT EXISTS market_depth_snapshots (
                timestamp DateTime64(3) CODEC(Delta, LZ4),
                instrument_token UInt32 CODEC(DoubleDelta, LZ4),
                exchange String CODEC(ZSTD(1)),
                
                -- Full order book depth (20 levels)
                bid_prices Array(Float64) CODEC(DoubleDelta, LZ4),
                bid_quantities Array(UInt32) CODEC(DoubleDelta, LZ4),
                bid_orders Array(UInt16) CODEC(DoubleDelta, LZ4),
                
                ask_prices Array(Float64) CODEC(DoubleDelta, LZ4),
                ask_quantities Array(UInt32) CODEC(DoubleDelta, LZ4),
                ask_orders Array(UInt16) CODEC(DoubleDelta, LZ4),
                
                -- Derived order book metrics
                bid_ask_spread Float64 CODEC(DoubleDelta, LZ4),
                mid_price Float64 CODEC(DoubleDelta, LZ4),
                total_bid_volume UInt64 CODEC(DoubleDelta, LZ4),
                total_ask_volume UInt64 CODEC(DoubleDelta, LZ4),
                
                -- Order book imbalance metrics
                volume_imbalance Float64 CODEC(DoubleDelta, LZ4),
                order_imbalance Float64 CODEC(DoubleDelta, LZ4),
                
                -- Liquidity metrics
                bid_liquidity_5 UInt64 CODEC(DoubleDelta, LZ4),
                ask_liquidity_5 UInt64 CODEC(DoubleDelta, LZ4),
                
                -- Market impact estimates
                market_impact_buy Float64 CODEC(DoubleDelta, LZ4),
                market_impact_sell Float64 CODEC(DoubleDelta, LZ4)
                
            ) ENGINE = MergeTree()
            PARTITION BY toYYYYMM(timestamp)
            ORDER BY (instrument_token, timestamp)
            SETTINGS index_granularity = 8192
            """
        )
    
    @staticmethod
    def get_materialized_views() -> List[TableDefinition]:
        """Get all materialized views for real-time feature computation."""
        return [
            # 1-minute OHLC materialized view
            TableDefinition(
                name="mv_ohlc_1m",
                description="Materialized view for 1-minute OHLC aggregation",
                partition_by="",
                order_by="",
                create_sql="""
                CREATE MATERIALIZED VIEW IF NOT EXISTS mv_ohlc_1m
                TO ohlc_1m AS
                SELECT
                    toStartOfMinute(timestamp) as minute,
                    instrument_token,
                    any(exchange) as exchange,
                    any(tradingsymbol) as tradingsymbol,
                    
                    argMin(last_price, timestamp) as open,
                    max(high) as high,
                    min(low) as low,
                    argMax(last_price, timestamp) as close,
                    
                    sum(last_quantity) as volume,
                    count() as trades_count,
                    
                    -- VWAP calculation
                    sum(last_price * last_quantity) / sum(last_quantity) as vwap,
                    
                    -- Market sentiment
                    sum(buy_quantity) / (sum(buy_quantity) + sum(sell_quantity)) as buy_volume_ratio,
                    
                    -- Volatility indicators
                    max(high) - min(low) as price_range,
                    stddevPop(last_price) as price_std,
                    
                    -- Open Interest
                    argMin(oi, timestamp) as oi_start,
                    argMax(oi, timestamp) as oi_end,
                    argMax(oi, timestamp) - argMin(oi, timestamp) as oi_change
                    
                FROM market_ticks
                GROUP BY minute, instrument_token
                """
            ),
            
            # ML features materialized view (basic technical indicators)
            TableDefinition(
                name="mv_ml_features_basic",
                description="Basic ML features materialized view",
                partition_by="",
                order_by="",
                create_sql="""
                CREATE MATERIALIZED VIEW IF NOT EXISTS mv_ml_features_basic
                TO ml_features AS
                SELECT
                    timestamp,
                    instrument_token,
                    any(exchange) as exchange,
                    'basic_technical' as feature_set,
                    '1.0' as feature_version,
                    
                    -- Price-based features
                    map(
                        'returns_1t', (last_price - lagInFrame(last_price, 1) OVER w) / lagInFrame(last_price, 1) OVER w,
                        'returns_5t', (last_price - lagInFrame(last_price, 5) OVER w) / lagInFrame(last_price, 5) OVER w,
                        'returns_volatility_20t', stddevPopInFrame(last_price, 20) OVER w / avgInFrame(last_price, 20) OVER w,
                        'price_momentum_10t', (last_price - lagInFrame(last_price, 10) OVER w) / lagInFrame(last_price, 10) OVER w
                    ) as price_features,
                    
                    -- Volume-based features
                    map(
                        'volume_sma_10t', avgInFrame(volume_traded, 10) OVER w,
                        'volume_ratio_current', volume_traded / avgInFrame(volume_traded, 20) OVER w,
                        'volume_trend_5t', (volume_traded - lagInFrame(volume_traded, 5) OVER w) / lagInFrame(volume_traded, 5) OVER w
                    ) as volume_features,
                    
                    -- Technical features
                    map(
                        'sma_20', avgInFrame(last_price, 20) OVER w,
                        'ema_12', exponentialMovingAverage(12)(last_price) OVER w,
                        'rsi_14', rsi(14)(last_price) OVER w,
                        'bb_upper', avgInFrame(last_price, 20) OVER w + 2 * stddevPopInFrame(last_price, 20) OVER w,
                        'bb_lower', avgInFrame(last_price, 20) OVER w - 2 * stddevPopInFrame(last_price, 20) OVER w
                    ) as technical_features,
                    
                    -- Microstructure features
                    map(
                        'bid_ask_spread', arrayElement(depth_sell, 1).1 - arrayElement(depth_buy, 1).1,
                        'depth_imbalance', (arrayElement(depth_buy, 1).2 - arrayElement(depth_sell, 1).2) / (arrayElement(depth_buy, 1).2 + arrayElement(depth_sell, 1).2)
                    ) as microstructure_features,
                    
                    -- Time features
                    map(
                        'hour_of_day', toHour(timestamp),
                        'minute_of_hour', toMinute(timestamp),
                        'day_of_week', toDayOfWeek(timestamp)
                    ) as time_features,
                    
                    -- Market regime features (placeholder)
                    map() as market_regime_features,
                    
                    -- Feature quality
                    1.0 as completeness_score,
                    1.0 as freshness_score,
                    1.0 as stability_score,
                    
                    0 as computation_time_ms,
                    10 as feature_count
                    
                FROM market_ticks
                WINDOW w AS (PARTITION BY instrument_token ORDER BY timestamp ROWS BETWEEN 20 PRECEDING AND CURRENT ROW)
                WHERE timestamp >= now() - INTERVAL 1 HOUR
                """
            ),
            
            # Market depth analytics materialized view
            TableDefinition(
                name="mv_depth_analytics",
                description="Market depth analytics materialized view",
                partition_by="",
                order_by="",
                create_sql="""
                CREATE MATERIALIZED VIEW IF NOT EXISTS mv_depth_analytics
                TO market_depth_snapshots AS
                SELECT
                    timestamp,
                    instrument_token,
                    any(exchange) as exchange,
                    
                    -- Extract prices and quantities from depth arrays
                    arrayMap(x -> x.1, depth_buy) as bid_prices,
                    arrayMap(x -> x.2, depth_buy) as bid_quantities,
                    arrayMap(x -> x.3, depth_buy) as bid_orders,
                    
                    arrayMap(x -> x.1, depth_sell) as ask_prices,
                    arrayMap(x -> x.2, depth_sell) as ask_quantities,
                    arrayMap(x -> x.3, depth_sell) as ask_orders,
                    
                    -- Derived metrics
                    arrayElement(depth_sell, 1).1 - arrayElement(depth_buy, 1).1 as bid_ask_spread,
                    (arrayElement(depth_sell, 1).1 + arrayElement(depth_buy, 1).1) / 2 as mid_price,
                    
                    arraySum(arrayMap(x -> x.2, depth_buy)) as total_bid_volume,
                    arraySum(arrayMap(x -> x.2, depth_sell)) as total_ask_volume,
                    
                    -- Imbalance metrics
                    (arraySum(arrayMap(x -> x.2, depth_buy)) - arraySum(arrayMap(x -> x.2, depth_sell))) / 
                    (arraySum(arrayMap(x -> x.2, depth_buy)) + arraySum(arrayMap(x -> x.2, depth_sell))) as volume_imbalance,
                    
                    (arraySum(arrayMap(x -> x.3, depth_buy)) - arraySum(arrayMap(x -> x.3, depth_sell))) / 
                    (arraySum(arrayMap(x -> x.3, depth_buy)) + arraySum(arrayMap(x -> x.3, depth_sell))) as order_imbalance,
                    
                    -- Top 5 liquidity
                    arraySum(arraySlice(arrayMap(x -> x.2, depth_buy), 1, 5)) as bid_liquidity_5,
                    arraySum(arraySlice(arrayMap(x -> x.2, depth_sell), 1, 5)) as ask_liquidity_5,
                    
                    -- Market impact estimates (simplified)
                    0.0 as market_impact_buy,
                    0.0 as market_impact_sell
                    
                FROM market_ticks
                WHERE arrayLength(depth_buy) > 0 AND arrayLength(depth_sell) > 0
                """
            )
        ]
    
    @staticmethod
    def get_all_table_definitions() -> List[TableDefinition]:
        """Get all table definitions."""
        tables = [
            ClickHouseSchemas.get_market_ticks_table(),
            ClickHouseSchemas.get_ohlc_1m_table(),
            ClickHouseSchemas.get_strategy_signals_table(),
            ClickHouseSchemas.get_ml_features_table(),
            ClickHouseSchemas.get_market_depth_snapshots_table(),
        ]
        
        # Add materialized views
        tables.extend(ClickHouseSchemas.get_materialized_views())
        
        return tables
    
    @staticmethod
    def get_indexes() -> List[str]:
        """Get index creation SQL statements."""
        return [
            # Market ticks indexes for common queries
            "ALTER TABLE market_ticks ADD INDEX IF NOT EXISTS idx_exchange (exchange) TYPE bloom_filter(0.01) GRANULARITY 8192",
            "ALTER TABLE market_ticks ADD INDEX IF NOT EXISTS idx_tradingsymbol (tradingsymbol) TYPE bloom_filter(0.01) GRANULARITY 8192",
            "ALTER TABLE market_ticks ADD INDEX IF NOT EXISTS idx_volume (volume_traded) TYPE minmax GRANULARITY 8192",
            
            # OHLC indexes
            "ALTER TABLE ohlc_1m ADD INDEX IF NOT EXISTS idx_ohlc_exchange (exchange) TYPE bloom_filter(0.01) GRANULARITY 8192",
            "ALTER TABLE ohlc_1m ADD INDEX IF NOT EXISTS idx_ohlc_volume (volume) TYPE minmax GRANULARITY 8192",
            
            # Strategy signals indexes
            "ALTER TABLE strategy_signals ADD INDEX IF NOT EXISTS idx_strategy_type (strategy_type) TYPE set(0) GRANULARITY 8192",
            "ALTER TABLE strategy_signals ADD INDEX IF NOT EXISTS idx_signal_type (signal_type) TYPE set(0) GRANULARITY 8192",
            "ALTER TABLE strategy_signals ADD INDEX IF NOT EXISTS idx_confidence (confidence) TYPE minmax GRANULARITY 8192",
        ]
    
    @staticmethod
    def get_database_settings() -> List[str]:
        """Get database-level settings for optimal performance."""
        return [
            "SET max_memory_usage = 10000000000",  # 10GB
            "SET max_bytes_before_external_group_by = 5000000000",  # 5GB
            "SET max_bytes_before_external_sort = 5000000000",  # 5GB
            "SET join_algorithm = 'hash'",
            "SET max_threads = 8",
            "SET max_execution_time = 300",  # 5 minutes
            "SET send_logs_level = 'warning'",
        ]