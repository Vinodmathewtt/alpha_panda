"""
Phase 1 Tests: Mock Data Generator Testing
Tests the realistic market data generator for testing infrastructure.
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from tests.mocks.realistic_data_generator import RealisticMarketDataGenerator, MarketScenarios
from core.schemas.events import MarketTick


class TestRealisticDataGenerator:
    """Test realistic market data generation"""
    
    def test_generator_initialization(self):
        """Test generator initializes with predefined instruments"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Should have predefined instruments
        assert len(generator.instruments) > 0
        assert 256265 in generator.instruments  # NIFTY 50
        assert 260105 in generator.instruments  # BANKNIFTY
        
        # Should have initial prices set
        assert 256265 in generator.current_prices
        assert generator.current_prices[256265] > 0
        
    def test_basic_tick_generation(self):
        """Test basic tick generation"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Generate tick for NIFTY
        tick = generator.generate_tick(256265, mode="ltp")
        
        assert isinstance(tick, MarketTick)
        assert tick.instrument_token == 256265
        assert tick.last_price > 0
        assert tick.timestamp is not None
        assert tick.mode == "ltp"
        assert tick.tradable is True
        
    def test_quote_mode_tick(self):
        """Test quote mode tick with volume data"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        tick = generator.generate_tick(256265, mode="quote")
        
        assert tick.mode == "quote"
        assert tick.volume_traded is not None
        assert tick.last_traded_quantity is not None
        assert tick.total_buy_quantity is not None
        assert tick.total_sell_quantity is not None
        assert tick.ohlc is not None
        assert tick.change is not None
        
    def test_full_mode_tick(self):
        """Test full mode tick with market depth"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        tick = generator.generate_tick(256265, mode="full")
        
        assert tick.mode == "full"
        assert tick.depth is not None
        assert hasattr(tick.depth, 'buy')
        assert hasattr(tick.depth, 'sell')
        assert len(tick.depth.buy) == 5  # 5-level depth
        assert len(tick.depth.sell) == 5
        
    def test_price_movement_realism(self):
        """Test that price movements are realistic"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Generate multiple ticks and check price movements
        initial_price = generator.current_prices[256265]
        prices = []
        
        for i in range(10):
            tick = generator.generate_tick(256265)
            prices.append(float(tick.last_price))
            
        # Prices should not be all the same
        assert len(set(prices)) > 1
        
        # Prices should not move too dramatically (within 5% typically)
        min_price = min(prices)
        max_price = max(prices)
        price_range = (max_price - min_price) / min_price
        assert price_range < 0.1  # Less than 10% range is realistic for short term
        
    def test_volume_generation(self):
        """Test volume generation patterns"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Generate multiple ticks and check volumes
        volumes = []
        for i in range(5):
            tick = generator.generate_tick(256265, mode="quote")
            volumes.append(tick.last_traded_quantity)
            
        # Volumes should be positive
        assert all(vol > 0 for vol in volumes)
        
        # Volumes should vary
        assert len(set(volumes)) > 1
        
    def test_cumulative_volume(self):
        """Test that cumulative volume increases"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Generate multiple ticks and track cumulative volume
        tick1 = generator.generate_tick(256265, mode="quote")
        tick2 = generator.generate_tick(256265, mode="quote")
        
        # Cumulative volume should increase
        assert tick2.volume_traded > tick1.volume_traded
        
    def test_market_scenarios(self):
        """Test market scenario configurations"""
        generator = RealisticMarketDataGenerator(seed=42)
        original_volatility = generator.instruments[256265].volatility
        
        # Test volatile market scenario
        MarketScenarios.volatile_market(generator)
        assert generator.instruments[256265].volatility > original_volatility
        
        # Reset and test trending market
        generator = RealisticMarketDataGenerator(seed=42)
        MarketScenarios.trending_up_market(generator)
        # Should have modified volatility (lower for trending)
        assert generator.instruments[256265].volatility < original_volatility
        
    def test_ohlc_data_consistency(self):
        """Test OHLC data is logically consistent"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        tick = generator.generate_tick(256265, mode="quote")
        
        if tick.ohlc:
            ohlc = tick.ohlc
            # High should be >= low
            assert ohlc.high >= ohlc.low
            # Open and close should be within high/low range
            assert ohlc.low <= ohlc.open <= ohlc.high
            assert ohlc.low <= ohlc.close <= ohlc.high
            
    def test_market_depth_structure(self):
        """Test market depth data structure"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        tick = generator.generate_tick(256265, mode="full")
        
        depth = tick.depth
        assert depth is not None
        
        # Check buy side
        buy_levels = depth.buy
        assert len(buy_levels) == 5
        
        for i, level in enumerate(buy_levels):
            assert hasattr(level, 'price')
            assert hasattr(level, 'quantity')
            assert hasattr(level, 'orders')
            assert level.quantity > 0
            assert level.orders > 0
            
            # Buy prices should decrease as we go down levels
            if i > 0:
                assert level.price < buy_levels[i-1].price
                
        # Check sell side
        sell_levels = depth.sell
        assert len(sell_levels) == 5
        
        for i, level in enumerate(sell_levels):
            assert level.quantity > 0
            assert level.orders > 0
            
            # Sell prices should increase as we go up levels
            if i > 0:
                assert level.price > sell_levels[i-1].price
                
    def test_deterministic_with_seed(self):
        """Test that generator is deterministic with seed"""
        # Two generators with same seed should produce same sequence
        gen1 = RealisticMarketDataGenerator(seed=123)
        gen2 = RealisticMarketDataGenerator(seed=123)
        
        tick1 = gen1.generate_tick(256265)
        tick2 = gen2.generate_tick(256265)
        
        # Should have same price (within tick size)
        assert abs(tick1.last_price - tick2.last_price) < Decimal("0.10")
        
    def test_invalid_instrument_handling(self):
        """Test handling of invalid instrument tokens"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        with pytest.raises(ValueError):
            generator.generate_tick(999999)  # Invalid token
            
    def test_market_event_simulation(self):
        """Test market event simulation"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        original_price = generator.current_prices[256265]
        
        # Simulate news event
        generator.simulate_market_event("news", 256265)
        
        # Price should change after news event
        new_price = generator.current_prices[256265]
        assert new_price != original_price
        
    def test_snapshot_functionality(self):
        """Test market snapshot functionality"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Generate some ticks to create state
        generator.generate_tick(256265)
        generator.generate_tick(260105)
        
        snapshot = generator.get_current_snapshot()
        
        assert isinstance(snapshot, dict)
        assert 256265 in snapshot
        assert 260105 in snapshot
        
        nifty_data = snapshot[256265]
        assert "symbol" in nifty_data
        assert "current_price" in nifty_data
        assert "cumulative_volume" in nifty_data
        assert nifty_data["symbol"] == "NIFTY50"


class TestMarketModes:
    """Test different market data modes (LTP, quote, full)"""
    
    def test_ltp_mode_minimal_data(self):
        """Test LTP mode returns minimal data"""
        generator = RealisticMarketDataGenerator(seed=42)
        tick = generator.generate_tick(256265, mode="ltp")
        
        # LTP mode should have minimal data
        assert tick.mode == "ltp"
        assert tick.volume_traded is None
        assert tick.ohlc is None
        assert tick.depth is None
        
    def test_quote_mode_extended_data(self):
        """Test quote mode includes volume and OHLC"""
        generator = RealisticMarketDataGenerator(seed=42)
        tick = generator.generate_tick(256265, mode="quote")
        
        assert tick.mode == "quote"
        assert tick.volume_traded is not None
        assert tick.ohlc is not None
        assert tick.depth is None  # Depth only in full mode
        
    def test_full_mode_complete_data(self):
        """Test full mode includes all available data"""
        generator = RealisticMarketDataGenerator(seed=42)
        tick = generator.generate_tick(256265, mode="full")
        
        assert tick.mode == "full"
        assert tick.volume_traded is not None
        assert tick.ohlc is not None
        assert tick.depth is not None
        
    def test_derivative_data(self):
        """Test derivative-specific data like OI"""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # BANKNIFTY is configured as derivative
        tick = generator.generate_tick(260105, mode="full")
        
        # Should have Open Interest data for derivatives
        assert tick.oi is not None
        assert tick.oi_day_high is not None
        assert tick.oi_day_low is not None
        assert tick.oi > 0