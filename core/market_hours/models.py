"""
Market hours data models and configuration.
"""

from datetime import time, datetime, date
from enum import Enum
from typing import Dict, Tuple, Optional, List
from pydantic import BaseModel, Field
import pytz


class MarketStatus(str, Enum):
    """Market status enumeration."""
    OPEN = "open"
    CLOSED = "closed"
    PRE_OPEN = "pre_open"
    LUNCH_BREAK = "lunch_break"
    WEEKEND = "weekend"
    HOLIDAY = "holiday"


class MarketSession(BaseModel):
    """Market session configuration."""
    start: time = Field(..., description="Session start time")
    end: time = Field(..., description="Session end time")
    
    def contains(self, check_time: time) -> bool:
        """Check if given time falls within this session."""
        return self.start <= check_time <= self.end


class MarketHoursConfig(BaseModel):
    """
    Configuration for Indian market hours.
    
    Based on NSE/BSE trading sessions:
    - Pre-open: 9:00 AM - 9:15 AM
    - Regular: 9:15 AM - 3:30 PM  
    - Lunch break: 12:30 PM - 1:30 PM (optional enforcement)
    """
    
    # Market sessions
    pre_open_session: MarketSession = Field(
        default=MarketSession(start=time(9, 0), end=time(9, 15)),
        description="Pre-open session (9:00 AM - 9:15 AM IST)"
    )
    
    regular_session: MarketSession = Field(
        default=MarketSession(start=time(9, 15), end=time(15, 30)),
        description="Regular trading session (9:15 AM - 3:30 PM IST)"
    )
    
    lunch_break: MarketSession = Field(
        default=MarketSession(start=time(12, 30), end=time(13, 30)),
        description="Lunch break (12:30 PM - 1:30 PM IST)"
    )
    
    # Configuration flags
    enforce_lunch_break: bool = Field(
        default=False,
        description="Whether to enforce lunch break as market closed period"
    )
    
    enforce_weekends: bool = Field(
        default=True,
        description="Whether to enforce weekends as market closed"
    )
    
    enforce_holidays: bool = Field(
        default=False,
        description="Whether to enforce Indian holidays (requires holiday calendar)"
    )
    
    # Development overrides
    market_24x7: bool = Field(
        default=False,
        description="Development mode - treat market as always open"
    )
    
    timezone: str = Field(
        default="Asia/Kolkata",
        description="Market timezone"
    )
    
    @property
    def ist(self) -> pytz.BaseTzInfo:
        """Get IST timezone object."""
        return pytz.timezone(self.timezone)
    
    def get_market_status(self, check_time: Optional[datetime] = None) -> MarketStatus:
        """
        Get current market status.
        
        Args:
            check_time: Time to check (defaults to current time in IST)
            
        Returns:
            Current market status
        """
        if self.market_24x7:
            return MarketStatus.OPEN
            
        if check_time is None:
            check_time = datetime.now(self.ist)
        elif check_time.tzinfo is None:
            check_time = self.ist.localize(check_time)
        else:
            check_time = check_time.astimezone(self.ist)
            
        # Check weekends
        if self.enforce_weekends and check_time.weekday() >= 5:
            return MarketStatus.WEEKEND
            
        current_time = check_time.time()
        
        # Check pre-open session
        if self.pre_open_session.contains(current_time):
            return MarketStatus.PRE_OPEN
            
        # Check regular session
        if self.regular_session.contains(current_time):
            # Check lunch break if enforced
            if self.enforce_lunch_break and self.lunch_break.contains(current_time):
                return MarketStatus.LUNCH_BREAK
            return MarketStatus.OPEN
            
        return MarketStatus.CLOSED
    
    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if market is open for trading.
        
        Args:
            check_time: Time to check (defaults to current time in IST)
            
        Returns:
            True if market is open for trading
        """
        status = self.get_market_status(check_time)
        return status in [MarketStatus.OPEN, MarketStatus.PRE_OPEN]
    
    def next_market_open(self, from_time: Optional[datetime] = None) -> datetime:
        """
        Calculate next market open time.
        
        Args:
            from_time: Time to calculate from (defaults to current time)
            
        Returns:
            Next market open datetime in IST
        """
        if from_time is None:
            from_time = datetime.now(self.ist)
        elif from_time.tzinfo is None:
            from_time = self.ist.localize(from_time)
        else:
            from_time = from_time.astimezone(self.ist)
            
        current_date = from_time.date()
        current_time = from_time.time()
        
        # If before market open today and it's a weekday, return today's open
        if (current_time < self.regular_session.start and 
            current_date.weekday() < 5):
            return datetime.combine(
                current_date, 
                self.regular_session.start,
                tzinfo=self.ist
            )
        
        # Otherwise find next weekday
        days_ahead = 1
        if current_date.weekday() >= 4:  # Friday or later
            days_ahead = 7 - current_date.weekday()  # Days until Monday
            
        next_date = current_date
        while next_date.weekday() >= 5 or days_ahead > 0:
            next_date = date.fromordinal(next_date.toordinal() + 1)
            days_ahead -= 1
            
        return datetime.combine(
            next_date,
            self.regular_session.start, 
            tzinfo=self.ist
        )