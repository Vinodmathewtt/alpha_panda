"""
Market hours checker implementation.

Provides comprehensive market hours checking functionality
following the patterns from the AlphaPT reference implementation.
"""

import asyncio
from datetime import datetime, time, timedelta
from typing import Optional, Dict, Any, Callable, List
import pytz

from core.logging import get_logger_safe
from .models import MarketHoursConfig, MarketStatus, MarketSession


class MarketHoursChecker:
    """
    Comprehensive market hours checker for Indian stock market.
    
    Features:
    - Real-time market status checking
    - Pre-market and regular session detection
    - Lunch break enforcement (configurable)
    - Weekend and holiday checking
    - Development 24x7 mode
    - Event callbacks for status changes
    """
    
    def __init__(self, config: Optional[MarketHoursConfig] = None):
        """
        Initialize market hours checker.
        
        Args:
            config: Market hours configuration (defaults to standard IST hours)
        """
        self.config = config or MarketHoursConfig()
        self.logger = get_logger_safe(__name__)
        
        # Status tracking
        self._last_status: Optional[MarketStatus] = None
        self._status_callbacks: List[Callable[[MarketStatus, MarketStatus], None]] = []
        
        # Monitoring task
        self._monitor_task: Optional[asyncio.Task] = None
        self._monitor_interval = 60  # Check every minute
        self._shutdown_event = asyncio.Event()
        
        self.logger.info(f"🕒 Market hours checker initialized - "
                        f"Regular: {self.config.regular_session.start} - {self.config.regular_session.end} IST")
    
    def get_current_status(self) -> MarketStatus:
        """Get current market status."""
        return self.config.get_market_status()
    
    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open for trading.
        
        Args:
            check_time: Time to check (defaults to current time)
            
        Returns:
            True if market is open
        """
        return self.config.is_market_open(check_time)
    
    def get_market_info(self, check_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Get comprehensive market information.
        
        Args:
            check_time: Time to check (defaults to current time)
            
        Returns:
            Dictionary with market status, times, and next open
        """
        if check_time is None:
            check_time = datetime.now(self.config.ist)
        elif check_time.tzinfo is None:
            check_time = self.config.ist.localize(check_time)
        else:
            check_time = check_time.astimezone(self.config.ist)
            
        status = self.config.get_market_status(check_time)
        
        info = {
            "current_time": check_time,
            "status": status,
            "is_open": status in [MarketStatus.OPEN, MarketStatus.PRE_OPEN],
            "is_trading_session": status == MarketStatus.OPEN,
            "is_pre_open": status == MarketStatus.PRE_OPEN,
            "market_date": check_time.date(),
            "sessions": {
                "pre_open": {
                    "start": self.config.pre_open_session.start,
                    "end": self.config.pre_open_session.end
                },
                "regular": {
                    "start": self.config.regular_session.start,
                    "end": self.config.regular_session.end
                }
            }
        }
        
        # Add lunch break info if enforced
        if self.config.enforce_lunch_break:
            info["sessions"]["lunch_break"] = {
                "start": self.config.lunch_break.start,
                "end": self.config.lunch_break.end
            }
            info["is_lunch_break"] = status == MarketStatus.LUNCH_BREAK
        
        # Calculate next open time if market is closed
        if not info["is_open"]:
            try:
                info["next_open"] = self.config.next_market_open(check_time)
                info["time_to_open"] = info["next_open"] - check_time
            except Exception as e:
                self.logger.warning(f"Could not calculate next market open: {e}")
                info["next_open"] = None
                info["time_to_open"] = None
        
        return info
    
    def time_until_market_open(self, from_time: Optional[datetime] = None) -> Optional[timedelta]:
        """
        Calculate time until next market open.
        
        Args:
            from_time: Time to calculate from (defaults to current time)
            
        Returns:
            Timedelta until market opens, or None if market is open
        """
        if self.is_market_open(from_time):
            return None
            
        try:
            next_open = self.config.next_market_open(from_time)
            current = from_time or datetime.now(self.config.ist)
            if current.tzinfo is None:
                current = self.config.ist.localize(current)
            return next_open - current
        except Exception as e:
            self.logger.error(f"Failed to calculate time until market open: {e}")
            return None
    
    def add_status_callback(self, callback: Callable[[MarketStatus, MarketStatus], None]):
        """
        Add callback for market status changes.
        
        Args:
            callback: Function called with (old_status, new_status) when status changes
        """
        self._status_callbacks.append(callback)
    
    def remove_status_callback(self, callback: Callable[[MarketStatus, MarketStatus], None]):
        """Remove status change callback."""
        if callback in self._status_callbacks:
            self._status_callbacks.remove(callback)
    
    async def start_monitoring(self, interval: int = 60):
        """
        Start monitoring market status changes.
        
        Args:
            interval: Check interval in seconds (default: 60)
        """
        if self._monitor_task is not None:
            self.logger.warning("Market hours monitoring already started")
            return
            
        self._monitor_interval = interval
        self._shutdown_event.clear()
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        
        self.logger.info(f"🕒 Started market hours monitoring (interval: {interval}s)")
    
    async def stop_monitoring(self):
        """Stop monitoring market status changes."""
        if self._monitor_task is None:
            return
            
        self._shutdown_event.set()
        try:
            await asyncio.wait_for(self._monitor_task, timeout=5.0)
        except asyncio.TimeoutError:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
                
        self._monitor_task = None
        self.logger.info("🕒 Stopped market hours monitoring")
    
    async def _monitor_loop(self):
        """Main monitoring loop with time-compensated intervals."""
        try:
            while not self._shutdown_event.is_set():
                start_time = asyncio.get_event_loop().time()
                try:
                    current_status = self.get_current_status()
                    
                    # Check for status change
                    if self._last_status != current_status:
                        self.logger.info(f"🕒 Market status changed: {self._last_status} → {current_status}")
                        
                        # Notify callbacks
                        for callback in self._status_callbacks:
                            try:
                                callback(self._last_status, current_status)
                            except Exception as e:
                                self.logger.error(f"Error in market status callback: {e}")
                        
                        self._last_status = current_status
                    
                    # Calculate elapsed time and adjust sleep duration
                    elapsed_time = asyncio.get_event_loop().time() - start_time
                    sleep_duration = max(0, self._monitor_interval - elapsed_time)
                    
                    # Wait for next check with compensated timing
                    try:
                        await asyncio.wait_for(
                            self._shutdown_event.wait(), 
                            timeout=sleep_duration
                        )
                        break  # Shutdown requested
                    except asyncio.TimeoutError:
                        continue  # Normal timeout, continue monitoring
                        
                except Exception as e:
                    self.logger.error(f"Error in market hours monitoring: {e}")
                    # Calculate elapsed time even for error case
                    elapsed_time = asyncio.get_event_loop().time() - start_time
                    sleep_duration = max(0, self._monitor_interval - elapsed_time)
                    await asyncio.sleep(sleep_duration)
                    
        except asyncio.CancelledError:
            self.logger.debug("Market hours monitoring cancelled")
            raise
        except Exception as e:
            self.logger.error(f"Fatal error in market hours monitoring: {e}")
    
    def __str__(self) -> str:
        """String representation."""
        status = self.get_current_status()
        return f"MarketHoursChecker(status={status}, config={self.config.regular_session.start}-{self.config.regular_session.end} IST)"
    
    def __repr__(self) -> str:
        """Detailed representation."""
        return (f"MarketHoursChecker(config={self.config}, "
                f"current_status={self.get_current_status()}, "
                f"monitoring={'active' if self._monitor_task else 'inactive'})")