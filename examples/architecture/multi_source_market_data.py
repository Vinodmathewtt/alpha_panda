"""
Multi-Source Market Data Architecture Example

This example demonstrates how the Alpha Panda system supports multiple market data 
sources through quality-based source selection by asset class.

Key Principle: Market data source is completely independent of broker selection.
All brokers (paper, zerodha, future brokers) consume the same high-quality market 
feed ensuring strategy consistency between paper and live trading.
"""

from core.schemas.topics import TopicNames, TopicMap

def demo_asset_class_routing():
    """Demonstrate asset-class-specific topic routing"""
    print("=== Multi-Source Market Data Architecture Demo ===\n")
    
    # Example: Strategy configuration specifies asset classes, not brokers
    equity_strategy_config = {
        "name": "momentum_strategy",
        "asset_classes": ["equity"],  # Subscribes to market.equity.ticks
        "brokers": ["paper", "zerodha"]  # Execution isolated by broker
    }
    
    crypto_strategy_config = {
        "name": "arbitrage_strategy", 
        "asset_classes": ["crypto"],  # Subscribes to market.crypto.ticks
        "brokers": ["paper", "zerodha"]  # Same brokers, different asset class
    }
    
    multi_asset_strategy_config = {
        "name": "cross_asset_strategy",
        "asset_classes": ["equity", "options"],  # Multiple asset classes
        "brokers": ["paper", "zerodha"]
    }
    
    # Demonstrate topic routing for each strategy
    for config in [equity_strategy_config, crypto_strategy_config, multi_asset_strategy_config]:
        print(f"Strategy: {config['name']}")
        print(f"Asset Classes: {config['asset_classes']}")
        
        # Get appropriate market data topics for each asset class
        market_topics = []
        for asset_class in config["asset_classes"]:
            topic = TopicNames.get_market_topic_by_asset_class(asset_class)
            market_topics.append(topic)
            print(f"  {asset_class.title()} data from: {topic}")
        
        # Show how execution is isolated by broker
        print(f"Execution brokers: {config['brokers']}")
        for broker in config["brokers"]:
            topic_map = TopicMap(broker)
            print(f"  {broker} signals: {topic_map.signals_raw()}")
            print(f"  {broker} orders: {topic_map.orders_filled()}")
        
        print()

def demo_data_source_independence():
    """Demonstrate market data source independence from broker selection"""
    print("=== Market Data Source Independence ===\n")
    
    # Example scenario: Trading RELIANCE stock
    instrument = "RELIANCE"
    asset_class = "equity"
    
    # Get the best market data source for equity (currently Zerodha)
    market_topic = TopicNames.get_market_topic_by_asset_class(asset_class)
    print(f"Trading {instrument} ({asset_class})")
    print(f"Market data source: {market_topic}")
    print()
    
    # Both paper and zerodha trading use the SAME market feed
    print("Broker execution (all use same market feed):")
    for broker in ["paper", "zerodha"]:
        topic_map = TopicMap(broker)
        print(f"  {broker.title()} trader:")
        print(f"    Consumes market data: {market_topic}")
        print(f"    Publishes signals to: {topic_map.signals_raw()}")
        print(f"    Publishes orders to: {topic_map.orders_filled()}")
    
    print("\n🎯 Key Benefit: Paper trading gets the same high-quality Zerodha feed")
    print("   as live trading, ensuring strategy consistency and realistic backtesting!")

def demo_future_extensibility():
    """Show how new asset classes and data sources can be added"""
    print("\n=== Future Extensibility ===\n")
    
    print("Adding new data sources (future implementation):")
    print("1. Crypto trading:")
    print("   - Add CryptoMarketFeedService → market.crypto.ticks")
    print("   - Connect to Binance/Coinbase for best crypto data")
    print("   - Paper and zerodha brokers both consume market.crypto.ticks")
    print()
    
    print("2. Options trading:")
    print("   - Enhance ZerodhaMarketFeedService → market.options.ticks") 
    print("   - Zerodha provides excellent options data")
    print("   - Paper and zerodha brokers both consume market.options.ticks")
    print()
    
    print("3. Forex trading:")
    print("   - Add ForexMarketFeedService → market.forex.ticks")
    print("   - Connect to specialized forex data provider")
    print("   - Paper and zerodha brokers both consume market.forex.ticks")
    print()
    
    print("🏗️  Each asset class gets the BEST data source, independent of broker!")

def demo_deployment_patterns():
    """Show deployment patterns for multi-source architecture"""
    print("\n=== Deployment Patterns ===\n")
    
    print("Separate Market Feed Services by Asset Class:")
    print("├── EquityMarketFeedService")
    print("│   ├── Connects to: Zerodha API")
    print("│   └── Publishes to: market.equity.ticks")
    print("├── CryptoMarketFeedService (future)")
    print("│   ├── Connects to: Binance API")
    print("│   └── Publishes to: market.crypto.ticks")
    print("└── OptionsMarketFeedService (future)")
    print("    ├── Connects to: Zerodha Options API")
    print("    └── Publishes to: market.options.ticks")
    print()
    
    print("Broker-Segregated Trading Services:")
    print("├── Paper Trading Pipeline")
    print("│   ├── Consumes: market.*.ticks (all asset classes)")
    print("│   ├── Publishes: paper.signals.*, paper.orders.*")
    print("│   └── Uses: PaperTrader for execution")
    print("└── Zerodha Trading Pipeline")
    print("    ├── Consumes: market.*.ticks (same asset classes)")
    print("    ├── Publishes: zerodha.signals.*, zerodha.orders.*")
    print("    └── Uses: ZerodhaTrader for execution")

if __name__ == "__main__":
    demo_asset_class_routing()
    demo_data_source_independence()
    demo_future_extensibility()
    demo_deployment_patterns()
    
    print("\n✅ Multi-Source Market Data Architecture Foundation Complete!")
    print("   Ready for asset-class-specific data sources as trading expands.")