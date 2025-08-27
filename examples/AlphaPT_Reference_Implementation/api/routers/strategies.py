"""Strategy management API endpoints."""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from strategy_manager import strategy_manager
from core.config.settings import settings
from core.logging.logger import get_logger
from ..middleware import get_current_user, require_admin_permission

logger = get_logger(__name__)

router = APIRouter()


class StrategyInfo(BaseModel):
    name: str
    strategy_type: str
    enabled: bool
    status: str
    instruments: List[int]
    parameters: Dict[str, Any]
    performance: Dict[str, Any]


class StrategySignal(BaseModel):
    strategy_name: str
    instrument_token: int
    tradingsymbol: str
    signal_type: str
    strength: str
    price: float
    quantity: int
    timestamp: str
    confidence: float
    reason: str


class StrategyPerformance(BaseModel):
    strategy_name: str
    total_signals: int
    successful_signals: int
    win_rate: float
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    active_positions: int


@router.get("/", response_model=List[StrategyInfo])
async def get_strategies(user=Depends(get_current_user)):
    """Get list of all strategies."""
    try:
        strategies = strategy_manager.get_all_strategies()
        
        result = []
        for name, strategy in strategies.items():
            performance = strategy.get_performance_stats()
            
            result.append(StrategyInfo(
                name=name,
                strategy_type=strategy.__class__.__name__,
                enabled=strategy.enabled,
                status=strategy.get_status(),
                instruments=strategy.instruments,
                parameters=strategy.get_parameters(),
                performance=performance
            ))
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to get strategies: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_name}", response_model=StrategyInfo)
async def get_strategy(
    strategy_name: str,
    user=Depends(get_current_user)
):
    """Get specific strategy details."""
    try:
        strategy = strategy_manager.get_strategy(strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        performance = strategy.get_performance_stats()
        
        return StrategyInfo(
            name=strategy_name,
            strategy_type=strategy.__class__.__name__,
            enabled=strategy.enabled,
            status=strategy.get_status(),
            instruments=strategy.instruments,
            parameters=strategy.get_parameters(),
            performance=performance
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get strategy {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_name}/start")
async def start_strategy(
    strategy_name: str,
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Start a strategy."""
    try:
        success = await strategy_manager.start_strategy(strategy_name)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to start strategy")
        
        return {
            "success": True,
            "message": f"Strategy {strategy_name} started successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to start strategy {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_name}/stop")
async def stop_strategy(
    strategy_name: str,
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Stop a strategy."""
    try:
        success = await strategy_manager.stop_strategy(strategy_name)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to stop strategy")
        
        return {
            "success": True,
            "message": f"Strategy {strategy_name} stopped successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to stop strategy {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_name}/reload")
async def reload_strategy(
    strategy_name: str,
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Reload a strategy configuration."""
    try:
        success = await strategy_manager.reload_strategy(strategy_name)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to reload strategy")
        
        return {
            "success": True,
            "message": f"Strategy {strategy_name} reloaded successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to reload strategy {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_name}/signals", response_model=List[StrategySignal])
async def get_strategy_signals(
    strategy_name: str,
    limit: int = 50,
    user=Depends(get_current_user)
):
    """Get recent signals from a strategy."""
    try:
        signals = await strategy_manager.get_strategy_signals(strategy_name, limit)
        
        return [
            StrategySignal(
                strategy_name=signal["strategy_name"],
                instrument_token=signal["instrument_token"],
                tradingsymbol=signal["tradingsymbol"],
                signal_type=signal["signal_type"],
                strength=signal["strength"],
                price=signal["price"],
                quantity=signal["quantity"],
                timestamp=signal["timestamp"].isoformat(),
                confidence=signal["confidence"],
                reason=signal["reason"]
            )
            for signal in signals
        ]
        
    except Exception as e:
        logger.error(f"Failed to get signals for strategy {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{strategy_name}/performance", response_model=StrategyPerformance)
async def get_strategy_performance(
    strategy_name: str,
    user=Depends(get_current_user)
):
    """Get strategy performance metrics."""
    try:
        strategy = strategy_manager.get_strategy(strategy_name)
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        performance = strategy.get_performance_stats()
        
        return StrategyPerformance(
            strategy_name=strategy_name,
            total_signals=performance.get("total_signals", 0),
            successful_signals=performance.get("successful_signals", 0),
            win_rate=performance.get("win_rate", 0.0),
            total_pnl=performance.get("total_pnl", 0.0),
            sharpe_ratio=performance.get("sharpe_ratio", 0.0),
            max_drawdown=performance.get("max_drawdown", 0.0),
            active_positions=performance.get("active_positions", 0)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get performance for strategy {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{strategy_name}/parameters")
async def update_strategy_parameters(
    strategy_name: str,
    parameters: Dict[str, Any],
    user=Depends(get_current_user),
    _=Depends(require_admin_permission)
):
    """Update strategy parameters."""
    try:
        success = await strategy_manager.update_strategy_parameters(strategy_name, parameters)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to update strategy parameters")
        
        return {
            "success": True,
            "message": f"Parameters updated for strategy {strategy_name}",
            "parameters": parameters
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update parameters for strategy {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manager/status")
async def get_strategy_manager_status(user=Depends(get_current_user)):
    """Get strategy manager status."""
    try:
        status = strategy_manager.get_manager_status()
        
        return {
            "running": strategy_manager.running,
            "total_strategies": len(strategy_manager.strategies),
            "active_strategies": len([s for s in strategy_manager.strategies.values() if s.enabled]),
            "status": status
        }
        
    except Exception as e:
        logger.error(f"Failed to get strategy manager status: {e}")
        raise HTTPException(status_code=500, detail=str(e))