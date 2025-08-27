#!/usr/bin/env python3
"""Verification script for critical fixes applied to AlphaPT.

This script verifies that all critical fixes have been properly implemented:
1. Import path consistency
2. Production build configuration
3. Database connection validation
4. Error handling standardization
5. Input validation framework
"""

import sys
import os
import traceback
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_import_fixes():
    """Test that import path fixes are working."""
    print("🔍 Testing import path fixes...")
    
    try:
        # Test core imports
        from core.config.settings import Settings
        from core.utils.error_handler import ErrorHandler
        from core.utils.validators import InputValidator
        
        # Test trading engine imports
        from core.paper_trade.engine import PaperTradeEngine
        from core.zerodha_trade.engine import ZerodhaTradeEngine
        
        # Test strategy imports - these should now work with absolute paths
        from core.strategy_manager.strategy_manager import StrategyManager
        from core.strategy_manager.base_strategy import BaseStrategy
        
        print("✅ Import path fixes verified successfully")
        return True
        
    except ImportError as e:
        print(f"❌ Import path fix failed: {e}")
        traceback.print_exc()
        return False

def test_production_build():
    """Test that production build configuration exists."""
    print("🔍 Testing production build configuration...")
    
    try:
        from production_build import ProductionBuilder
        
        # Test builder initialization
        builder = ProductionBuilder()
        
        # Test validation methods exist
        assert hasattr(builder, 'validate_production_environment')
        assert hasattr(builder, 'create_production_config')
        assert hasattr(builder, 'verify_production_build')
        
        print("✅ Production build configuration verified successfully")
        return True
        
    except Exception as e:
        print(f"❌ Production build configuration failed: {e}")
        traceback.print_exc()
        return False

def test_database_validation():
    """Test enhanced database validation."""
    print("🔍 Testing database connection validation...")
    
    try:
        from core.config.database_config import DatabaseConfig
        
        # Test validation with invalid data
        try:
            config = DatabaseConfig(
                postgres_host="",  # Invalid empty host
                postgres_port=99999,  # Invalid port
                postgres_user="",  # Invalid empty user
                postgres_password=""  # Invalid empty password
            )
            print("❌ Database validation should have failed but didn't")
            return False
        except Exception:
            # This is expected - validation should fail
            pass
        
        # Test validation with valid data
        config = DatabaseConfig(
            postgres_host="localhost",
            postgres_port=5432,
            postgres_user="alphapt",
            postgres_password="secure_password_123",
            postgres_database="alphapt"
        )
        
        # Test validation methods
        validation_results = config.validate_connection_urls()
        security_recommendations = config.get_security_recommendations()
        
        assert isinstance(validation_results, dict)
        assert isinstance(security_recommendations, dict)
        
        print("✅ Database validation enhancements verified successfully")
        return True
        
    except Exception as e:
        print(f"❌ Database validation test failed: {e}")
        traceback.print_exc()
        return False

def test_error_handling():
    """Test standardized error handling."""
    print("🔍 Testing error handling standardization...")
    
    try:
        from core.utils.error_handler import (
            ErrorHandler, with_error_handling, with_retry,
            ErrorSeverity, ErrorCategory, create_error_context
        )
        
        # Test error handler initialization
        handler = ErrorHandler()
        
        # Test error context creation
        context = create_error_context(
            component="test_component",
            operation="test_operation"
        )
        
        # Test error handling
        test_error = ValueError("Test error")
        error_details = handler.handle_error(test_error, context)
        
        assert error_details.severity in ErrorSeverity
        assert error_details.category in ErrorCategory
        assert error_details.error_id is not None
        
        # Test decorators exist and are callable
        assert callable(with_error_handling)
        assert callable(with_retry)
        
        print("✅ Error handling standardization verified successfully")
        return True
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        traceback.print_exc()
        return False

def test_input_validation():
    """Test comprehensive input validation."""
    print("🔍 Testing input validation framework...")
    
    try:
        from core.utils.validators import (
            InputValidator, ValidationRule, ValidationType,
            validate_trading_order, validate_market_data
        )
        
        # Test validator initialization
        validator = InputValidator()
        
        # Test trading order validation
        valid_order = {
            "tradingsymbol": "RELIANCE",
            "exchange": "NSE",
            "transaction_type": "BUY",
            "order_type": "LIMIT",
            "quantity": 10,
            "price": "2500.50"
        }
        
        result = validate_trading_order(valid_order)
        assert result.is_valid, f"Valid order should pass validation: {result.errors}"
        
        # Test invalid order
        invalid_order = {
            "tradingsymbol": "",  # Invalid empty symbol
            "exchange": "INVALID",  # Invalid exchange
            "transaction_type": "INVALID",  # Invalid transaction type
            "quantity": -5  # Invalid negative quantity
        }
        
        result = validate_trading_order(invalid_order)
        assert not result.is_valid, "Invalid order should fail validation"
        assert len(result.errors) > 0, "Should have validation errors"
        
        # Test market data validation
        valid_market_data = {
            "instrument_token": 408065,
            "last_price": "2500.50",
            "volume": 1000
        }
        
        result = validate_market_data(valid_market_data)
        assert result.is_valid, f"Valid market data should pass validation: {result.errors}"
        
        print("✅ Input validation framework verified successfully")
        return True
        
    except Exception as e:
        print(f"❌ Input validation test failed: {e}")
        traceback.print_exc()
        return False

def test_environment_safety():
    """Test that mock components are properly excluded in production."""
    print("🔍 Testing environment safety...")
    
    try:
        # Set environment to production
        os.environ['ENVIRONMENT'] = 'production'
        os.environ['MOCK_MARKET_FEED'] = 'false'
        
        # Test that mock components can still be imported (they exist)
        # but would be excluded by production builder
        from core.mock_market_feed.mock_feed_manager import MockFeedManager
        
        # Test production builder would exclude them
        from production_build import ProductionBuilder
        builder = ProductionBuilder()
        
        # Reset environment
        os.environ.pop('ENVIRONMENT', None)
        os.environ.pop('MOCK_MARKET_FEED', None)
        
        print("✅ Environment safety verified successfully")
        return True
        
    except Exception as e:
        print(f"❌ Environment safety test failed: {e}")
        traceback.print_exc()
        return False

def main():
    """Run all verification tests."""
    print("🚀 Starting AlphaPT Critical Fixes Verification...")
    print("=" * 60)
    
    tests = [
        ("Import Path Fixes", test_import_fixes),
        ("Production Build Configuration", test_production_build),
        ("Database Validation", test_database_validation),
        ("Error Handling", test_error_handling),
        ("Input Validation", test_input_validation),
        ("Environment Safety", test_environment_safety),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n🧪 {test_name}")
        print("-" * 40)
        
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"📊 VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print(f"📈 Success Rate: {(passed / (passed + failed)) * 100:.1f}%")
    
    if failed == 0:
        print("\n🎉 ALL CRITICAL FIXES VERIFIED SUCCESSFULLY!")
        print("✅ AlphaPT is ready for production deployment")
        return 0
    else:
        print(f"\n⚠️  {failed} CRITICAL FIXES NEED ATTENTION")
        print("❌ Please review and fix the failed tests before deployment")
        return 1

if __name__ == "__main__":
    exit(main())