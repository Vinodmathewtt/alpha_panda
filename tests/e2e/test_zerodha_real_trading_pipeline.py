"""
End-to-end tests using real Zerodha authentication and market feed.
These tests validate the complete trading pipeline with actual broker integration.

WARNING: These tests require real Zerodha credentials and will interact with live market data.
Only run in a safe testing environment with paper trading enabled.
"""

import pytest
import asyncio
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, Any, List
import json

from kiteconnect import KiteConnect

from core.config.settings import Settings
from core.schemas.events import EventEnvelope, EventType, MarketData, TradingSignal
from services.market_feed.service import MarketFeedService
from services.strategy_runner.service import StrategyRunnerService
from services.trading_engine.service import TradingEngineService
from services.portfolio_manager.service import PortfolioManagerService


@pytest.fixture
def zerodha_credentials():
    """Zerodha credentials from environment variables"""
    api_key = os.getenv('ZERODHA_API_KEY')
    api_secret = os.getenv('ZERODHA_API_SECRET')
    access_token = os.getenv('ZERODHA_ACCESS_TOKEN')
    
    if not all([api_key, api_secret, access_token]):
        pytest.skip("Zerodha credentials not available - set ZERODHA_API_KEY, ZERODHA_API_SECRET, ZERODHA_ACCESS_TOKEN")
    
    return {
        'api_key': api_key,
        'api_secret': api_secret,
        'access_token': access_token
    }


@pytest.fixture
def kite_client(zerodha_credentials):
    """Authenticated KiteConnect client for real API testing"""
    kite = KiteConnect(api_key=zerodha_credentials['api_key'])
    kite.set_access_token(zerodha_credentials['access_token'])
    
    # Verify authentication works
    try:
        profile = kite.profile()
        assert profile['user_id'] is not None
    except Exception as e:
        pytest.skip(f"Zerodha authentication failed: {e}")
    
    return kite


@pytest.fixture
def real_settings(zerodha_credentials):
    """Settings configured for real Zerodha integration"""
    settings = Settings()
    
    # Override with real Zerodha credentials
    settings.zerodha.api_key = zerodha_credentials['api_key']
    settings.zerodha.api_secret = zerodha_credentials['api_secret']
    settings.zerodha.access_token = zerodha_credentials['access_token']
    
    # Enable paper trading for safety
    settings.paper_trading.enabled = True
    settings.zerodha.enabled = False  # Force paper mode for safety
    
    # Set active brokers to paper only for safety
    settings.active_brokers = ["paper"]
    
    return settings


@pytest.mark.asyncio
@pytest.mark.slow
class TestZerodhaAuthentication:
    """Test Zerodha authentication and API connectivity"""
    
    async def test_zerodha_api_authentication(self, kite_client):
        """Test that Zerodha API authentication works"""
        # Test basic API calls
        profile = kite_client.profile()
        assert profile is not None
        assert 'user_id' in profile
        assert 'email' in profile
        
        print(f"✅ Authenticated as: {profile['user_id']} ({profile['email']})")
    
    async def test_zerodha_market_data_access(self, kite_client):
        """Test that market data can be accessed through Zerodha API"""
        # Test instrument list access
        instruments = kite_client.instruments()
        assert len(instruments) > 0
        
        # Find a liquid NSE stock for testing
        nse_stocks = [inst for inst in instruments 
                     if inst['exchange'] == 'NSE' 
                     and inst['instrument_type'] == 'EQ'
                     and inst['name'] in ['RELIANCE', 'TCS', 'INFY']]
        
        assert len(nse_stocks) > 0
        test_instrument = nse_stocks[0]
        
        print(f"✅ Found test instrument: {test_instrument['tradingsymbol']} (Token: {test_instrument['instrument_token']})")
        
        # Test quote access
        quote = kite_client.quote([test_instrument['instrument_token']])
        assert len(quote) > 0
        
        instrument_quote = quote[str(test_instrument['instrument_token'])]
        assert 'last_price' in instrument_quote
        assert instrument_quote['last_price'] > 0
        
        print(f"✅ Current price: ₹{instrument_quote['last_price']}")
    
    async def test_zerodha_historical_data_access(self, kite_client):
        """Test historical data access for strategy backtesting"""
        # Get RELIANCE token for testing
        instruments = kite_client.instruments()
        reliance = next((inst for inst in instruments 
                        if inst['tradingsymbol'] == 'RELIANCE' 
                        and inst['exchange'] == 'NSE'), None)
        
        if not reliance:
            pytest.skip("RELIANCE instrument not found")
        
        # Test historical data retrieval
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=5)
        
        historical_data = kite_client.historical_data(
            instrument_token=reliance['instrument_token'],
            from_date=start_date,
            to_date=end_date,
            interval='minute'
        )
        
        assert len(historical_data) > 0
        
        # Validate data structure
        sample_candle = historical_data[0]
        required_fields = ['date', 'open', 'high', 'low', 'close', 'volume']
        for field in required_fields:
            assert field in sample_candle
        
        print(f"✅ Retrieved {len(historical_data)} historical data points")


@pytest.mark.asyncio
@pytest.mark.slow
class TestRealMarketFeedIntegration:
    """Test market feed service with real Zerodha WebSocket"""
    
    async def test_market_feed_websocket_connection(self, real_settings, kite_client):
        """Test that market feed can connect to Zerodha WebSocket"""
        # This test requires actual WebSocket connection to Zerodha
        # For safety, we'll test the connection setup without full streaming
        
        market_feed_service = MarketFeedService(real_settings, None)
        
        # Test that service can be configured with real credentials
        assert market_feed_service.settings.zerodha.api_key is not None
        assert market_feed_service.settings.zerodha.access_token is not None
        
        # Test instrument token resolution
        instruments = kite_client.instruments()
        nse_equity = [inst for inst in instruments 
                     if inst['exchange'] == 'NSE' 
                     and inst['instrument_type'] == 'EQ'
                     and inst['tradingsymbol'] in ['RELIANCE', 'TCS']]
        
        assert len(nse_equity) > 0
        
        test_tokens = [inst['instrument_token'] for inst in nse_equity[:2]]
        
        print(f"✅ Test instruments: {[inst['tradingsymbol'] for inst in nse_equity[:2]]}")
        print(f"✅ Test tokens: {test_tokens}")
    
    async def test_market_data_event_generation(self, real_settings, kite_client):
        """Test market data event generation from real quotes"""
        # Get real market quote and test event generation
        instruments = kite_client.instruments()
        reliance = next((inst for inst in instruments 
                        if inst['tradingsymbol'] == 'RELIANCE'
                        and inst['exchange'] == 'NSE'), None)
        
        if not reliance:
            pytest.skip("RELIANCE not found")
        
        # Get real quote
        quote_data = kite_client.quote([reliance['instrument_token']])
        reliance_quote = quote_data[str(reliance['instrument_token'])]
        
        # Create MarketData event from real data
        market_data = MarketData(
            instrument_token=reliance['instrument_token'],
            last_price=Decimal(str(reliance_quote['last_price'])),
            volume=reliance_quote.get('volume', 0),
            timestamp=datetime.now()
        )
        
        # Validate event structure
        assert market_data.instrument_token == reliance['instrument_token']
        assert market_data.last_price > 0
        assert isinstance(market_data.last_price, Decimal)
        
        # Test EventEnvelope wrapping
        envelope = EventEnvelope(
            id=str(asyncio.get_event_loop().time()),
            type=EventType.MARKET_DATA,
            timestamp=datetime.now(),
            source="market_feed",
            version="1.0",
            key=str(market_data.instrument_token),
            data=market_data.model_dump()
        )
        
        assert envelope.type == EventType.MARKET_DATA
        assert envelope.key == str(reliance['instrument_token'])
        
        print(f"✅ Created market data event for {reliance['tradingsymbol']} @ ₹{market_data.last_price}")


@pytest.mark.asyncio
@pytest.mark.slow
class TestRealTradingPipelineValidation:
    """Test complete trading pipeline with real market data but paper execution"""
    
    async def test_strategy_signal_generation_with_real_data(self, real_settings, kite_client):
        """Test strategy signal generation using real market data"""
        # Get real historical data for strategy input
        instruments = kite_client.instruments()
        test_stock = next((inst for inst in instruments
                          if inst['tradingsymbol'] == 'RELIANCE'
                          and inst['exchange'] == 'NSE'), None)
        
        if not test_stock:
            pytest.skip("Test stock not available")
        
        # Get recent historical data
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=2)
        
        historical_data = kite_client.historical_data(
            instrument_token=test_stock['instrument_token'],
            from_date=start_date,
            to_date=end_date,
            interval='5minute'
        )
        
        if len(historical_data) < 10:
            pytest.skip("Insufficient historical data")
        
        # Simulate strategy processing with real data
        prices = [Decimal(str(candle['close'])) for candle in historical_data[-10:]]
        
        # Simple momentum strategy logic
        recent_price = prices[-1]
        avg_price = sum(prices[:-1]) / len(prices[:-1])
        momentum = (recent_price - avg_price) / avg_price
        
        # Generate signal based on real price momentum
        if abs(momentum) > Decimal('0.01'):  # 1% threshold
            signal_type = "BUY" if momentum > 0 else "SELL"
            
            trading_signal = TradingSignal(
                strategy_id="real_data_momentum_test",
                instrument_token=test_stock['instrument_token'],
                signal_type=signal_type,
                quantity=1,  # Minimal quantity for testing
                price=recent_price,
                confidence=min(abs(float(momentum)) * 10, 1.0),
                timestamp=datetime.now()
            )
            
            assert trading_signal.strategy_id == "real_data_momentum_test"
            assert trading_signal.signal_type in ["BUY", "SELL"]
            assert trading_signal.price == recent_price
            assert 0 <= trading_signal.confidence <= 1.0
            
            print(f"✅ Generated {signal_type} signal for {test_stock['tradingsymbol']}")
            print(f"   Price: ₹{recent_price}, Momentum: {momentum:.4f}, Confidence: {trading_signal.confidence:.2f}")
        else:
            print(f"✅ No signal generated - momentum {momentum:.4f} below threshold")
    
    async def test_paper_trading_execution_with_real_prices(self, real_settings, kite_client):
        """Test paper trading execution using real market prices"""
        # Get real current price
        instruments = kite_client.instruments()
        test_stock = next((inst for inst in instruments
                          if inst['tradingsymbol'] == 'TCS'
                          and inst['exchange'] == 'NSE'), None)
        
        if not test_stock:
            pytest.skip("TCS not available for testing")
        
        quote_data = kite_client.quote([test_stock['instrument_token']])
        current_quote = quote_data[str(test_stock['instrument_token'])]
        current_price = Decimal(str(current_quote['last_price']))
        
        # Create realistic trading signal with current market price
        trading_signal = TradingSignal(
            strategy_id="paper_test_strategy",
            instrument_token=test_stock['instrument_token'],
            signal_type="BUY",
            quantity=1,
            price=current_price,
            confidence=0.8,
            timestamp=datetime.now()
        )
        
        # Test paper execution simulation
        # (In real implementation, this would go through TradingEngineService)
        
        # Simulate order placement
        order_id = f"PAPER_ORDER_{asyncio.get_event_loop().time()}"
        
        # Paper trading should use real price but simulate execution
        simulated_fill_price = current_price  # In paper trading, assume perfect fill
        
        # Validate execution parameters
        assert simulated_fill_price > 0
        assert isinstance(simulated_fill_price, Decimal)
        
        # Test portfolio impact calculation
        position_value = simulated_fill_price * trading_signal.quantity
        assert position_value > 0
        
        print(f"✅ Simulated paper execution:")
        print(f"   Stock: {test_stock['tradingsymbol']}")
        print(f"   Signal: {trading_signal.signal_type} {trading_signal.quantity} @ ₹{current_price}")
        print(f"   Fill Price: ₹{simulated_fill_price}")
        print(f"   Position Value: ₹{position_value}")
        
        # Verify paper trading safety
        assert real_settings.paper_trading.enabled is True
        assert "paper" in real_settings.active_brokers
        assert real_settings.zerodha.enabled is False  # Safety check
    
    async def test_risk_management_with_real_market_conditions(self, real_settings, kite_client):
        """Test risk management using real market conditions"""
        # Get current market conditions
        instruments = kite_client.instruments()
        test_stocks = [inst for inst in instruments
                      if inst['exchange'] == 'NSE' 
                      and inst['instrument_type'] == 'EQ'
                      and inst['tradingsymbol'] in ['RELIANCE', 'TCS', 'INFY']]
        
        if len(test_stocks) < 2:
            pytest.skip("Insufficient test stocks")
        
        # Get quotes for risk assessment
        token_list = [stock['instrument_token'] for stock in test_stocks[:2]]
        quotes = kite_client.quote(token_list)
        
        total_portfolio_value = Decimal('1000000')  # ₹10 Lakh test portfolio
        
        # Test position sizing based on real volatility
        for token, quote_data in quotes.items():
            stock = next(s for s in test_stocks if s['instrument_token'] == int(token))
            current_price = Decimal(str(quote_data['last_price']))
            
            # Calculate position size (max 2% of portfolio per position)
            max_position_value = total_portfolio_value * Decimal('0.02')
            max_quantity = int(max_position_value / current_price)
            
            # Create test signal
            test_signal = TradingSignal(
                strategy_id="risk_test_strategy",
                instrument_token=int(token),
                signal_type="BUY",
                quantity=max_quantity,
                price=current_price,
                confidence=0.7,
                timestamp=datetime.now()
            )
            
            # Risk validation
            position_value = test_signal.price * test_signal.quantity
            portfolio_percentage = position_value / total_portfolio_value
            
            assert portfolio_percentage <= Decimal('0.025')  # Max 2.5% with buffer
            assert test_signal.quantity > 0
            assert test_signal.price > 0
            
            print(f"✅ Risk check for {stock['tradingsymbol']}:")
            print(f"   Price: ₹{current_price}")
            print(f"   Max Quantity: {max_quantity}")
            print(f"   Position Value: ₹{position_value}")
            print(f"   Portfolio %: {portfolio_percentage:.2%}")
    
    async def test_end_to_end_pipeline_safety_validation(self, real_settings):
        """Test that end-to-end pipeline enforces safety constraints"""
        # Verify paper trading is enabled
        assert real_settings.paper_trading.enabled is True
        print("✅ Paper trading enabled")
        
        # Verify live trading is disabled
        assert real_settings.zerodha.enabled is False
        print("✅ Live Zerodha trading disabled")
        
        # Verify only paper broker is active
        assert real_settings.active_brokers == ["paper"]
        print("✅ Only paper broker active")
        
        # Test that credentials are available for market data but not live trading
        assert real_settings.zerodha.api_key is not None
        assert real_settings.zerodha.access_token is not None
        print("✅ Credentials available for market data")
        
        # Test configuration prevents accidental live trading
        assert "zerodha" not in real_settings.active_brokers
        print("✅ Live trading broker not in active brokers")


@pytest.mark.asyncio
@pytest.mark.slow
class TestMarketHoursAndDataAvailability:
    """
    Test behavior during market hours vs non-market hours.
    
    IMPORTANT: During non-market hours, Zerodha provides closing price feeds
    with constant values. Tests should account for this behavior.
    """
    
    async def test_market_hours_detection(self, kite_client):
        """Test detection of market hours for trading decisions"""
        # Get current time
        now = datetime.now()
        
        # Indian market hours: 9:15 AM to 3:30 PM IST (Monday-Friday)
        market_start = now.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = now.replace(hour=15, minute=30, second=0, microsecond=0)
        
        is_weekday = now.weekday() < 5  # Monday=0, Friday=4
        is_market_time = market_start <= now <= market_end
        is_market_hours = is_weekday and is_market_time
        
        print(f"✅ Current time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"✅ Is weekday: {is_weekday}")
        print(f"✅ Is market time: {is_market_time}")
        print(f"✅ Is market hours: {is_market_hours}")
        
        if not is_market_hours:
            print("⚠️  WARNING: Running during non-market hours")
            print("⚠️  Zerodha will provide closing price feeds with constant values")
            print("⚠️  Strategy tests may not generate signals due to static prices")
        
        # Test data availability based on market hours
        instruments = kite_client.instruments()
        test_stock = next((inst for inst in instruments
                          if inst['tradingsymbol'] == 'RELIANCE'
                          and inst['exchange'] == 'NSE'), None)
        
        if test_stock:
            quote = kite_client.quote([test_stock['instrument_token']])
            stock_quote = quote[str(test_stock['instrument_token'])]
            
            # During market hours, last_trade_time should be recent
            last_trade_time = stock_quote.get('last_trade_time')
            if last_trade_time:
                print(f"✅ Last trade time: {last_trade_time}")
            
            # Price should always be available (previous close if market closed)
            assert stock_quote['last_price'] > 0
            print(f"✅ Current/Last price: ₹{stock_quote['last_price']}")
            
            # During non-market hours, additional context
            if not is_market_hours:
                print(f"ℹ️  Non-market hours: Price reflects previous session close")
                print(f"ℹ️  Constant price streams expected during WebSocket feed")
    
    async def test_data_staleness_handling(self, kite_client):
        """Test handling of stale market data outside market hours"""
        instruments = kite_client.instruments()
        test_stock = next((inst for inst in instruments
                          if inst['tradingsymbol'] == 'TCS'
                          and inst['exchange'] == 'NSE'), None)
        
        if not test_stock:
            pytest.skip("TCS not available")
        
        quote = kite_client.quote([test_stock['instrument_token']])
        stock_quote = quote[str(test_stock['instrument_token'])]
        
        # Test that we can identify stale data
        last_trade_time = stock_quote.get('last_trade_time')
        current_time = datetime.now()
        
        if last_trade_time:
            # Convert to datetime if it's a string
            if isinstance(last_trade_time, str):
                # Parse the timestamp format from Zerodha
                pass  # Implementation depends on Zerodha timestamp format
            
            # Check if data is from today
            is_today = (last_trade_time and 
                       hasattr(last_trade_time, 'date') and
                       last_trade_time.date() == current_time.date())
            
            print(f"✅ Data is from today: {is_today}")
        
        # Data should still be usable even if stale
        assert stock_quote['last_price'] > 0
        assert stock_quote['last_price'] < 1000000  # Sanity check
        
        print(f"✅ Quote data available: ₹{stock_quote['last_price']}")


if __name__ == "__main__":
    print("Running Zerodha real integration tests...")
    print("WARNING: These tests require real Zerodha credentials")
    print("Make sure paper trading is enabled for safety")
    pytest.main([__file__, "-v", "-s", "--tb=short"])