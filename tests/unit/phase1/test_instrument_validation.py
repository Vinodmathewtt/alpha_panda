"""
Additional tests for instrument validation and processing to ensure production readiness.
Tests that all instruments from instruments.csv are properly handled by the mock data generator
and can be processed by strategies.
"""

import pytest
from decimal import Decimal
from tests.mocks.realistic_data_generator import RealisticMarketDataGenerator
from core.schemas.events import MarketTick


class TestInstrumentValidation:
    """Test that all instruments from instruments.csv are properly supported."""
    
    # All instrument tokens from instruments.csv
    ALL_INSTRUMENTS = [
        256265, 260105, 738561, 408065, 81153, 1270529, 492033, 2815745,
        4267265, 177665, 3861249, 225537, 1346049, 2939649, 140033, 3050241,
        1195009, 857857, 424961, 2714625
    ]
    
    def test_all_instruments_in_mock_generator(self):
        """Test that all instruments from CSV are configured in mock generator."""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Verify all instruments are configured
        for instrument_token in self.ALL_INSTRUMENTS:
            assert instrument_token in generator.instruments, f"Instrument {instrument_token} missing from mock generator"
        
        # Verify instruments have proper configuration
        for instrument_token in self.ALL_INSTRUMENTS:
            config = generator.instruments[instrument_token]
            assert config.instrument_token == instrument_token
            assert config.symbol is not None and config.symbol != ""
            assert config.base_price > Decimal('0')
            assert config.volatility > 0
            assert config.volume_base > 0
            assert config.tick_size > Decimal('0')
            assert config.lot_size > 0
    
    def test_tick_generation_for_all_instruments(self):
        """Test that ticks can be generated for all instruments."""
        generator = RealisticMarketDataGenerator(seed=42)
        
        for instrument_token in self.ALL_INSTRUMENTS:
            # Generate tick for each instrument
            tick = generator.generate_tick(instrument_token)
            
            # Validate tick structure
            assert isinstance(tick, MarketTick)
            assert tick.instrument_token == instrument_token
            assert tick.last_price > Decimal('0')
            assert tick.timestamp is not None
            assert tick.tradable is True
    
    def test_multi_instrument_tick_stream(self):
        """Test generating ticks for multiple instruments simultaneously."""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Test with a subset of instruments
        test_instruments = self.ALL_INSTRUMENTS[:5]
        
        tick_count = 0
        instruments_seen = set()
        
        # Generate ticks for 10 seconds at 1 tick/second
        for tick in generator.generate_tick_stream(
            instrument_tokens=test_instruments,
            duration_seconds=10,
            ticks_per_second=1.0
        ):
            tick_count += 1
            instruments_seen.add(tick.instrument_token)
            
            # Validate each tick
            assert tick.instrument_token in test_instruments
            assert tick.last_price > Decimal('0')
            
            # Stop if we've seen enough
            if tick_count >= 10:
                break
        
        # Should have generated ticks for multiple instruments
        assert len(instruments_seen) > 1, "Should generate ticks for multiple instruments"
        assert tick_count >= 5, "Should generate reasonable number of ticks"
    
    def test_instrument_price_movement_realism(self):
        """Test that price movements are realistic for all instruments."""
        generator = RealisticMarketDataGenerator(seed=42)
        
        for instrument_token in self.ALL_INSTRUMENTS[:5]:  # Test subset for performance
            config = generator.instruments[instrument_token]
            initial_price = config.base_price
            
            prices = []
            for i in range(10):
                tick = generator.generate_tick(instrument_token)
                prices.append(tick.last_price)
            
            # Prices should vary but stay within reasonable bounds
            min_price = min(prices)
            max_price = max(prices)
            price_range = (max_price - min_price) / initial_price
            
            # Price movement should be reasonable (less than 10% over 10 ticks)
            assert price_range < Decimal('0.1'), f"Price movement too large for {instrument_token}: {price_range}"
            
            # Prices should be properly rounded to tick size
            for price in prices:
                remainder = price % config.tick_size
                assert remainder == Decimal('0'), f"Price {price} not aligned to tick size {config.tick_size}"
    
    def test_volume_generation_scaling(self):
        """Test that volume generation scales appropriately with different instruments."""
        generator = RealisticMarketDataGenerator(seed=42)
        
        volumes_by_instrument = {}
        
        # Generate several ticks for each instrument and collect volumes
        for instrument_token in self.ALL_INSTRUMENTS[:5]:  # Test subset
            volumes = []
            for _ in range(5):
                tick = generator.generate_tick(instrument_token, mode="quote")
                if hasattr(tick, 'last_traded_quantity'):
                    volumes.append(tick.last_traded_quantity)
            
            if volumes:
                volumes_by_instrument[instrument_token] = sum(volumes) / len(volumes)
        
        # Different instruments should have different average volumes
        unique_volumes = set(volumes_by_instrument.values())
        assert len(unique_volumes) > 1, "Should have different volume patterns for different instruments"
        
        # All volumes should be positive
        for volume in volumes_by_instrument.values():
            assert volume > 0, "Volumes should be positive"
    
    def test_market_scenarios_with_all_instruments(self):
        """Test that market scenarios work with all instruments."""
        from tests.mocks.realistic_data_generator import MarketScenarios
        
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Record original volatility
        original_volatility = {}
        for instrument_token in self.ALL_INSTRUMENTS[:3]:
            original_volatility[instrument_token] = generator.instruments[instrument_token].volatility
        
        # Test volatile market scenario
        MarketScenarios.volatile_market(generator)
        
        # Verify that volatility was increased for all instruments
        for instrument_token in self.ALL_INSTRUMENTS[:3]:
            config = generator.instruments[instrument_token]
            original = original_volatility[instrument_token]
            assert config.volatility > original, f"Volatility should be increased for instrument {instrument_token}"
            
        # Test that ticks can still be generated without crashing
        for instrument_token in self.ALL_INSTRUMENTS[:3]:
            tick = generator.generate_tick(instrument_token)
            assert isinstance(tick, MarketTick)
            assert tick.instrument_token == instrument_token
    
    def test_instrument_symbol_consistency(self):
        """Test that instrument symbols match expected format from CSV."""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Expected symbols from the CSV file
        expected_symbols = {
            256265: "NIFTY50",
            260105: "BANKNIFTY", 
            738561: "RELIANCE",
            408065: "BAJFINANCE",
            81153: "TCS",
            # Add a few more key ones
        }
        
        for instrument_token, expected_symbol in expected_symbols.items():
            config = generator.instruments[instrument_token]
            assert config.symbol == expected_symbol, f"Expected {expected_symbol}, got {config.symbol}"
    
    def test_snapshot_includes_all_instruments(self):
        """Test that snapshot functionality includes all configured instruments."""
        generator = RealisticMarketDataGenerator(seed=42)
        
        # Generate some activity for all instruments
        for instrument_token in self.ALL_INSTRUMENTS[:5]:  # Test subset
            generator.generate_tick(instrument_token)
        
        snapshot = generator.get_current_snapshot()
        
        # Snapshot should include all instruments that had activity
        for instrument_token in self.ALL_INSTRUMENTS[:5]:
            assert instrument_token in snapshot, f"Instrument {instrument_token} missing from snapshot"
            
            data = snapshot[instrument_token]
            assert "symbol" in data
            assert "current_price" in data
            assert "cumulative_volume" in data
            assert data["current_price"] > Decimal('0')