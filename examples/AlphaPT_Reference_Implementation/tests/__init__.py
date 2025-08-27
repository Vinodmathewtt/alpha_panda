"""
AlphaPT Testing Framework

This package contains comprehensive tests for the AlphaPT trading platform:

Test Types:
- Unit Tests: Individual component testing with mocked dependencies
- Integration Tests: Component interaction testing
- E2E Tests: Full workflow testing with real services
- Smoke Tests: Basic functionality and sanity checks

Test Execution:
    # Run all tests
    TESTING=true python -m pytest tests/ -v
    
    # Run specific test categories
    TESTING=true python -m pytest tests/ -m unit -v
    TESTING=true python -m pytest tests/ -m integration -v
    TESTING=true python -m pytest tests/ -m e2e -v
    TESTING=true python -m pytest tests/ -m smoke -v
    
    # Run performance tests
    TESTING=true python -m pytest tests/ -m performance -v
    
    # Exclude slow tests
    TESTING=true python -m pytest tests/ -m "not slow" -v

Environment Variables:
- TESTING=true: Required for all test execution
- MOCK_MARKET_FEED=true: Use mock market data (default for testing)
- ENVIRONMENT=testing: Set testing environment
"""

__version__ = "1.0.0"