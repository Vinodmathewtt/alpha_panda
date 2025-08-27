from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
import redis.asyncio as redis
from core.logging.logger import get_logger
from instrument_data.config.settings import InstrumentDataConfig

logger = get_logger(__name__)


class DownloadScheduler:
    """Smart download scheduler with market awareness and Redis tracking."""
    
    def __init__(self, redis_client: redis.Redis, config: InstrumentDataConfig):
        self.redis = redis_client
        self.config = config
        self.download_prefix = config.redis_download_prefix
        self.india_offset = timedelta(minutes=config.india_offset_minutes)
    
    async def get_download_status(self) -> Dict[str, Any]:
        """Get comprehensive download status with market awareness."""
        now_utc = datetime.now(timezone.utc)
        india_time = self.get_india_time(now_utc)
        
        # Get last download info from Redis
        last_date_key = f"{self.download_prefix}:last_date"
        last_timestamp_key = f"{self.download_prefix}:last_timestamp"
        download_count_key = f"{self.download_prefix}:count"
        
        last_date_str = await self.redis.get(last_date_key)
        last_timestamp_str = await self.redis.get(last_timestamp_key)
        download_count = await self.redis.get(download_count_key)
        
        # Parse last download info
        last_download_date = None
        last_download_timestamp = None
        
        if last_date_str:
            try:
                last_download_date = datetime.strptime(last_date_str.decode(), "%Y-%m-%d").date()
            except (ValueError, AttributeError):
                pass
        
        if last_timestamp_str:
            try:
                last_download_timestamp = datetime.fromisoformat(last_timestamp_str.decode())
            except (ValueError, AttributeError):
                pass
        
        # Determine if download is needed
        should_download = await self.should_download_today()
        is_market_time = self.is_after_market_open(india_time) and not self.should_skip_download(india_time)
        
        # Calculate next scheduled check
        next_check = await self.get_next_scheduled_download()
        
        return {
            "last_download_date": last_download_date.strftime("%Y-%m-%d") if last_download_date else None,
            "last_download_timestamp": last_download_timestamp,
            "download_count": int(download_count) if download_count else 0,
            "should_download_today": should_download,
            "is_market_time": is_market_time,
            "next_scheduled_check": next_check,
            "current_india_time": india_time,
            "market_open_time": f"{self.config.market_open_hour:02d}:{self.config.market_open_minute:02d}",
            "is_weekend": self.is_weekend(india_time),
            "is_holiday": self.is_holiday(india_time)
        }
    
    async def should_download_today(self) -> bool:
        """Determine if download is needed today with smart logic."""
        now_utc = datetime.now(timezone.utc)
        india_time = self.get_india_time(now_utc)
        today_str = india_time.strftime("%Y-%m-%d")
        
        # Check if we should skip download (weekend/holiday)
        if self.should_skip_download(india_time):
            logger.debug(f"Skipping download for {today_str} - weekend or holiday")
            return False
        
        # Check if it's after market open time
        if not self.is_after_market_open(india_time):
            logger.debug(f"Market not open yet in IST: {india_time.strftime('%H:%M')}")
            return False
        
        # Check if already downloaded today
        last_date_key = f"{self.download_prefix}:last_date"
        last_date_str = await self.redis.get(last_date_key)
        
        if last_date_str:
            try:
                last_date = last_date_str.decode()
                if last_date == today_str:
                    logger.debug(f"Already downloaded today: {today_str}")
                    return False
            except (ValueError, AttributeError):
                pass
        
        # Check force download condition
        last_timestamp_key = f"{self.download_prefix}:last_timestamp"
        last_timestamp_str = await self.redis.get(last_timestamp_key)
        
        if last_timestamp_str:
            try:
                last_timestamp = datetime.fromisoformat(last_timestamp_str.decode())
                hours_since_last = (now_utc - last_timestamp).total_seconds() / 3600
                
                if hours_since_last < self.config.download_force_hours:
                    logger.debug(f"Last download {hours_since_last:.1f} hours ago, not forcing")
                    return False
            except (ValueError, AttributeError):
                pass
        
        logger.info(f"Download needed for {today_str}")
        return True
    
    async def mark_download_completed(self, instruments_count: int) -> None:
        """Mark download as completed with metadata."""
        now_utc = datetime.now(timezone.utc)
        india_time = self.get_india_time(now_utc)
        today_str = india_time.strftime("%Y-%m-%d")
        
        # Update Redis tracking
        pipe = self.redis.pipeline()
        
        # Set last download date and timestamp
        pipe.set(f"{self.download_prefix}:last_date", today_str)
        pipe.set(f"{self.download_prefix}:last_timestamp", now_utc.isoformat())
        
        # Increment download count
        pipe.incr(f"{self.download_prefix}:count")
        
        # Store download metadata
        metadata = {
            "instruments_count": instruments_count,
            "download_date": today_str,
            "download_timestamp": now_utc.isoformat(),
            "india_time": india_time.isoformat()
        }
        pipe.hset(f"{self.download_prefix}:metadata", mapping=metadata)
        
        # Set expiry for tracking keys (keep for 30 days)
        expiry_seconds = 30 * 24 * 3600
        pipe.expire(f"{self.download_prefix}:last_date", expiry_seconds)
        pipe.expire(f"{self.download_prefix}:last_timestamp", expiry_seconds)
        pipe.expire(f"{self.download_prefix}:count", expiry_seconds)
        pipe.expire(f"{self.download_prefix}:metadata", expiry_seconds)
        
        await pipe.execute()
        
        logger.info(f"Marked download completed: {instruments_count} instruments on {today_str}")
    
    async def reset_download_tracking(self) -> None:
        """Reset download tracking for testing or manual reset."""
        keys = [
            f"{self.download_prefix}:last_date",
            f"{self.download_prefix}:last_timestamp",
            f"{self.download_prefix}:count",
            f"{self.download_prefix}:metadata"
        ]
        
        await self.redis.delete(*keys)
        logger.info("Reset download tracking")
    
    def get_india_time(self, dt: Optional[datetime] = None) -> datetime:
        """Convert to IST timezone."""
        if dt is None:
            dt = datetime.now(timezone.utc)
        
        # Ensure we have UTC timezone
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        elif dt.tzinfo != timezone.utc:
            dt = dt.astimezone(timezone.utc)
        
        # Convert to IST
        india_time = dt + self.india_offset
        return india_time.replace(tzinfo=None)  # Remove timezone for easier comparison
    
    def is_after_market_open(self, india_time: datetime) -> bool:
        """Check if current time is after market open in IST."""
        market_open = india_time.replace(
            hour=self.config.market_open_hour,
            minute=self.config.market_open_minute,
            second=0,
            microsecond=0
        )
        
        return india_time >= market_open
    
    def is_weekend(self, dt: Optional[datetime] = None) -> bool:
        """Check if date is weekend (Saturday = 5, Sunday = 6)."""
        if dt is None:
            dt = self.get_india_time()
        
        return dt.weekday() >= 5
    
    def is_holiday(self, dt: Optional[datetime] = None) -> bool:
        """Check if date is market holiday (extensible for Indian market holidays)."""
        if dt is None:
            dt = self.get_india_time()
        
        # Basic holiday logic - can be extended with actual holiday calendar
        # For now, just checking common holidays
        
        # New Year's Day
        if dt.month == 1 and dt.day == 1:
            return True
        
        # Independence Day
        if dt.month == 8 and dt.day == 15:
            return True
        
        # Gandhi Jayanti
        if dt.month == 10 and dt.day == 2:
            return True
        
        # Diwali (approximate - varies each year)
        # This is a simplified check - real implementation should use a holiday calendar
        
        return False
    
    def should_skip_download(self, dt: Optional[datetime] = None) -> bool:
        """Check if download should be skipped (weekend or holiday)."""
        if dt is None:
            dt = self.get_india_time()
        
        return self.is_weekend(dt) or self.is_holiday(dt)
    
    async def get_next_scheduled_download(self) -> datetime:
        """Calculate next scheduled download time."""
        india_time = self.get_india_time()
        
        # Start with tomorrow
        next_date = india_time.date() + timedelta(days=1)
        
        # Find next working day
        while True:
            next_datetime = datetime.combine(
                next_date,
                datetime.min.time().replace(
                    hour=self.config.market_open_hour,
                    minute=self.config.market_open_minute
                )
            )
            
            if not self.should_skip_download(next_datetime):
                # Convert back to UTC for return
                utc_time = next_datetime - self.india_offset
                return utc_time.replace(tzinfo=timezone.utc)
            
            next_date += timedelta(days=1)
            
            # Prevent infinite loop
            if (next_date - india_time.date()).days > 10:
                logger.warning("Could not find next working day within 10 days")
                break
        
        # Fallback to tomorrow at market open
        tomorrow = india_time.date() + timedelta(days=1)
        next_datetime = datetime.combine(
            tomorrow,
            datetime.min.time().replace(
                hour=self.config.market_open_hour,
                minute=self.config.market_open_minute
            )
        )
        utc_time = next_datetime - self.india_offset
        return utc_time.replace(tzinfo=timezone.utc)