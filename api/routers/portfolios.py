from fastapi import APIRouter, Depends, HTTPException
from typing import List

from core.trading.portfolio_cache import PortfolioCache
from core.trading.portfolio_models import Portfolio
from api.dependencies import get_portfolio_cache, get_current_user

router = APIRouter(
    prefix="/portfolios",
    tags=["Portfolios"],
    dependencies=[Depends(get_current_user)]  # Protect all routes in this file
)


@router.get("/{portfolio_id}", response_model=Portfolio)
async def get_portfolio_by_id(
    portfolio_id: str,
    cache: PortfolioCache = Depends(get_portfolio_cache)
):
    """
    Retrieves the complete, real-time state of a single portfolio by its ID.
    (e.g., "paper_momentum_test_1" or "zerodha_momentum_test_1")
    """
    await cache.initialize()
    portfolio = await cache.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    return portfolio


@router.get("/", response_model=List[Portfolio])
async def get_all_portfolios(
    cache: PortfolioCache = Depends(get_portfolio_cache)
):
    """
    Retrieves the state of all tracked portfolios.
    NOTE: This could be slow if there are many portfolios. A real implementation
    would use Redis SCAN to get all keys without blocking.
    """
    await cache.initialize()
    
    # This is a simplified implementation. A production version would use SCAN.
    all_keys = await cache.redis_client.keys("portfolio:*")
    portfolios = []
    for key in all_keys:
        portfolio_id = key.split(":")[-1]
        p = await cache.get_portfolio(portfolio_id)
        if p:
            portfolios.append(p)
    return portfolios


@router.get("/summary/stats")
async def get_portfolio_summary(
    cache: PortfolioCache = Depends(get_portfolio_cache),
    current_user: dict = Depends(get_current_user)
):
    """
    Get summary statistics across all portfolios.
    """
    await cache.initialize()
    
    all_keys = await cache.redis_client.keys("portfolio:*")
    total_portfolios = len(all_keys)
    total_pnl = 0.0
    total_realized_pnl = 0.0
    total_unrealized_pnl = 0.0
    
    paper_portfolios = 0
    zerodha_portfolios = 0
    
    for key in all_keys:
        portfolio_id = key.split(":")[-1]
        portfolio = await cache.get_portfolio(portfolio_id)
        if portfolio:
            total_pnl += portfolio.total_pnl
            total_realized_pnl += portfolio.total_realized_pnl
            total_unrealized_pnl += portfolio.total_unrealized_pnl
            
            if portfolio_id.startswith("paper_"):
                paper_portfolios += 1
            elif portfolio_id.startswith("zerodha_"):
                zerodha_portfolios += 1
    
    return {
        "total_portfolios": total_portfolios,
        "paper_portfolios": paper_portfolios,
        "zerodha_portfolios": zerodha_portfolios,
        "total_pnl": total_pnl,
        "total_realized_pnl": total_realized_pnl,
        "total_unrealized_pnl": total_unrealized_pnl,
        "user": current_user["username"]
    }
