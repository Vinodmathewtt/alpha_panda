# alphaP/app/pre_trading_checks.py

from datetime import datetime, time
import pytz
from typing import List, Any, Dict

from core.health import HealthCheck, HealthCheckResult
from core.database.connection import DatabaseManager
from core.database.models import StrategyConfiguration
from services.auth.service import AuthService
from services.auth.models import AuthStatus
from core.market_hours import MarketHoursChecker, MarketHoursConfig, MarketStatus
from sqlalchemy import select

class ActiveStrategiesCheck(HealthCheck):
    """Checks if there is at least one active strategy in the database."""
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    async def check(self) -> HealthCheckResult:
        try:
            async with self.db_manager.get_session() as session:
                stmt = select(StrategyConfiguration).where(StrategyConfiguration.is_active == True)
                result = await session.execute(stmt)
                active_strategies = result.scalars().all()

                if not active_strategies:
                    return HealthCheckResult(
                        component="Strategy Config",
                        passed=False,
                        message="No active strategies found in the database. Trading cannot proceed."
                    )

                return HealthCheckResult(
                    component="Strategy Config",
                    passed=True,
                    message=f"Found {len(active_strategies)} active strategies."
                )
        except Exception as e:
            return HealthCheckResult(component="Strategy Config", passed=False, message=f"Database query failed: {e}")


class BrokerApiHealthCheck(HealthCheck):
    """
    Checks if the broker API is responsive by attempting to fetch the user profile.
    This also validates the stored access token.
    """
    def __init__(self, auth_service: AuthService):
        self.auth_service = auth_service

    async def check(self) -> HealthCheckResult:
        if not self.auth_service.is_authenticated():
            # Try to initialize authentication
            try:
                auth_initialized = await self.auth_service.auth_manager.initialize()
                if not auth_initialized:
                    # Check the specific authentication status for better error reporting
                    auth_status = self.auth_service.auth_manager.status
                    if auth_status == AuthStatus.ERROR:
                        return HealthCheckResult(
                            component="Zerodha API",
                            passed=False,
                            message="CRITICAL: Zerodha authentication configuration error. Check logs for details."
                        )
                    else:
                        return HealthCheckResult(
                            component="Zerodha API", 
                            passed=False,
                            message="CRITICAL: Zerodha authentication required but failed. System cannot start."
                        )
            except Exception as e:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=False,
                    message=f"CRITICAL: Zerodha authentication initialization failed: {e}"
                )
        try:
            profile = await self.auth_service.get_current_user_profile()
            if profile:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=True,
                    message=f"Successfully connected to broker API for user: {profile.user_shortname}."
                )
            else:
                return HealthCheckResult(
                    component="Zerodha API",
                    passed=False,
                    message="Session is active but failed to fetch user profile. Token may be invalid."
                )
        except Exception as e:
            return HealthCheckResult(component="Zerodha API", passed=False, message=f"API call failed: {e}")


class MarketHoursCheck(HealthCheck):
    """Enhanced market hours checker using the new market hours utility."""
    
    def __init__(self, config: MarketHoursConfig = None):
        """
        Initialize market hours check.
        
        Args:
            config: Market hours configuration (defaults to standard IST hours)
        """
        self.market_hours_checker = MarketHoursChecker(config)

    async def check(self) -> HealthCheckResult:
        """
        Check current market hours status.
        
        Returns comprehensive market status information as a health check result.
        """
        try:
            market_info = self.market_hours_checker.get_market_info()
            status = market_info["status"]
            
            # Create appropriate message based on status
            if status == MarketStatus.OPEN:
                message = f"Market is open for trading (Regular session: {market_info['sessions']['regular']['start']} - {market_info['sessions']['regular']['end']} IST)"
                passed = True
                
            elif status == MarketStatus.PRE_OPEN:
                message = f"Market is in pre-open session ({market_info['sessions']['pre_open']['start']} - {market_info['sessions']['pre_open']['end']} IST)"
                passed = True
                
            elif status == MarketStatus.LUNCH_BREAK:
                lunch_end = market_info['sessions'].get('lunch_break', {}).get('end', '1:30 PM')
                message = f"Market is closed for lunch break (resumes at {lunch_end} IST)"
                passed = True  # Warning only
                
            elif status == MarketStatus.WEEKEND:
                message = "Market is closed (weekend) - warning only"
                passed = True  # Warning only
                
            elif status == MarketStatus.HOLIDAY:
                message = "Market is closed (holiday) - warning only"  
                passed = True  # Warning only
                
            else:  # MarketStatus.CLOSED
                next_open = market_info.get("next_open")
                if next_open:
                    message = f"Market is closed (next open: {next_open.strftime('%Y-%m-%d %H:%M IST')}) - warning only"
                else:
                    regular_session = market_info['sessions']['regular']
                    message = f"Market is closed (outside {regular_session['start']} - {regular_session['end']} IST) - warning only"
                passed = True  # Warning only
                
            return HealthCheckResult(
                component="Market Hours",
                passed=passed,
                message=message
            )
            
        except Exception as e:
            return HealthCheckResult(
                component="Market Hours",
                passed=False,
                message=f"Failed to check market hours: {e}"
            )