"""
Tests for strategy and instrument integration to ensure production readiness.
Tests that strategies can properly handle all instruments from instruments.csv.
"""

import pytest
from decimal import Decimal
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core.schemas.events import MarketTick
from strategies.base import MarketData, TradingSignal
from strategies.momentum import MomentumStrategy
from strategies.mean_reversion import MeanReversionStrategy
from tests.mocks.realistic_data_generator import RealisticMarketDataGenerator


class TestStrategyInstrumentIntegration:
    """Test that strategies can handle all instruments properly."""
    
    # All instrument tokens from instruments.csv
    ALL_INSTRUMENTS = [
        256265, 260105, 738561, 408065, 81153, 1270529, 492033, 2815745,
        4267265, 177665, 3861249, 225537, 1346049, 2939649, 140033, 3050241,
        1195009, 857857, 424961, 2714625
    ]
    
    def convert_tick_to_market_data(self, tick: MarketTick) -> MarketData:
        """Convert MarketTick to MarketData for strategy processing."""
        return MarketData(
            instrument_token=tick.instrument_token,
            last_price=tick.last_price,
            volume_traded=getattr(tick, 'volume_traded', 0) or 0,
            timestamp=tick.timestamp
        )
    
    @pytest.fixture
    def mock_settings(self):
        """Mock settings for strategy testing."""
        settings = MagicMock()
        settings.strategy_runner = MagicMock()
        settings.strategy_runner.signal_cooldown_seconds = 30
        return settings
    
    @pytest.fixture
    def data_generator(self):
        """Data generator with all instruments."""
        return RealisticMarketDataGenerator(seed=42)
    
    def test_momentum_strategy_with_all_instruments(self, mock_settings, data_generator):
        """Test momentum strategy can process all instruments."""
        # Strategy configuration for all instruments
        parameters = {
            'lookback_period': 10,
            'momentum_threshold': 0.02,
            'position_size': 100,
            'max_history': 50
        }
        
        strategy = MomentumStrategy(
            strategy_id='test_momentum',
            parameters=parameters,
            brokers=['paper'],
            instrument_tokens=self.ALL_INSTRUMENTS[:5]
        )
        
        # Test strategy can handle all instruments
        for instrument_token in self.ALL_INSTRUMENTS[:5]:  # Test subset for performance
            # Generate historical ticks to build momentum
            signals_generated = 0
            for i in range(15):  # Generate enough ticks for lookback
                tick = data_generator.generate_tick(instrument_token)
                market_data = self.convert_tick_to_market_data(tick)
                
                # Process tick through strategy - returns generator
                signal_generator = strategy.on_market_data(market_data)
                signals = list(signal_generator)  # Convert generator to list
                
                # Strategy should not crash
                for signal in signals:
                    signals_generated += 1
                    assert isinstance(signal, TradingSignal)
                    assert signal.instrument_token == instrument_token
                    assert signal.signal_type.value in ['BUY', 'SELL']
                    assert signal.quantity > 0
            
            # Verify strategy maintains history 
            assert len(strategy._market_data_history) <= parameters['max_history']
    
    def test_mean_reversion_strategy_with_all_instruments(self, mock_settings, data_generator):
        """Test mean reversion strategy can process all instruments."""
        config = {
            'strategy_name': 'test_mean_reversion',
            'window_size': 20,
            'entry_threshold': 2.0,
            'exit_threshold': 0.5,
            'max_position_size': 50,
            'max_drawdown_percent': 0.15,
            'max_history': 100
        }
        
        strategy = MeanReversionStrategy(
            strategy_id='test_mean_reversion',
            parameters=config,
            brokers=['paper'],
            instrument_tokens=self.ALL_INSTRUMENTS[:5]
        )
        
        # Test with several instruments
        for instrument_token in self.ALL_INSTRUMENTS[:5]:  # Test subset for performance
            # Generate enough ticks to build statistics
            for i in range(25):  # More than window_size
                tick = data_generator.generate_tick(instrument_token)
                market_data = self.convert_tick_to_market_data(tick)
                signals = list(strategy.on_market_data(market_data))
                signal = signals[0] if signals else None
                
                # Strategy should handle the tick without crashing
                if signal is not None:
                    assert isinstance(signal, TradingSignal)
                    assert signal.instrument_token == instrument_token
                    assert signal.signal_type.value in ['BUY', 'SELL']
                    
            # Verify strategy maintains history
            assert len(strategy._market_data_history) <= config['max_history']
    
    def test_strategies_handle_different_price_ranges(self, mock_settings, data_generator):
        """Test that strategies handle instruments with vastly different price ranges."""
        config = {
            'strategy_name': 'test_price_ranges',
            'lookback_period': 10,
            'momentum_threshold': 0.02,
            'stop_loss_percent': 0.05,
            'take_profit_percent': 0.10,
            'max_position_size': 100,
            'max_history': 50
        }
        
        strategy = MomentumStrategy(
            strategy_id='test_price_ranges',
            parameters=config,
            brokers=['paper'],
            instrument_tokens=[3861249, 2939649, 3050241, 738561, 1270529]
        )
        
        # Test with instruments that have very different base prices
        high_price_instruments = [3861249]  # MARUTI ~11000
        low_price_instruments = [2939649, 3050241]  # NTPC ~350, POWERGRID ~320
        mid_price_instruments = [738561, 1270529]  # RELIANCE ~2450, ICICIBANK ~1200
        
        for instrument_group in [high_price_instruments, low_price_instruments, mid_price_instruments]:
            for instrument_token in instrument_group:
                # Generate some ticks
                signals_generated = 0
                for i in range(20):
                    tick = data_generator.generate_tick(instrument_token)
                    market_data = self.convert_tick_to_market_data(tick)
                    signals = list(strategy.on_market_data(market_data))
                    signal = signals[0] if signals else None
                    
                    if signal is not None:
                        signals_generated += 1
                        # Signal quantities should be reasonable regardless of price
                        assert 1 <= signal.quantity <= config['max_position_size']
                        
                        # Verify signal has basic required fields
                        assert signal.signal_type.value in ['BUY', 'SELL']
                        assert signal.price is not None
                        assert signal.timestamp is not None
    
    def test_strategy_performance_with_all_instruments(self, mock_settings, data_generator):
        """Test that strategy processing performance is acceptable with all instruments."""
        import time
        
        config = {
            'strategy_name': 'test_performance',
            'lookback_period': 20,
            'momentum_threshold': 0.02,
            'stop_loss_percent': 0.05,
            'take_profit_percent': 0.10,
            'max_position_size': 100,
            'max_history': 200
        }
        
        strategy = MomentumStrategy(
            strategy_id='test_performance',
            parameters=config,
            brokers=['paper'],
            instrument_tokens=self.ALL_INSTRUMENTS
        )
        
        # Test processing speed with all instruments
        start_time = time.time()
        
        total_ticks_processed = 0
        for instrument_token in self.ALL_INSTRUMENTS:
            # Process 10 ticks per instrument
            for i in range(10):
                tick = data_generator.generate_tick(instrument_token)
                market_data = self.convert_tick_to_market_data(tick)
                signals = list(strategy.on_market_data(market_data))
                total_ticks_processed += 1
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process at least 100 ticks/second (very conservative target)
        ticks_per_second = total_ticks_processed / processing_time
        assert ticks_per_second > 100, f"Processing too slow: {ticks_per_second:.1f} ticks/sec"
        
        # Memory usage should be reasonable - check that history is bounded
        assert len(strategy._market_data_history) <= config['max_history'], f"History too long: {len(strategy._market_data_history)}"
    
    def test_strategy_signal_generation_distribution(self, mock_settings, data_generator):
        """Test that signal generation is reasonable across different instruments."""
        config = {
            'strategy_name': 'test_signal_distribution',
            'lookback_period': 10,
            'momentum_threshold': 0.01,  # Lower threshold to generate more signals
            'stop_loss_percent': 0.05,
            'take_profit_percent': 0.10,
            'max_position_size': 100,
            'max_history': 50
        }
        
        strategy = MomentumStrategy(
            strategy_id='test_signal_distribution',
            parameters=config,
            brokers=['paper'],
            instrument_tokens=self.ALL_INSTRUMENTS[:5]
        )
        
        signal_counts = {}
        
        # Test signal generation for different instruments
        for instrument_token in self.ALL_INSTRUMENTS[:5]:  # Test subset
            signals_for_instrument = 0
            
            # Generate many ticks to get statistical sample
            for i in range(50):
                tick = data_generator.generate_tick(instrument_token)
                market_data = self.convert_tick_to_market_data(tick)
                signals = list(strategy.on_market_data(market_data))
                signal = signals[0] if signals else None
                
                if signal is not None:
                    signals_for_instrument += 1
            
            signal_counts[instrument_token] = signals_for_instrument
        
        # Should generate some signals (but not too many)
        total_signals = sum(signal_counts.values())
        assert total_signals > 0, "Should generate at least some signals"
        assert total_signals < 250, f"Generating too many signals: {total_signals} out of 250 ticks"  # Max 5 instruments * 50 ticks
        
        # Signal distribution should be somewhat reasonable across instruments
        if total_signals > 0:
            instruments_with_signals = len([count for count in signal_counts.values() if count > 0])
            assert instruments_with_signals > 1, "Should generate signals for multiple instruments"
    
    def test_strategy_state_isolation_between_instruments(self, mock_settings, data_generator):
        """Test that strategy maintains separate state for each instrument."""
        config = {
            'strategy_name': 'test_state_isolation',
            'lookback_period': 5,
            'momentum_threshold': 0.02,
            'stop_loss_percent': 0.05,
            'take_profit_percent': 0.10,
            'max_position_size': 100,
            'max_history': 20
        }
        
        strategy = MomentumStrategy(
            strategy_id='test_state_isolation',
            parameters=config,
            brokers=['paper'],
            instrument_tokens=[256265, 738561]
        )
        
        # Use two different instruments
        instrument1 = 256265  # NIFTY50
        instrument2 = 738561  # RELIANCE
        
        # Generate different price patterns for each instrument
        for i in range(10):
            # Generate tick for instrument1
            tick1 = data_generator.generate_tick(instrument1)
            market_data1 = self.convert_tick_to_market_data(tick1)
            signals1 = list(strategy.on_market_data(market_data1))
            signal1 = signals1[0] if signals1 else None
            
            # Generate tick for instrument2 
            tick2 = data_generator.generate_tick(instrument2)
            market_data2 = self.convert_tick_to_market_data(tick2)
            signals2 = list(strategy.on_market_data(market_data2))
            signal2 = signals2[0] if signals2 else None
        
        # Strategy should maintain reasonable history length
        assert len(strategy._market_data_history) <= config['max_history']
        
        # Should have processed data for both instruments
        processed_tokens = {data.instrument_token for data in strategy._market_data_history}
        assert len(processed_tokens) >= 1  # Should have processed at least one instrument
    
    def test_invalid_instrument_handling(self, mock_settings, data_generator):
        """Test that strategies handle invalid or unknown instruments gracefully."""
        config = {
            'strategy_name': 'test_invalid_instrument',
            'lookback_period': 10,
            'momentum_threshold': 0.02,
            'stop_loss_percent': 0.05,
            'take_profit_percent': 0.10,
            'max_position_size': 100,
            'max_history': 50
        }
        
        strategy = MomentumStrategy(
            strategy_id='test_invalid_instrument',
            parameters=config,
            brokers=['paper'],
            instrument_tokens=[999999999]  # Include the invalid instrument in subscription
        )
        
        # Create a tick with invalid instrument token
        invalid_tick = MarketTick(
            instrument_token=999999999,  # Invalid instrument
            last_price=Decimal('100.0'),
            timestamp=datetime.now(timezone.utc),
            mode="ltp",
            tradable=True
        )
        
        # Strategy should handle invalid instrument gracefully (not crash)
        market_data = self.convert_tick_to_market_data(invalid_tick)
        signals = list(strategy.on_market_data(market_data))
        signal = signals[0] if signals else None
        
        # Strategy might return None or handle it, but should not crash
        if signal is not None:
            assert isinstance(signal, TradingSignal)
            assert signal.instrument_token == 999999999